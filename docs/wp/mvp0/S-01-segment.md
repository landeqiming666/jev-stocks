---
id: S-01
title: 分句与分段
phase: mvp0
platform: shared
lane: semantic
deps: [C-00]
size: S
owns: [core/sentinel/semantic/segment.py, core/tests/unit/semantic/test_segment.py, core/tests/fixtures/semantic/segment/]
appends: []
stubs: []
---

# S-01 分句与分段

## 0. 一眼看懂

- **目标**：把清洗后的披露文本确定性切成可回切原文的句子与段落；段落不超过 1200 字符，每份文档最多 60 段。
- **完成后解锁**：S-05 的证据句定位、P-02 的段落落库。
- **预计规模**：实现约 180 行，测试约 190 行；纯标准库，无 I/O、无网络、无数据库。

## 1. 背景与边界

### 1.1 为什么需要它
Jev 对无关内容敏感，段落过长会稀释判定；证据又必须是原文子串。分句和分段若不能稳定回切，用户会看到偏移错位的高亮，缓存哈希也会不稳定。所有文本处理必须由确定性纯函数完成。

### 1.2 范围内
1. `split_sentences(text)`：处理英文缩写、数字小数点、中英文句末标点、引号与括号。
2. `split_passages(text)`：优先在段落与句子边界组合，单句过长时硬切。
3. 所有 `TextSpan` 的 `text` 必须等于 `original[start:end]`。
4. 超过 60 段时只返回前 60 段，并把 `truncated=True`。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| HTML 解析、Unicode/控制字符清洗 | D-03；本包输入已是清洗文本 |
| 调用 Jev、生成证据判定 | S-05 |
| 翻译、摘要、改写 | 不做 |
| 用正则 `\s+` 重写原文 | 禁止；会改变偏移 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 1.4 虚构数据、3.3 语言、4 时间与数值 | 示例公司、中文和字符计数 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 1、3.2、5.2、8 输入清洗 | 1200 字符、证据句、注入边界 |
| [04-数据模型.md](../../04-数据模型.md) | 3.4 `event_passage` | `file_seq/seq/start_offset/end_offset` 语义 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.1–2.2 | 测试命名与确定性 |

## 3. 前置条件

