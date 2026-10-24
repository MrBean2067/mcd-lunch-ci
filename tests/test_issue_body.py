"""报名 Issue 正文的格式校验。

第一次报名被系统判「报名信息未通过校验」，原因是我们把四个字段压成了一行。
官方的模板其实是四行：`【参赛申请】` 单独一行，后面三个字段各占一行，
且「标签：内容」之间不能换行。

这类失败没有任何本地报错，只能等官方机器人回复才知道，所以把它固化成测试：
改文案时如果格式跑偏，`unittest` 会先拦住。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY_PATH = ROOT / "docs" / "ISSUE_BODY.txt"

LABELS = ("项目名称：", "项目地址：", "项目简介：")


class IssueBodyFormatTest(unittest.TestCase):
    def setUp(self):
        self.raw = BODY_PATH.read_text(encoding="utf-8")
        self.lines = [line for line in self.raw.splitlines() if line.strip()]

    def test_first_line_is_the_marker(self):
        self.assertEqual(self.lines[0], "【参赛申请】", "第一行必须是【参赛申请】，且单独成行")

    def test_four_lines_only(self):
        self.assertEqual(len(self.lines), 4, "正文必须正好四行：标记 + 三个字段")

    def test_each_label_on_its_own_line(self):
        for label, line in zip(LABELS, self.lines[1:]):
            self.assertTrue(line.startswith(label), f"这一行必须以 {label} 开头，实际是：{line[:20]}")

    def test_label_and_content_not_split(self):
        """「项目简介」和它的内容之间不能再换行，否则校验器读到的是空值。"""
        for label, line in zip(LABELS, self.lines[1:]):
            self.assertGreater(len(line), len(label), f"{label} 后面没有内容")

    def test_address_is_not_markdown_link(self):
        addr = self.lines[2]
        self.assertNotIn("](", addr, "项目地址不能用 Markdown 链接，必须贴裸链接")
        self.assertNotIn("[", addr)
        self.assertIn("https://github.com/MrBean2067/mcd-lunch-ci", addr)

    def test_file_has_no_windows_line_ending(self):
        self.assertNotIn("\r", self.raw, "CRLF 会让校验器的行切分出错，仓库统一用 LF")


if __name__ == "__main__":
    unittest.main()
