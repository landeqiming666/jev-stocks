---
id: U-06
title: 风险页
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: M
owns: [apps/desktop/src/pages/risk/]
appends: []
stubs: []
---

# U-06 风险页

## 0. 一眼看懂

- **目标**：回答“我的组合是不是押注在同一个风险上”：年化波动率、最大回撤、有效持仓数、相关系数热图、SVD 解释方差。
- **完成后解锁**：I-01 可以演示“只看个股不够，组合风险不同”的完整叙事。
- **预计规模**：约 10 个文件、代码加测试 640 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
用户容易把“持有 5 只股票”误当成“分散”。风险页用共同交易日、相关矩阵和主成分告诉用户：组合的风险可能集中在一个因子上。这是矩阵分析课程内容在产品里的落点。

### 1.2 范围内
1. 窗口切换 `6M | 1Y | 3Y`，美元口径固定，人民币禁用并标 v1。
2. 四个指标卡与说明。
3. 相关系数热图（SVG）与表格视图切换。
4. SVD 前 5 个主成分解释方差条、第一主成分载荷前 5。
5. 加载、样本不足、只有 1 只、3Y 数据不足。
6. 图表无障碍与键盘切换。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 协方差、收缩、SVD 计算 | P-06 |
| 人民币汇率换算 | v1 |
| 组合优化与再平衡建议 | 永远不做（不给投资建议） |
| K 线、回测曲线 | v1 |
| 新的图表库 | 本页用自绘 SVG；不安装 ECharts/D3 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.6 风险、§5.9 热图、§5.10 条形、§8 无障碍 | 布局、颜色与替代视图 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `RiskResult`、§5.8 风险 | 字段与错误 |
| [08-模拟交易与风险.md](../../08-模拟交易与风险.md) | §8 风险公式、§9 样本不足 | 指标定义与边界 |

## 3. 前置条件

