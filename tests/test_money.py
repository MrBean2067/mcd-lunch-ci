import unittest

from mcd_lunch_ci.money import Money, MoneyError, parse_amount, sum_money


class MoneyTest(unittest.TestCase):
    def test_from_yuan_rounds_half_up(self):
        self.assertEqual(Money.from_yuan(25.5).fen, 2550)
        self.assertEqual(Money.from_yuan("0.005").fen, 1)
        self.assertEqual(Money.from_yuan(0.014).fen, 1)
        self.assertEqual(Money.from_yuan(0.015).fen, 2)

    def test_unit_must_be_explicit(self):
        self.assertEqual(parse_amount(58, "fen").fen, 58)
        self.assertEqual(parse_amount("58", "元").fen, 5800)
        self.assertEqual(parse_amount(58, "yuan").fen, 5800)
        with self.assertRaises(MoneyError):
            parse_amount(58, "元角分" if False else "块")

    def test_mixed_unit_trap(self):
        """场次价是分（5800 = ¥58），餐品价是元（58 = ¥58）。当成元读会差 100 倍。"""
        session_price = parse_amount(5800, "fen")
        same_money_from_yuan = parse_amount(58, "yuan")
        misread_as_yuan = parse_amount(5800, "yuan")
        self.assertEqual(session_price, same_money_from_yuan)
        self.assertNotEqual(session_price, misread_as_yuan)
        self.assertEqual(misread_as_yuan.fen, session_price.fen * 100)

    def test_arithmetic_and_display(self):
        self.assertEqual(str(Money.from_yuan(25.5)), "¥25.50")
        self.assertEqual(str(Money.zero()), "¥0.00")
        self.assertEqual((Money.from_yuan(10) - Money.from_yuan(3.5)).fen, 650)
        self.assertEqual(sum_money([Money.from_yuan(1.1), Money.from_yuan(2.2)]).fen, 330)
        with self.assertRaises(MoneyError):
            Money(fen=1.5)  # type: ignore[arg-type]

    def test_float_accumulation_is_exact(self):
        """浮点会给出 0.30000000000000004，我们这里必须是 30 分。"""
        total = sum_money(Money.from_yuan(0.1) for _ in range(3))
        self.assertEqual(total.fen, 30)


if __name__ == "__main__":
    unittest.main()
