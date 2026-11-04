---
id: P-03
title: 待处理清单与处理动作
phase: mvp0
platform: shared
lane: semantic
deps: [P-02]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/sentinel/scan/pending.py, core/sentinel/storage/migrations/007_action.sql, core/tests/unit/scan/test_pending.py, core/sentinel/messages/inbox.py]
appends: []
stubs: []
---

# P-03 待处理清单与处理动作

## 0. 一眼看懂

- **目标**：从判定中选出每个（逻辑，披露）对的代表判定，形成待处理、待确认、已处理三组，并实现四种处理动作与重新打开。
- **完成后解锁**：U-02 可以渲染今日清单，U-03 可以显示持仓待处理数，I-01 可以走完整用户闭环。
- **预计规模**：实现约 420 行，测试约 280 行；1 个模块、1 个测试文件。

## 1. 背景与边界

### 1.1 为什么需要它

同一份披露可能含多个段落，同一段落也可能触发多条判定。用户不应看到成百上千条重复提醒，而应看到“这条逻辑最近受到哪份披露的最强挑战”，并能明确记录自己的处理。

### 1.2 范围内

1. `inbox.list` 的聚合、分组、排序、计数和 30 天已处理窗口。
2. 每个（`thesis_id`，`event_id`）只选一个代表判定。
3. `decision.get` 的详情、证据与动作历史。
4. `decision.act` 的四种动作；动作只追加，不修改逻辑、订单或持仓。
5. `decision.reopen` 与派生状态恢复。

### 1.3 明确不做

| 不做 | 由谁做 |
|---|---|
| 生成判定、概率与证据句 | S-05 |
| 扫描调度与批次状态 | P-02 |
| 修改逻辑内容 | P-01；`revise` 只记录意图 |
| 产生模拟订单 | P-05；`exit_intent` 只记录意图 |
| 物理删除处理记录 | 不做；表只追加 |
| 其他迁移文件 | 各自工作包；本包创建 `007_action.sql`，不改其他编号 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §2 判定、关系、处理、清单、§4 时间 | 状态与字段名称 |
| [04-数据模型.md](../../04-数据模型.md) | §3.6 `decision`、§3.7 `007_action.sql`、§7 完整性、§8.1 清单查询 | SQL 与分组规则 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `DecisionSummary`/`Inbox`、§5.5、§7.4、§8 | 返回结构与派生状态 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | §3.4 阈值、§4 真值表、§5 证据句 | 关系与证据含义 |

## 3. 前置条件

- P-02 已能提交 `scan_run`、`scan_batch` 与判定；本包不启动扫描。
- C-03 提供 `Database.read()`、`Database.write()`；`v_last_action` 视图已由 `007_action.sql` 创建。
- C-00 提供 `new_id()`、`clock.now()`、`to_iso()` 和 15 个错误码。
- 本包只依赖 `pydantic` 与标准库；不新增第三方包。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/scan/pending.py` | 新建 | `InboxService`、行模型、代表判定查询、4 个 RPC handler |
| `core/sentinel/storage/migrations/007_action.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.7 的 `thesis_action` 与视图 `v_last_action` |
| `core/tests/unit/scan/test_pending.py` | 新建 | 聚合、排序、动作、重新打开和分页测试 |

## 5. 接口规格

### 5.1 公开接口

```python
class InboxService:
    def list_inbox(self, *, limit: int = 50, cursor: str | None = None) -> InboxPage: ...
    def get_decision(self, decision_id: str) -> DecisionDetail: ...
    def act(self, decision_id: str, action: ActionType,
            note: str | None) -> DecisionSummary: ...
    def reopen(self, decision_id: str) -> DecisionSummary: ...

def register_handlers(registrar: HandlerRegistrar, service: InboxService) -> None: ...
```

- `ActionType` 只能是 `still_valid`、`revise`、`exit_intent`、`ignore`；`reopen` 不是 `decision.act` 的合法参数。
- `list_inbox` 一次读取同一数据库快照，`asOf = clock.now()`；分页只作用于 `processed`，待处理与待确认始终完整返回。
- `act` 与 `reopen` 各自是一个写事务；事务内先确认判定存在，再追加动作，最后重新读取代表判定返回。
- 所有读取使用参数化 SQL，不拼接 ID、备注或游标。
- 返回对象中的概率保留原始 `float`，`headline` 是代表判定的 `decision.headline`。

