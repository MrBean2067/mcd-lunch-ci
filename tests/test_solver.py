import itertools
import unittest

from mcd_lunch_ci.models import Member, Team
from mcd_lunch_ci.money import Money
from mcd_lunch_ci.provider import SnapshotProvider
from mcd_lunch_ci.solver import InfeasibleError, _allocate, build_ladder, solve


def _items():
    return [item for item in SnapshotProvider().menu() if item.category != "breakfast"]


def _team(budget_yuan=200):
    members = [
        Member(name="阿岚", budget=Money.from_yuan(30), avoid_tags=frozenset({"pork"}), target_kcal=800),
        Member(name="Kevin", budget=Money.from_yuan(30), avoid_tags=frozenset({"fried"}),
               max_kcal=600, target_kcal=550),
        Member(name="老周", budget=Money.from_yuan(45), target_kcal=1100),
    ]
    return Team(members=members, budget=Money.from_yuan(budget_yuan))


class ConstraintTest(unittest.TestCase):
    def test_plan_respects_every_hard_constraint(self):
        result = solve(_team(), _items())
        plan = result.best
        self.assertEqual(plan.headcount, 3)
        for assignment in plan.assignments:
            self.assertIsNone(assignment.member.violation(assignment.combo))
        self.assertLessEqual(plan.total.fen, plan.budget.fen)
        self.assertLessEqual(plan.subtotal.fen, plan.budget.fen)

    def test_no_allergen_leaks_into_plan(self):
        team = Team(
            members=[Member(name="Momo", budget=Money.from_yuan(40), avoid_tags=frozenset({"dairy"}))],
            budget=Money.from_yuan(40),
        )
        plan = solve(team, _items(), levels=((1.0, "唯一档"),)).best
        assignment = plan.assignments[0]
        self.assertFalse({"dairy"} & set(assignment.combo.tags))
        self.assertNotIn("牛奶", assignment.combo.describe())

    def test_calorie_cap_is_hard(self):
        team = Team(
            members=[Member(name="Kevin", budget=Money.from_yuan(35), max_kcal=400, avoid_tags=frozenset({"fried"}))],
            budget=Money.from_yuan(35),
        )
        plan = solve(team, _items(), levels=((1.0, "唯一档"),)).best
        self.assertLessEqual(plan.assignments[0].combo.kcal, 400)

    def test_infeasible_budget_explains_itself(self):
        team = Team(members=[Member(name="阿哲", budget=Money.from_yuan(6))], budget=Money.from_yuan(6))
        with self.assertRaises(InfeasibleError) as ctx:
            solve(team, _items())
        message = " ".join(ctx.exception.diagnostics)
        self.assertIn("阿哲", message)
        self.assertIn("预算", message)

    def test_infeasible_team_budget(self):
        team = Team(
            members=[Member(name=f"人{i}", budget=Money.from_yuan(30)) for i in range(8)],
            budget=Money.from_yuan(30),
        )
        with self.assertRaises(InfeasibleError) as ctx:
            solve(team, _items())
        self.assertIn("总预算", str(ctx.exception))


class OptimalityTest(unittest.TestCase):
    def test_dp_matches_bruteforce(self):
        """小规模穷举比对：DP 必须给出真正的最优，而不是"差不多"。"""
        team = _team(budget_yuan=60)
        items = _items()
        ladders = [build_ladder(m, items, keep=5) for m in team.members]
        allocated = _allocate(ladders, team.budget.fen, 50)
        self.assertIsNotNone(allocated)
        picks, welfare = allocated

        best = 0.0
        for combo_picks in itertools.product(*[range(len(l.candidates)) for l in ladders]):
            cost = sum(l.candidates[i].combo.price.fen for l, i in zip(ladders, combo_picks))
            if cost > team.budget.fen:
                continue
            value = sum(l.candidates[i].utility for l, i in zip(ladders, combo_picks))
            best = max(best, value)
        self.assertAlmostEqual(welfare, best, places=6)

    def test_frontier_is_monotone(self):
        result = solve(_team(budget_yuan=200), _items())
        welfares = [plan.welfare for plan in result.plans]
        self.assertEqual(welfares, sorted(welfares, reverse=True))
        totals = [plan.total.fen for plan in result.plans]
        self.assertEqual(totals, sorted(totals))

    def test_diversify_never_downgrades_structure(self):
        result = solve(_team(budget_yuan=90), _items())
        plan = result.best
        self.assertLessEqual(plan.subtotal.fen, plan.budget.fen)
        for assignment in plan.assignments:
            self.assertIsNone(assignment.member.violation(assignment.combo))


if __name__ == "__main__":
    unittest.main()