- C-00 已合并：只使用 `sentinel.errors.SentinelError` 处理调用方缺陷时可选包装；本包公开函数对非法参数直接抛 `ValueError`。
- 输入是 `str`，已由 D-03 做 NFC、换行归一和控制字符删除。
- 不读取环境变量、不调用 `clock.now()`、不访问文件系统。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/semantic/__init__.py` | 新建 | 空文件或只导出 `TextSpan/split_sentences/split_passages` |
| `core/sentinel/semantic/segment.py` | 新建 | 句子与段落切分、偏移计算、硬切逻辑 |
| `core/tests/unit/semantic/test_segment.py` | 新建 | §8.1 的 12 个测试 |
| `core/tests/fixtures/semantic/segment/cases.json` | 新建 | 固定输入、预期句子、偏移与段落长度 |
| `core/tests/fixtures/semantic/segment/e1_passage.txt` | 新建 | 06 §10 的 E1 段落 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str

@dataclass(frozen=True)
class PassageSplit:
    passages: list[TextSpan]
    truncated: bool
    original_chars: int

def split_sentences(text: str) -> list[TextSpan]: ...
def split_passages(
    text: str,
    *,
    max_chars: int = 1200,
    max_passages: int = 60,
) -> PassageSplit: ...
```
参数：`text` 可为空；`max_chars` 必须在 `100..1200`，`max_passages` 必须在 `1..60`，越界抛 `ValueError`。两个函数线程安全、无副作用。`split_sentences` 对空文本返回 `[]`；`split_passages` 对空文本返回 `PassageSplit([], False, 0)`。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `start` | int | 是 | `0 ≤ start < end ≤ len(text)` | 原文起点，含 |
| `end` | int | 是 | `end - start == len(span.text)` | 原文终点，不含 |
| `text` | str | 是 | `text[start:end]` 的精确切片 | 去首尾空白后的原文 |
| `truncated` | bool | 是 | — | 是否因 60 段上限丢弃后续内容 |
| `original_chars` | int | 是 | `len(input)` | 输入 Unicode 码点数 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_PASSAGE_CHARS` | `1200` | `segment.py` | 06 §8 的段落上限 |
| `MAX_PASSAGES_PER_DOCUMENT` | `60` | 同上 | 每份披露最多判定段落数 |
| `MIN_PASSAGE_CHARS` | `100` | 同上 | 防止测试误用极小上限 |
| `ABBREVIATIONS` | `frozenset`，见 §6.1 | 同上 | 句中句点例外 |
| `SENTENCE_END` | `".?!。！？"` | 同上 | 句末标点 |
| `CLOSERS` | `"\"'”’)]}）】」』"` | 同上 | 标点后并入的闭合符 |

## 6. 实现步骤
### 6.1 句子切分
1. 若输入为空或全空白，返回 `[]`；否则先扫描非空白起点和终点，后续只在 `[first,last)` 内产出。
2. `ABBREVIATIONS` 固定为：`mr. mrs. ms. dr. prof. inc. corp. ltd. co. llc. plc. no. vs. u.s. u.k. e.g. i.e. item.`。比较时取句点前连续字母/点号并转小写，保留结尾句点。
3. 对每个位置 `i`，若 `text[i]` 在 `SENTENCE_END`：小数点情形 `i>0`、`i+1<n`、两侧都是 ASCII 数字时不切；英文句点前 token 在缩写集合时不切。
4. 其余句末标点若后面紧跟零个或多个空格/换行，再跟大写字母、数字、`"'“（([` 或 CJK 字符，则视为边界；文本末尾也是边界。
5. 把句末后连续 `CLOSERS` 并入当前句；切片起点跳过前导空白，终点跳过尾随空白。句子之间的空白不属于任何 span。
6. 不满足边界条件的标点不切；`\n\n` 总是边界，即使没有句末标点。

### 6.2 段落组合
1. 先调用 `split_sentences(text)`；若没有句子但文本非空，把整段非空白文本作为一个句子。
2. 维护当前段落起点 `p_start`。加入下一句后若 `span.end - p_start > max_chars`：先提交当前段落；若当前段落为空且单句超过 `max_chars`，走 §6.3 硬切。
3. 若两句之间原文包含 `\n\n`，先提交当前段落，再从下一句开始新段落；空段不提交。
4. 当已提交 `max_passages` 段时停止，`truncated` 等于“仍未处理的非空文本存在”。否则 `truncated=False`。
5. 每段再次去首尾空白并重算 `start/end`；相邻段不得重叠，段落顺序必须与原文一致。

