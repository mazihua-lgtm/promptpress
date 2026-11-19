"""Run with: python3 -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import compress as c  # noqa: E402


class NegationTests(unittest.TestCase):
    def test_keeps_bu_keyi(self):
        out = c.compress("这里不可以删除文件")
        self.assertIn("不可以", out)

    def test_bu_keyi_not_truncated_to_bu(self):
        out = c.compress("这个接口不可以调用")
        self.assertIn("不可以", out)
        self.assertNotIn("接口不调用", out)

    def test_keeps_bu_neng_and_bu_yao(self):
        self.assertIn("不能", c.compress("你不能修改配置"))
        self.assertIn("不要", c.compress("不要删除日志"))


class CompoundWordTests(unittest.TestCase):
    def test_huanyou_kept(self):
        self.assertIn("还有", c.compress("还有其他问题吗"))

    def test_daima_shenhe_kept_whole(self):
        out = c.compress("请做一次代码审查")
        self.assertIn("代码审查", out)

    def test_liaojie_kept(self):
        self.assertIn("了解", c.compress("我想了解一下这个库"))

    def test_guolv_kept(self):
        self.assertIn("过滤", c.compress("过滤掉空行"))

    def test_hanshu_mapped_to_func(self):
        self.assertIn("func", c.compress("写一个函数"))


class StatsTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(c.estimate_tokens(""), 0)
        s = c.compress_stats("", "")
        self.assertEqual(s["char_saving_pct"], 0.0)
        self.assertEqual(s["token_saving_pct"], 0.0)

    def test_tokens_differ_from_chars(self):
        text = "数据库连接失败，请检查配置"
        self.assertNotEqual(c.estimate_tokens(text), len(text))

    def test_stats_keys_and_ranges(self):
        orig = "请问一下，麻烦你能不能帮我看看最近有什么好的ETF投资机会？"
        s = c.compress_stats(orig, c.compress(orig))
        for k in ("chars_before", "chars_after", "char_saving_pct",
                  "tokens_before", "tokens_after", "token_saving_pct", "token_method"):
            self.assertIn(k, s)
        self.assertLess(s["chars_after"], s["chars_before"])
        self.assertGreater(s["char_saving_pct"], 0)

    def test_benchmark_runs(self):
        lines = []
        summary = c.benchmark(out=lines.append)
        self.assertGreater(summary["char_saving_pct"], 0)
        self.assertTrue(any("token" in line for line in lines))

    def test_unknown_level_raises(self):
        with self.assertRaises(ValueError):
            c.compress("x", level="bogus")


if __name__ == "__main__":
    unittest.main()
