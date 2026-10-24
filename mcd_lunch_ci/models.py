"""领域模型：餐品、组合、成员、方案。

刻意保持与具体 provider（在线 MCP / 离线快照）无关，求解器只认这些数据类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .money import Money, sum_money

# 硬约束标签：出现在 Member.avoid_tags 里表示「绝对不能出现」
HARD_TAGS = frozenset(
    {"beef", "pork", "chicken", "fish", "soy", "dairy", "egg", "gluten", "spicy", "fried", "caffeine", "salty"}
)

CATEGORY_LABELS = {
    "burger": "汉堡",
    "side": "小食",
    "drink": "饮料",
    "dessert": "甜品",
    "breakfast": "早餐",
    "kids": "儿童餐",
}

TAG_LABELS = {
    "beef": "牛肉",
    "pork": "猪肉",
    "chicken": "鸡肉",
    "fish": "鱼肉",
    "soy": "大豆",
    "dairy": "乳制品",
    "egg": "鸡蛋",
    "gluten": "麸质",
    "spicy": "辣",
    "fried": "油炸",
    "caffeine": "咖啡因",
    "salty": "高盐",
    "sugar": "含糖",
    "veg": "素食可用",
}


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag)


@dataclass(frozen=True)
class Nutrition:
    kcal: int = 0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    sodium_mg: int = 0
    calcium_mg: int = 0


@dataclass(frozen=True)
class Item:
    code: str
    name: str
    category: str
    price: Money
    tags: frozenset[str] = frozenset()
    popularity: float = 0.5
    nutrition: Nutrition = field(default_factory=Nutrition)
    nutrition_source: str = "unavailable"  # measured | snapshot | unavailable

    @property
    def is_main(self) -> bool:
        return self.category in {"burger", "breakfast", "kids"}


@dataclass(frozen=True)
class Combo:
    """一个人的一份饭：一个主食 + 可选小食 + 可选饮料。"""

    main: Item
    side: Item | None = None
    drink: Item | None = None

    @property
    def items(self) -> tuple[Item, ...]:
        return tuple(i for i in (self.main, self.side, self.drink) if i is not None)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.items)

    @property
    def price(self) -> Money:
        return sum_money(i.price for i in self.items)

    @property
    def kcal(self) -> int:
        return sum(i.nutrition.kcal for i in self.items)

    @property
    def kcal_known(self) -> bool:
        """每个组成都有可靠营养数据时为 True。

        营养数据缺失时 kcal 会偏低甚至为 0，如果拿它去过热量上限，
        「没有数据」就会被当成「热量很低」——这是最危险的默认值。
        """
        return all(i.nutrition_source != "unavailable" for i in self.items)

    @property
    def kcal_text(self) -> str:
        return str(self.kcal) if self.kcal_known else "未知"

    @property
    def tags(self) -> frozenset[str]:
        acc: set[str] = set()
        for item in self.items:
            acc |= set(item.tags)
        return frozenset(acc)

    def describe(self) -> str:
        parts = [self.main.name]
        if self.side:
            parts.append(self.side.name)
        if self.drink:
            parts.append(self.drink.name)
        return " + ".join(parts)


@dataclass
class Member:
    """一个要吃饭的人。"""

    name: str
    budget: Money | None = None           # 个人心理价位（硬上限）
    avoid_tags: frozenset[str] = frozenset()  # 忌口 / 过敏 / 信仰（硬约束）
    max_kcal: int | None = None           # 热量硬上限
    target_kcal: int = 800                # 期望热量（软约束）
    likes: Mapping[str, float] = field(default_factory=dict)
    dislikes: Mapping[str, float] = field(default_factory=dict)
    recent_mains: tuple[str, ...] = ()    # 最近吃过的主食，用于避免重复
    note: str = ""

    def violation(self, combo: Combo) -> str | None:
        """返回违反的硬约束说明；合法时返回 None。"""
        hit = self.avoid_tags & combo.tags
        if hit:
            return "含忌口：" + "、".join(sorted(tag_label(t) for t in hit))
        if self.max_kcal is not None:
            # 热量上限是「证明安全」而不是「无法证伪就放行」：
            # 营养数据缺失的餐品一律不进入该成员的候选，否则缺数据=0 kcal 会骗过上限。
            if not combo.kcal_known:
                return "营养数据缺失，无法验证热量上限"
            if combo.kcal > self.max_kcal:
                return f"热量 {combo.kcal} kcal 超上限 {self.max_kcal} kcal"
        if self.budget is not None and combo.price > self.budget:
            return f"{combo.price} 超个人预算 {self.budget}"
        return None


@dataclass
class Assignment:
    member: Member
    combo: Combo
    utility: float
    ceiling: float       # 该成员在硬约束内的最高效用（不考虑预算）
    floor: float         # 该成员可选方案的最低效用
    price: Money
    ideal: "Combo | None" = None   # 「他心里的最佳」具体是哪一份，用于把后悔值翻译成人话

    @property
    def satisfaction(self) -> float:
        span = self.ceiling - self.floor
        if span <= 1e-9:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (self.ceiling - self.utility) / span))

    @property
    def regret(self) -> float:
        return max(0.0, self.ceiling - self.utility)


@dataclass
class Plan:
    assignments: list[Assignment]
    budget: Money
    label: str = "推荐方案"
    coupon: "Coupon | None" = None
    diversify_note: str = ""

    @property
    def subtotal(self) -> Money:
        return sum_money(a.price for a in self.assignments)

    @property
    def discount(self) -> Money:
        if self.coupon is None:
            return Money.zero()
        return self.coupon.apply(self.subtotal)

    @property
    def total(self) -> Money:
        return self.subtotal - self.discount

    @property
    def welfare(self) -> float:
        return sum(a.utility for a in self.assignments)

    @property
    def avg_satisfaction(self) -> float:
        if not self.assignments:
            return 0.0
        return sum(a.satisfaction for a in self.assignments) / len(self.assignments)

    @property
    def headcount(self) -> int:
        return len(self.assignments)

    @property
    def per_head(self) -> Money:
        if not self.assignments:
            return Money.zero()
        return Money(self.total.fen // len(self.assignments))

    @property
    def kcal_total(self) -> int:
        return sum(a.combo.kcal for a in self.assignments)

    @property
    def kcal_unknown(self) -> int:
        """营养数据缺失的份数。缺数据时合计热量只能当**下限**看。"""
        return sum(1 for a in self.assignments if not a.combo.kcal_known)

    @property
    def kcal_text(self) -> str:
        prefix = "≥" if self.kcal_unknown else ""
        return f"{prefix}{self.kcal_total}"

    def ranked_regrets(self) -> list[Assignment]:
        return sorted(self.assignments, key=lambda a: a.regret, reverse=True)

    @property
    def item_count(self) -> int:
        return sum(len(a.combo.items) for a in self.assignments)


@dataclass(frozen=True)
class Coupon:
    code: str
    title: str
    kind: str                     # orderThreshold | itemDiscount
    threshold: Money | None = None
    discount_amount: Money = field(default_factory=Money.zero)
    item_code: str | None = None
    note: str = ""

    def eligible(self, subtotal: Money) -> bool:
        if self.kind == "orderThreshold":
            return self.threshold is not None and subtotal >= self.threshold
        return False

    def apply(self, subtotal: Money) -> Money:
        if not self.eligible(subtotal):
            return Money.zero()
        return min(self.discount_amount, subtotal)


@dataclass
class Team:
    members: list[Member]
    budget: Money
    store_id: str | None = None
    store_name: str | None = None
    meal_type: str = "到店取餐"

    @property
    def headcount(self) -> int:
        return len(self.members)

    def member_names(self) -> list[str]:
        return [m.name for m in self.members]


def collect_codes(combos: Iterable[Combo]) -> set[str]:
    codes: set[str] = set()
    for combo in combos:
        codes.update(combo.codes)
    return codes