### 6.3 单句硬切
1. 从剩余片段起点开始，窗口终点为 `start+max_chars`。
2. 在 `[start+max_chars//2, start+max_chars]` 内找最后一个空格、制表或换行；找到则切在该空白前，否则切在 `start+max_chars`。
3. 新片段去首尾空白后提交；若仍有剩余，重复直到不超过 `max_chars`。
4. 硬切不改变标点，不插入省略号；证据仍可精确回切。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| `max_chars < 100` 或 `> 1200` | 抛 `ValueError("max_chars")` | `INTERNAL`（调用方缺陷） | `error.INTERNAL` |
| `max_passages < 1` 或 `> 60` | 抛 `ValueError("max_passages")` | `INTERNAL` | `error.INTERNAL` |
| 输入含 `\x00` | 不清理，照常按字符切；D-03 应已删除 | 不适用 | 不适用 |
| 无句末标点但有换行 | 按 `\n\n` 或硬切产出 | 不适用 | 不适用 |
| 单句恰好 1200 字符 | 作为一段，不再硬切 | 不适用 | 不适用 |
| 超过 60 段 | 返回前 60 段，`truncated=True` | 不适用 | 界面由 S-05 标注“仅分析前 60 段” |
| span 回切不相等 | 抛 `AssertionError`，测试失败 | `INTERNAL` | 不得上线 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_split_sentences_handles_inc_and_decimal` | `core/tests/unit/semantic/test_segment.py` | `Zenith Arc Robotics Inc. rose 3.5 percent. Atlas sold shares.` | 2 句；第一句含 `Inc.` 与 `3.5` |
| `test_split_sentences_handles_chinese_punctuation` | 同上 | `公司公告。控股股东拟减持！` | 2 句：`公司公告。`、`控股股东拟减持！` |
| `test_split_sentences_keeps_closing_quote` | 同上 | `He said "no." Then left.` | 2 句；第一句以 `no."` 结束 |
| `test_split_sentences_uses_paragraph_break_without_punctuation` | 同上 | `Heading\n\nBody text` | 2 句 |
| `test_every_sentence_is_exact_original_substring` | 同上 | E1 fixture | 每句 `span.text == text[start:end]` |
| `test_split_passages_never_exceeds_1200_chars` | 同上 | `x ` 重复 900 次 | 所有段落 ≤ 1200；相邻不重叠 |
| `test_split_passages_prefers_paragraph_boundary` | 同上 | 两句以 `\n\n` 分隔且总长 < 1200 | 2 段 |
| `test_split_passages_hard_splits_one_long_sentence` | 同上 | 无空格字符 `a` 重复 2500 次 | 3 段，长度 1200/1200/100 |
| `test_split_passages_stops_at_60_and_sets_truncated` | 同上 | 70 段各 20 字符 | `len(passages)==60`；`truncated is True` |
| `test_split_passages_empty_text` | 同上 | `""` | `PassageSplit([], False, 0)` |
| `test_split_passages_rejects_out_of_range_limits` | 同上 | `max_chars=99`、`max_passages=61` | 两次 `ValueError` |
| `test_e1_passage_offsets_match_fixture` | 同上 | `e1_passage.txt` | 4 句；第 2 句 start/end 与 `cases.json` 完全一致 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `cases.json` | 上述 12 个测试的输入与预期 span | 手工编写；禁止从真实持仓或邮件复制 |
| `e1_passage.txt` | 06 §10 的虚构 ZZAR 8-K 段落 | 逐字复制文档，末尾保留一个 `\n` |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/unit/semantic/test_segment.py -q
# 期望：12 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；ruff、mypy、pytest 全绿
```

### 9.2 完成清单
- [ ] 第 4 节全部文件已创建
- [ ] 第 8.1 节 12 个测试存在且通过
- [ ] 所有 span 可精确回切，段落长度与 60 段上限有测试
- [ ] 没有修改 `owns` 之外文件、没有新增依赖
- [ ] 已写 `docs/wp/status/S-01.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| D-03 | `split_passages()`、`PassageSplit.truncated` | 写库前用 `passage_id(event_id,file_seq,start,end)` |
| S-05 | `split_sentences()`、`TextSpan.start/end` | 最多取前 40 句；偏移直接写 `evidence_start/end` |
| E-02 | fixture 与分句规则 | 标注证据句时使用同一 `split_sentences` |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 缩写表漏项导致错切 | 证据句跨两个句子 | 加回归样例并升规则版本；不得在线用模型纠正 |
| 硬切切断单词 | 段落末尾出现半个单词 | 已优先在空白处切；无空白时接受固定 1200 字符 |
| Unicode 代理对偏移错误 | Python 码点与 JS UTF-16 长度不同 | 后端偏移固定为 Python 码点；前端必须 `Array.from(text).slice(start, end)`；回归样例 `A😀. Revenue fell.` 的 `[4,17)` 必须高亮 `Revenue fell.` |
