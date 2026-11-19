"""
PromptPress v2 —— 中文 Prompt 规则压缩引擎（无模型调用）

核心思路：
  1. PROTECTED：否定词、逻辑连词、模态词、复合词整体保留，绝不拆分。
  2. DROP_WORDS：纯礼貌语、语气词、无语义填充。
  3. SHORTCUT_MAP 符号化、TECH_TERMS 术语缩写。
  以上规则合并为一个正则，按词长从长到短匹配（最长匹配优先）。每段文本只扫描一次，
  替换结果不会再被替换，避免 "函数式" 被先拆成 "func式" 之类的串改。

Token 计量：estimate_tokens() 若检测到 tiktoken 则精确计数，否则用启发式估算
（CJK 字符约 1 token，ASCII 单词约每 4 字符 1 token，其余符号 1 token）。
字符数 != token 数，压缩收益以 token 为准，统计请使用 compress_stats()。
"""

import math
import re
import sys
from functools import lru_cache

# ---------------------------------------------------------------
# 规则表
# ---------------------------------------------------------------

# 保护词：原样保留。优先级最高，用于防止删除/替换切断词语或反转语义。
PROTECTED = [
    # 否定：必须整体保留，否则语义反转
    "不可以", "不能", "不要", "不需要", "不应该", "不必", "不得", "不会",
    "不是", "不用", "不一定", "没有", "未必",
    # 逻辑连词与顺序
    "还是", "还有", "还要", "以及", "或者", "并且", "而且", "但是", "不过",
    "因为", "所以", "如果", "虽然", "否则", "另外", "然后",
    # 模态：删除会改变语义强度
    "可以", "能够", "需要", "应该", "必须", "可能",
    # 复合词 / 含虚词字的词（删除其中的虚词字会拆坏词）
    "代码审查", "代码生成", "代码库", "代码块", "脚本语言",
    "是否", "目的", "的确", "了解", "了不起", "过滤", "地址",
    "人才", "哈希", "再次", "再见", "着急", "得到", "得出", "都是", "都市",
    "很多", "很少",
]

# 删除词：礼貌语、语气词、虚词、填充。仅在不属于保护词时生效。
DROP_WORDS = [
    "请问", "麻烦", "拜托", "谢谢", "感谢", "不好意思", "打扰",
    "吗", "呢", "吧", "啊", "呀", "哦", "哈", "啦",
    "的", "地", "得", "了", "着", "过",
    "是", "很", "都", "也", "就", "才", "还", "又", "再",
    "一个", "一只", "一条", "一张", "一份", "一次", "一下", "一些",
    "这个", "那个", "这些", "那些", "哪个", "哪些",
    "我想", "我觉得", "我认为", "我希望", "我打算", "帮我",
    "进行", "加以", "予以",
]

# 符号化：常见短语 → 符号或短词
SHORTCUT_MAP = {
    "写一个": "→", "写一段": "→", "生成一个": "→", "创建": "→",
    "帮我写": "→", "帮我生成": "→",
    "查询": "@", "搜索": "@", "查找": "@", "查看": "@",
    "帮我查": "@", "帮我搜索": "@", "帮我看看": "@",
    "帮我分析": "分析", "分析一下": "分析",
    "保存到": "→", "输出到": "→", "导出到": "→",
    "ETF数据": "ETF", "股票数据": "股票", "实时行情": "行情",
    "函数": "func",
}

# 技术术语 → 英文缩写
TECH_TERMS = {
    "数据库": "DB", "人工智能": "AI", "机器学习": "ML",
    "应用程序接口": "API", "前端": "FE", "后端": "BE",
    "命令行": "CLI", "用户界面": "UI", "自然语言处理": "NLP",
    "软件开发工具包": "SDK", "搜索引擎优化": "SEO",
    "面向对象": "OOP", "函数式": "FP", "版本控制": "VCS",
    "内容分发网络": "CDN", "高可用": "HA", "负载均衡": "LB",
    "正则表达式": "regex", "回调函数": "callback",
}

# 轻量模式只删除的内容
LIGHT_DROP = [
    "请问", "麻烦你", "能不能帮我", "可不可以", "谢谢你", "不好意思", "打扰了",
    "的", "得", "了", "着", "过",
]


def _build_rules(*groups):
    """合并多组规则，任何关键词重复都直接报错，避免静默覆盖。"""
    rules = {}
    for group in groups:
        for key, value in group.items():
            if key in rules:
                raise ValueError(f"重复规则: {key!r}")
            rules[key] = value
    return rules


def _compile(rules):
    """按词长降序排列，保证正则为最长匹配。"""
    keys = sorted(rules, key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in keys))


_PROTECT_MAP = {w: w for w in PROTECTED}
_MAX_RULES = _build_rules(
    _PROTECT_MAP,
    {w: "" for w in DROP_WORDS},
    SHORTCUT_MAP,
    TECH_TERMS,
)
_MAX_PATTERN = _compile(_MAX_RULES)

