# UI 原型

> 投资逻辑哨兵的可点击原型。**双击 `index.html` 就能打开**，不需要服务器、不需要安装任何东西。
> 规范在 [docs/03-界面设计规范.md](../../docs/03-界面设计规范.md)；本原型是规范的落地，React 页面以它为实现基线（[ADR-010](../../docs/decisions.md)）。
> 示例数据全部虚构（`ZZ*` 公司），页面角落常驻“原型示例数据”水印。

## 怎么看

| 文件 | 内容 |
|---|---|
| `index.html` | 应用外壳 + 7 个页面（今日、持仓、交易、风险、扫描、设置、v1 草图），右下角“原型控制条”切换状态 |
| `gallery.html` | 全部颜色令牌、字体、组件及其状态的陈列页 |

在 `index.html` 里：

- 左侧导航或地址栏切换页面：`#/today` `#/holdings` `#/trading` `#/risk` `#/scan` `#/settings` `#/v1`。
- 右下角控制条：选“页面状态”，选“证据抽屉”（今日页），切换 macOS / Windows 标题栏，切换窗口尺寸（适应 / 1280×820 / 1024×700）。
- 地址栏参数（都写在 `#` 后面）：`state=<状态>`、`drawer=<overturn|weaken|uncertain|title_only|processed|not_found>`、`platform=macos|windows`、`w=`、`h=`、`bare=1`。`bare=1` 隐藏控制条和水印，用于截图。
- 例：`index.html#/today?state=pending&drawer=overturn&bare=1`

可以真的点的：证据抽屉的打开与关闭（`Esc` 也行）、“仍然成立 / 修正逻辑 / 忽略”（卡片会移到“已处理”，可“重新打开”）、“更多”菜单、折叠组、持仓行展开、交易页的选项卡与买卖切换、风险页的窗口与“表格视图”、扫描页点一行看明细。其余按钮只弹出提示“该操作在 React 版本里实现”。

## 状态一览

状态 id 的权威清单与它们组合的契约示例在 [03 第 6 节](../../docs/03-界面设计规范.md)；下表只是速查。

| 页面 | 状态 |
|---|---|
| 今日 | `pending` 有待处理 · `empty` 全部已处理 · `loading` · `scanning` · `scan_failed` · `offline` · `no_holdings` · `unconfigured` · `engine_fallback` |
| 持仓 | `default` · `expanded` · `editor-new` · `editor-error` · `editor-too-long` · `conflict` · `no-theses` · `search` · `search-empty` · `empty` |
| 交易 | `default` · `new_account` · `no_account` · `error-cash` · `error-position` · `no-price` · `advanced` |
| 风险 | `ok` · `ok-table` · `insufficient` · `loading` · `single` · `three-year` |
| 扫描 | `default` · `running` · `detail` · `empty` · `budget` |
| 设置 | `configured` · `unconfigured` · `test-ok` · `test-failed` · `invalid-email` |

## 目录

```text
index.html  gallery.html  README.md
css/
  tokens.css          设计令牌（颜色只在这里定义）
  base.css            重置、排版、焦点环
  layout.css          l-*  外壳布局
  components.css      c-*  组件
  pages.css           p-*  页面专用
  platform-macos.css  platform-windows.css
  proto.css           仅原型：控制条与陈列页（proto-* 类名，React 不复制）
js/                   经典脚本（非 ES module），这样从 file:// 打开不会被浏览器拦截
  icons.js            图标路径数据（权威，React 复制同一份）
  format.js           日期、金额、百分比格式化（时区固定 Asia/Shanghai）
  render-ui.js        组件渲染函数（纯函数：数据进，HTML 字符串出）
  render-pages.js     外壳、今日、证据抽屉、持仓
  render-pages2.js    交易、风险、扫描、设置、v1 草图
  states.js           （页面，状态）→ 契约示例的映射；Proto.build() 是纯函数
  router.js  app.js  proto-controls.js  gallery.js     浏览器入口与交互
data/mock.js          契约示例数据（纯 JSON，由 scripts/gen_proto_mock.py 生成，勿手改）
```

## 与 React 的对应

| 原型 | React（`apps/desktop/src/`） |
|---|---|
| `css/{tokens,base,layout,components,pages}.css`、`platform-*.css` | 原样复制到 `styles/`，**不改类名** |
| `js/icons.js` 的路径 | `components/ui/Icon.tsx`，渲染同一份 `<svg>` |
| `js/render-ui.js` 的每个 `ui.xxx` | `components/ui/Xxx.tsx`，输出相同的 DOM |
| `js/render-pages*.js` 的每个页面 | `pages/<页面>/index.tsx`，输出相同的 DOM |
| `js/format.js` | `lib/format.ts`（时区取用户本机；测试用环境变量 `TZ` 固定） |
| `js/states.js` 的状态表 | 前端 mock 与 Playwright 场景 |
| `css/proto.css`、`js/{app,proto-controls,gallery}.js` | 不复制 |

验收：像素比对（[09 第 7 节](../../docs/09-测试与评测.md)）。

## 约定（`scripts/check_proto.py` 会检查）

1. 十六进制颜色只出现在 `tokens.css`；其他 CSS 只用 `var(--…)`。
2. 类名前缀只能是 `c-` `l-` `p-` `u-` `is-` `has-`（`proto.css` 另可用 `proto-`）。
3. 内联 `style` 只能设置自定义属性，例如 `style="--w:40%"`。
4. 不写 `outline: none`；不写无限循环动画；骨架屏没有闪烁动画。
5. 每个 `<button>`、`<a>`、表单控件有可访问名称；装饰性 `svg` 带 `aria-hidden="true"`。
6. 渲染函数里所有动态文字都经过 `esc()`。
7. 文案不出现禁用词（建议买入、置信度等）。

运行检查：`python3 scripts/check_proto.py`（需要 `node`；加 `--no-render` 只做静态检查）。

## 修改原型时

1. 先改 [03](../../docs/03-界面设计规范.md)（如果规格变了），再改本目录。
2. 新增页面状态：在 `js/states.js` 的 `STATES` 里登记，并保证引用的契约示例存在。
3. 新增契约示例：改 `contracts/`，再运行 `scripts/gen_proto_mock.py` 重新生成 `data/mock.js`。**过渡期**：`contracts/` 和这个脚本要等工作包 C-06 才有；在那之前改 `.kiro/notes/author/examples.py`，然后在该目录运行 `python3 build_mock.py`（见 [docs/wp/HANDOFF.md](../../docs/wp/HANDOFF.md) 第 5 节）。
4. 运行 `python3 scripts/check_proto.py`，用浏览器过一遍 `index.html` 的每个状态。
