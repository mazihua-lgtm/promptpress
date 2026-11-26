---
name: promptpress
description: >
  使用显式完整输入规则对比中文 prompt，并用固定 tokenizer 实测 token 数。
  仅当用户需要审核规则或测量给定文本时使用；没有已审核规则时保持原文。
---

# PromptPress

不自动删除虚词、否定词、模态词或指代，也不自动缩写术语。
只有用户审核的整句 JSON 规则才可改写；未知输入逐字返回。
不要把字符减少或 token 减少宣称为实际费用节省。

从仓库目录运行（Python 3.9+）：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python compress.py "你的 prompt"
python compress.py bench
python compress.py bench --rules examples/rules.json
python -m unittest discover -s tests -v
```

向用户展示原文、输出和 token 对比。规则示例、测量口径与局限见 README.md。
`tiktoken==0.12.0` / `o200k_base` 是唯一计量路径；首次下载词表需网络，失败就报告失败，不用启发式数字代替。
