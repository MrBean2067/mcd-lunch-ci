"""报告渲染：终端、Markdown（可直接贴进 GitHub 评论）、单文件 HTML 卡片。"""

from __future__ import annotations

import html
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from .models import CATEGORY_LABELS, Plan, tag_label
from .money import Money
from .provider import OrderResult, Quote
from .solver import SolveResult

BRAND_RED = "#DA291C"
BRAND_YELLOW = "#FFC72C"


# ---------------------------------------------------------------- 上下文

@dataclass
class Stage:
    key: str
    title: str
    detail: str
    status: str = "ok"       # ok | warn | skip | fail


@dataclass
class RunContext:
    result: SolveResult
    store_name: str
    mode: str
    stages: list[Stage] = field(default_factory=list)
    quote: Quote | None = None
    order: OrderResult | None = None
    generated_at: str = ""


# ---------------------------------------------------------------- 文字宽度

def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - _width(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def _rule(widths: Sequence[int]) -> str:
    return "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"


# ---------------------------------------------------------------- 终端

def _pct(value: float) -> str:
    return f"{round(value * 100):d}%"


def render_terminal(ctx: RunContext) -> str:
    plan = ctx.result.best
    team = ctx.result.team
    lines: list[str] = []
    lines.append("")
    lines.append(f"  \033[1m午餐流水线\033[0m  mcd-lunch-ci")
    lines.append(
        f"  {team.headcount} 人 · 团队预算 {team.budget} · {ctx.store_name} · "
        f"数据源 {'离线快照' if ctx.mode == 'offline' else '麦当劳 MCP 实时'}"
    )
    lines.append("")

    for index, stage in enumerate(ctx.stages, start=1):
        mark = {"ok": "\033[32m✓\033[0m", "warn": "\033[33m!\033[0m",
                "skip": "\033[90m-\033[0m", "fail": "\033[31m✗\033[0m"}[stage.status]
        label = f"[{index}/{len(ctx.stages)}]"
        lines.append(f"  {mark} \033[90m{label}\033[0m {_pad(stage.title, 9)} {stage.detail}")

    # 金额口径：官方核价优先。本地逐项求和只作参考——真下单时促销是按整单算的，
    # 本地永远算不准「满减摊分」，所以有核价结果就一律以官方为准。
    shell_total = plan.total
    if ctx.quote is not None and ctx.quote.verified:
        shell_total = ctx.quote.total
    verified = "已核价" if (ctx.quote and ctx.quote.verified) else "未核价"
    lines.append("")
    lines.append(f"  \033[1;31m推荐方案\033[0m  {plan.label} · 应付 {shell_total} · {verified}")
    if ctx.quote is not None and ctx.quote.verified and shell_total != plan.subtotal:
        saving = plan.subtotal - shell_total
        if saving.fen > 0:
            lines.append(f"  \033[33m官方优惠\033[0m 本地合计 {plan.subtotal} − {saving} = 应付 {shell_total}"
                         f"（人均 {Money(shell_total.fen // max(1, plan.headcount))}）")
        else:
            lines.append(f"  \033[33m核对提示\033[0m 本地合计 {plan.subtotal}，官方核价 {shell_total}"
                         f"（差额 {shell_total - plan.subtotal}，以官方为准）")

    headers = ["成员", "组合", "热量", "价格", "满意度"]
    rows = [
        [
            a.member.name,
            a.combo.describe(),
            a.combo.kcal_text,
            str(a.price),
            _pct(a.satisfaction),
        ]
        for a in plan.assignments
    ]
    rows.append(["合计", f"{plan.headcount} 人 · {plan.item_count} 件", plan.kcal_text, str(plan.subtotal), _pct(plan.avg_satisfaction)])

    widths = [max(_width(r[i]) for r in [headers] + rows) for i in range(len(headers))]
    lines.append("  ┌" + "┬".join("─" * (w + 2) for w in widths) + "┐")
    lines.append("  │" + "│".join(" " + _pad(h, w) + " " for h, w in zip(headers, widths)) + "│")
    lines.append("  " + _rule(widths).replace("├", "├").replace("┤", "┤"))
    for row in rows[:-1]:
        lines.append("  │" + "│".join(" " + _pad(c, w) + " " for c, w in zip(row, widths)) + "│")
    lines.append("  " + _rule(widths))
    lines.append("  │" + "│".join(" " + _pad(c, w) + " " for c, w in zip(rows[-1], widths)) + "│")
    lines.append("  └" + "┴".join("─" * (w + 2) for w in widths) + "┘")

    if plan.discount.fen > 0 and plan.coupon:
        lines.append(f"  \033[33m优惠券\033[0m {plan.coupon.title} −{plan.discount} → 应付 {plan.total}，人均 {plan.per_head}")

    regrets = [a for a in plan.ranked_regrets() if a.regret > 1e-9]
    if regrets:
        lines.append("")
        lines.append("  \033[1m谁妥协了\033[0m")
        for assignment in regrets[:5]:
            # 「差 0.22 分效用」没人看得懂，翻译成「他更想吃哪份、差多少钱」
            ideal = getattr(assignment, "ideal", None)
            tail = ""
            if ideal is not None and ideal.describe() != assignment.combo.describe():
                gap = ideal.price - assignment.price
                if gap.fen > 0:
                    tail = f"；他更想吃 {ideal.describe()}（{ideal.price}），差 {gap}"
                else:
                    tail = f"；他更想吃 {ideal.describe()}（{ideal.price}）"
            lines.append(
                f"    · {assignment.member.name}：拿到 {assignment.combo.describe()}，"
                f"满意度 {_pct(assignment.satisfaction)}{tail}"
            )

    if len(ctx.result.plans) > 1:
        lines.append("")
        lines.append("  \033[1m预算—满意度前沿\033[0m")
        for candidate in ctx.result.plans:
            lines.append(
                f"    · {_pad(candidate.label, 10)} 应付 {str(candidate.total):>9}  人均 {str(candidate.per_head):>8}"
                f"   平均满意度 {_pct(candidate.avg_satisfaction)}"
            )

    if ctx.result.diagnostics:
        lines.append("")
        lines.append("  \033[1m提示\033[0m")
        for note in ctx.result.diagnostics[:4]:
            lines.append(f"    · {note}")

    if ctx.order:
        state = "预览（未下单）" if ctx.order.dry_run else f"已创建订单 {ctx.order.order_id}"
        lines.append("")
        lines.append(f"  \033[1m下单\033[0m {state}" + (f" · 支付链接 {ctx.order.pay_url}" if ctx.order.pay_url else ""))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- Markdown

def render_markdown(ctx: RunContext) -> str:
    plan = ctx.result.best
    team = ctx.result.team
    out: list[str] = []
    out.append("## 🍟 午餐流水线执行报告")
    out.append("")
    out.append(
        f"**{team.headcount} 人 · 团队预算 {team.budget} · {ctx.store_name}**  \n"
        f"数据源：`{'离线快照（无需 Token）' if ctx.mode == 'offline' else '麦当劳 MCP 实时'}`"
        + (f" ｜ 生成时间：{ctx.generated_at}" if ctx.generated_at else "")
    )
    out.append("")

    out.append("| 阶段 | 说明 | 结果 |")
    out.append("| --- | --- | --- |")
    for stage in ctx.stages:
        icon = {"ok": "✅", "warn": "⚠️", "skip": "⏭️", "fail": "❌"}[stage.status]
        out.append(f"| `{stage.title}` | {stage.detail} | {icon} |")
    out.append("")

    total = plan.total  # 券后应付；核价结果（券前）在第 5 阶段单独展示
    out.append(f"### 推荐方案 · 应付 {total}")
    out.append("")
    out.append("| 成员 | 组合 | 热量 | 价格 | 满意度 |")
    out.append("| --- | --- | ---: | ---: | ---: |")
    for assignment in plan.assignments:
        out.append(
            f"| {assignment.member.name} | {assignment.combo.describe()} | "
            f"{assignment.combo.kcal_text} kcal | {assignment.price} | {_pct(assignment.satisfaction)} |"
        )
    out.append(
        f"| **合计** | {plan.headcount} 人 · {plan.item_count} 件 | {plan.kcal_text} kcal | "
        f"**{plan.subtotal}** | {_pct(plan.avg_satisfaction)} |"
    )
    out.append("")
    if plan.discount.fen > 0 and plan.coupon:
        out.append(f"> 已套用「{plan.coupon.title}」减 {plan.discount}，应付 **{plan.total}**，人均 **{plan.per_head}**")
        out.append("")

    regrets = [a for a in plan.ranked_regrets() if a.regret > 1e-9]
    if regrets:
        out.append("### 谁妥协了")
        out.append("")
        out.append("| 成员 | 拿到 | 满意度 | 他更想吃 | 差额 |")
        out.append("| --- | --- | ---: | --- | ---: |")
        for assignment in regrets[:6]:
            ideal = getattr(assignment, "ideal", None)
            wish = ideal.describe() if (ideal and ideal.describe() != assignment.combo.describe()) else "—"
            gap = (ideal.price - assignment.price) if ideal else Money.zero()
            out.append(
                f"| {assignment.member.name} | {assignment.combo.describe()} | "
                f"{_pct(assignment.satisfaction)} | {wish} | {gap if gap.fen > 0 else '—'} |"
            )
        out.append("")

    if len(ctx.result.plans) > 1:
        out.append("### 预算—满意度前沿")
        out.append("")
        out.append("| 档位 | 应付 | 人均 | 平均满意度 |")
        out.append("| --- | ---: | ---: | ---: |")
        for candidate in ctx.result.plans:
            out.append(
                f"| {candidate.label} | {candidate.total} | {candidate.per_head} | {_pct(candidate.avg_satisfaction)} |"
            )
        out.append("")

    out.append("### 硬约束核对")
    out.append("")
    violations = 0
    for assignment in plan.assignments:
        reason = assignment.member.violation(assignment.combo)
        if reason:
            violations += 1
            out.append(f"- ❌ {assignment.member.name}：{reason}")
    if violations == 0:
        out.append(f"- ✅ {plan.headcount} 人全部满足忌口、个人预算与热量上限")
        avoided = sorted({tag_label(t) for m in team.members for t in m.avoid_tags})
        if avoided:
            out.append(f"- 本轮忌口标签：{'、'.join(avoided)}")
    out.append("")
    out.append("<sub>本报告由 mcd-lunch-ci 生成，非麦当劳官方产品；价格以门店实时结果为准。</sub>")
    return "\n".join(out)


# ---------------------------------------------------------------- HTML

def render_html(ctx: RunContext) -> str:
    plan = ctx.result.best
    team = ctx.result.team
    esc = html.escape
    total = plan.total  # 券后应付；核价结果（券前）在第 5 阶段单独展示

    stage_rows = "".join(
        f'<li class="stage {stage.status}"><span class="dot"></span>'
        f'<span class="t">{esc(stage.title)}</span>'
        f'<span class="d">{esc(stage.detail)}</span></li>'
        for stage in ctx.stages
    )
    member_rows = "".join(
        f"<tr><td class='name'>{esc(a.member.name)}</td>"
        f"<td>{esc(a.combo.describe())}</td>"
        f"<td class='num'>{a.combo.kcal_text}</td>"
        f"<td class='num'>{esc(str(a.price))}</td>"
        f"<td class='num'><span class='bar'><i style=\"width:{round(a.satisfaction * 100)}%\"></i></span>"
        f"{round(a.satisfaction * 100)}%</td></tr>"
        for a in plan.assignments
    )
    frontier_rows = "".join(
        f"<tr><td>{esc(c.label)}</td><td class='num'>{esc(str(c.total))}</td>"
        f"<td class='num'>{esc(str(c.per_head))}</td><td class='num'>{round(c.avg_satisfaction * 100)}%</td></tr>"
        for c in ctx.result.plans
    )
    regrets = [a for a in plan.ranked_regrets() if a.regret > 1e-9][:4]
    regret_items = []
    for a in regrets:
        # 「差 0.22 分效用」没人看得懂，卡片上更要说人话：他更想吃哪份、差多少钱
        ideal = getattr(a, "ideal", None)
        tail = ""
        if ideal is not None and ideal.describe() != a.combo.describe():
            gap = ideal.price - a.price
            tail = (f"，他更想吃 {esc(ideal.describe())}（{esc(str(ideal.price))}），差 {esc(str(gap))}"
                    if gap.fen > 0 else f"，他更想吃 {esc(ideal.describe())}（{esc(str(ideal.price))}）")
        regret_items.append(
            f"<li><b>{esc(a.member.name)}</b> 拿到 {esc(a.combo.describe())}，"
            f"满意度 {round(a.satisfaction * 100)}%{tail}</li>"
        )
    regret_html = "".join(regret_items) or "<li>没人需要妥协，这一轮和平收场。</li>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>午餐流水线 · mcd-lunch-ci</title>
<style>
  :root {{
    --red: {BRAND_RED}; --yellow: {BRAND_YELLOW};
    --ink: #14100e; --muted: #6b6259; --line: #eadfd2; --paper: #fffdf8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px; background: linear-gradient(180deg, #fff8ea, #fdf1e0 60%, #fbe9d6);
    font-family: "PingFang SC", "Microsoft YaHei", -apple-system, "Segoe UI", sans-serif;
    color: var(--ink);
  }}
  .card {{ max-width: 860px; margin: 0 auto; background: var(--paper); border-radius: 22px;
    box-shadow: 0 24px 60px rgba(120, 72, 20, .16); overflow: hidden; border: 1px solid var(--line); }}
  header {{ padding: 26px 30px 20px; background: radial-gradient(120% 140% at 0% 0%, #fff3cd, #ffe9a8 45%, #ffd95e);
    border-bottom: 3px solid var(--red); }}
  .eyebrow {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: #8a5a00; font-weight: 700; }}
  h1 {{ margin: 8px 0 6px; font-size: 30px; letter-spacing: -.5px; }}
  h1 span {{ color: var(--red); }}
  .meta {{ font-size: 13px; color: #6b4a00; }}
  .hero {{ display: flex; gap: 14px; padding: 20px 30px 6px; flex-wrap: wrap; }}
  .kpi {{ flex: 1 1 120px; background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; }}
  .kpi b {{ display: block; font-size: 22px; letter-spacing: -.5px; }}
  .kpi small {{ color: var(--muted); font-size: 12px; }}
  .kpi.accent b {{ color: var(--red); }}
  ol.stages {{ list-style: none; margin: 18px 30px 0; padding: 0; display: grid; gap: 6px; }}
  .stage {{ display: grid; grid-template-columns: 18px 88px 1fr; align-items: center; font-size: 13px; }}
  .stage .dot {{ width: 9px; height: 9px; border-radius: 50%; background: #23a26d; }}
  .stage.warn .dot {{ background: #d99a00; }}
  .stage.skip .dot {{ background: #b9b1a6; }}
  .stage .t {{ font-weight: 700; }}
  .stage .d {{ color: var(--muted); }}
  section {{ padding: 8px 30px 4px; }}
  h2 {{ font-size: 15px; letter-spacing: .02em; margin: 22px 0 10px; display: flex; align-items: center; gap: 8px; }}
  h2::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--line); }}
  th {{ font-size: 11px; letter-spacing: .08em; color: var(--muted); text-transform: uppercase; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.name {{ font-weight: 700; }}
  tfoot td {{ font-weight: 700; border-bottom: none; }}
  .bar {{ display: inline-block; width: 54px; height: 6px; background: #f0e6d8; border-radius: 99px; margin-right: 6px;
    vertical-align: middle; overflow: hidden; }}
  .bar i {{ display: block; height: 100%; background: linear-gradient(90deg, var(--yellow), var(--red)); }}
  ul.regret {{ margin: 0; padding-left: 18px; font-size: 13.5px; color: #3a332c; }}
  ul.regret li {{ margin-bottom: 5px; }}
  footer {{ padding: 16px 30px 24px; font-size: 11.5px; color: var(--muted); border-top: 1px dashed var(--line);
    margin-top: 18px; }}
  code {{ background: #f6efe3; padding: 1px 5px; border-radius: 5px; font-size: 12px; }}
</style>
</head>
<body>
<div class="card">
  <header>
    <div class="eyebrow">M-CODE 1024 · 麦当劳程序员创意开发大赛参赛作品</div>
    <h1>午餐<span>流水线</span> mcd-lunch-ci</h1>
    <div class="meta">{team.headcount} 人 · 团队预算 {esc(str(team.budget))} · {esc(ctx.store_name)} · 数据源 {esc(ctx.mode)}</div>
  </header>
  <div class="hero">
    <div class="kpi accent"><b>{esc(str(total))}</b><small>应付总额</small></div>
    <div class="kpi"><b>{esc(str(plan.per_head))}</b><small>人均</small></div>
    <div class="kpi"><b>{round(plan.avg_satisfaction * 100)}%</b><small>平均满意度</small></div>
    <div class="kpi"><b>{plan.kcal_text}</b><small>全队热量 kcal</small></div>
  </div>
  <ol class="stages">{stage_rows}</ol>
  <section>
    <h2>推荐方案</h2>
    <table>
      <thead><tr><th>成员</th><th>组合</th><th class="num">热量</th><th class="num">价格</th><th class="num">满意度</th></tr></thead>
      <tbody>{member_rows}</tbody>
      <tfoot><tr><td>合计</td><td>{plan.headcount} 人 · {plan.item_count} 件</td>
        <td class="num">{plan.kcal_text}</td><td class="num">{esc(str(plan.subtotal))}</td>
        <td class="num">{round(plan.avg_satisfaction * 100)}%</td></tr></tfoot>
    </table>
  </section>
  <section>
    <h2>预算—满意度前沿</h2>
    <table>
      <thead><tr><th>档位</th><th class="num">应付</th><th class="num">人均</th><th class="num">平均满意度</th></tr></thead>
      <tbody>{frontier_rows}</tbody>
    </table>
  </section>
  <section>
    <h2>谁妥协了</h2>
    <ul class="regret">{regret_html}</ul>
  </section>
  <footer>
    由 <code>mcd-lunch-ci</code> 生成 · 非麦当劳官方产品 · 价格为离线快照，真实点餐以
    <code>calculate-price</code> / 门店实时结果为准。方案在给定约束下由整数背包 DP 求解，非启发式近似。
  </footer>
</div>
</body>
</html>
"""
