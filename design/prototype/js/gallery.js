/* 陈列页：令牌与全部组件及其状态。只在 gallery.html 使用。 */
(function (P) {
  'use strict';
  var ui = P.ui, esc = P.esc, root;

  var SWATCHES = [
    ['基底', ['--paper', '--surface', '--surface-2', '--ink', '--ink-2', '--muted', '--line', '--line-strong']],
    ['强调', ['--accent', '--accent-text', '--accent-soft']],
    ['判定', ['--verdict-over', '--verdict-over-bg', '--verdict-weak', '--verdict-weak-bg', '--verdict-hold', '--verdict-hold-bg', '--verdict-none', '--verdict-none-bg', '--verdict-unsure', '--verdict-unsure-bg']],
    ['状态', ['--ok', '--warn', '--warn-bg', '--danger', '--danger-bg', '--info', '--info-bg', '--up', '--down']]
  ];
  function section(title, html) { return '<section><h2 class="u-h2">' + esc(title) + '</h2>' + html + '</section>'; }
  function demo(html) { return '<div class="proto-demo">' + html + '</div>'; }

  function build() {
    var s = '<div class="proto-gallery"><h1 class="u-h1">组件陈列</h1><p class="u-text-2 u-mb-3">令牌与组件的全部状态。与 docs/03-界面设计规范.md 对照。示例数据全部虚构。</p>';
    s += section('颜色令牌', SWATCHES.map(function (g) {
      return '<h3 class="u-small u-muted u-mt-3 u-mb-1">' + g[0] + '</h3><div class="proto-swatches">' + g[1].map(function (t) {
        return '<div class="proto-swatch"><div class="proto-swatch__chip" style="--sw:var(' + t + ')"></div><div class="proto-swatch__meta"><code>' + t + '</code></div></div>';
      }).join('') + '</div>';
    }).join(''));
    s += section('字体', demo('<div><div class="u-display">今天没有需要处理的变化</div><div class="u-h1">页面标题 24/32</div><div class="u-h2">区块标题 18/26</div><p>正文 14/22：系统按字面理解你写的内容。</p><p class="u-small u-muted">辅助信息 12/18</p><p class="u-num-l">18.7%</p><p class="u-mono">0.93 · 1,234.56 · AAPL</p></div>'));
    s += section('按钮', demo(ui.button('立即扫描', { variant: 'primary' }) + ui.button('查看原文', { variant: 'secondary' }) + ui.button('重置账户', { variant: 'text' }) + ui.button('清除演示数据', { variant: 'danger' }) +
      ui.button('刷新行情', { variant: 'secondary', icon: 'refresh-cw' }) + ui.button('已禁用', { variant: 'primary', disabled: true, title: '原因写在这里' }) + ui.button('加载中', { variant: 'secondary', icon: 'refresh-cw', loading: true }) + ui.iconButton('x', '关闭') + ui.iconButton('more-horizontal', '更多')));
    s += section('判定标签与概率', demo(['overturn', 'weaken', 'support', 'none', 'uncertain'].map(ui.verdict).join('') + ui.prob(0.93) + ui.prob(0.5) + ui.market('us') + ui.tag('守护中', 'ok') + ui.tag('有待处理', 'warn') + ui.tag('没有逻辑') + ui.tag('已拒绝', 'danger') + ui.tag('进行中', 'info')));
    s += section('引擎徽标', demo(ui.engine({ active: 'jev_direct', modelId: 'jev-1.14.0', state: 'ok' }) + ui.engine({ active: 'jev_direct', modelId: 'jev-1.14.0', state: 'degraded' }) + ui.engine({ active: 'jevdb', modelId: 'jev-1.14.0', state: 'ok' }) + ui.engine({ active: null, modelId: 'jev-1.14.0', state: 'unconfigured' })));
    s += section('表单', demo('<div class="u-maxw-360">' + ui.field({ id: 'g1', label: '逻辑', textarea: true, value: '控股股东长期持股', max: 500, help: '帮助文字' }) + '</div><div class="u-maxw-360">' + ui.field({ id: 'g2', label: '逻辑（错误态）', textarea: true, value: '   ', max: 500, error: '逻辑内容不能为空' }) + '</div><div class="u-maxw-360">' + ui.field({ id: 'g3', label: '数量', value: '120', num: true }) + '</div>' + ui.segmented('g', [{ value: 'buy', label: '买入' }, { value: 'sell', label: '卖出' }], 'buy', '买卖方向')));
    s += section('提示条与 Toast', '<div class="p-stack">' + ui.banner('info', '尚未配置 Jev 密钥和 SEC 联系邮箱。', { actions: ui.button('去设置', { variant: 'secondary', small: true }) }) + ui.banner('warn', '当前离线，显示的是上次的结果。') + ui.banner('danger', '无法连接 SEC，请检查网络后重试。', { actions: ui.button('重试', { variant: 'secondary', small: true }) }) + '</div><div class="proto-demo u-mt-3">' + ui.toast('ok', '已处理：仍然成立') + ui.toast('error', '行情源暂时无法访问') + '</div>');
    s += section('空状态与骨架', '<div class="c-card">' + ui.empty({ title: '先添加第一只标的', text: '搜索你持有或关注的美股，然后为它写下买入的理由。', action: ui.button('去持仓', { variant: 'primary' }) }) + '</div><div class="u-mt-3">' + ui.skeletonCards(2) + '</div>');
    s += section('进度与指标', '<div class="p-stack"><div class="c-card">' + ui.progress(9, 17, '判定进度', '9 / 17') + '</div><div class="c-card">' + ui.progress(1640000, 2000000, '今日已用', '1,640,000 / 2,000,000 tokens', 'warn') + '</div><div class="c-card">' + ui.progress(2000000, 2000000, '今日预算已用完', '2,000,000 / 2,000,000 tokens', 'danger') + '</div></div><div class="c-metrics u-mt-3">' + ui.metric('年化波动率', '18.7%') + ui.metric('最大回撤', '21.4%', '按当前权重回看') + ui.metric('有效持仓数', '4.67') + ui.metric('前三大权重占比', '68.3%', 'ZZFD · ZZAR · ZZCL') + '</div>');
    var risk = P.mock.res('risk.compute', 'ok');
    s += section('热力图与条形', '<div class="p-grid-2"><div class="c-card">' + ui.heatmap(risk.correlation.symbols, risk.correlation.matrix) + ui.legend() + '</div><div class="c-card">' + ui.barlist(risk.svd.explained.map(function (v, i) { return { label: '第 ' + (i + 1) + ' 主成分', value: v, fraction: v, text: P.fmt.pct(v, 1) }; }), '主成分解释方差') + '</div></div>');
    var d = P.mock.res('inbox.list', 'pending').items[0];
    s += section('判定卡片', '<div class="p-stack">' + P.pages.decisionCard(d) + P.pages.decisionCard(P.mock.res('inbox.list', 'pending').uncertain[1]) + '</div>');
    return s + '</div>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    root = document.getElementById('root');
    P.now = window.MOCK.examples['app.bootstrap'].ready.result.now;
    root.innerHTML = build();
    document.documentElement.setAttribute('data-platform', /platform=windows/.test(location.hash) ? 'windows' : 'macos');
  });
})(window.Proto = window.Proto || {});
