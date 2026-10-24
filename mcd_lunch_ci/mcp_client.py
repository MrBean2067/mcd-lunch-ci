"""一个只用标准库的 MCP 客户端（Streamable HTTP）。

为什么自己写：参赛作品最常见的死法是"演示时要 pip install 一堆东西"，评审下载
下来跑不起来。这里零依赖，`python -m mcd_lunch_ci` 直接就能连真实服务。

协议要点：
* POST JSON-RPC 2.0 到接入地址；
* `Accept` 必须同时声明 json 和 text/event-stream，服务端可能用 SSE 回包；
* 服务端会在 initialize 的响应头里给出 `Mcp-Session-Id`，后续请求要带上；
* 401 = Token 无效，429 = 触发限流（600 次/分钟），都翻译成人话再抛。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """MCP 调用失败。"""


@dataclass
class TraceEntry:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    summary: str = ""


def _iter_sse_events(raw: str):
    """把 SSE 文本拆成 JSON 事件，忽略心跳与注释行。"""
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.strip() == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines.clear()
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
    if data_lines:
        payload = "\n".join(data_lines)
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            pass


class McpHttpClient:
    """极简 MCP 客户端：initialize / tools/list / tools/call。"""

    def __init__(self, url: str = DEFAULT_URL, token: str | None = None, timeout: float = 45.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self._next_id = 0
        self.trace: list[TraceEntry] = []
        self.server_info: dict[str, Any] = {}

    # ------------------------------------------------------------ 底层
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": "mcd-lunch-ci/1.0 (+https://github.com/)",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.session_id = session
                raw = response.read().decode("utf-8", errors="replace")
                content_type = (response.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 401:
                raise McpError("MCP Token 无效或已过期（401）。请到 open.mcd.cn 控制台重新复制 Token。") from exc
            if exc.code == 429:
                raise McpError("触发限流（429，每分钟 600 次）。等几十秒再试，别在循环里刷。") from exc
            raise McpError(f"HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise McpError(f"连不上 {self.url}：{exc.reason}") from exc

        if not raw.strip():
            return {}
        if "text/event-stream" in content_type:
            for event in _iter_sse_events(raw):
                if isinstance(event, dict) and event.get("id") == payload.get("id"):
                    return event
            for event in _iter_sse_events(raw):
                if isinstance(event, dict):
                    return event
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McpError(f"服务端返回的不是 JSON：{raw[:200]}") from exc

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        reply = self._post(payload)
        if "error" in reply:
            error = reply["error"]
            raise McpError(f"{method} 失败：{error.get('message') or error}")
        return reply.get("result", {})

    # ------------------------------------------------------------ 高层
    def initialize(self) -> dict[str, Any]:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-lunch-ci", "version": "1.0.0"},
            },
        )
        self.server_info = result.get("serverInfo", {})
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except McpError:
            pass  # 通知失败不影响后续调用
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return self._rpc("tools/list", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = arguments or {}
        entry = TraceEntry(tool=name, arguments=arguments)
        try:
            result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        except McpError as exc:
            entry.ok = False
            entry.summary = str(exc)[:160]
            self.trace.append(entry)
            raise
        entry.summary = "ok"
        self.trace.append(entry)

        if result.get("isError"):
            raise McpError(f"{name} 返回错误：{_flatten_text(result)[:300]}")

        content = result.get("content")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            joined = "\n".join(t for t in texts if t)
            return extract_json(joined)
        return result.get("structuredContent", result)


def _flatten_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(result, ensure_ascii=False)


_JSON_DECODER = json.JSONDecoder()


def extract_json(text: Any) -> Any:
    """把工具回包里的 JSON 抠出来。

    真实回包不是纯 JSON，而是「一段给人看的说明 + 一段 JSON」：

        每个门店的基本信息按单行展示：\\n{...}
        {"success":true,"code":200,"data":[...]}

    直接 json.loads 会炸，所以退化成「从左到右每个 { / [ 都试一次 raw_decode」。
    解析不出来就原样返回文本，绝不因为格式问题吞掉错误信息。
    """
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    for opener in ("{", "["):
        index = stripped.find(opener)
        while index != -1:
            try:
                value, _ = _JSON_DECODER.raw_decode(stripped[index:])
                return value
            except json.JSONDecodeError:
                index = stripped.find(opener, index + 1)
    return stripped


def probe(url: str, token: str) -> int:
    """`doctor` 子命令：连通性 + 工具清单自检。"""
    client = McpHttpClient(url=url, token=token)
    try:
        info = client.initialize()
    except McpError as exc:
        print(f"[FAIL] 初始化失败：{exc}", file=sys.stderr)
        return 2
    server = info.get("serverInfo", {})
    print(f"[ OK ] 已连接 {server.get('name', '未知服务')} {server.get('version', '')}".rstrip())
    try:
        tools = client.list_tools()
    except McpError as exc:
        print(f"[FAIL] tools/list 失败：{exc}", file=sys.stderr)
        return 2
    names = sorted(t.get("name", "") for t in tools)
    print(f"[ OK ] 可用工具 {len(names)} 个")
    wanted = [
        "query-meals", "query-meal-detail", "list-nutrition-foods", "calculate-price",
        "query-store-coupons", "create-order", "query-order", "query-nearby-stores",
    ]
    for name in wanted:
        print(f"       {'✓' if name in names else '×'} {name}")
    return 0
