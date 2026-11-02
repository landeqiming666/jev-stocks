---
id: U-07
title: 设置页
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: M
owns: [apps/desktop/src/pages/settings/]
appends: []
stubs: []
---

# U-07 设置页

## 0. 一眼看懂

- **目标**：让用户安全地配置 Jev 密钥、SEC 联系邮箱、引擎、预算与外联域名，并能判断“哪一项真的通了”。
- **完成后解锁**：US-05 的“去设置”路径可完整走通；I-01 可验证密钥从不回显。
- **预计规模**：约 11 个文件、代码加测试 660 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
密钥和邮箱是扫描的前置条件；引擎与预算决定成本和可解释性。设置页必须做到：密钥只写不读、连接测试逐项可见、隐私边界可核对、演示数据可清除。

### 1.2 范围内
1. 密钥与联系方式：保存、替换、清除、状态徽标。
2. 语义引擎：自动/JEVDB/Jev 直连、当前引擎、模型 ID、三项连接测试。
3. 预算：每日 token 上限、估算费用、首次回看天数。
4. 隐私与外联：只读域名表与固定声明。
5. 演示数据：载入/清除与状态。
6. 关于：版本、构建时间、协议版本、许可证入口、免责声明。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 钥匙串读写与密钥校验 | C-04 |
| JEVDB 构建与引擎选择逻辑 | G0-JEVDB、S-02 |
| 演示数据生成 | E-01 |
| 账户、导出、诊断包 | v1 |
| 多语言切换 | MVP-0 固定 `zh-CN` |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.8 设置、§5.1–§5.5、§7 文案 | 分组与状态 |
| [05-接口契约.md](../../05-接口契约.md) | §5.2 设置与密钥、§5.9 演示数据 | RPC 与错误 |
| [02-技术架构.md](../../02-技术架构.md) | §1 外联域名、§13 安全边界 | 隐私表内容 |
| [01-产品需求.md](../../01-产品需求.md) | §7 US-05、§8 验收 | 用户故事 |

## 3. 前置条件