_LIGHT_RULES = _build_rules(_PROTECT_MAP, {w: "" for w in LIGHT_DROP})
_LIGHT_PATTERN = _compile(_LIGHT_RULES)


# ---------------------------------------------------------------
# 压缩
# ---------------------------------------------------------------

def _clean_punct(text: str) -> str:
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"[。.]{2,}", "。", text)
    text = re.sub(r"[！!]+", "!", text)
    text = re.sub(r"[？?]+", "?", text)
    text = re.sub(r"[；;]", "；", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"^[，,。.；;！!？?\s]+", "", text)
    text = re.sub(r"[，,。.；;！!？?\s]+$", "", text)
    return text.strip()


def compress(text: str, level: str = "max") -> str:
    """
    压缩中文 prompt。
    level: "light"（只删礼貌语与少量虚词） | "max"（默认，激进）
    """
    if level == "light":
        out = _LIGHT_PATTERN.sub(lambda m: _LIGHT_RULES[m.group(0)], text)
        out = re.sub(r"\s{2,}", " ", out)
        return out.strip()
    if level != "max":
        raise ValueError(f"unknown level: {level!r}")
    out = _MAX_PATTERN.sub(lambda m: _MAX_RULES[m.group(0)], text)
    return _clean_punct(out)


# ---------------------------------------------------------------
# Token 计量
# ---------------------------------------------------------------

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")


@lru_cache(maxsize=1)
def _tiktoken_encoder():
    try:
        import tiktoken
    except ImportError:
        return None
    return tiktoken.get_encoding("o200k_base")


def token_method() -> str:
    """返回当前使用的 token 计量方式。"""
    return "tiktoken:o200k_base" if _tiktoken_encoder() is not None else "heuristic"


def estimate_tokens(text: str) -> int:
    """估算 token 数。安装 tiktoken 时为精确值，否则为启发式估算。"""
    if not text:
        return 0
    enc = _tiktoken_encoder()
    if enc is not None:
        return len(enc.encode(text))
    cjk = len(_CJK_RE.findall(text))
    rest = _CJK_RE.sub(" ", text)
    ascii_tokens = sum(math.ceil(len(w) / 4) for w in re.findall(r"[A-Za-z0-9]+", rest))
    symbols = len(re.findall(r"[^\sA-Za-z0-9]", rest))
    return cjk + ascii_tokens + symbols


def _saving_pct(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return round((1 - after / before) * 100, 1)


def compress_stats(original: str, compressed: str) -> dict:
    """返回字符与 token 两个维度的压缩统计。"""
    tokens_before = estimate_tokens(original)
    tokens_after = estimate_tokens(compressed)
    return {
        "chars_before": len(original),
        "chars_after": len(compressed),
        "char_saving_pct": _saving_pct(len(original), len(compressed)),
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "token_saving_pct": _saving_pct(tokens_before, tokens_after),
        "token_method": token_method(),
    }


# ---------------------------------------------------------------
# 基准测试
# ---------------------------------------------------------------

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


def benchmark(out=print) -> dict:
    """对 TEST_CASES 运行压缩并输出字符与 token 统计，返回汇总。"""
    total = {"chars_before": 0, "chars_after": 0, "tokens_before": 0, "tokens_after": 0}
    out("PromptPress v2 —— 压缩基准")
    out("=" * 60)
    out(f"token 计量方式: {token_method()}")
    for name, case in TEST_CASES:
        result = compress(case)
        s = compress_stats(case, result)
        for k in total:
            total[k] += s[k]
        out(f"\n【{name}】")
        out(f"  原文: {s['chars_before']} 字 / {s['tokens_before']} tokens")
        out(f"  压缩: {s['chars_after']} 字 / {s['tokens_after']} tokens")
        out(f"  节省: 字符 {s['char_saving_pct']}% | token {s['token_saving_pct']}%")
    summary = {
        "chars_before": total["chars_before"],
        "chars_after": total["chars_after"],
        "char_saving_pct": _saving_pct(total["chars_before"], total["chars_after"]),
        "tokens_before": total["tokens_before"],
        "tokens_after": total["tokens_after"],
        "token_saving_pct": _saving_pct(total["tokens_before"], total["tokens_after"]),
        "token_method": token_method(),
    }
    out(f"\n{'=' * 60}")
    out(f"整体: 字符 {summary['char_saving_pct']}% | token {summary['token_saving_pct']}%")
    return summary


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "bench":
        benchmark()
        return 0
    text = " ".join(argv) if argv else sys.stdin.read().strip()
    if not text:
        benchmark()
        return 0
    result = compress(text)
    s = compress_stats(text, result)
    print(f"节省 字符 {s['char_saving_pct']}% | token {s['token_saving_pct']}% ({s['token_method']})")
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
