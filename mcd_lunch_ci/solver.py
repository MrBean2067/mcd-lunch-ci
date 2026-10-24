"""求解器：把「今天吃什么」变成一个带硬约束的多重选择背包问题。

模型
----
* 每个人从候选组合里恰好选一份（主食 + 可选小食 + 可选饮料）；
* 硬约束：忌口/过敏标签、个人预算、热量上限——违反即淘汰，绝不"稍微超一点"；
* 软目标：`utility()` 把口味偏好、热量贴合度、重复惩罚揉成一个可加的效用；
* 全局：在团队总预算下最大化总效用（社会福利）。

为什么是精确解而不是贪心
----------------------
先把每个人的候选按 (价格, 效用) 做成帕累托前沿（去掉"更贵还更难吃"的劣解），
再对预算做整数分桶 DP。这样得到的是该离散化尺度下的**最优解**，而不是"看起来
还行"的贪心结果——报告里那句"这是一份数学上最优的方案"才站得住脚。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import Combo, Coupon, Item, Member, Plan, Assignment, Team
from .money import Money

DEFAULT_BUCKET_FEN = 50          # 预算分桶粒度：0.5 元
DEFAULT_KEEP = 40                # 每人保留的候选上限
BUDGET_LEVELS = ((1.0, "推荐方案"), (0.85, "省着点方案"), (0.70, "极限方案"))


class InfeasibleError(RuntimeError):
    """在给定约束下不存在任何可行方案。"""

    def __init__(self, message: str, diagnostics: Sequence[str] = ()):
        super().__init__(message)
        self.diagnostics = list(diagnostics)


@dataclass(frozen=True)
class Candidate:
    combo: Combo
    utility: float
    buckets: int


@dataclass(frozen=True)
class MemberLadder:
    """某个人的候选阶梯。"""

    member: Member
    candidates: tuple[Candidate, ...]

    @property
    def ceiling(self) -> float:
        return max(c.utility for c in self.candidates)

    @property
    def floor(self) -> float:
        return min(c.utility for c in self.candidates)


@dataclass
class SolveResult:
    team: Team
    plans: list[Plan]
    diagnostics: list[str]
    candidate_stats: dict[str, int]

    @property
    def best(self) -> Plan:
        return self.plans[0]


# ---------------------------------------------------------------- 候选生成

def iter_combos(items: Iterable[Item]) -> Iterable[Combo]:
    items = list(items)
    mains = [i for i in items if i.is_main]
    # 小食槽同时接受小食和甜品：麦当劳的派/新地本来就是配餐的一部分
    sides: list[Item | None] = [i for i in items if i.category in ("side", "dessert")] + [None]
    drinks: list[Item | None] = [i for i in items if i.category == "drink"] + [None]
    for main in mains:
        for side in sides:
            for drink in drinks:
                yield Combo(main, side, drink)


def utility(member: Member, combo: Combo) -> float:
    """可加效用：结构完整度 + 口味偏好 + 热量贴合 - 重复惩罚。"""
    score = 1.2                                  # 有主食是底线，不是加分项
    if combo.side:
        score += 0.35
    if combo.drink:
        score += 0.45

    for item in combo.items:
        score += 0.15 * (item.popularity - 0.5)   # 大众偏好，只做轻微先验
        for tag in item.tags:
            score += member.likes.get(tag, 0.0)
            score -= member.dislikes.get(tag, 0.0)

    target = max(member.target_kcal, 1)
    score += 0.9 * max(0.0, 1.0 - abs(combo.kcal - target) / target)

    if combo.main.code in member.recent_mains or combo.main.name in member.recent_mains:
        score -= 0.5                              # 昨天刚吃过，别再来一份
    return score


def _pareto_filter(scored: list[tuple[float, Combo]]) -> list[tuple[float, Combo]]:
    """去掉被支配的候选：存在更便宜且不更难吃的方案时，贵的那份没有存在意义。"""
    scored.sort(key=lambda pair: (pair[1].price.fen, -pair[0]))
    frontier: list[tuple[float, Combo]] = []
    best = float("-inf")
    for u, combo in scored:
        if u > best + 1e-12:
            frontier.append((u, combo))
            best = u
    return frontier


def build_ladder(member: Member, items: Iterable[Item], bucket_fen: int = DEFAULT_BUCKET_FEN,
                 keep: int = DEFAULT_KEEP) -> MemberLadder:
    feasible = [c for c in iter_combos(items) if member.violation(c) is None]
    if not feasible:
        return MemberLadder(member, ())

    frontier = _pareto_filter([(utility(member, c), c) for c in feasible])

    # 前沿可能很长，按效用保留 top-K；同时确保最便宜的那档一定在，用于兜底
    by_utility = sorted(frontier, key=lambda pair: -pair[0])[:keep]
    cheapest = min(frontier, key=lambda pair: pair[1].price.fen)
    if all(combo != cheapest[1] for _, combo in by_utility):
        by_utility.append(cheapest)
    by_utility.sort(key=lambda pair: pair[1].price.fen)

    candidates = tuple(
        Candidate(combo=c, utility=u, buckets=-(-c.price.fen // bucket_fen))
        for u, c in by_utility
    )
    return MemberLadder(member, candidates)


def diagnose_member(member: Member, items: Sequence[Item]) -> list[str]:
    """说明一个人为什么一条候选都没有——报错要能直接指导动作。"""
    notes: list[str] = []
    relaxed_tags = Member(
        name=member.name, budget=member.budget, avoid_tags=frozenset(),
        max_kcal=member.max_kcal, target_kcal=member.target_kcal,
    )
    relaxed_budget = Member(
        name=member.name, budget=None, avoid_tags=member.avoid_tags,
        max_kcal=member.max_kcal, target_kcal=member.target_kcal,
    )
    relaxed_kcal = Member(
        name=member.name, budget=member.budget, avoid_tags=member.avoid_tags,
        max_kcal=None, target_kcal=member.target_kcal,
    )

    no_tag = [c for c in iter_combos(items) if relaxed_tags.violation(c) is None]
    no_budget = [c for c in iter_combos(items) if relaxed_budget.violation(c) is None]
    no_kcal = [c for c in iter_combos(items) if relaxed_kcal.violation(c) is None]

    if no_budget:
        cheapest = min(no_budget, key=lambda c: c.price.fen)
        have = member.budget.fen if member.budget else 0
        notes.append(
            f"{member.name}：个人预算至少要 {cheapest.price} 才吃得上一份"
            f"（{cheapest.describe()}），当前只给了 {Money(have)}"
        )
    elif no_kcal:
        lightest = min(no_kcal, key=lambda c: c.kcal)
        notes.append(
            f"{member.name}：热量上限 {member.max_kcal} kcal 太紧，最低可行组合是 "
            f"{lightest.kcal} kcal（{lightest.describe()}）"
        )
    elif no_tag:
        notes.append(
            f"{member.name}：忌口「{'、'.join(sorted(tag_label(t) for t in member.avoid_tags))}」"
            f"把菜单筛空了，需要放宽忌口或换门店"
        )
    else:
        notes.append(f"{member.name}：当前菜单没有任何可售主食，请检查门店或时段")
    return notes


# ---------------------------------------------------------------- 分配 DP

def _allocate(ladders: list[MemberLadder], budget_fen: int, bucket_fen: int):
    buckets = budget_fen // bucket_fen
    if buckets <= 0:
        return None
    NEG = float("-inf")
    dp = [NEG] * (buckets + 1)
    dp[0] = 0.0
    parents: list[list[tuple[int, int]]] = []

    for ladder in ladders:
        ndp = [NEG] * (buckets + 1)
        parent: list[tuple[int, int]] = [(-1, -1)] * (buckets + 1)
        for b in range(buckets + 1):
            base = dp[b]
            if base == NEG:
                continue
            for idx, cand in enumerate(ladder.candidates):
                nb = b + cand.buckets
                if nb > buckets:
                    continue
                value = base + cand.utility
                if value > ndp[nb] + 1e-12:   # 同分保留更便宜的那档（b 递增）
                    ndp[nb] = value
                    parent[nb] = (b, idx)
        parents.append(parent)
        dp = ndp

    best_b = max(range(buckets + 1), key=lambda b: (dp[b], -b))
    if dp[best_b] == NEG:
        return None

    picks: list[int] = []
    b = best_b
    for parent in reversed(parents):
        prev, idx = parent[b]
        picks.append(idx)
        b = prev
    picks.reverse()
    return picks, dp[best_b]


def _build_plan(team: Team, ladders: list[MemberLadder], picks: list[int], label: str,
                coupons: Sequence[Coupon]) -> Plan:
    assignments: list[Assignment] = []
    for ladder, idx in zip(ladders, picks):
        cand = ladder.candidates[idx]
        ideal = max(ladder.candidates, key=lambda c: c.utility).combo
        assignments.append(
            Assignment(
                member=ladder.member,
                combo=cand.combo,
                utility=cand.utility,
                ceiling=ladder.ceiling,
                floor=ladder.floor,
                price=cand.combo.price,
                ideal=ideal,
            )
        )
    plan = Plan(assignments=assignments, budget=team.budget, label=label)
    plan.diversify_note = _diversify(plan, ladders)
    plan.coupon = best_coupon(plan.subtotal, coupons)
    return plan


def _diversify(plan: Plan, ladders: list[MemberLadder], tolerance: float = 0.03) -> str:
    """去重微调：纯最优解经常给出「八个人八份吉士汉堡」。

    DP 的最优解只看总效用，不看"这顿饭像不像人吃的"。所以在最优解之上做一次有界
    替换：把重复主食的成员换成别的主食，代价是总效用最多下降 tolerance（默认 3%）。
    这是可解释的工程折中，不是暗改——报告里会把替换次数和福利损失写出来。
    """
    by_name = {ladder.member.name: ladder for ladder in ladders}
    welfare = plan.welfare
    allowed_loss = welfare * tolerance
    spent_loss = 0.0
    budget_fen = plan.budget.fen
    total_fen = plan.subtotal.fen
    swaps = 0

    for _ in range(len(plan.assignments)):
        counts: dict[str, int] = {}
        for assignment in plan.assignments:
            counts[assignment.combo.main.code] = counts.get(assignment.combo.main.code, 0) + 1
        duplicated = {code for code, count in counts.items() if count > 1}
        if not duplicated:
            break

        used = set(counts)
        # 先照顾"损失最小的人"，让他们换口味最不痛
        candidates = sorted(
            (a for a in plan.assignments if a.combo.main.code in duplicated),
            key=lambda a: a.regret,
        )
        swapped = False
        for assignment in candidates:
            ladder = by_name[assignment.member.name]
            for cand in ladder.candidates:
                if cand.combo.main.code in used:
                    continue
                loss = assignment.utility - cand.utility
                if loss < 0:
                    continue
                if spent_loss + loss > allowed_loss:
                    continue
                # 不为换口味牺牲结构（让人从"汉堡+饮料"退化成"光一个汉堡"，是净亏）
                if len(cand.combo.items) < len(assignment.combo.items):
                    continue
                span = assignment.ceiling - assignment.floor
                new_sat = 1.0 if span <= 1e-9 else 1.0 - (assignment.ceiling - cand.utility) / span
                if new_sat < 0.65:
                    continue
                extra = cand.combo.price.fen - assignment.price.fen
                if total_fen + extra > budget_fen:
                    continue
                # 应用替换
                assignment.combo = cand.combo
                assignment.utility = cand.utility
                assignment.price = cand.combo.price
                total_fen += extra
                spent_loss += loss
                swaps += 1
                swapped = True
                break
            if swapped:
                break
        if not swapped:
            break

    if not swaps:
        return ""
    drop = spent_loss / welfare * 100 if welfare else 0.0
    return f"为避免全组同款，替换了 {swaps} 份主食，总效用仅下降 {drop:.1f}%"


def best_coupon(subtotal: Money, coupons: Sequence[Coupon]) -> Coupon | None:
    """只应用整单满减券；单品券规则常与满减冲突，一律只作提示不参与计算。"""
    usable = [c for c in coupons if c.kind == "orderThreshold" and c.eligible(subtotal)]
    if not usable:
        return None
    return max(usable, key=lambda c: c.discount_amount.fen)


def solve(team: Team, items: Sequence[Item], coupons: Sequence[Coupon] = (),
          bucket_fen: int = DEFAULT_BUCKET_FEN, keep: int = DEFAULT_KEEP,
          levels: Sequence[tuple[float, str]] = BUDGET_LEVELS) -> SolveResult:
    ladders: list[MemberLadder] = []
    diagnostics: list[str] = []
    stats: dict[str, int] = {}

    for member in team.members:
        ladder = build_ladder(member, items, bucket_fen=bucket_fen, keep=keep)
        stats[member.name] = len(ladder.candidates)
        if not ladder.candidates:
            diagnostics.extend(diagnose_member(member, items))
        ladders.append(ladder)

    if diagnostics:
        raise InfeasibleError(
            "有成员在菜单里找不到任何符合约束的组合，流水线在 lint 阶段就停了。", diagnostics
        )
    if not ladders:
        raise InfeasibleError("团队里没有人。")

    cheapest_total = sum(min(l.candidates, key=lambda c: c.combo.price.fen).combo.price.fen for l in ladders)
    if cheapest_total > team.budget.fen:
        raise InfeasibleError(
            f"总预算 ¥{team.budget.yuan} 不足以让每个人都吃上最便宜的组合（至少需要 ¥{Money(cheapest_total).yuan}）。",
            [f"把总预算提到 ¥{Money(cheapest_total).yuan} 以上，或减少人数/放宽忌口"],
        )

    plans: list[Plan] = []
    seen: set[tuple[str, ...]] = set()
    for ratio, label in levels:
        level_budget = max(team.budget.fen if ratio >= 1.0 else team.budget.pct(ratio).fen, cheapest_total)
        allocated = _allocate(ladders, level_budget, bucket_fen)
        if allocated is None:
            continue
        picks, _ = allocated
        plan = _build_plan(team, ladders, picks, label, coupons)
        # 用真实价格复核：DP 的分桶只会更保守，这里做一次显式断言
        if plan.total > team.budget:
            raise AssertionError("内部错误：方案超预算")
        signature = tuple(sorted(a.combo.codes for a in plan.assignments))
        if signature in seen:
            continue
        seen.add(signature)
        plans.append(plan)

    if not plans:
        raise InfeasibleError("预算约束下解不出任何方案。", diagnostics)

    diagnostics.extend(_plan_warnings(plans[0]))
    return SolveResult(team=team, plans=plans, diagnostics=diagnostics, candidate_stats=stats)


def _plan_warnings(plan: Plan) -> list[str]:
    warnings: list[str] = []
    if plan.diversify_note:
        warnings.append(plan.diversify_note)
    for assignment in plan.assignments:
        if assignment.combo.kcal >= 1000:
            warnings.append(
                f"{assignment.member.name} 这份 {assignment.combo.kcal} kcal，已接近一顿正餐上限，建议换小食"
            )
        if assignment.utility == assignment.floor and len(assignment.combo.items) == 1:
            warnings.append(
                f"{assignment.member.name} 只拿到一个单品（{assignment.combo.main.name}），是预算压到极限的结果"
            )
    return warnings
