# PromptPress

无需模型调用的中文 Prompt 规则压缩器。

## 能做什么 / What it does
- 删除礼貌语、虚词与冗余表达
- 将技术术语缩写并符号化短语
- 提供轻量与激进压缩模式
- 实测典型样本压缩率约 33–42%

## 快速使用 / Quick Start
```bash
python3 compress.py "请帮我查询数据库"
```

## 示例输出 / Example Output
```text
@DB
```

## 技术栈 / Tech
- Python 3.9+，纯规则、无第三方依赖

## 适用场景 / Use Cases
- 降低 token 消耗、精简重复指令

## 许可证 / License
MIT