### 5.2 数据结构

| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `InboxPage` | `asOf` | datetime | 是 | UTC | 快照时间 |
| | `summary` | object | 是 | 五个计数均 ≥ 0 | 汇总 |
| | `items` | list | 是 | 仅 `overturn/weaken` | 待处理 |
| | `uncertain` | list | 是 | 仅 `uncertain` | 待确认 |
| | `processed` | list | 是 | 最近 30 天 | 已处理 |
| `DecisionSummary` | `decisionId` | str | 是 | ULID | 代表判定 |
| | `thesisVersion` | int | 是 | ≥ 1 | 判定时的版本 |
| | `thesisCurrentVersion` | int | 是 | ≥ 1 | 当前版本 |
| | `relation` | enum | 是 | 五种关系 | 结论 |
| | `probabilities` | object | 是 | 五个 0–1 数值 | 原始概率 |
| | `evidence` | object | 是 | 非空 | 证据文本与位置 |
| | `action` | object/null | 否 | 最新一条 | null 或 `reopen` 表示待处理 |
| `ActionRecord` | `action` | enum | 是 | 四动作加 `reopen` | 用户回应 |
| | `note` | str/null | 否 | ≤ 200 个码点 | 备注 |
| | `actedAt` | datetime | 是 | UTC | 记录时间 |

### 5.3 常量与配置

| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `PROCESSED_DAYS` | `30` | `pending.py` | 已处理保留展示窗口 |
| `DEFAULT_LIMIT` / `MAX_LIMIT` | `50` / `200` | `pending.py` | 已处理分页 |
| `MAX_NOTE_CODEPOINTS` | `200` | `pending.py` | 动作备注上限 |
| `RELATION_RANK` | `overturn=0, weaken=1, uncertain=2` | `pending.py` | 代表判定严重度 |

## 6. 实现步骤

