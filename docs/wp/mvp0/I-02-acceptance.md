---
id: I-02
title: MVP-0 验收与 5 分钟演示
phase: mvp0
platform: shared
lane: integration
deps: [I-01, E-02]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [scripts/acceptance.py, scripts/acceptance_live.py, scripts/tests/test_acceptance.py, scripts/tests/test_acceptance_live.py, apps/desktop/e2e/acceptance/]
appends: []
stubs: []
---

# I-02 MVP-0 验收与 5 分钟演示

## 0. 一眼看懂

- **目标**：把第 8 节八项“必须”变成一条可重复执行的验收命令，并给出任何人在离线环境都能按表演完的 5 分钟演示。最终提交必须包含一次真实 JEVDB 贯通记录。
- **完成后解锁**：课程提交、W-05 的 Windows 对照验收。
- **预计规模**：约 520 行，验收编排 260 行、Playwright 160 行、演示数据脚本 100 行。

## 1. 背景与边界

### 1.1 为什么需要它
功能测试通过不等于交付通过。密钥是否泄露、断网是否还能看、证据是否缺失、评测能否一条命令跑完，都需要在一个干净数据目录里按产品路径核对。现场演示还需要明确失败时的诚实降级，不准临时编数据。

### 1.2 范围内
1. 自动化核对 M-1～M-8，输出每项证据路径和总判定。
2. 运行真实核心 + 前端的验收场景、评测回放、密钥扫描和三处数据库查询。
3. 5 分钟演示脚本、预期界面与固定数据、逐段降级方案。
4. macOS 与 Windows 共用同一验收报告格式，平台结果分开记录。
5. `--full` 模式下用一份固定公开 SEC 披露跑通真实 JEVDB 查询，保存 M-8 的 SQL、统计、数据库结果与界面证据；HTTP 可回放，模型响应不可伪造。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修复验收发现的问题 | 对应工作包；本包只记录和阻断 |
| 构建安装包 | v1；MVP-0 用开发模式 |
| 默认运行付费模型 | 默认 `--offline`；只有最终验收显式使用 `--full` |
| 改任何 RPC、业务逻辑或 UI | 共享工作包 |
| 用 `jev_direct`、cassette 或 SQL 字符串测试替代真实 JEVDB | ADR-018；M-8 直接失败 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [01-产品需求.md](../../01-产品需求.md) | 第 8 节 MVP-0 验收标准 | M-1～M-8 的唯一来源 |
| [09-测试与评测.md](../../09-测试与评测.md) | 11.2 MVP-0 验收、9.7 复现与产物 | 人工项与评测命令 |
| [10-协作与工作包规范.md](../../10-协作与工作包规范.md) | 6 状态文件、9 Windows 协议 | 报告与平台隔离 |
| [05-接口契约.md](../../05-接口契约.md) | 3.2 错误码、5.9 演示数据 | 断网与演示断言 |
| [E-01-demo-data.md](E-01-demo-data.md) | 5.2 固定计数 | 页面与报告期望值 |
| [E-02-eval.md](E-02-eval.md) | 9.1 离线回放命令 | M-5 的执行入口 |

## 3. 前置条件

- I-01 的真实核心 + 前端测试全部通过。
- E-02 的 `dataset.jsonl`、manifest 和 cassette 完整，离线回放可运行。
- `scripts/check.py` 已包含 lint、typecheck、pytest、前端测试、Rust 检查、文档检查与平台隔离检查。
- 验收在 macOS arm64 主线运行；Windows 只复用报告 schema，由 W-05 执行。
- `--full` 还要求：macOS arm64 上 JEVDB 扩展可加载，`JEV_API_KEY`、`SENTINEL_SEC_CONTACT` 存在，且使用 `--confirm-live-model-cost` 确认真实模型费用。缺配置时 M-8=`fail`；未确认费用时为 `not_run`，整体不得通过。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/acceptance.py` | 新建 | 编排检查、隔离数据目录、生成报告与退出码 |
| `scripts/acceptance_live.py` | 新建 | 真实 SEC 快照、内存密钥组合根、实际 SQL/统计审计与持久化证据校验 |
| `scripts/tests/test_acceptance*.py` | 新建 | 验收环境、Python 启动、报告路径和 M-8 的显式合成回归 |
| `apps/desktop/e2e/acceptance/playwright.config.ts` | 新建 | 串行验收场景，禁用重试 |
| `apps/desktop/e2e/real-core/fixture.ts` | 修改 | 复用 I-01 核心桥；可选 `memorySecrets` 只供验收使用 |
| `apps/desktop/e2e/acceptance/memory_core.py` | 新建 | 验收专用核心入口，注入 `MemorySecretStore`，不读写系统钥匙串 |
| `apps/desktop/e2e/acceptance/acceptance.spec.ts` | 新建 | 6 个用例：M-1 清除/重载、M-2 离线/键盘/重启/演示时长、M-3 真实 RPC |
| `apps/desktop/e2e/acceptance/demo-script.ts` | 新建 | 5 分钟章节、选择器与预期文本 |
| `apps/desktop/e2e/acceptance/manual-checklist.md` | 新建 | 键盘、断网、取消/重启、密钥、窄屏、演示清除六项人工证据；另附录屏 |
| `apps/desktop/e2e/acceptance/m8.config.ts` / `m8.spec.ts` | 新建 | 显式运行的真实模型扫描、真实核心 RPC 与证据抽屉截图 |
| `apps/desktop/e2e/acceptance/report.schema.json` | 新建 | `acceptance.json` 字段约束 |

M-3 的假密钥只存在于验收子进程内存；`memory_core.py` 仅用于验收，生产入口仍使用系统钥匙串。验收数据目录必须是独立临时目录，不得指向默认应用数据。

## 5. 接口规格

### 5.1 公开接口
```python
class AcceptanceRunner:
    def __init__(self, root: Path, work_dir: Path, mode: Literal["offline", "full"]) -> None: ...
    def preflight(self) -> list[CheckResult]: ...
    def run(self) -> AcceptanceReport: ...

