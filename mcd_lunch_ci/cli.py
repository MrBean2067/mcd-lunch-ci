"""命令行入口。

    python -m mcd_lunch_ci demo                # 零 Token 跑通全流程
    python -m mcd_lunch_ci sync                # 从真实 MCP 同步菜单，落成本地快照
    python -m mcd_lunch_ci run --live          # 真实 MCP 实时核价（需要 MCD_MCP_TOKEN）
    python -m mcd_lunch_ci run --live --confirm  # 真实下单（默认只出预览载荷）
    python -m mcd_lunch_ci doctor              # 连通性 + 门店 + 菜单自检
    python -m mcd_lunch_ci tally --comments c.json --out team.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from .mcp_client import McpError, probe
from .models import Member, Team
from .money import Money
from .pipeline import RunOptions, run
from .provider import SnapshotProvider
from .report import render_terminal
from .votes import Comment, tally, to_team

ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\033\[[0-9;]*m")
LIVE_SNAPSHOT = "live_menu_snapshot.json"


# ---------------------------------------------------------------- 环境

def load_dotenv(path: Path | str | None = None) -> None:
    """读项目根目录的 .env 到 os.environ（已存在的环境变量优先，不覆盖）。

    只为了省掉「每次开新终端都要先 export」这一步。.env 在 .gitignore 里，不会进仓库。
    """
    env_path = Path(path) if path else ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _token() -> str | None:
    load_dotenv()
    return os.environ.get("MCD_MCP_TOKEN")


# ---------------------------------------------------------------- 团队文件

def load_team(path: Path | str, budget_override: Money | None = None) -> Team:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    members = [
        Member(
            name=str(entry["name"]),
            budget=Money.from_yuan(entry["budgetYuan"]) if entry.get("budgetYuan") is not None else None,
            avoid_tags=frozenset(entry.get("avoid", [])),
            max_kcal=entry.get("maxKcal"),
            target_kcal=int(entry.get("targetKcal", 800)),
            likes=entry.get("likes", {}),
            dislikes=entry.get("dislikes", {}),
            recent_mains=tuple(entry.get("recent", [])),
            note=str(entry.get("note", "")),
        )
        for entry in raw.get("members", [])
    ]
    store = raw.get("store", {})
    budget = budget_override or Money.from_yuan(raw.get("budgetYuan", 0))
    return Team(
        members=members,
        budget=budget,
        store_id=store.get("storeId"),
        store_name=store.get("storeName"),
    )


def save_team(team: Team, path: Path | str) -> None:
    payload = {
        "budgetYuan": float(team.budget.yuan),
        "store": {"storeId": team.store_id, "storeName": team.store_name},
        "members": [
            {
                "name": member.name,
                "budgetYuan": float(member.budget.yuan) if member.budget else None,
                "avoid": sorted(member.avoid_tags),
                "maxKcal": member.max_kcal,
                "targetKcal": member.target_kcal,
                "likes": dict(member.likes),
                "dislikes": dict(member.dislikes),
                "recent": list(member.recent_mains),
                "note": member.note,
            }
            for member in team.members
        ],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 子命令

def cmd_demo(args: argparse.Namespace) -> int:
    team = load_team(ROOT / "examples" / "team.json", _budget(args.budget))
    snapshot = args.snapshot
    if snapshot is None:
        snapshot = LIVE_SNAPSHOT if (ROOT / "data" / LIVE_SNAPSHOT).exists() else "menu_snapshot.json"
    provider = SnapshotProvider(snapshot=snapshot)
    store_id, store_name = provider.store()
    team.store_id, team.store_name = store_id, store_name
    ctx = run(team, provider, RunOptions(mode="offline", out_dir=args.out))
    print(_maybe_strip(render_terminal(ctx), args.no_color))
    print(f"  数据源：{provider.label}（{snapshot}）")
    print(f"  报告：{Path(args.out) / 'lunch-report.md'}")
    print(f"  卡片：{Path(args.out) / 'lunch-card.html'}")
    print()
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """从真实 MCP 拉一份菜单快照，之后不配 Token 也能用真数据跑。"""
    from .live import LiveSession, LiveTuning, snapshot_from_live

    token = _token()
    if not token:
        return _no_token()
    tuning = LiveTuning.for_be_type(args.be_type, refresh=args.refresh, jobs=args.jobs)
    session = LiveSession(token=token, url=os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn"),
                          store_code=args.store_code, city=args.city, keyword=args.keyword, tuning=tuning)
    print(f"→ 解析门店（{args.city} / {args.keyword}）…")
    store = session.resolve_store()
    print(f"  {store.store_name}（storeCode={store.store_code}，距离 {store.distance}m）")
    print(f"→ 拉取菜单 + 逐个详情 + 批量核价 + 营养匹配（{tuning.jobs} 并发）…")
    menu, nutrition = snapshot_from_live(session, store_name=args.store_name)
    menu_path = ROOT / "data" / (args.out_name or LIVE_SNAPSHOT)
    nutrition_name = "live_nutrition_snapshot.json"
    menu_path.write_text(json.dumps(menu, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data" / nutrition_name).write_text(json.dumps(nutrition, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    products = menu["products"]
    by_category: dict[str, int] = {}
    for product in products:
        by_category[product["category"]] = by_category.get(product["category"], 0) + 1
    print(f"✓ 已写入 {menu_path.relative_to(ROOT)}：{len(products)} 个餐品、"
          f"{len(menu['coupons'])} 张券")
    print(f"  品类分布：{', '.join(f'{k}={v}' for k, v in sorted(by_category.items()))}")
    print(f"  营养覆盖：{menu['_meta']['nutritionCoverage']}")
    dropped = session.nutrition().dropped
    if dropped:
        print(f"  ! 营养表有 {dropped} 行列数不齐（疑似餐品名含逗号），已丢弃而不是错位解析")
    print(f"✓ 已写入 data/{nutrition_name}")
    print()
    print("  接下来（都不需要 Token）：")
    print("    python -m mcd_lunch_ci demo          # 用真实菜单跑完整流水线")
    print("    python -m mcd_lunch_ci run --live    # 仍然可以实时核价/下单")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.live and args.offline:
        print("--live 和 --offline 只能选一个", file=sys.stderr)
        return 2
    team = load_team(args.team, _budget(args.budget))
    if args.live:
        token = _token()
        if not token:
            return _no_token()
        from .provider import LiveProvider
        provider = LiveProvider(
            token=token,
            url=os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn"),
            store_code=args.store_id,
            city=args.city,
            keyword=args.keyword,
            be_type=args.be_type,
            out_dir=args.out,
            refresh=args.refresh,
            jobs=args.jobs,
            take_way=args.take_way,
        )
        store_id, store_name = provider.store()
        team.store_id, team.store_name = store_id, store_name
    else:
        snapshot = args.snapshot or (LIVE_SNAPSHOT if (ROOT / "data" / LIVE_SNAPSHOT).exists()
                                     else "menu_snapshot.json")
        provider = SnapshotProvider(snapshot=snapshot)
        store_id, store_name = provider.store()
        team.store_id, team.store_name = store_id, store_name
    if args.store_name:
        team.store_name = args.store_name
    ctx = run(team, provider, RunOptions(mode="live" if args.live else "offline",
                                         confirm=args.confirm, out_dir=args.out))
    if args.json:
        print(json.dumps(json.loads((Path(args.out) / "plan.json").read_text(encoding="utf-8")),
                         ensure_ascii=False, indent=2))
    else:
        print(_maybe_strip(render_terminal(ctx), args.no_color))
    if args.live and getattr(provider, "flush", None):
        print(f"  原始回包：{Path(args.out) / 'live-trace.json'}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    token = _token()
    if not token:
        return _no_token()
    url = os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn")
    code = probe(url, token)
    if code != 0:
        return code
    # 再往下走一层：真实解析门店 + 菜单 + 核价，确认整条链路能跑通
    from .live import LiveSession, LiveTuning, infer_category

    session = LiveSession(token=token, url=url, city=args.city, keyword=args.keyword,
                          tuning=LiveTuning.for_be_type(args.be_type, jobs=4), cache_dir=Path("out") / ".cache")
    try:
        store = session.resolve_store()
        print(f"[ OK ] 门店 {store.store_name}（storeCode={store.store_code}，{store.distance}m）")
        items = session.build_items()
    except McpError as exc:
        print(f"[FAIL] 菜单链路失败：{exc}", file=sys.stderr)
        return 2
    by_category: dict[str, int] = {}
    for item in items:
        by_category[item.category] = by_category.get(item.category, 0) + 1
    print(f"[ OK ] 餐品 {len(items)} 个（{', '.join(f'{k}={v}' for k, v in sorted(by_category.items()))}）")
    measured = sum(1 for item in items if item.nutrition.kcal)
    print(f"[ OK ] 营养覆盖 {measured}/{len(items)}")
    cheapest = min(items, key=lambda i: i.price.fen)
    print(f"[ OK ] 最便宜：{cheapest.name} {cheapest.price}（{infer_category(cheapest.name)}）")
    total, data = session.price_plan([(cheapest.code, 2, "")])
    print(f"[ OK ] 核价 2×{cheapest.name} = {total}（原始字段 price={data.get('price')} 分）")
    print(f"[ OK ] 取餐方式：{session.choose_take_way()}")
    return 0


def cmd_tally(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.comments).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("comments", raw.get("items", []))
    comments = [
        Comment(author=str(entry.get("user", {}).get("login") if isinstance(entry.get("user"), dict)
                           else entry.get("author", "匿名")), body=str(entry.get("body", "")))
        for entry in raw
    ]
    result = tally(comments)
    if result.errors:
        for error in result.errors:
            print(f"! {error}", file=sys.stderr)
    team = to_team(result, _budget(args.budget) or Money.from_yuan(args.total_budget),
                   store_name=args.store_name)
    save_team(team, args.out)
    print(f"已汇总 {team.headcount} 人 → {args.out}")
    for member in team.members:
        avoid = "、".join(sorted(member.avoid_tags)) or "无"
        print(f"  · {member.name:<8} 预算 {member.budget or '不限'}  忌口 {avoid}")
    print(f"  确认率 {result.approved_ratio(team.headcount):.0%}（下单前需要全员 /lunch approve）")
    return 0


# ---------------------------------------------------------------- 辅助

def _no_token() -> int:
    print("缺少 MCD_MCP_TOKEN。\n"
          "  1) 到 https://open.mcd.cn/mcp 用手机号登录 → 控制台 → 激活 → 复制 Token\n"
          "  2) 写进项目根目录的 .env：MCD_MCP_TOKEN=你的Token（该文件已在 .gitignore 里）\n"
          "  3) 或者继续用零 Token 的离线演示：python -m mcd_lunch_ci demo", file=sys.stderr)
    return 2


def _budget(value: str | None) -> Money | None:
    return Money.from_yuan(value) if value else None


def _maybe_strip(text: str, no_color: bool) -> str:
    if no_color or not sys.stdout.isatty():
        return ANSI.sub("", text)
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcd-lunch-ci", description="把「今天吃什么」变成一条 CI 流水线")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="零 Token 跑通全流程（离线快照）")
    demo.add_argument("--budget", help="覆盖团队预算，如 260")
    demo.add_argument("--snapshot", help=f"指定快照文件名；默认识别有 data/{LIVE_SNAPSHOT} 就用真实同步数据")
    demo.add_argument("--out", default="out", help="产物目录，默认 out/")
    demo.set_defaults(func=cmd_demo)

    run_parser = sub.add_parser("run", help="跑一次流水线")
    run_parser.add_argument("--team", default=str(ROOT / "examples" / "team.json"))
    run_parser.add_argument("--budget", help="覆盖团队预算")
    run_parser.add_argument("--live", action="store_true", help="走真实 MCP（需要 MCD_MCP_TOKEN）")
    run_parser.add_argument("--offline", action="store_true", help="显式走离线快照（默认行为，写出来更清楚）")
    run_parser.add_argument("--confirm", action="store_true", help="允许真实下单（默认只出预览载荷）")
    run_parser.add_argument("--snapshot", help="离线模式下指定快照文件名")
    run_parser.add_argument("--store-id", help="指定门店 storeCode")
    run_parser.add_argument("--store-name", help="门店名，仅用于展示")
    run_parser.add_argument("--city", default="深圳市", help="按城市搜门店（默认 深圳市）")
    run_parser.add_argument("--keyword", default="科技园", help="位置关键词（默认 科技园）")
    run_parser.add_argument("--be-type", type=int, default=1, choices=[1, 2, 5, 6],
                            help="1-到店自取 2-麦乐送 5-得来速 6-企业团餐（默认 1）")
    run_parser.add_argument("--take-way", help="取餐方式 code，默认自动选 eat-in")
    run_parser.add_argument("--refresh", action="store_true", help="忽略本地菜单/详情缓存")
    run_parser.add_argument("--jobs", type=int, default=6, help="查详情的并发数，默认 6")
    run_parser.add_argument("--price-unit", default="fen", choices=["yuan", "fen"],
                            help="兼容参数：calculate-price 返回的是分，默认 fen 不用改")
    run_parser.add_argument("--address", help="（兼容参数）已废弃，改为 --city/--keyword")
    run_parser.add_argument("--out", default="out")
    run_parser.add_argument("--json", action="store_true", help="输出 plan.json")
    run_parser.set_defaults(func=cmd_run)

    sync = sub.add_parser("sync", help="从真实 MCP 同步菜单快照（之后零 Token 可用）")
    sync.add_argument("--city", default="深圳市")
    sync.add_argument("--keyword", default="科技园")
    sync.add_argument("--store-code", help="直接指定 storeCode，跳过搜索")
    sync.add_argument("--store-name", help="覆盖快照里的门店名")
    sync.add_argument("--be-type", type=int, default=1, choices=[1, 2, 5, 6])
    sync.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新拉全部详情")
    sync.add_argument("--jobs", type=int, default=6)
    sync.add_argument("--out-name", help=f"快照文件名，默认 {LIVE_SNAPSHOT}")
    sync.set_defaults(func=cmd_sync)

    doctor = sub.add_parser("doctor", help="检查 Token、门店、菜单、核价四项")
    doctor.add_argument("--city", default="深圳市")
    doctor.add_argument("--keyword", default="科技园")
    doctor.add_argument("--be-type", type=int, default=1, choices=[1, 2, 5, 6])
    doctor.set_defaults(func=cmd_doctor)

    tally_parser = sub.add_parser("tally", help="汇总 Issue 评论里的 /lunch 指令")
    tally_parser.add_argument("--comments", required=True, help="GitHub 评论 JSON（API 原始结构或简化结构）")
    tally_parser.add_argument("--budget", help="团队预算，如 260")
    tally_parser.add_argument("--total-budget", default="260", help="未给 --budget 时的默认团队预算")
    tally_parser.add_argument("--store-name", default=None)
    tally_parser.add_argument("--out", default="team.json")
    tally_parser.set_defaults(func=cmd_tally)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "no_color"):
        args.no_color = False
    try:
        return args.func(args)
    except McpError as exc:
        print(f"!\n! MCP 调用失败：{exc}", file=sys.stderr)
        print("! 先用 `python -m mcd_lunch_ci doctor` 自检；离线演示加 --offline 或跑 demo。", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