1. **代表判定**：使用 [04-数据模型.md](../../04-数据模型.md) §8.1 的窗口查询，`PARTITION BY d.thesis_id, d.event_id`；排序为关系等级升序、`d.headline DESC`、`p.seq ASC`、`d.decision_id ASC`。最后一项是并列时的确定性兜底。
2. **最新动作**：代表判定左连接 `v_last_action`。`action IS NULL` 或 `action = 'reopen'` 归为待处理；其他值归为已处理。
3. **分组**：待处理中 `relation IN ('overturn','weaken')` 放 `items`，`uncertain` 放 `uncertain`；已处理只保留 `acted_at >= asOf - 30 days`。
4. **排序**：`items` 先按 `overturn` 在 `weaken` 前，再按 `headline DESC`、`event.publishedAt DESC`、`decisionId ASC`；`uncertain` 按 `headline DESC`、`event.publishedAt DESC`、`decisionId ASC`；`processed` 按 `actedAt DESC`、动作 ID 逆序。
5. **证据**：拼接 `event_doc`、`event_passage`、`event_file`。`evidence_kind=sentence` 时从 `evidence_start/end` 截取段落；`passage` 返回整段；`title` 返回披露标题。`filePart` 对 `file_seq=-1` 写“标题”、0 写“主文档”、正数写 `event_file.doc_type`。
6. **计数**：`pendingCount = len(items) + len(uncertain)`；`overturnCount` 与 `weakenCount` 只统计 `items` 的对应关系；`uncertainCount` 与 `processedCount` 分别是数组长度。
7. **动作校验**：`note` 去首尾空白；空串转 null；超过 200 个码点抛 `INVALID_ARGUMENT(field="note")`。动作枚举由参数模型先校验。
8. **追加动作**：`act` 用 `new_id()`、`clock.now()` 插入一行；不检查之前是否处理过，允许连续追加。`reopen` 插入字面值 `reopen`；如果当前已是待处理，则不写新行并直接返回。
9. **返回摘要**：动作提交后重新执行 `get_decision` 的同一条聚合查询，保证返回的 `action`、`thesisCurrentVersion` 和排序字段来自已提交事务。
10. **分页游标**：`processed` 的 cursor 为 `base64url(acted_at|action_id)`；下一页使用严格“小于”条件，不允许跳过同秒记录。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| `decisionId` 不存在 | 不返回占位对象 | `NOT_FOUND` | `error.NOT_FOUND` |
| 非法动作值 | 参数模型拒绝，`field="action"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 备注超过 200 码点 | 不写动作，`field="note"`、`data.max=200` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 对已处理项再次 act | 追加新动作，最新一条决定状态 | — | — |
| 对已处理项 reopen | 追加 `reopen`，条目回到对应组 | — | — |
| 对已待处理项 reopen | 幂等返回，不新增记录 | — | — |
| 代表判定证据偏移越界 | 不截断字符串；记录 `INTERNAL`，完整性测试应提前捕获 | `INTERNAL` | `error.INTERNAL` |
| 逻辑已编辑但旧判定仍待处理 | 显示“逻辑已更新”，仍以旧版本判定 | — | 不自动关闭 |
| 已处理超过 30 天 | 不在 `processed` 返回，数据仍保留 | — | — |

## 8. 测试（先写）

### 8.1 测试清单

| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_representative_prefers_overturn_over_weaken` | `test_pending.py` | 同逻辑同披露一条 weaken、一条 overturn | 只返回 overturn |
| `test_representative_uses_headline_then_passage_seq` | 同上 | 同关系，headline 0.8/0.9 | 返回 0.9 |
| `test_tie_uses_smallest_decision_id` | 同上 | 概率和段落序号相同，ID 为 `01B`/`01A` | 返回 `01A` |
| `test_uncertain_is_separate_from_items` | 同上 | 一条 uncertain、一条 weaken | `uncertain` 与 `items` 各 1，pendingCount 2 |
| `test_last_action_reopen_returns_item_to_pending` | 同上 | 先 still_valid，再 reopen | 条目在 `items`，不在 `processed` |
| `test_only_latest_action_controls_state` | 同上 | ignore 后 still_valid | 已处理，最新动作 still_valid |
| `test_processed_window_excludes_31_days_old` | 同上 | 两个 act，时间差 31 天 | 只返回较新的一个 |
| `test_act_does_not_modify_thesis_or_order_tables` | 同上 | 执行 exit_intent | thesis 更新时间不变；paper_order 行数 0 |
| `test_act_appends_multiple_records` | 同上 | 连续 act ignore 两次 | thesis_action 2 行，返回最新 |
| `test_reopen_on_pending_is_noop` | 同上 | 无动作判定调用 reopen | 仍为 0 行动作 |
| `test_note_is_trimmed_and_blank_becomes_null` | 同上 | `"   "` | 数据库备注为 NULL |
| `test_missing_decision_raises_not_found` | 同上 | `"01ZZZZ..."` | `NOT_FOUND` |

### 8.2 Fixture

| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 临时 DuckDB，虚构标的 `us:ZZAR`，一条逻辑、一份 8-K、两个段落、五个判定 | 测试内插入；使用固定时钟 `2026-11-02T00:35:00Z` |

## 9. 验收

### 9.1 命令与期望输出

```bash
(cd core && uv run pytest tests/unit/scan/test_pending.py -q)
# 期望：12 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/scan/pending.py 全绿
```

### 9.2 完成清单

- [ ] 第 4 节三个文件存在，`007_action.sql` 与 04 §3.7 逐字一致，`owns` 外无改动
- [ ] 4 个 RPC 方法严格匹配 §5.5
- [ ] 代表判定严格按推翻、削弱、待确认的顺序
- [ ] `act` 与 `reopen` 都不触发逻辑修改或订单
- [ ] 已写 `docs/wp/status/P-03.md`

## 10. 交接、风险与回退

| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| U-02 | 使用 `inbox.list`、`decision.get`、`decision.act`、`decision.reopen` | 待处理数组不翻译关系，只展示服务端排序 |
| U-03 | 使用 P-01 的计数 | P-01 与 P-03 必须使用相同的“最新动作”定义 |
| P-01 | 持仓 `pendingCount` 与清单计数可能漂移 | 集成测试对同一数据库断言两个计数相等 |
| 动作历史增长 | 只在用户操作时增长，数据量低 | 不删除记录；超过 30 天只从列表隐藏 |
| 证据偏移损坏 | 可能抛 `INTERNAL` | 启动完整性检查报告；不静默截取空白 |
