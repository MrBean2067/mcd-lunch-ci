"""两套数据源，同一套接口。

* `SnapshotProvider`：读 `data/*.json` 快照，**不需要 Token**，把 7 个阶段完整跑通。
  快照可以是手写样例，也可以是 `sync` 子命令从真实 MCP 同步下来的真菜单。
* `LiveProvider`：真正调用麦当劳 MCP（协议细节全部封装在 `live.py`）。

设计原则：管线代码只依赖本文件的 `LunchProvider` 协议，因此"离线演示"和"真实下单"
跑的是同一套求解器、同一套报告——不存在"演示一套、真跑另一套"的偷懒空间。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .live import LiveSession, LiveTuning
from .mcp_client import McpError, TraceEntry
from .models import Coupon, Item, Nutrition, Plan
from .money import Money, parse_amount

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------- 协议

@dataclass
class Quote:
    total: Money
    source: str            # calculate-price | snapshot
    verified: bool         # 是否经过官方核价工具
    detail: str = ""


@dataclass
class OrderResult:
    order_id: str
    pay_url: str = ""
    status: str = ""
    dry_run: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


class LunchProvider(Protocol):
    label: str

    def store(self) -> tuple[str, str]: ...
    def menu(self) -> list[Item]: ...
    def coupons(self) -> list[Coupon]: ...
    def quote(self, plan: Plan) -> Quote: ...
    def create_order(self, plan: Plan, confirm: bool) -> OrderResult: ...
    def trace(self) -> list[TraceEntry]: ...


# ---------------------------------------------------------------- 小工具

def _pick(node: Any, *names: str) -> Any:
    """从可能是嵌套结构的字典里找第一个命中的键。"""
    if not isinstance(node, dict):
        return None
    for name in names:
        if name in node and node[name] not in (None, ""):
            return node[name]
    for value in node.values():
        if isinstance(value, dict):
            found = _pick(value, *names)
            if found not in (None, ""):
                return found
    return None


def _nutrition_from(food: dict[str, Any]) -> Nutrition:
    return Nutrition(
        kcal=int(_pick(food, "energyKcal", "calorie", "kcal") or 0),
        protein_g=float(_pick(food, "proteinG", "protein") or 0),
        fat_g=float(_pick(food, "fatG", "fat") or 0),
        carb_g=float(_pick(food, "carbohydrateG", "carbohydrate", "carbG") or 0),
        sodium_mg=int(_pick(food, "sodiumMg", "sodium") or 0),
        calcium_mg=int(_pick(food, "calciumMg", "calcium") or 0),
    )


# ---------------------------------------------------------------- 离线快照

class SnapshotProvider:
    """离线数据源：菜单、营养、优惠券都是快照文件。"""

    def __init__(self, data_dir: Path | str = DATA_DIR, snapshot: str = "menu_snapshot.json"):
        self.data_dir = Path(data_dir)
        self.snapshot = snapshot
        self._menu_raw = json.loads((self.data_dir / snapshot).read_text(encoding="utf-8"))
        nutrition_name = str((self._menu_raw.get("_meta") or {}).get("nutritionFile") or "nutrition_snapshot.json")
        nutrition_path = self.data_dir / nutrition_name
        self._nutrition_raw = (
            json.loads(nutrition_path.read_text(encoding="utf-8")) if nutrition_path.exists() else {"foods": []}
        )
        self.label = str((self._menu_raw.get("_meta") or {}).get("source") or "offline-snapshot")
        self._items: list[Item] | None = None
        self._coupons: list[Coupon] | None = None
        self._trace: list[TraceEntry] = [
            TraceEntry(tool="(offline)", arguments={"file": snapshot},
                       summary=f"读取菜单快照 {self._menu_raw.get('_meta', {}).get('source', '')}".strip()),
            TraceEntry(tool="(offline)", arguments={"file": nutrition_name},
                       summary="读取营养快照" if nutrition_path.exists() else "无营养快照，营养标记为不可用"),
        ]

    def store(self) -> tuple[str, str]:
        store = self._menu_raw.get("_meta", {}).get("store", {})
        return str(store.get("storeId", "DEMO-0001")), str(store.get("storeName", "示例门店·离线快照"))

    def menu(self) -> list[Item]:
        if self._items is not None:
            return self._items
        nutrition: dict[str, Nutrition] = {}
        for food in self._nutrition_raw.get("foods", []):
            code = str(_pick(food, "productCode", "code", "mealCode") or "")
            if code:
                nutrition[code] = _nutrition_from(food)
        items: list[Item] = []
        for product in self._menu_raw.get("products", []):
            code = str(product["productCode"])
            items.append(
                Item(
                    code=code,
                    name=str(product["productName"]),
                    category=str(product["category"]),
                    price=Money.from_yuan(product["priceYuan"]),
                    tags=frozenset(product.get("tags", [])),
                    popularity=float(product.get("popularity", 0.5)),
                    nutrition=nutrition.get(code, Nutrition()),
                    nutrition_source=str(product.get("nutritionSource") or
                                         ("snapshot" if code in nutrition else "unavailable")),
                )
            )
        self._items = items
        return items

    def coupons(self) -> list[Coupon]:
        if self._coupons is not None:
            return self._coupons
        coupons: list[Coupon] = []
        for raw in self._menu_raw.get("coupons", []):
            coupons.append(
                Coupon(
                    code=str(raw["couponCode"]),
                    title=str(raw["title"]),
                    kind=str(raw["kind"]),
                    threshold=Money.from_yuan(raw["thresholdYuan"]) if raw.get("thresholdYuan") is not None else None,
                    discount_amount=Money.from_yuan(raw.get("discountYuan", 0)),
                    item_code=raw.get("itemCode"),
                    note=str(raw.get("note", "")),
                )
            )
        self._coupons = coupons
        return coupons

    def quote(self, plan: Plan) -> Quote:
        return Quote(
            total=plan.subtotal,
            source="snapshot",
            verified=False,
            detail="离线快照价，未经 calculate-price 核价",
        )

    def create_order(self, plan: Plan, confirm: bool) -> OrderResult:
        return OrderResult(order_id="OFFLINE-PREVIEW", status="preview", dry_run=True,
                           payload={"note": "离线模式不会真实下单"})

    def trace(self) -> list[TraceEntry]:
        return list(self._trace)


# ---------------------------------------------------------------- 在线 MCP

class LiveProvider:
    """真实调用麦当劳 MCP。需要 MCP Token。

    所有协议适配都在 `live.LiveSession` 里，本类只负责把它接到 `LunchProvider` 协议上。
    每次运行的原始回包会写到 `out/live-trace.json`，字段一旦变动可以立刻定位。
    """

    label = "live-mcp"

    def __init__(self, token: str, url: str = "https://mcp.mcd.cn", *,
                 store_code: str | None = None, city: str = "深圳市", keyword: str = "科技园",
                 be_type: int = 1, out_dir: Path | str = "out", refresh: bool = False, jobs: int = 6,
                 take_way: str | None = None):
        self.out_dir = Path(out_dir)
        self.take_way = take_way
        self.session = LiveSession(
            token=token, url=url, store_code=store_code, city=city, keyword=keyword,
            tuning=LiveTuning.for_be_type(be_type, refresh=refresh, jobs=jobs),
            cache_dir=self.out_dir / ".cache",
        )

    # ---- 协议实现
    def store(self) -> tuple[str, str]:
        ref = self.session.resolve_store()
        return ref.store_code, ref.store_name or f"门店 {ref.store_code}"

    def menu(self) -> list[Item]:
        return self.session.build_items()

    def coupons(self) -> list[Coupon]:
        return self.session.coupons()

    def quote(self, plan: Plan) -> Quote:
        aggregated = self._aggregate(plan)
        try:
            total, data = self.session.price_plan(aggregated)
        except (McpError, Exception) as exc:  # noqa: BLE001 - 核价失败要降级，不能挡住整条流水线
            self.flush()
            return Quote(total=plan.subtotal, source="local", verified=False,
                         detail=f"calculate-price 失败（{str(exc)[:80]}），已回退到本地求和")
        self.flush()
        detail = "已通过官方 calculate-price 核价（单位：分）"
        original = data.get("originalPrice")
        discount = data.get("discount")
        if isinstance(original, (int, float)) and isinstance(discount, (int, float)) and discount:
            detail += f"，原价 ¥{parse_amount(original, 'fen').yuan}，直减 ¥{parse_amount(discount, 'fen').yuan}"
        return Quote(total=total, source="calculate-price", verified=True, detail=detail)

    def create_order(self, plan: Plan, confirm: bool) -> OrderResult:
        items = [{"productCode": code, "quantity": quantity} for code, quantity, _ in self._aggregate(plan)]
        remark = f"mcd-lunch-ci 团队午餐 {plan.headcount} 人"
        payload = self.session.order_payload(items, remark, self.take_way)
        if not confirm:
            self.flush()
            return OrderResult(order_id="DRY-RUN", status="payload-ready", dry_run=True, payload=payload)
        data = self.session.create_order(items, remark, self.take_way)
        self.flush()
        return OrderResult(
            order_id=str(_pick(data, "orderId", "orderNo", "orderCode") or ""),
            pay_url=str(_pick(data, "payUrl", "paymentUrl", "url", "payCode") or ""),
            status="created",
            payload=payload,
        )

    def trace(self) -> list[TraceEntry]:
        return self.session.client.trace

    # ---- 内部
    @staticmethod
    def _aggregate(plan: Plan) -> list[tuple[str, int, str]]:
        """把「每个人的套餐」折叠成「每个餐品买几份」，并带上可选券码。

        官方核价按商品行计算，同一个堡 8 个人点就该合并成 quantity=8——
        既少传几十行，也让券的阈值判断跟实际订单一致。
        """
        counts: dict[str, int] = {}
        order: list[str] = []
        for assignment in plan.assignments:
            for item in assignment.combo.items:
                if item.code not in counts:
                    counts[item.code] = 0
                    order.append(item.code)
                counts[item.code] += 1
        coupon_code = plan.coupon.code if plan.coupon else ""
        return [(code, counts[code], coupon_code) for code in order]

    def flush(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "live-trace.json").write_text(
            json.dumps({
                "store": self.session.store_ref.__dict__ if self.session.store_ref else None,
                "tuning": self.session.tuning.__dict__,
                "calls": self.session.raw_log,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_provider(mode: str, token: str | None = None, *, data_dir: Path | str = DATA_DIR,
                   store_id: str | None = None, address: str | None = None,
                   price_unit: str = "yuan", out_dir: Path | str = "out") -> LunchProvider:
    if mode == "live":
        if not token:
            raise SystemExit("实时模式需要 MCD_MCP_TOKEN，或者用 --offline 跑离线演示")
        return LiveProvider(token=token, store_code=store_id, out_dir=out_dir)
    return SnapshotProvider(data_dir=data_dir)
