import json
import tempfile
import unittest
from pathlib import Path

from mcd_lunch_ci.votes import Comment, tally, to_team
from mcd_lunch_ci.money import Money


class VoteParsingTest(unittest.TestCase):
    def test_join_with_constraints(self):
        result = tally([
            Comment("alan", "/lunch join name=阿岚 budget=30 avoid=猪肉 likes=咖啡"),
            Comment("kevin", "/lunch join name=Kevin budget=30 maxkcal=600 avoid=炸 target=550"),
        ])
        self.assertEqual(set(result.members), {"阿岚", "Kevin"})
        self.assertEqual(result.members["阿岚"].avoid_tags, frozenset({"pork"}))
        self.assertEqual(result.members["阿岚"].budget, Money.from_yuan(30))
        self.assertEqual(result.members["阿岚"].likes.get("caffeine"), 0.4)
        self.assertEqual(result.members["Kevin"].max_kcal, 600)
        self.assertEqual(result.errors, [])

    def test_name_falls_back_to_author(self):
        result = tally([Comment("momo", "/lunch join budget=28 avoid=奶")])
        self.assertIn("momo", result.members)

    def test_unknown_tag_is_reported(self):
        result = tally([Comment("x", "/lunch join name=x avoid=香菜")])
        self.assertTrue(result.errors)
        self.assertIn("香菜", result.errors[0])

    def test_approve_and_veto(self):
        result = tally([
            Comment("a", "/lunch join name=a budget=30"),
            Comment("b", "/lunch join name=b budget=30"),
            Comment("a", "/lunch approve"),
            Comment("b", "/lunch veto 牛"),
        ])
        self.assertEqual(result.approvals, {"a"})
        self.assertEqual(result.vetoes, [("b", "beef")])
        self.assertAlmostEqual(result.approved_ratio(2), 0.5)

    def test_non_command_comments_are_ignored(self):
        result = tally([Comment("a", "今天想吃饭"), Comment("b", "/lunch what")])
        self.assertEqual(result.members, {})
        self.assertEqual(len(result.errors), 1)

    def test_to_team_applies_veto(self):
        result = tally([
            Comment("a", "/lunch join name=a budget=30"),
            Comment("b", "/lunch veto 辣"),
        ])
        team = to_team(result, Money.from_yuan(30))
        self.assertEqual(team.members[0].avoid_tags, frozenset({"spicy"}))


class TallyCommandTest(unittest.TestCase):
    def test_github_api_shape(self):
        """真实 GitHub 评论接口的结构也要能解析。"""
        payload = [
            {"user": {"login": "alan"}, "body": "/lunch join name=阿岚 budget=30"},
            {"user": {"login": "bob"}, "body": "/lunch approve"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "comments.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            raw = json.loads(path.read_text(encoding="utf-8"))
        comments = [
            Comment(author=e["user"]["login"], body=e["body"]) for e in raw
        ]
        result = tally(comments)
        self.assertEqual(list(result.members), ["阿岚"])


if __name__ == "__main__":
    unittest.main()
