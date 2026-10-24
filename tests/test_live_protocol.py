"""真实 MCP 协议适配的测试。

这里锁死的每一条，都是实测踩过的坑；改坏了这些断言，线上就会重新翻车。
"""

from __future__ import annotations

import unittest

from mcd_lunch_ci.live import (classify_tag, infer_category, is_sauce_only, looks_like_merchandise)
from mcd_lunch_ci.mcp_client import extract_json
from mcd_lunch_ci.models import Combo, Item, Member, Nutrition
from mcd_lunch_ci.money import Money
from mcd_lunch_ci.nutrition_table import NutritionTable


class TestExtractJson(unittest.TestCase):
    def test_mixed_text_and_json(self):
        """真实回包是「说明文字 + JSON」，直接 json.loads 会炸。"""
        raw = ('每个门店的基本信息按单行展示：\n'
               '{"success":true,"code":200,"data":[{"storeCode":"1420762"}]}')
        self.assertEqual(extract_json(raw)["data"][0]["storeCode"], "1420762")

    def test_pure_json_and_plain_text(self):
        self.assertEqual(extract_json('{"a":1}')["a"], 1)
        self.assertEqual(extract_json("纯文本没有 JSON"), "纯文本没有 JSON")

    def test_brace_inside_prose_is_skipped(self):
        raw = 'Hint: 用 {storeCode} 这个字段\n{"success":true,"data":{"x":1}}'
        self.assertEqual(extract_json(raw)["data"]["x"], 1)


class TestNutritionTable(unittest.TestCase):
    SAMPLE = (
        "[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\n"
        "  猪柳麦满分,null,1288,308,16,16,24,781,213\n"
        "  中薯条,null,1210,289,4,12,38,165,18\n"
    )

    def test_parses_csv_like_payload(self):
        table = NutritionTable.from_tool_payload({"success": True, "data": self.SAMPLE})
        self.assertEqual(len(table), 2)
        self.assertEqual(table.get("中薯条").kcal, 289)
        self.assertEqual(table.get("猪柳麦满分").sodium_mg, 781)

    def test_exact_beats_fuzzy(self):
        table = NutritionTable.from_tool_payload(self.SAMPLE)
        _, how = table.match("中薯条")
        self.assertEqual(how, "exact")
        value, how = table.match("中薯条（大份）")
        self.assertEqual(how, "fuzzy")
        self.assertEqual(value.kcal, 289)

    def test_missing_nutrition_is_none_not_zero(self):
        """匹配不上必须返回 None。返回 0 会让「热量未知」被当成「0 卡」。"""
        table = NutritionTable.from_tool_payload(self.SAMPLE)
        value, how = table.match("根本不存在的汉堡")
        self.assertIsNone(value)
        self.assertEqual(how, "miss")


class TestCategoryInference(unittest.TestCase):
    def test_burger_wins_over_side_keyword(self):
        """实测坑：麦辣鸡腿汉堡含"鸡腿"，曾被塞进小食槽。"""
        self.assertEqual(infer_category("麦辣鸡腿汉堡"), "burger")
        self.assertEqual(infer_category("板烧鸡腿堡"), "burger")

    def test_side_and_drink(self):
        self.assertEqual(infer_category("中薯条"), "side")
        self.assertEqual(infer_category("可乐"), "drink")
        self.assertEqual(infer_category("圆筒冰淇淋"), "dessert")

    def test_marketing_category_as_fallback(self):
        self.assertEqual(infer_category("黄金橙橙", "饮品"), "drink")


class TestTagSafety(unittest.TestCase):
    def test_milk_is_not_beef(self):
        """「纯牛奶」曾因含"牛"被标成牛肉——过敏原误标比漏标更尴尬。"""
        self.assertNotIn("beef", classify_tag("纯牛奶(盒装)"))
        self.assertIn("dairy", classify_tag("纯牛奶(盒装)"))
        self.assertIn("beef", classify_tag("巨无霸"))

    def test_unknown_sodium_does_not_crash(self):
        self.assertNotIn("salty", classify_tag("中薯条"))
        self.assertIn("salty", classify_tag("中薯条", Nutrition(sodium_mg=900)))

    def test_merchandise_and_sauce_filtered(self):
        self.assertTrue(looks_like_merchandise("麦当劳限定丝巾"))
        self.assertTrue(looks_like_merchandise("“葱不求人“按摩捶痒痒挠"))
        self.assertTrue(is_sauce_only("韩式烟熏芝士风味酱"))
        self.assertFalse(is_sauce_only("蘸酱炸鸡"))


class TestKcalIntegrity(unittest.TestCase):
    def _item(self, source: str, kcal: int) -> Item:
        return Item(code="X", name="汉堡", category="burger", price=Money.from_yuan(20),
                    nutrition=Nutrition(kcal=kcal), nutrition_source=source)

    def test_unknown_nutrition_blocks_kcal_cap(self):
        """缺营养数据时不能靠"0 kcal"混过热量上限。"""
        member = Member(name="Kevin", max_kcal=600)
        combo = Combo(main=self._item("unavailable", 0))
        self.assertEqual(member.violation(combo), "营养数据缺失，无法验证热量上限")

    def test_known_nutrition_still_enforced(self):
        member = Member(name="Kevin", max_kcal=600)
        self.assertIsNone(member.violation(Combo(main=self._item("measured", 500))))
        self.assertIn("超上限", member.violation(Combo(main=self._item("measured", 900))))

    def test_no_cap_means_no_extra_requirement(self):
        member = Member(name="老周")
        self.assertIsNone(member.violation(Combo(main=self._item("unavailable", 0))))


if __name__ == "__main__":
    unittest.main()