def write_report(report: AcceptanceReport, out_dir: Path) -> Path: ...

def main(argv: Sequence[str] | None = None) -> int: ...
```
CLI：`scripts/acceptance.py [--offline|--full] [--report-dir PATH] [--skip-e2e] [--skip-gate] [--json] [--self-test] [--confirm-live-model-cost] [--m8-symbol SYMBOL] [--m8-accession ACCESSION] [--m8-statement TEXT] [--m8-token-budget N]`。默认 `--offline`，只做开发回归；M-8 固定为 `not_run`，因此整体 `overall=fail`。最终提交必须无 `--skip-e2e` 运行 `--full --confirm-live-model-cost`，且 M-1～M-8 全 pass。

### 5.2 报告字段
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `schemaVersion` | str | 是 | 固定 `"1"` | 报告 schema |
| `platform` | str | 是 | `macos/windows` | 平台 |
| `mode` | str | 是 | `offline/full` | 验收模式 |
| `startedAt/finishedAt` | str | 是 | UTC、以 `Z` 结尾 | 起止时间 |
| `checks[]` | object | 是 | 至少 M-1～M-8 | 单项结果 |
| `checks[].id` | str | 是 | `M-1`…`M-8` | 对应产品标准 |
| `checks[].status` | str | 是 | `pass/fail/not_run` | 只有 pass 可交付 |
| `checks[].evidence[]` | list[str] | 是 | 相对报告目录的路径 | 可点击复核 |
| `overall` | str | 是 | `pass/fail` | 所有必须项均为 pass |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `ACCEPTANCE_VIEWPORT` | `1440×900` | Playwright config | 主视口 |
| `MIN_VIEWPORT` | `1024×700` | Playwright config | 无横向滚动 |
| `DEMO_MINUTES` | `5` | `demo-script.ts` | 演示上限 |
| `SECRET_SENTINEL` | `test-key-do-not-use` | acceptance.py | 扫描泄漏的假密钥 |
| `MAX_ACCEPTANCE_SECONDS` | `900` | acceptance.py | 总超时 15 分钟 |

## 6. 实现步骤

1. 创建唯一且保留的临时工作目录；显式 `--work-dir` 必须为空。仅演示数据和离线浏览器子进程设置 `SENTINEL_OFFLINE=1`、`SENTINEL_CLOCK=2026-11-02T08:35:00Z`。
2. 运行 `scripts/check.py` 时清除继承的离线开关、固定时钟和真实模型凭据，防止禁掉 MockTransport 单测或触发真实模型；失败则 M-7 fail，保留完整 stdout/stderr。
3. 运行 `scripts/load_demo.py --json` 载入，再 `--clear` 清除，最后重载；三次均校验计数 `6/5/6/6/12/1560`，并断言清除确实删除行，保存 JSON 为 M-1 证据。
4. 运行本目录 Playwright（真实核心 headless）；保存 `results.json`、日志和证据。结构化结果缺失时 M-2 即使退出码为 0 也 fail。
5. 在 `SENTINEL_OFFLINE=1` 下打开六个页面；断言已有数据仍可见、扫描按钮禁用并提示“当前离线，无法开始扫描。”，归入 M-2。
6. 用假密钥走真实 UI/RPC：保存、连接测试、扫描、清除；扫描 UI、日志、DuckDB 文本列、`settings.get`、`app.bootstrap` 与 `settings.testConnection`，泄漏一处即 M-3 fail。验收核心必须走 `memory_core.py` 的进程内存存储，不得读写系统钥匙串。
7. 查询 `decision`，断言 12 行的 `engine/model_id/question_set_version/evidence_kind` 非空且值在白名单；归入 M-4。
8. 运行 `scripts/eval.py --replay … --split test`；把 `report.md`、`report.json`、`predictions.jsonl` 归入 M-5。MVP-0 只要求完整报告，不调用 v1 的 `--gate`；评测执行失败或报告缺失时 M-5 fail，但不得删产物。
9. 运行 I-01 的“无证据不展示”测试，人工在数据库插入一条缺少证据的阳性判定并重启，断言不进清单；归入 M-6。
10. **仅 `--full --confirm-live-model-cost`**：从 SEC 获取标的与披露，默认 AAPL 最新 Item 2.02，可用 `--m8-symbol`、`--m8-accession`、`--m8-statement` 固定复核案例。保存原始 submissions 与选中行的 HTTP 快照、哈希和来源；以披露时刻固定时钟，只回放该披露 HTTP。启动生产组合根/真实 RPC（密钥仅在独立子进程内存中），强制 `jevdb` 并真正调用远端模型，预算缺省 50000 tokens（`--m8-token-budget`）。保存扩展 SHA、DuckDB 版本、实际执行 SQL、同连接 `jevdb_stats()`、扫描状态、判定、清单与证据抽屉截图。零请求、零判定、降级、数据库与页面来源不一致、缺图或无可展示的阳性/待确认条目均 fail，不调整分数凑通过。HTTP 回放不能称作现场 SEC 扫描；F18-S04-CR-01 的 criteria 等价问题仍独立未验证。
11. 汇总 `overall`：仅当 M-1～M-8 全部 pass 时为 pass；任何 `not_run` 视为 fail。终端输出一行 `ACCEPTANCE PASS/FAIL <passed>/8`。
12. 复制 `manual-checklist.md` 到报告目录，要求在录屏后逐项完成六项人工验收；自动化结果不自动勾选清单，未完成不得宣称人工验收通过。
13. 生成 `acceptance.json`、`summary.md`、`artifacts/`，不清理失败的临时目录，路径打印在终端。

## 7. 5 分钟演示脚本

| 时间 | 操作与预期界面 | 固定数据 | 失败时降级 |
|---|---|---|---|
| 0:00–0:25 | 启动应用；标题“投资逻辑哨兵” | 无 | 启动超过 15 秒则重启一次，仍失败只展示已知缺陷，不继续 |
| 0:25–1:05 | 今日页：3 条待处理，顺序 ZZAR 推翻 0.93、ZZCL 削弱 0.78、ZZEN 削弱 0.71；“系统拿不准 1 条”折叠 | 4 个数字来自 manifest | 今日页异常则直接打开证据抽屉 URL，说明页面缺陷，不手工造卡 |
| 1:05–1:45 | 打开 ZZAR 证据抽屉；高亮已完成的 4.5% 减持句；显示 JEVDB 回放来源与模型 ID | 披露 0009990001-26-000001；M-8 真实运行记录 | 原文抓取失败则显示已存句子，并明确“演示数据预置”；不得使用未留证据的直连结果 |
| 1:45–2:15 | 点“仍然成立”；条目移出，待处理变 2；展开已处理可重新打开 | 动作记录追加 | 写入失败则展示错误编号，不继续交易步骤 |
| 2:15–2:55 | 持仓页：5 个标的、6 条逻辑；展开 ZZAR 两条逻辑与失效条件 | 数量 5/6 | 编辑器异常则只读展示，不现场修改数据库 |
| 2:55–3:25 | 扫描页：1 条预置扫描历史、6 份披露、预算与引擎信息；说明这是离线演示数据，不是现场扫描 | 6 份披露 | 历史为空则展示 E-01 fixture，不声称刚扫描成功 |
| 3:25–4:05 | 交易页：demo 账户、1 笔待成交、1 笔已成交；点“下一交易日”后状态更新 | 初始现金 100000.0000 | 推进失败则展示拒单原因与投资组合，不伪造成交 |
| 4:05–4:35 | 风险页：3 只持仓、260 个共同交易日；相关矩阵、波动率、回撤、SVD | 至少 60 个交易日 | 样本不足则展示页面真实提示，并跳过数字讲解 |
| 4:35–4:55 | 设置页：演示数据已载入；密钥只显示“已保存”；列出外联域名 | 不显示密钥 | 密钥未配置则演示“去设置”的阻断，不输入真实密钥 |
| 4:55–5:00 | 点“清除演示数据”，确认框出现后取消，保持数据供提问 | `demo.clear` 不执行 | 按钮异常则命令行演示 `--clear`，明确是清理动作 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_full_acceptance_all_pass_exits_zero` | `apps/desktop/e2e/acceptance/acceptance.spec.ts` | 全部 fixture + 真实 JEVDB 探针 | `overall=pass`，8/8 |
| `test_skip_e2e_cannot_report_pass` | 同上 | `--skip-e2e` | `overall=fail`，M-1=`not_run` |
| `test_offline_cannot_pass_final_acceptance` | 同上 | `--offline` | M-8=`not_run`，`overall=fail` |
| `test_full_without_jevdb_marks_m8_fail` | 同上 | JEVDB 扩展不可用 | M-8=`fail`，整体 exit=1 |
| `test_offline_keeps_six_pages_readable` | 同上 | `SENTINEL_OFFLINE=1` | 六页有数据、有离线提示 |
| `test_secret_scan_finds_planted_secret` | `scripts/acceptance.py --self-test` | 日志写入假密钥 | M-3 fail，证据路径存在 |
| `test_missing_evidence_blocks_inbox` | 同上 | 无证据阳性判定 | M-6 pass，清单不计该条 |
| `test_eval_low_f1_still_reports_for_mvp0` | 同上 | F1 `0.79` 且报告完整 | M-5 pass，报告保留；缺报告或执行失败另测为 fail |
| `test_demo_timing_under_five_minutes` | `demo-script.ts` | 按步骤自动计时 | 总时长 ≤ 300 s |
| `test_1024_view_has_no_horizontal_scroll` | `acceptance.spec.ts` | 1024×700 | 六页均无页面级横向滚动 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `apps/desktop/e2e/acceptance/fixtures/planted-secret.log` | 一行含 `test-key-do-not-use` | 手工构造，仅测试 |
| `apps/desktop/e2e/acceptance/fixtures/missing-evidence.sql` | 一条缺证据阳性判定 | 按 04 表结构手写，载入临时库 |
| `apps/desktop/e2e/acceptance/fixtures/eval-fail.json` | 严格 F1 0.79 | 手工构造的 E-02 报告 |

