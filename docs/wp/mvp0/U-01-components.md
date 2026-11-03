---
id: U-01
title: 组件库
phase: mvp0
platform: shared
lane: ui
deps: [U-00]
size: L
size_approval: cr/N10-01-execution-clarifications.md
owns: [apps/desktop/src/components/ui/]
appends: []
stubs: []
---

# U-01 组件库

## 0. 一眼看懂

- **目标**：实现 [03](../../03-界面设计规范.md) §5 的全部基础组件，DOM 与类名和 `design/prototype/js/render-ui.js` 一致，供六个页面复用。
- **完成后解锁**：U-02～U-08；页面只组合组件，不再写按钮、输入框、标签和抽屉的样式。
- **预计规模**：25 个公开组件及其回归，已按 N10-01 §19 批准 L，约 2600 行实现、复制 CSS、开发陈列与测试；不得删除测试或压缩格式降低计数。

## 1. 背景与边界

### 1.1 为什么需要它
原型已经定义了每个组件的 DOM、尺寸和状态。组件库把这些结构固定下来，页面才能通过像素比对；同时集中处理焦点、`aria-*`、禁用原因和错误文案，避免每个页面各写一遍。

### 1.2 范围内
1. 图标：复制 `design/prototype/js/icons.js` 的 23 个路径，输出相同的 `<svg>`，不引入图标库。
2. 按钮、图标按钮、字段、输入框、文本域、搜索框、单选、分段控件。
3. 判定标签、概率、市场徽标、引擎徽标、状态标签。
4. 卡片、表格、横幅、Toast、骨架、空状态、进度、菜单。
5. 抽屉、模态框、热图、SVD 条形列表。
6. 每个组件覆盖 §5 规定的默认、悬停、聚焦、禁用、加载、错误状态。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 今日页卡片的数据拼装、排序和 RPC | U-02 |
| 业务表单的校验规则（500 字、数量非负） | U-03～U-07 |
| 全局 Toast 队列与错误边界 | U-08 |
| 图表库边界 | MVP-0 不安装 `lightweight-charts`；v1 的 K 线才用它；热图与 SVD 始终自绘 SVG |
| 新颜色、新字号、新间距 | 禁止；只能使用 U-00 的令牌 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §2 令牌、§5 组件规格、§8 可访问性 | 尺寸、DOM、键盘与对比度 |
| [09-测试与评测.md](../../09-测试与评测.md) | §2.1 命名、§7 像素比对 | 测试名与视觉验收 |
| `design/prototype/js/render-ui.js` | 全部 `ui.*` 函数 | DOM 基线，只读参考 |
| `design/prototype/css/components.css` | 全部 `c-*` 规则 | 类名与状态类 |

## 3. 前置条件

