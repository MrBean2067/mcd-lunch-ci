"""流水线编排：intake → lint → menu → solve → quote → approve → deploy。

阶段名刻意复用 CI 词汇（lint / deploy），因为它就是一条 CI：每个阶段要么过，要么
带着可读的原因失败，不存在"生成了个差不多能用但没人知道哪一步错了"的中间态。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Plan, Team
from .provider import LunchProvider, Quote
from .report import RunContext, Stage, render_html, render_markdown, render_terminal
from .solver import InfeasibleError, solve
from .models import tag_label


@dataclass
class RunOptions:
    mode: str = "offline"
    confirm: bool = False
    out_dir: Path | str = "out"
    write_files: bool = True
    bucket_fen: int = 50
    meal_period: str = "lunch"     # lunch 时排除早餐专属餐品


class StageTimer:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self.start) * 1000)


def run(team: Team, provider: LunchProvider, options: RunOptions) -> RunContext:
    out_dir = Path(options.out_dir)
    stages: list[Stage] = []

    # 1. intake --------------------------------------------------------
    timer = StageTimer()
    if not team.members:
        raise SystemExit("团队为空：先让同事在 Issue 里 /lunch join")
    stages.append(Stage("intake", "读取名单", f"{team.headcount} 人，预算 {team.budget}（{timer.ms()}ms）"))

    # 2. lint ----------------------------------------------------------
    timer = StageTimer()
    warnings: list[str] = []
    names = team.member_names()
    if len(set(names)) != len(names):
        warnings.append("有重名成员，报告里会分不清谁是谁")
    cap_sum = sum((m.budget.fen for m in team.members if m.budget), 0)
    if cap_sum and cap_sum < team.budget.fen:
        warnings.append(f"个人预算之和 ¥{cap_sum / 100:.2f} 低于团队预算，实际花不了那么多")
    for member in team.members:
        if member.max_kcal is not None and member.max_kcal < 200:
            warnings.append(f"{member.name} 的热量上限 {member.max_kcal} kcal 低于任何一份主食")
    stages.append(
        Stage("lint", "硬约束预检", "通过" if not warnings else f"{len(warnings)} 条提示",
              status="ok" if not warnings else "warn")
    )

    # 3. menu ----------------------------------------------------------
    timer = StageTimer()
    items = provider.menu()
    coupons = provider.coupons()
    store_id, store_name = provider.store()
    if options.meal_period == "lunch":
        # 麦满分、热香饼只在早餐时段供应，午餐不该出现在候选里
        items = [item for item in items if item.category != "breakfast"]
    missing = sum(1 for item in items if item.nutrition_source == "unavailable")
    menu_detail = f"{len(items)} 个餐品、{len(coupons)} 张券"
    if missing:
        # 「缺数据」不是小瑕疵：设了热量上限的成员会被排除掉这些餐品，
        # 所以这里必须说清楚缺了会有什么后果，而不是只报个数。
        caps = sum(1 for m in team.members if m.max_kcal is not None)
        suffix = f"，设了热量上限的 {caps} 位已排除这类餐品" if caps else "，仅标注不参与热量判断"
        menu_detail += f"，{missing} 个缺营养数据{suffix}"
    menu_detail += f"（{timer.ms()}ms）"
    stages.append(Stage("menu", "拉取菜单", menu_detail, status="warn" if missing else "ok"))

    # 4. solve ---------------------------------------------------------
    timer = StageTimer()
    try:
        result = solve(team, items, coupons=coupons, bucket_fen=options.bucket_fen)
    except InfeasibleError as exc:
        print("\n  \033[1;31m✗ 求解失败\033[0m")
        for stage in stages:
            print(f"    ✓ {stage.title}  {stage.detail}")
        print(f"    ✗ solve     {exc}")
        for note in exc.diagnostics:
            print(f"      → {note}")
        raise SystemExit(20) from exc
    best = result.best
    stages.append(
        Stage("solve", "求解方案", f"帕累托前沿 + 预算 DP，最优解 {len(result.plans)} 档（{timer.ms()}ms）")
    )

    # 5. quote ---------------------------------------------------------
    timer = StageTimer()
    quote: Quote = provider.quote(best)
    stages.append(
        Stage("quote", "核对金额", f"{quote.total} · {quote.detail}（{timer.ms()}ms）",
              status="ok" if quote.verified else "warn")
    )

    # 6. approve -------------------------------------------------------
    if options.mode == "live" and options.confirm:
        stages.append(Stage("approve", "人工确认", "已带 --confirm，直连真实下单通道", status="warn"))
    else:
        stages.append(Stage("approve", "人工确认", "未带 --confirm，停在预览（默认行为）", status="skip"))

    # 7. deploy --------------------------------------------------------
    timer = StageTimer()
    order = provider.create_order(best, confirm=options.confirm and options.mode == "live")
    if order.dry_run:
        stages.append(Stage("deploy", "下单", f"预览载荷已就绪，未产生真实订单（{timer.ms()}ms）", status="skip"))
    else:
        stages.append(Stage("deploy", "下单", f"订单 {order.order_id}（{timer.ms()}ms）"))

    ctx = RunContext(
        result=result,
        store_name=store_name,
        mode=options.mode,
        stages=stages,
        quote=quote,
        order=order,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    ctx.result.diagnostics = warnings + ctx.result.diagnostics

    if options.write_files:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "lunch-report.md").write_text(render_markdown(ctx), encoding="utf-8")
        (out_dir / "lunch-card.html").write_text(render_html(ctx), encoding="utf-8")
        (out_dir / "plan.json").write_text(json.dumps(_plan_json(ctx), ensure_ascii=False, indent=2), encoding="utf-8")
    return ctx


def _quote_payload(ctx: RunContext, plan: Plan) -> dict:
    """金额口径：有官方核价就用官方金额，否则用本地求和。

    `payable` 是自动化（GitHub Action、看板）直接读的字段，口径必须和终端报告一致，
    否则同一份方案在终端显示 ¥199.40、在 Action 里显示另一个数。
    """
    verified = bool(ctx.quote and ctx.quote.verified)
    payable = ctx.quote.total if verified else plan.total
    return {
        "total": str(ctx.quote.total) if ctx.quote else None,
        "payable": str(payable),
        "subtotal": str(plan.subtotal),
        "discount": str(plan.subtotal - payable),
        "verified": verified,
        "source": ctx.quote.source if ctx.quote else None,
    }


def _plan_json(ctx: RunContext) -> dict:
    plan = ctx.result.best
    return {
        "storeName": ctx.store_name,
        "mode": ctx.mode,
        "budget": str(ctx.result.team.budget),
        "headcount": plan.headcount,
        "quote": _quote_payload(ctx, plan),
        "members": [
            {
                "name": a.member.name,
                "combo": a.combo.describe(),
                "codes": list(a.combo.codes),
                "kcal": a.combo.kcal,
                "price": str(a.price),
                "satisfaction": round(a.satisfaction, 4),
            }
            for a in plan.assignments
        ],
        "frontier": [
            {
                "label": p.label,
                "total": str(p.total),
                "perHead": str(p.per_head),
                "avgSatisfaction": round(p.avg_satisfaction, 4),
            }
            for p in ctx.result.plans
        ],
        "order": {
            "id": ctx.order.order_id if ctx.order else None,
            "dryRun": ctx.order.dry_run if ctx.order else None,
            "payUrl": ctx.order.pay_url if ctx.order else None,
        },
    }
