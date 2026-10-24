"""`list-nutrition-foods` 回包解析。

这个工具返回的不是 JSON，而是一张「类 CSV」的纯文本表：

    [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
      猪柳麦满分,null,1288,308,16,16,24,781,213
      中薯条,null,1210,289,4,12,38,165,18

两个必须注意的点：

1. **索引键是餐品名，不是产品编码**。所以营养数据只能按名字 join 菜单，
   名字对不上就是 unavailable——绝不能猜一个数字填进去。
2. 缺失值写作 `null` 或空串，必须当 0 处理，而不是让 `int()` 抛异常。
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import Nutrition

_HEADER = re.compile(r"\[(?P<count>\d+)\]\{(?P<cols>[^}]+)\}")


class NutritionTable:
    """按餐品名查询营养，名字做一次归一化（去空格、全半角统一）。"""

    def __init__(self, rows: dict[str, Nutrition], declared: int = 0, dropped: int = 0):
        self._rows = rows
        self.declared = declared or len(rows)
        self.dropped = dropped

    def __len__(self) -> int:
        return len(self._rows)

    def get(self, name: str) -> Nutrition | None:
        return self._rows.get(normalize_name(name))

    def match(self, name: str) -> tuple[Nutrition | None, str]:
        """先精确匹配，再尝试「包含」匹配（如「巨无霸汉堡」→「巨无霸」）。

        返回 (营养, 命中方式)。命中方式用于报告里标注可信度，
        因为模糊命中可能是错的，不该和精确命中一样理直气壮。
        """
        exact = self._rows.get(normalize_name(name))
        if exact is not None:
            return exact, "exact"
        key = normalize_name(name)
        if not key:
            return None, "miss"
        for candidate, value in self._rows.items():
            if candidate and (candidate in key or key in candidate):
                return value, "fuzzy"
        return None, "miss"

    @classmethod
    def from_tool_payload(cls, payload: object) -> "NutritionTable":
        text = _as_text(payload)
        if not text:
            return cls({})
        columns, rows, dropped = _parse(text)
        if not columns:
            return cls({})
        index = {name: i for i, name in enumerate(columns)}
        rows_out: dict[str, Nutrition] = {}
        declared = 0
        match = _HEADER.search(text)
        if match:
            declared = int(match.group("count"))
        for tokens in rows:
            if not tokens:
                continue
            name = _cell(tokens, index, "productName")
            if not name:
                continue
            rows_out[normalize_name(name)] = Nutrition(
                kcal=_int(_cell(tokens, index, "energyKcal")),
                protein_g=_float(_cell(tokens, index, "protein")),
                fat_g=_float(_cell(tokens, index, "fat")),
                carb_g=_float(_cell(tokens, index, "carbohydrate")),
                sodium_mg=_int(_cell(tokens, index, "sodium")),
                calcium_mg=_int(_cell(tokens, index, "calcium")),
            )
        return cls(rows_out, declared=declared or len(rows_out), dropped=dropped)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).replace("（", "(").replace("）", ")")


def _as_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, str):
            return data
        for value in payload.values():
            if isinstance(value, str) and "{" in value:
                return value
    return ""


def _parse(text: str) -> tuple[list[str], list[list[str]], int]:
    """拆表头与数据行。返回 (列名, 数据行, 被丢弃的行数)。

    列数对不上的行直接丢弃：这条表是纯文本，如果餐品名里带英文逗号，
    `split(",")` 会让后面所有列左移一位——静默错位比缺一行危险得多。
    """
    match = _HEADER.search(text)
    if not match:
        return [], [], 0
    columns = [c.strip() for c in match.group("cols").split(",") if c.strip()]
    # 表头行以 "}:" 结尾，冒号会落在正文第一行，先剥掉；否则会被当成一行数据
    body = text[match.end():].lstrip(":").lstrip()
    rows: list[list[str]] = []
    dropped = 0
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        tokens = [token.strip() for token in line.split(",")]
        if len(tokens) < 2:      # 残行（只剩标点/分隔符），不是数据
            continue
        if len(tokens) != len(columns):
            dropped += 1
            continue
        rows.append(tokens)
    return columns, rows, dropped


def _cell(tokens: Iterable[str], index: dict[str, int], key: str) -> str:
    position = index.get(key)
    values = list(tokens)
    if position is None or position >= len(values):
        return ""
    return values[position]


def _int(value: str) -> int:
    number = _float(value)
    return int(number)


def _float(value: str) -> float:
    text = str(value or "").strip().lower()
    if text in ("", "null", "none", "n/a", "-", "--"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