## 9. 验收

### 9.1 命令与期望输出
```bash
uv run --project core python scripts/acceptance.py --full --confirm-live-model-cost --json
# 期望：真实 JEVDB 可用时退出码 0；ACCEPTANCE PASS 8/8
uv run --project core python scripts/acceptance.py --offline --json
# 期望：开发回归可执行，但 M-8=not_run、退出码 1；不得用于最终提交
python3 scripts/acceptance.py --skip-e2e
# 期望：退出码 1；overall=fail；M-2/M-3=not_run，其余按实际执行
python3 scripts/check_docs.py --strict
# 期望：错误 0
```
人工录屏必须覆盖 §7 全表，并保存到 `test-results/acceptance/录屏.mov`；报告只引用路径，不把视频提交进仓库。

### 9.2 完成清单
- [ ] M-1～M-8 每项有状态、证据路径和复核命令
- [ ] 5 分钟脚本实测 ≤ 300 秒，两个视口无横向滚动
- [ ] 密钥泄漏、缺证据、离线、评测失败四种反向测试通过
- [ ] M-8 保存真实 JEVDB 的扩展 SHA、SQL、统计、数据库结果与界面截图；任何直连替代均失败
- [ ] 人工录屏与六项清单全部完成
- [ ] 报告中没有任何真实密钥、持仓或个人信息
- [ ] 已写 `docs/wp/status/I-02.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-05 | `acceptance.json` schema 与 §7 演示表 | Windows 单独生成报告，不覆盖 macOS |
| 课程报告 | `summary.md`、评测报告和证据路径 | 只能引用 pass 项；not_run 必须写成未验证 |
| 协调者 | `overall` 与失败项 | 任一必须项 fail 不得宣布 MVP-0 完成 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 现场网络或密钥失效 | SEC/Jev 超时 | 现场只回放已保存的 M-8 记录；若从未完成 `--full`，不得提交或宣称验收通过 |
| 演示超时 | 5 分钟表走到 4:30 后未完成 | 跳过风险数字讲解，保留今日、证据、交易三段 |
| 验收脚本自身改变数据 | 重复运行计数变化 | 每次新建临时目录；报告记录数据目录，失败不复用 |
