"""运行：python -m unittest discover -s tests -v"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tiktoken
import compress as c


class SemanticsTests(unittest.TestCase):
    def test_preserves_unreviewed_inputs_in_both_levels(self):
        cases = [
            "这里不可以删除文件", "这个接口不可以调用", "你不能修改配置",
            "不要删除日志", "请做一次代码审查", "必须保留这个字段",
            "不必须提供身份证", "不是所有请求都可以重试", "如果失败就停止，否则继续",
            "只处理这些文件，不处理那些文件", "哪个字段是可选的？",
            "只有管理员才可以删除", "还没有完成代码审查", "我认为这不是同一个对象",
            "必须保留的字段和可以删除的字段", "了解过滤函数式编程和哈希算法",
            '  def f():\n    return "谢谢"\n\n', "值为1.0...不要改标点！？",
            "谢谢是一种礼貌用语", "<|endoftext|>", "", " \n\t",
        ]
        for level in ("light", "max"):
            for text in cases:
                with self.subTest(level=level, text=text):
                    self.assertEqual(c.compress(text, level), text)

    def test_explicit_rules_match_only_entire_input_and_do_not_cascade(self):
        rules = {"请问，必须保留这个字段吗？": "必须保留这个字段吗？",
                 "必须保留这个字段吗？": "另一条已审核输出"}
        for text, expected in [
            ("请问，必须保留这个字段吗？", "必须保留这个字段吗？"),
            ("不可以说：请问，必须保留这个字段吗？", "不可以说：请问，必须保留这个字段吗？"),
            ('输出原文“请问，必须保留这个字段吗？”', '输出原文“请问，必须保留这个字段吗？”'),
            ("请问，必须保留这个字段吗？\n", "请问，必须保留这个字段吗？\n"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(c.compress(text, rules=rules), expected)

    def test_sample_rules_only_remove_reviewed_politeness(self):
        rules = c.load_rules("examples/rules.json")
        self.assertEqual(len(rules), 2)
        for source, target in rules.items():
            self.assertEqual(c.compress(source, rules=rules), target)
            self.assertEqual(c.compress("不要改写：" + source, rules=rules), "不要改写：" + source)
            if "数据" in source:
                self.assertIn("如果可以的话再帮我画几张图表展示一下", target)

    def test_invalid_rules_and_levels_fail(self):
        for rules in ([], {"": "x"}, {"x": ""}, {"x": 1}, {"x": {}}):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                c.compress("x", rules=rules)
        with self.assertRaises(ValueError):
            c.compress("x", level="bogus")

    def test_non_object_rule_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for value in ("null", "[]", '"text"'):
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    c.load_rules(path)

    def test_duplicate_json_rules_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text('{"x":"a","x":"b"}')
            with self.assertRaisesRegex(ValueError, "重复规则"):
                c.load_rules(path)


class MeasurementTests(unittest.TestCase):
    def test_exact_known_token_counts(self):
        self.assertEqual(c.estimate_tokens("hello world"), 2)
        self.assertEqual(c.estimate_tokens(""), 0)
        self.assertEqual(c.estimate_tokens("你好"), 1)
        encoder = tiktoken.get_encoding("o200k_base")
        for text in ("必须进行代码审查", "emoji🙂 mixed SQL", "<|endoftext|>"):
            self.assertEqual(c.estimate_tokens(text), len(encoder.encode(text, disallowed_special=())))

    def test_missing_tokenizer_fails_without_heuristic(self):
        with patch.object(c, "_tiktoken_encoder", side_effect=ImportError("missing")):
            with self.assertRaises(ImportError):
                c.compress_stats("abc", "a")

    def test_empty_and_negative_savings(self):
        self.assertEqual(c.compress_stats("", "")["token_saving_pct"], 0.0)
        self.assertLess(c.compress_stats("hi", "this is a much longer prompt")["token_saving_pct"], 0)

    def test_benchmark_matches_independent_encoding_totals(self):
        encoder = tiktoken.get_encoding("o200k_base")
        rules = c.load_rules("examples/rules.json")
        for selected in (None, rules):
            lines = []
            result = c.benchmark(out=lines.append, rules=selected)
            before = sum(len(encoder.encode(text)) for _, text in c.TEST_CASES)
            after = sum(len(encoder.encode((selected or {}).get(text, text))) for _, text in c.TEST_CASES)
            self.assertEqual(result['tokens_before'], before)
            self.assertEqual(result['tokens_after'], after)
            self.assertEqual(result['token_saving_pct'], round((1 - after / before) * 100, 1))
            self.assertTrue(any('原文:' in line for line in lines))
            self.assertTrue(any('输出:' in line for line in lines))

    def test_cli_preserves_stdin_and_displays_comparison(self):
        source = "  不可以删除代码审查记录\n\n"
        result = subprocess.run([sys.executable, "compress.py"], input=source, text=True, capture_output=True, check=True)
        self.assertIn("原文: " + json.dumps(source, ensure_ascii=False), result.stdout)
        self.assertIn("输出: " + json.dumps(source, ensure_ascii=False), result.stdout)

    def test_cli_explicit_rules(self):
        source, target = next(iter(c.load_rules("examples/rules.json").items()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(c.main([source, "--rules", "examples/rules.json"]), 0)
        self.assertIn("输出: " + json.dumps(target, ensure_ascii=False), output.getvalue())


if __name__ == "__main__":
    unittest.main()
