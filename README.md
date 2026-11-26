# PromptPress

中文 Prompt **显式整句规则 + 前后对比 + token 实测**工具，无模型调用。

默认逐字保留输入。旧版无边界删除虚词和缩写术语会损坏否定、条件、数量和指代；有限保护词表无法覆盖任意上下文，因此不再自动删词。你可以审核并提供完整输入到完整输出的 JSON 映射：只有整段完全相同才匹配，不匹配子串、不级联替换、不清理空白或标点。`light` / `max` Python 参数仅为兼容保留，行为相同。

## 安装与使用

Python 3.9+。用于 token 计量的依赖固定为 `tiktoken==0.12.0`（MIT，与本仓 MIT 兼容；常见平台有预编译 wheel，无模型权重）。选择它是为了直接使用公开 tokenizer，而非字符数估算。首次使用 `o200k_base` 需联网下载并缓存词表；缺依赖、下载失败均报错，绝不回退为估算。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python compress.py "这个接口不可以调用，必须进行代码审查"
printf '必须保留这个字段\n' | python compress.py
python compress.py --rules examples/rules.json "你的完整输入"
```

CLI 总是展示原文、输出（JSON 字符串，以显示换行/空白）及 token/字符对比。Python API：

```python
from compress import compress, compress_stats
rules = {"请问，必须保留这个字段吗？": "必须保留这个字段吗？"}
original = "请问，必须保留这个字段吗？"
result = compress(original, rules=rules)
print(original, result, compress_stats(original, result), sep="\n")
```

规则是调用者批准的改写，工具不证明自定义规则的语义等价。请逐条核对否定、条件、指代、数量和模态词；空键、空输出、重复 JSON 键和非字符串映射会被拒绝。

## 可复现实测

样例集是 `compress.py` 的 `TEST_CASES` 六条固定中文 prompt。`examples/rules.json` 仅为其中两条显式移除开头/结尾客套语，其余四条原样返回；这是人工编写的样例规则，不代表对未知 prompt 的压缩能力。两条输出的全文可在 JSON 和 benchmark 对比中检查。

安装后运行：

```bash
python -m unittest discover -s tests -v
python compress.py bench
python compress.py bench --rules examples/rules.json
```

实测环境 Python 3.13.5、tiktoken 0.12.0、`o200k_base`，计数单条原始文本（不含聊天模板、系统提示、工具调用或模型输出）。上述两条 benchmark 命令会逐条打印完整前后文本和所有数字：

| 样例 | 原始 token | 显式规则后 token |
|---|---:|---:|
| 日常提问 | 33 | 23 |
| 编程任务 | 47 | 47 |
| 数据分析 | 48 | 38 |
| 持仓诊断 | 112 | 112 |
| 复杂指令 | 56 | 56 |
| 多步任务 | 82 | 82 |
| 合计 | 378 | 358 |

- `python compress.py bench`：无规则，378 → 378 tokens，节省 **0.0%**；字符 604 → 604，节省 **0.0%**。
- `python compress.py bench --rules examples/rules.json`：378 → 358 tokens，节省 **5.3%**；字符 604 → 578，节省 **4.3%**。

节省比例 = `(原始总数 - 输出总数) / 原始总数 × 100`，保留一位小数；合计按总 token 数计算，不平均各样例百分比。空输入的节省比例约定为零；变长时允许负数。字符数为 Python `len(str)`，仅作辅助。

## 局限

这不是通用自动压缩器，也没有跨任务语义等价保证。测试覆盖“不可以”“代码审查”“必须”、否定范围、条件、指代、引用、代码空白等二十余条输入及显式规则的正反例，但不代替下游模型质量评估。示例规则针对已知输入编写，不能视为独立测试集效果。token 数只对指定编码有效，不等于其他模型的 token 数，更不能直接换算账单节省；本仓未测量模型回答质量、延迟、缓存计费或实际费用。

## 许可证

MIT
