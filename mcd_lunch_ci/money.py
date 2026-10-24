"""金额工具。

所有内部计算一律使用「分」的整数，杜绝浮点误差。

为什么需要这一层：麦当劳 MCP 各工具的金额字段单位并不统一——餐品价是「元」，
主题活动场次价实测是「分」（5800 表示 ¥58）。混算一次就错 100 倍，而且这种错误
在演示时最容易翻车。因此本项目禁止裸数字参与金额运算：每个外部金额都必须经
`parse_amount(value, unit)` 显式声明单位，单位未知时直接抛错而不是猜。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

FEN_PER_YUAN = 100

_UNIT_ALIASES = {
    "yuan": ("yuan", "元", "rmb", "cny", "¥"),
    "fen": ("fen", "分", "cent", "cents"),
}


class MoneyError(ValueError):
    """金额类型或单位不合法。"""


@dataclass(frozen=True, order=True)
class Money:
    """以分为单位的不可变金额。"""

    fen: int

    def __post_init__(self) -> None:
        if isinstance(self.fen, bool) or not isinstance(self.fen, int):
            raise MoneyError(f"Money 只接受整数分，收到 {self.fen!r}；请用 from_yuan()/from_fen()")

    # ---- 构造 ----
    @classmethod
    def from_fen(cls, fen: int) -> "Money":
        return cls(int(fen))

    @classmethod
    def from_yuan(cls, yuan: "int | float | str | Decimal") -> "Money":
        try:
            amount = Decimal(str(yuan))
        except Exception as exc:  # pragma: no cover - 防御性分支
            raise MoneyError(f"无法解析金额 {yuan!r}") from exc
        return cls(int((amount * FEN_PER_YUAN).to_integral_value(rounding=ROUND_HALF_UP)))

    @classmethod
    def zero(cls) -> "Money":
        return cls(0)

    # ---- 展示 ----
    @property
    def yuan(self) -> Decimal:
        return (Decimal(self.fen) / FEN_PER_YUAN).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def __str__(self) -> str:
        return f"¥{self.yuan}"

    # ---- 运算 ----
    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            raise MoneyError("金额只能与金额相加")
        return Money(self.fen + other.fen)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            raise MoneyError("金额只能与金额相减")
        return Money(self.fen - other.fen)

    def __mul__(self, factor: int) -> "Money":
        if isinstance(factor, bool) or not isinstance(factor, int):
            raise MoneyError("金额只允许乘以整数倍")
        return Money(self.fen * factor)

    __rmul__ = __mul__

    def pct(self, ratio: float) -> "Money":
        """按比例缩放（仅用于预算档位等展示场景，四舍五入到分）。"""
        return Money(int(Decimal(str(ratio)) * self.fen))


def sum_money(values: Iterable[Money]) -> Money:
    total = Money.zero()
    for value in values:
        total = total + value
    return total


def parse_amount(value: "int | float | str", unit: str) -> Money:
    """按显式单位解析外部金额。

    >>> parse_amount(58, "fen")      # 场次价：分
    Money(fen=58)
    >>> parse_amount("58", "yuan")   # 餐品价：元
    Money(fen=5800)
    """
    if unit is None:
        raise MoneyError("缺少金额单位：禁止对无单位金额做运算")
    key = str(unit).strip().lower()
    for canonical, aliases in _UNIT_ALIASES.items():
        if key in aliases:
            return Money.from_fen(value) if canonical == "fen" else Money.from_yuan(value)
    raise MoneyError(f"未知金额单位 {unit!r}：必须显式指定 yuan 或 fen")
