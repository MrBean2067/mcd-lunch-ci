"""把 GitHub Issue 里的评论变成团队配置。

这是"午餐流水线"真正长在 GitHub 上的那部分：同事不必装任何东西，只要在 Issue 里
回一行 `/lunch join ...`，工作流就会把所有人的约束收集起来跑一遍求解器。

命令格式（大小写不敏感，一行一条）：

    /lunch join name=阿岚 budget=30 avoid=pork likes=coffee
    /lunch join name=Kevin budget=30 maxkcal=600 avoid=fried target=550
    /lunch approve
    /lunch veto 牛
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .models import Member, Team
from .money import Money

COMMAND = re.compile(r"^\s*/lunch\s+(?P<sub>\w+)\s*(?P<rest>.*)$", re.IGNORECASE)
PAIR = re.compile(r"(\w+)\s*=\s*([^\s]+)")

TAG_ALIASES = {
    "辣": "spicy", "辣椒": "spicy", "spicy": "spicy",
    "猪": "pork", "猪肉": "pork", "pork": "pork",
    "牛": "beef", "牛肉": "beef", "beef": "beef",
    "鸡": "chicken", "chicken": "chicken",
    "鱼": "fish", "fish": "fish",
    "奶": "dairy", "乳": "dairy", "乳制品": "dairy", "dairy": "dairy",
    "蛋": "egg", "鸡蛋": "egg", "egg": "egg",
    "麸质": "gluten", "gluten": "gluten",
    "炸": "fried", "油炸": "fried", "fried": "fried",
    "咖啡因": "caffeine", "caffeine": "caffeine",
    "大豆": "soy", "豆": "soy", "soy": "soy",
}

LIKE_ALIASES = {
    "咖啡": "caffeine", "caffeine": "caffeine",
    "辣": "spicy", "spicy": "spicy",
    "牛": "beef", "beef": "beef",
    "鸡": "chicken", "chicken": "chicken",
    "甜": "sugar", "sugar": "sugar",
    "奶": "dairy", "dairy": "dairy",
    "鱼": "fish", "fish": "fish",
}

KEY_ALIASES = {
    "name": "name", "名字": "name", "昵称": "name",
    "budget": "budget", "预算": "budget",
    "avoid": "avoid", "忌口": "avoid", "不吃": "avoid",
    "likes": "likes", "喜欢": "likes",
    "dislikes": "dislikes", "讨厌": "dislikes",
    "maxkcal": "max_kcal", "max_kcal": "max_kcal", "热量上限": "max_kcal",
    "target": "target_kcal", "target_kcal": "target_kcal", "目标热量": "target_kcal",
    "recent": "recent", "最近吃过": "recent",
    "note": "note", "备注": "note",
}


@dataclass
class Comment:
    author: str
    body: str


@dataclass
class TallyResult:
    members: dict[str, Member] = field(default_factory=dict)
    approvals: set[str] = field(default_factory=set)
    vetoes: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def approved_ratio(self, headcount: int) -> float:
        if headcount <= 0:
            return 0.0
        return len(self.approvals & set(self.members)) / headcount


def _translate_tag(word: str) -> str | None:
    word = word.strip()
    if not word:
        return None
    return TAG_ALIASES.get(word.lower(), word.lower() if word.isascii() else None)


def _split_list(raw: str) -> list[str]:
    return [part for part in re.split(r"[,，/|+]", raw) if part.strip()]


def parse_join(author: str, rest: str) -> tuple[Member | None, str | None]:
    fields: dict[str, str] = {}
    for key, value in PAIR.findall(rest):
        canonical = KEY_ALIASES.get(key.lower(), KEY_ALIASES.get(key, key.lower()))
        fields[canonical] = value

    name = fields.get("name") or author
    if not name:
        return None, "缺少 name=（也可以直接用 GitHub 昵称）"

    avoid: set[str] = set()
    for word in _split_list(fields.get("avoid", "")):
        tag = _translate_tag(word)
        if tag is None:
            return None, f"无法识别的忌口标签「{word}」，可用：辣/猪/牛/鱼/奶/蛋/麸质/炸/咖啡因/大豆"
        avoid.add(tag)

    likes = {}
    for word in _split_list(fields.get("likes", "")):
        tag = LIKE_ALIASES.get(word.strip().lower(), word.strip().lower() if word.strip().isascii() else None)
        if tag:
            likes[tag] = 0.4
    dislikes = {}
    for word in _split_list(fields.get("dislikes", "")):
        tag = LIKE_ALIASES.get(word.strip().lower(), word.strip().lower() if word.strip().isascii() else None)
        if tag:
            dislikes[tag] = 0.4

    try:
        budget = Money.from_yuan(fields["budget"]) if "budget" in fields else None
        max_kcal = int(fields["max_kcal"]) if "max_kcal" in fields else None
        target_kcal = int(fields.get("target_kcal", 800))
    except (ValueError, ArithmeticError):
        return None, f"{name} 的 budget / maxkcal 必须是数字"

    member = Member(
        name=name,
        budget=budget,
        avoid_tags=frozenset(avoid),
        max_kcal=max_kcal,
        target_kcal=target_kcal,
        likes=likes,
        dislikes=dislikes,
        recent_mains=tuple(_split_list(fields.get("recent", ""))),
        note=fields.get("note", ""),
    )
    return member, None


def tally(comments: Iterable[Comment]) -> TallyResult:
    result = TallyResult()
    for comment in comments:
        match = COMMAND.match(comment.body.strip().splitlines()[0] if comment.body.strip() else "")
        if not match:
            continue
        sub = match.group("sub").lower()
        rest = match.group("rest")
        if sub in {"join", "报名", "加入"}:
            member, error = parse_join(comment.author, rest)
            if error:
                result.errors.append(f"@{comment.author}：{error}")
            elif member:
                if member.name in result.members:
                    result.errors.append(f"@{comment.author}：{member.name} 已报名，后一条覆盖前一条")
                result.members[member.name] = member
        elif sub in {"approve", "ok", "确认", "同意"}:
            result.approvals.add(comment.author)
        elif sub in {"veto", "否决"}:
            word = rest.strip()
            if word:
                tag = _translate_tag(word)
                if tag is None:
                    result.errors.append(f"@{comment.author}：否决理由「{word}」无法识别")
                else:
                    result.vetoes.append((comment.author, tag))
        else:
            result.errors.append(f"@{comment.author}：未知子命令 {sub}")
    return result


def to_team(result: TallyResult, budget: Money, store_id: str | None = None,
            store_name: str | None = None) -> Team:
    members = list(result.members.values())
    for _, tag in result.vetoes:
        for member in members:
            member.avoid_tags = frozenset(set(member.avoid_tags) | {tag})
    return Team(members=members, budget=budget, store_id=store_id, store_name=store_name)