- U-02 已交付 `PageFrame`、`Banner` 用法与 Toast 事件。
- U-01 已交付 `Field`、`Radio`、`Button`、`Modal`、`Table`、`Banner`、`StatusTag`。
- C-05 的 mock 支持 `settings.*`、`secrets.*`、`demo.*` 示例；密钥值只存在于测试注入，不写入 fixture。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/settings/index.tsx` | 新建 | 页面入口、分区顺序、保存反馈 |
| `pages/settings/SecretsSection.tsx` | 新建 | Jev 密钥与 SEC 邮箱；不回显明文 |
| `pages/settings/EngineSection.tsx` | 新建 | 引擎单选、当前引擎、模型 ID、测试连接 |
| `pages/settings/BudgetSection.tsx` | 新建 | token 上限、估算费用、回看天数 |
| `pages/settings/PrivacySection.tsx` | 新建 | 只读外联域名表与隐私声明 |
| `pages/settings/DemoSection.tsx` | 新建 | 载入/清除演示数据与确认 |
| `pages/settings/AboutSection.tsx` | 新建 | 版本、构建、协议、许可证、免责声明 |
| `pages/settings/useSettings.ts` | 新建 | 读取、更新、密钥状态、测试连接 |
| `pages/settings/validation.ts` | 新建 | 邮箱、预算、回看天数、密钥格式 |
| `pages/settings/*.test.tsx` | 新建 | §8.1 的 10 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
type SettingsPatch = Partial<Pick<Settings,"engine"|"secContactEmail"|"dailyTokenBudget"|"firstScanLookbackDays">>;
type ConnectionResult = { ok:boolean; engine:Engine; modelId:string; checks:{name:string;ok:boolean;latencyMs:number;message:string}[] };
function SettingsPage(): JSX.Element;
function SecretsSection(props: {
  status: {jevKey:boolean}; configured: {secEmail:boolean}; email: string | null;
  onSaveKey: (value:string) => Promise<void>;
  onClearKey: () => Promise<void>;
  onSaveEmail: (value:string) => Promise<void>;
}): JSX.Element;
function EngineSection(props: {
  settings: Settings; active: Engine | null; onUpdate: (patch: SettingsPatch) => Promise<void>;
  onTest: () => Promise<ConnectionResult>;
}): JSX.Element;
function validateEmail(value: string): boolean;
function validateBudget(value: string): {ok:boolean; value?:number; error?:string};
function validateLookback(value: string): {ok:boolean; value?:number; error?:string};
function useSettings(client: RpcClient): {
  settings: Settings | null; secretStatus: {jevKey:boolean} | null;
  loading: boolean; error: RpcError | null; refresh: () => Promise<void>;
  update: (patch: SettingsPatch) => Promise<void>;
  testConnection: () => Promise<ConnectionResult>;
};
```
- `onSaveKey` 成功后清空本地输入并把状态切为“已保存”；任何时刻 DOM 中不得出现密钥明文。
- `validateEmail` 只做基础格式校验：一个 `@`、域名含 `.`、总长 ≤254、无空白。
- `validateBudget` 允许 1000..10,000,000 的整数；`validateLookback` 允许 1..30 的整数。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Settings.engine` | enum | 是 | `auto`/`jevdb`/`jev_direct` | 引擎选择 |
| `Settings.modelId` | string | 是 | 只读 | 固定版本号 |
| `Settings.dailyTokenBudget` | number | 是 | 1000..10,000,000 | 每日上限 |
| `Settings.firstScanLookbackDays` | number | 是 | 1..30 | 首次回看 |
| `Settings.allowedDomains` | array | 是 | 只读 5 项 | 外联清单 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `BUDGET_MIN` / `BUDGET_MAX` | `1000` / `10000000` | `validation.ts` | token 上下限 |
| `LOOKBACK_MIN` / `LOOKBACK_MAX` | `1` / `30` | 同上 | 回看天数 |
| `KEY_MAX` | `512` | `SecretsSection.tsx` | 密钥长度上限 |
| `EMAIL_MAX` | `254` | `validation.ts` | 邮箱长度 |
| `CHECK_ORDER` | `Jev,SEC,JEVDB` | `EngineSection.tsx` | 测试结果顺序 |

## 6. 实现步骤

1. 挂载时并行调用 `settings.get` 与 `secrets.status`；加载中显示 6 个分区骨架。失败时显示全页错误与“重试”，不清空已有表单。
2. 分区顺序固定：密钥与联系方式、语义引擎、预算、隐私与外联、演示数据、关于。每个分区是独立卡片，标题 18px，说明 12px。
3. 密钥：未保存时显示 `type="password"` 输入与“保存”；已保存时只显示“已保存”徽标和“替换”“清除”。替换时显示新输入，保存后立即清空输入；清除需 `Modal` 确认“清除后扫描无法开始”，`Esc` 关闭并把焦点还给“清除”。
4. 邮箱：显示已保存值（邮箱不是密钥，可回显），保存前校验格式；非法时红边 + “联系邮箱格式不正确”，不发 `settings.update`。说明小字固定“SEC 要求访问时声明联系方式。邮箱只会出现在发给 SEC 的请求头里。”
5. 引擎：三项单选：`自动（推荐）`、`JEVDB`、`Jev 直连`，方向键在选项间移动并即时保存；显示当前实际引擎徽标和只读模型 ID。选择 `jevdb` 但扩展不可用时，保存成功但显示 warn“JEVDB 不可用，将阻止扫描”，不静默降到直连。
6. `测试连接` 调 `settings.testConnection`；结果固定三行 `Jev`、`SEC`、`JEVDB`，每行 ✓/✗、延迟 ms、说明。失败项用 danger 文案；`JEVDB` 失败不影响整体 `ok`，但必须显示“已使用 Jev 直连（同一模型）”。
7. 预算：数字输入 + 估算费用 `≈ $0.084`，界面公式为 `round(dailyTokenBudget / 2,000,000 * 0.084, 2)`，仅表示量级、不参与计费；回看天数 1–30，失焦时校验。
8. 隐私表：只读 5 行域名、用途、发送内容；底部固定声明“持仓数量、成本、备注永远不会离开本机。”不得提供编辑。
9. 演示数据：显示“已载入/未载入”；载入调用 `demo.load`，已载入时 `CONFLICT` 提示“演示数据已载入”；清除需 `Modal` 确认，成功后状态变为未载入。
10. 关于：版本、构建时间、协议版本、许可证入口（外链 `https://github.com/...` 由 Rust 打开）、固定声明“仅记录与提醒，不构成投资建议。”

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 密钥为空/含空白/超 512 | 不提交，字段错误 | `INVALID_ARGUMENT` | `settings.invalidKey` |
| 密钥 401 | 保存成功但测试失败，提示替换 | `UNAUTHENTICATED` | `settings.keyInvalid` |
| 邮箱格式错误 | 字段错误，不提交 | `INVALID_ARGUMENT` | `settings.invalidEmail` |
| 预算越界 | 字段错误 | `INVALID_ARGUMENT` | `settings.budgetRange` |
| 回看天数越界 | 字段错误 | `INVALID_ARGUMENT` | `settings.lookbackRange` |
| JEVDB 不可用 | 保存选择但警告 | `ENGINE_UNAVAILABLE` | `settings.jevdbUnavailable` |
| 演示数据已载入 | 阻止重复载入 | `CONFLICT` | `settings.demoLoaded` |
| 清除演示数据失败 | 状态不变 + Toast | `INTERNAL` | `settings.demoClearFailed` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `settings_configured_hides_key_value` | `SettingsPage.test.tsx` | `secrets.status/configured` | DOM 不含假密钥 `test-key-do-not-use`；显示“已保存” |
| `settings_save_key_clears_input` | `SecretsSection.test.tsx` | 输入假密钥并保存 | 保存后 input 值为空，状态“已保存” |
| `settings_clear_key_requires_confirm` | 同上 | 点清除 | 确认前不调用 `secrets.clear` |
| `settings_invalid_email_blocks_update` | `SettingsPage.test.tsx` | `abc` | 错误“联系邮箱格式不正确”，不发 `settings.update` |
| `settings_budget_rejects_999` | `validation.test.ts` | `"999"` | `ok=false`，错误含 `1000` |
| `settings_lookback_rejects_31` | 同上 | `"31"` | `ok=false`，错误含 `30` |
| `settings_test_connection_renders_three_rows` | `EngineSection.test.tsx` | `settings.testConnection/ok` | 3 行，顺序 Jev/SEC/JEVDB |
| `settings_jevdb_failure_keeps_overall_ok` | 同上 | JEVDB ✗，Jev/SEC ✓ | 整体“可用”，说明含“已使用 Jev 直连” |
| `settings_privacy_table_is_read_only` | `SettingsPage.test.tsx` | 默认 | 5 行域名；没有 input/button 编辑 |
| `settings_demo_conflict_shows_message` | `DemoSection.test.tsx` | `demo.load` 抛 `CONFLICT` | 文本“演示数据已载入” |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/settings/__fixtures__/{settings,settings-unconfigured}.json` | `settings.get/configured` 与 `unconfigured` | 从契约复制 |
| `pages/settings/__fixtures__/connection-ok.json` | `settings.testConnection/ok` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/settings
# 期望：10 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 `configured`、`unconfigured`、`test-ok`
- [ ] 密钥明文不出现在 DOM、快照或状态文件
- [ ] 邮箱、预算、回看天数的错误都在字段下
- [ ] 键盘可完成保存、清除确认、引擎切换、测试连接
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-02 | `configured` 状态与“去设置” | 设置成功后外壳横幅消失 |
| I-01 | 三项连接测试 | 每项独立失败，不合并成一个布尔 |
| E-01 | 演示数据状态 | 载入/清除后刷新设置页 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 密钥进入 React DevTools | 输入值被保留 | 保存后立即 `setValue("")`；不在全局 store 存明文 |
| 测试连接把密钥写日志 | 日志出现 `sk-` | 后端负责脱敏；前端不打印请求 |