- U-00 已交付 `tokens.css`、`base.css`、`layout.css`、`Icon` 插槽和 `app/format.ts`。
- WP-00 已安装 React 19、Vitest、Testing Library、jsdom；本包不得新增依赖。
- `design/prototype` 只读；不得为了让 React 通过而修改原型。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `components/ui/Icon.tsx` | 新建 | 23 个内联 SVG 路径；`size` 16/20；装饰时 `aria-hidden` |
| `components/ui/Button.tsx` | 新建 | 5 种变体；32px 高；加载与禁用 |
| `components/ui/Field.tsx` | 新建 | label、help、count、error、`aria-describedby` |
| `components/ui/Input.tsx` / `Textarea.tsx` / `SearchInput.tsx` | 新建 | 受控输入；搜索带 `role="combobox"` |
| `components/ui/Radio.tsx` / `SegmentedControl.tsx` | 新建 | `radiogroup`/`radio` 键盘语义 |
| `components/ui/VerdictChip.tsx` / `Probability.tsx` | 新建 | 5 类判定 + 两位小数概率 |
| `components/ui/MarketBadge.tsx` / `EngineBadge.tsx` / `StatusTag.tsx` | 新建 | 市场、引擎、状态文本标签 |
| `components/ui/Card.tsx` / `Table.tsx` | 新建 | 卡片容器、表头/行/数值列原语 |
| `components/ui/Banner.tsx` / `Toast.tsx` | 新建 | info/warn/danger；`role` 按严重度 |
| `components/ui/Skeleton.tsx` / `EmptyState.tsx` / `Progress.tsx` | 新建 | 无 shimmer；空状态三要素；进度语义 |
| `components/ui/Menu.tsx` | 新建 | `role="menu"`、方向键、Esc |
| `components/ui/Drawer.tsx` / `Modal.tsx` | 新建 | 焦点陷阱、焦点归还、遮罩 |
| `components/ui/Heatmap.tsx` / `BarList.tsx` | 新建 | SVG 相关系数图、SVD 解释方差条 |
| `components/ui/index.ts` | 新建 | 统一导出；页面不得深路径导入 |
| `components/ui/*.test.tsx` | 新建 | §8.1 的 12 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
type IconName = "sun"|"briefcase"|"arrow-left-right"|"activity"|"radar"|"settings"|"search"|"x"|"chevron-down"|"chevron-right"|"external-link"|"check"|"alert-triangle"|"info"|"refresh-cw"|"play"|"more-horizontal"|"wifi-off"|"clock"|"plus"|"arrow-down"|"minus"|"help-circle";
type ButtonVariant = "primary"|"secondary"|"text"|"danger"|"icon";
type Tone = "ok"|"warn"|"danger"|"none"|"info";
type VerdictKind = "overturn"|"weaken"|"support"|"none"|"uncertain";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant; loading?: boolean; icon?: IconName; disabledReason?: string;
}
interface IconProps { name: IconName; size?: 16|20; label?: string; }
interface FieldProps { id: string; label: string; help?: string; error?: string; count?: {value:number;max:number}; children: React.ReactNode; }
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> { invalid?: boolean; numeric?: boolean; }
interface SegmentedControlProps { name:string; label:string; value:string; items:{value:string;label:string;disabled?:boolean;title?:string}[]; onChange:(v:string)=>void; }
interface VerdictChipProps { kind: VerdictKind; }
interface ProbabilityProps { value: number; }
interface MarketBadgeProps { market: "us"|"cn"|"hk"; }
interface EngineBadgeProps { active: "jevdb"|"jev_direct"|null; modelId: string; state: "ok"|"degraded"|"unconfigured"; }
interface StatusTagProps { tone: Tone; children: React.ReactNode; }
interface BannerProps { tone: "info"|"warn"|"danger"; text: string; action?: React.ReactNode; }
interface ToastProps { tone: "success"|"error"; text: string; onClose: () => void; }
interface EmptyStateProps { title:string; text?:string; action?:React.ReactNode; display?:boolean; }
interface ProgressProps { value:number; max:number; label:string; }
interface CardProps { children: React.ReactNode; } interface TableProps { children: React.ReactNode; label: string; } interface MenuProps { items: {id:string;label:string;icon?:IconName;danger?:boolean;disabled?:boolean}[]; onSelect:(id:string)=>void; onClose:()=>void; triggerRef: React.RefObject<HTMLButtonElement | null>; } type SearchInputProps = InputProps & { expanded?: boolean }; type RadioProps = {name:string;value:string;checked:boolean;label:string;hint?:string;onChange:(v:string)=>void}; type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {invalid?:boolean}; interface SkeletonProps { rows?: number; }
interface DrawerProps { open: boolean; titleId: string; overlay: boolean; onClose: () => void; children: React.ReactNode; }
interface ModalProps { open: boolean; titleId: string; onClose: () => void; children: React.ReactNode; }
interface HeatmapProps { symbols: string[]; matrix: (number|null)[][]; label: string; }
interface BarListProps { items: {label:string;value:number}[]; label: string; }
```
所有组件 forwardRef：交互组件到实际控件，非交互标签/图表到原型根元素，不额外增加 Tab 停靠点；Field/Segmented/Menu/Drawer/Modal 到其根，Table 到 table 本体。Button 默认 type=button；loading 保留文字、加 refresh-cw 与 aria-busy=true；disabledReason 写 title。Drawer 仅 overlay=true 启用焦点陷阱与 aria-modal=true，推开模式不陷阱。Menu 的方向键/Home/End 移动焦点，Esc 调用 onClose 并归还触发焦点。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `VerdictKind` | union | 是 | 5 个值 | 标签文字与图标映射唯一 |
| `HeatmapProps.matrix` | `(number \| null)[][]` | 是 | 方阵；值 −1..1 | `null` 画斜线纹理 |
| `BarListProps.items` | array | 是 | `value` 0..1 | 填充宽度取 `round(value*100)`% |
| `Menu.item` | `{id,label,icon?,danger?,disabled?}` | 是 | id 唯一 | 菜单项 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `BUTTON_H` / `ICON_SIZE` | `32` / `16` | `Button.tsx` | 点击目标 ≥32×32 |
| `CARD_RADIUS` / `CARD_PAD` | `10px` / `20px` | `Card.tsx` | 卡片圆角与内边距 |
| `ROW_H` / `HEAD_H` | `44px` / `36px` | `Table.tsx` | 表格尺寸 |
| `TOAST_MS` | `4000` | `Toast.tsx` | 成功 Toast 自动关闭 |
| `HEAT_CELL` / `HEAT_GAP` | `56` / `2` | `Heatmap.tsx` | 热图几何 |
| `HEAT_MAX_MIX` | `70` | `Heatmap.tsx` | 色块最大混色百分比 |

## 6. 实现步骤

1. 从 `icons.js` 复制每个图标的 `viewBox="0 0 24 24"` 路径；`Icon` 设置 `stroke="currentColor"`、`stroke-width="1.5"`、`fill="none"`；无 `aria-label` 时加 `aria-hidden="true"`。
2. `Button` 输出 `class="c-button c-button--{variant}"`；图标按钮必须有 `aria-label`；加载时图标不旋转；按下用 `transform:translateY(1px)`。
3. Field 用 useId 生成错误与帮助 id，合并子控件已有的 aria-describedby；错误时 aria-invalid=true、错误文本 role=alert。count 保留 number 签名：单一子控件提供 string value/defaultValue 时按 trim 后 Unicode 码点计数，否则用调用方 count.value；不新增 text/max props。
4. `SegmentedControl` 用 `role="radiogroup"`，每项 `role="radio"` 与 `aria-checked`；左右方向键切换并聚焦；禁用项不参与。
5. `VerdictChip` 映射：推翻/`alert-triangle`/`over`，削弱/`arrow-down`/`weak`，支持/`check`/`hold`，无关/`minus`/`none`，待确认/`help-circle`/`unsure`。
6. `Table` 只负责 `<table class="c-table">`、`thead`、`tbody`、`tr`；数值列由页面传 `className="c-table__num"`；行悬停色用 `color-mix`，不得写十六进制。
7. `Drawer` 在 overlay=true 时用 createPortal 挂到 document.body，固定于顶栏与状态栏之间的右侧，宽 400px，遮罩与焦点陷阱启用。overlay=false 时 inline 渲染 c-drawer/dialog 内容到 PageFrame 的 aside 插槽，由 PageFrame 的 l-drawer 承担第三列；不得再造一层 l-drawer 或 body portal，避免重复占位。打开时记录原焦点并聚焦标题；关闭时恢复；只在覆盖模式 Tab 首尾循环。
8. `Modal` 最大宽 480px，只用于破坏性确认；打开时焦点落到第一个输入或取消按钮；`Esc` 与遮罩点击都调用 `onClose`。
9. `Heatmap` 计算 `k = Math.round(Math.abs(rho) * 70)`，正值混 `--heat-pos`，负值混 `--heat-neg`；对角线 `--surface-2`；每格加 `title="{a} 与 {b}：{rho.toFixed(2)}"`。
10. `BarList` 只允许 `style={{"--w": `${Math.round(value*100)}%`}}`；颜色固定 `--ink-2`；无动画。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案 |
|---|---|---|---|
| 图标按钮缺少 `aria-label` | 开发模式抛 `Error`，测试失败 | — | 不适用 |
| `Toast` 超过 3 条 | 由 U-08 丢弃最旧一条 | — | 不适用 |
| `Drawer` 无 `titleId` | 开发模式抛 `Error` | — | 不适用 |
| `Heatmap` 矩阵不是方阵 | 渲染空状态，不抛到页面 | — | `common.chartInvalid`：“图表数据不完整。” |
| `BarList` 值为 NaN | 该行显示 `0%` 并记录开发警告 | — | 不适用 |
| 禁用按钮被点击 | 不触发 `onClick`，保留 `title` 原因 | — | 由页面提供 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `button_loading_sets_aria_busy` | `Button.test.tsx` | `loading` | `aria-busy="true"`，文字“立即扫描”仍在 |
| `field_error_links_aria_describedby` | `Field.test.tsx` | `error="逻辑内容不能为空"` | 输入 `aria-invalid=true`，错误 id 在 `aria-describedby` 中 |
| `field_count_trims_whitespace` | 同上 | 值 `"   "`，max 500 | 显示 `0 / 500` |
| `verdict_chip_has_text_and_icon` | `VerdictChip.test.tsx` | `kind="overturn"` | 文本“推翻”，`svg` 存在且 `aria-hidden` |
| `probability_formats_two_decimals` | `Probability.test.tsx` | `0.9` | 文本 `0.90` |
| `segmented_arrow_moves_selection` | `SegmentedControl.test.tsx` | 焦点在第一项按 `ArrowRight` | 第二项 `aria-checked=true` |
| `drawer_overlay_traps_focus_and_restores` | `Drawer.test.tsx` | 打开后按 Tab 循环，Esc 关闭 | 焦点回到触发按钮 |
| `drawer_push_does_not_trap` | 同上 | `overlay=false` | `aria-modal=false`，Tab 可离开 |
| `menu_escape_closes_and_restores_focus` | `Menu.test.tsx` | 打开后按 Esc | `onClose` 调用，触发按钮聚焦 |
| `heatmap_uses_max_70_percent_mix` | `Heatmap.test.tsx` | `rho=1` | 单元格样式含 `70%` |
| `modal_escape_and_overlay_close` | `Modal.test.tsx` | 打开后按 Esc 或点遮罩 | 每次调用 onClose；关闭后焦点回到触发元素 |
| `bar_list_nonfinite_value_is_safe` | `BarList.test.tsx` | value 为 NaN | 该行显示 `0%`，没有 NaN 样式或未捕获异常 |

### 8.2 Fixture
无新增 fixture；所有数据在测试内构造，图标快照以 `icons.js` 为准。

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/components/ui
# 期望：12 passed，0 failed
cd apps/desktop && pnpm eslint src/components/ui && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] §4 的组件全部导出，页面无需深路径导入
- [ ] 所有颜色来自令牌；没有内联十六进制色
- [ ] 1280×820 与 1024×700 的组件陈列截图已写入状态文件
- [ ] 键盘可完成每个交互；`prefers-reduced-motion` 下无动画
- [ ] 未新增依赖；未修改 `design/`；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-02 / U-03 | `Card`、`VerdictChip`、`Probability`、`Drawer`、`Banner`、`Table`、`Field`、`SearchInput`、`Menu` | 证据抽屉用 `Drawer overlay={width<1200}`；行展开用 `aria-expanded` |
| U-05/U-06/U-08 | `SegmentedControl`、`BarList`、`Heatmap`、`Toast`、`Banner`、`Skeleton` | 图表有表格替代；队列与挂载由 U-08 负责 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 原型 DOM 与 React 有微小差异 | 像素比对 >1% | 以原型为准改 React，不改原型 |