- U-02 已交付 `PageFrame`、`app/format.ts` 和错误 Toast 事件。
- U-01 已交付 `SegmentedControl`、`Heatmap`、`BarList`、`Table`、`EmptyState`、`Skeleton`。
- C-05 的 mock 支持 `risk.compute/ok`、`insufficient`、`single`、`three_year`。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/risk/index.tsx` | 新建 | 页面入口、窗口切换、加载与错误 |
| `pages/risk/RiskControls.tsx` | 新建 | 6M/1Y/3Y、币种、表格视图开关 |
| `pages/risk/MetricCards.tsx` | 新建 | 四个指标卡与副行说明 |
| `pages/risk/CorrelationHeatmap.tsx` | 新建 | 自绘 SVG、图例、`title`、表格切换 |
| `pages/risk/SvdPanel.tsx` | 新建 | 解释方差条与第一主成分载荷 |
| `pages/risk/RiskTable.tsx` | 新建 | 热图的表格替代 |
| `pages/risk/useRisk.ts` | 新建 | `risk.compute` 与请求取消 |
| `pages/risk/format.ts` | 新建 | 百分比、两位小数、有效持仓数 |
| `pages/risk/*.test.tsx` | 新建 | §8.1 的 11 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
function RiskPage(): JSX.Element;
function RiskControls(props: {
  window: "6M"|"1Y"|"3Y"; table: boolean;
  onWindow: (w:"6M"|"1Y"|"3Y") => void;
  onTable: (v:boolean) => void;
}): JSX.Element;
function MetricCards(props: { result: RiskResult }): JSX.Element;
function CorrelationHeatmap(props: {
  result: RiskResult; table: boolean;
}): JSX.Element;
function SvdPanel(props: { result: RiskResult }): JSX.Element;
function useRisk(client: RpcClient): {
  result: RiskResult | null; loading: boolean; error: RpcError | null;
  window: "6M"|"1Y"|"3Y"; setWindow: (w:"6M"|"1Y"|"3Y") => void;
  refresh: () => Promise<void>;
};
```
- `setWindow` 立即把控件切到新值并请求；请求未返回前保留旧图但加 `is-loading`，不得显示空图。
- 同一时间只保留最后一个请求结果；旧响应通过 `AbortController` 或递增序号丢弃。
- `table=true` 时用 `<table>` 替换 SVG，但指标卡与 SVD 保持。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `RiskResult.window.observations` | number | 是 | ≥0 | 共同交易日 |
| `RiskResult.annualizedVol` | number | 是 | ≥0 | 0.187 显示 18.7% |
| `RiskResult.maxDrawdown` | number | 是 | ≥0 | 显示 21.4% |
| `RiskResult.effectiveHoldings` | number | 是 | ≥1 | 1/Σw²，显示两位 |
| `RiskResult.correlation.matrix` | `(number\|null)[][]` | 是 | 方阵 | 对角为 1 |
| `RiskResult.svd.explained` | number[] | 是 | 降序，≤5 项 | 解释方差比例 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `WINDOWS` | `6M,1Y,3Y` | `RiskControls.tsx` | 窗口顺序 |
| `MIN_OBS` | `60` | `useRisk.ts` | 样本不足阈值（以后端为准） |
| `CELL` / `GAP` | `56` / `2` | `CorrelationHeatmap.tsx` | 热图几何 |
| `MAX_MIX` | `70` | 同上 | 颜色最大强度 |
| `TOP_LOADINGS` | `5` | `SvdPanel.tsx` | 载荷展示条数 |
| `TOP_WEIGHTS` | `3` | `MetricCards.tsx` | 前三大权重副行 |

## 6. 实现步骤

1. 挂载时请求 `risk.compute({scope:"holdings",window:"1Y",currency:"USD"})`；加载中显示 4 个指标卡骨架和 5×5 热图骨架。
2. 控制条：`6M|1Y|3Y` 用 `SegmentedControl`（方向键切换）；`美元` 选中，`人民币` 禁用且 `title="v1 支持人民币口径"`；右侧 `表格视图` 开关绑定 `aria-pressed`，`Space`/`Enter` 切换。
3. 指标卡：年化波动率 `18.7%`、最大回撤 `21.4%`（副行“按当前权重回看”）、有效持仓数 `4.67`、前三大权重占比 `69.3%`（副行列出三只代码与权重）。
4. 热图 SVG：整体 `viewBox` 宽 = 左侧标签宽 64 + n×(56+2)，高 = 顶部标签高 24 + n×(56+2)。单元格颜色按 `k=round(abs(rho)*70)` 与 `--heat-pos`/`--heat-neg` 混 `--heat-zero`；对角线 `--surface-2`；`null` 用 `<pattern>` 斜线。
5. 每个单元格显示两位小数，文字固定 `--ink`；`<title>` 写“ZZAR 与 ZZCL：0.58”。行列标签 11px 等宽；图例为 `−1 … 0 … +1`。
6. `table=true` 时渲染 `RiskTable`：首列标的，其余列为两位小数；`null` 显示“—”；表格外层 `overflow-x:auto`，页面不得横向溢出。
7. SVD：前 5 个主成分每行“第 N 主成分”、条形、`46.0%`；条宽用 `--w`，颜色 `--ink-2`。第一主成分载荷前 5 个标的按绝对值降序，显示两位小数。
8. 底部固定信息：`观测 251 个共同交易日 · 2025-10-30 至 2026-10-30 · 价格已复权`；`excluded` 显示“未计入：ZZMD（只关注）”。
9. `insufficient`：指标与图表替换为空状态“样本不足：共同交易日 42 天，至少需要 60 天。”+“请先刷新行情，或换更长的窗口”；不显示 0 值。
10. `single`：指标卡正常显示；热图区写“至少需要 2 只持仓才能显示相关性”；SVD 区写“主成分分析至少需要 2 只标的”。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 样本不足 | 不出数字，显示原因 | `DATA_INSUFFICIENT` | `risk.insufficient` |
| 只有 1 只持仓 | 指标可用，图表区说明 | — | `risk.single` |
| 3Y 数据不足 | 保留已返回窗口，说明实际范围 | `DATA_INSUFFICIENT` | `risk.threeYearShort` |
| 请求失败 | 保留旧图并标记“数据未更新” | `SOURCE_UNAVAILABLE`/`INTERNAL` | `risk.loadFailed` |
| 矩阵含 `null` | 表格显示“—”，热图画斜线 | — | 不适用 |
| 窗口切换过快 | 只显示最后一次结果 | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `risk_renders_four_metrics` | `RiskPage.test.tsx` | `risk.compute/ok` | 四个标题；值含 `18.7%`、`21.4%`、`4.67`、`69.3%` |
| `risk_heatmap_has_aria_label` | `CorrelationHeatmap.test.tsx` | 5 只标的 | `role=img`，`aria-label` 含“5 只标的” |
| `risk_heatmap_cell_title_has_pair` | 同上 | `(0,1)=0.21` | `title` 文本“ZZAR 与 ZZCL：0.21” |
| `risk_heatmap_uses_70_percent_max` | 同上 | `rho=1` | 非对角单元格样式含 `70%` |
| `risk_null_cell_renders_dash_in_table` | `RiskTable.test.tsx` | `matrix[0][2]=null` | 表格文本“—” |
| `risk_table_toggle_replaces_svg` | `RiskPage.test.tsx` | 点击“表格视图” | SVG 不存在，`table` 存在 |
| `risk_insufficient_hides_metrics` | 同上 | `risk.compute/insufficient` | 文本“至少需要 60 天”，无 `18.7%` |
| `risk_single_shows_two_asset_message` | 同上 | `risk.compute/single` | 文本含“至少需要 2 只持仓” |
| `risk_window_change_requests_new_window` | 同上 | 点“6M” | `risk.compute` 参数 `window="6M"` |
| `risk_svd_renders_five_bars` | `SvdPanel.test.tsx` | 5 个 `explained` | 5 行，首行含 `46.0%` |
| `risk_ignores_stale_response` | `useRisk.test.ts` | 先 6M 后 1Y，6M 后返回 | 最终显示 1Y 的 `observations` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/risk/__fixtures__/ok.json` | `risk.compute/ok` | 从契约复制 |
| `pages/risk/__fixtures__/insufficient.json` | `risk.compute/insufficient` | 从契约复制 |
| `pages/risk/__fixtures__/single.json` | `risk.compute/single` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/risk
# 期望：11 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 `ok`、`ok-table`、`insufficient`
- [ ] 热图在窄窗口内部滚动，标签不被裁切
- [ ] 图表有 `role=img` 与表格替代；颜色不是唯一信息
- [ ] 所有数字等宽、固定小数位；切换窗口不跳动
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-01 | 风险页与真实 `risk.compute` | 前端不重算矩阵；数值原样格式化 |
| E-02 | 评测截图 | 使用 `risk.compute/ok` 示例，不手改数字 |
| 课程报告 | 指标定义 | 引用 [08](../../08-模拟交易与风险.md) §8，不另写公式 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| SVG 在窄窗口溢出 | 出现页面横向滚动 | 外层 `overflow-x:auto`，只让图表内部滚动 |
| 颜色混色对比度不足 | 数字看不清 | 强度上限 70%，文字固定 `--ink` |
| 后端窗口不足仍返回旧数据 | 图表与标题不一致 | 以 `window.from/to/observations` 为准显示实际范围 |
