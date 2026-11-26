"""显式整句规则与可复现 token 计量；默认不改写未知输入。"""

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path


def compress(text: str, level: str = "max", *, rules=None) -> str:
    """仅匹配完整输入，不做子串删除。规则由调用者逐条审核。

    light/max 为旧 API 兼容参数，两者现在采用同一保守行为。
    不提供规则时逐字返回，包括空白、标点和代码。
    """
    if level not in ("light", "max"):
        raise ValueError(f"unknown level: {level!r}")
    if rules is None:
        return text
    if not isinstance(rules, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) or not k or not v
        for k, v in rules.items()
    ):
        raise ValueError("rules 必须是非空字符串到非空字符串的映射")
    return rules.get(text, text)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复规则: {key!r}")
        result[key] = value
    return result


def load_rules(path):
    rules = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    if not isinstance(rules, dict):
        raise ValueError("规则文件顶层必须是 JSON 对象")
    compress("", rules=rules)  # 验证类型；不接受嵌套或空改写
    return rules


@lru_cache(maxsize=1)
def _tiktoken_encoder():
    import tiktoken
    return tiktoken.get_encoding("o200k_base")


def token_method() -> str:
    return "tiktoken:o200k_base"


def estimate_tokens(text: str) -> int:
    """兼容旧函数名，始终真实编码计数；缺依赖或词表时直接报错。"""
    return len(_tiktoken_encoder().encode(text, disallowed_special=()))


def _saving_pct(before, after):
    return round((1 - after / before) * 100, 1) if before else 0.0


def compress_stats(original: str, compressed: str) -> dict:
    before, after = estimate_tokens(original), estimate_tokens(compressed)
    return {
        "chars_before": len(original), "chars_after": len(compressed),
        "char_saving_pct": _saving_pct(len(original), len(compressed)),
        "tokens_before": before, "tokens_after": after,
        "token_saving_pct": _saving_pct(before, after),
        "token_method": token_method(),
    }


TEST_CASES = [
    ("日常提问",
     "请问一下，麻烦你能不能帮我看看最近有什么好的ETF投资机会？我想了解一下半导体和新能源方面的，谢谢你！"),
    ("编程任务",
     "你好，我想请你帮我写一个Python脚本，这个脚本的功能是自动从东方财富网站上爬取A股所有ETF的实时行情数据，然后把数据保存到CSV文件里面，非常感谢！"),
    ("数据分析",
     "不好意思打扰了，我现在需要你做一件事情：帮我分析一下这份数据，看看里面有没有什么异常值或者规律，如果可以的话再帮我画几张图表展示一下，拜托了！"),
    ("持仓诊断",
     "我之前买了几只ETF，包括512480半导体ETF、513650标普500ETF还有511010国债ETF。我想请你帮我做一个全面的分析，包括看看每只ETF的收益率怎么样、风险大不大、溢价有没有问题、资金是在流入还是流出、还有没有更好的同类ETF可以选择。另外也帮我看看目前的宏观环境适不适合继续持有这些ETF。如果你能给我一些调仓建议就更好了，非常感谢你的帮助！"),
    ("复杂指令",
     "请你用面向对象的方式写一个Python类，这个类需要包含以下功能：连接数据库、执行SQL查询、将查询结果转换成JSON格式、支持分页查询、以及自动重连机制。代码需要有完整的错误处理和日志记录。"),
    ("多步任务",
     "第一步：从网站上爬取最新的新闻标题和链接。第二步：对爬取到的新闻进行分类，分成科技、财经、体育三类。第三步：把分类好的新闻保存到数据库里面。第四步：生成一个简单的HTML页面来展示这些新闻。如果遇到反爬虫机制，需要自动切换User-Agent和代理IP。"),
]


def benchmark(out=print, *, rules=None) -> dict:
    """固定样例集，汇总按 token 总数加权，不取百分比平均。"""
    total = dict(chars_before=0, chars_after=0, tokens_before=0, tokens_after=0)
    import importlib.metadata
    out(f"token 计量方式: {token_method()} (tiktoken {importlib.metadata.version('tiktoken')})")
    out("样例集: TEST_CASES（6 条）；规则: " + ("显式整句规则" if rules is not None else "无（原样保留）"))
    for name, case in TEST_CASES:
        result = compress(case, rules=rules)
        stats = compress_stats(case, result)
        for key in total:
            total[key] += stats[key]
        out(f"【{name}】token {stats['tokens_before']} -> {stats['tokens_after']} ({stats['token_saving_pct']}%); 字符 {stats['chars_before']} -> {stats['chars_after']} ({stats['char_saving_pct']}%)")
        out("  原文: " + json.dumps(case, ensure_ascii=False))
        out("  输出: " + json.dumps(result, ensure_ascii=False))
    total.update(token_saving_pct=_saving_pct(total['tokens_before'], total['tokens_after']),
                 char_saving_pct=_saving_pct(total['chars_before'], total['chars_after']),
                 token_method=token_method())
    out(f"整体: token {total['tokens_before']} -> {total['tokens_after']} ({total['token_saving_pct']}%); 字符 {total['chars_before']} -> {total['chars_after']} ({total['char_saving_pct']}%)")
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="原文；bench 运行固定样例；省略则读取 stdin")
    parser.add_argument("--rules", help="经你审核的 JSON 完整输入到完整输出映射")
    args = parser.parse_args(argv)
    rules = load_rules(args.rules) if args.rules else None
    if args.text == "bench":
        benchmark(rules=rules)
        return 0
    original = args.text if args.text is not None else sys.stdin.read()
    result = compress(original, rules=rules)
    stats = compress_stats(original, result)
    print("原文: " + json.dumps(original, ensure_ascii=False))
    print("输出: " + json.dumps(result, ensure_ascii=False))
    print(f"token {stats['tokens_before']} -> {stats['tokens_after']} ({stats['token_saving_pct']}%); 字符 {stats['chars_before']} -> {stats['chars_after']} ({stats['char_saving_pct']}%); {token_method()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
