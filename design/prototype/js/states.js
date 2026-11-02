/* 页面 × 状态 → 契约示例。状态 id 就是 docs/03-界面设计规范.md 第 4 节“状态表”里的名字。
   Proto.build(route, stateId, opts) 是纯函数，返回完整的 .l-app HTML，Node 可直接调用做自动检查。 */
(function (P) {
  'use strict';
  var ui = P.ui, pages = P.pages, F = P.fmt;

  function ex(method, name) {
    var m = window.MOCK.examples[method];
    if (!m || !m[name]) { throw new Error('缺少契约示例 ' + method + ' / ' + name); }
    return m[name];
  }
  function res(method, name) { var e = ex(method, name); if (!e.result) { throw new Error(method + '/' + name + ' 不是成功示例'); } return e.result; }
  function err(method, name) { var e = ex(method, name); if (!e.error) { throw new Error(method + '/' + name + ' 不是失败示例'); } return e.error; }
  P.mock = { ex: ex, res: res, err: err };

  /* 状态清单：{ id, label }，控制条用。 */
  var STATES = {
    today: [
      ['pending', '有待处理条目（3 件）'], ['empty', '全部已处理'], ['loading', '加载中'], ['scanning', '扫描进行中'],
      ['scan_failed', '扫描失败'], ['offline', '离线'], ['no_holdings', '还没有标的'], ['unconfigured', '未配置密钥与邮箱'], ['engine_fallback', '引擎降级为 Jev 直连']
    ],
    holdings: [
      ['default', '持仓列表'], ['expanded', '展开 ZZAR（两条逻辑）'], ['editor-new', '添加逻辑（编辑器）'], ['editor-error', '编辑器：内容为空'],
      ['editor-too-long', '编辑器：超过 500 字'], ['conflict', '编辑冲突'], ['no-theses', '展开 ZZEN（没有逻辑）'], ['search', '搜索 “ze”'], ['search-empty', '搜索无结果'], ['empty', '还没有持仓']
    ],
    trading: [
      ['default', '有挂单、成交、拒单'], ['new_account', '新账户'], ['no_account', '还没有账户'], ['error-cash', '下单被拒：资金不足'],
      ['error-position', '下单被拒：可卖不足'], ['no-price', '推进失败：没有行情'], ['advanced', '推进后（Toast）']
    ],
    risk: [['ok', '正常'], ['ok-table', '表格视图'], ['insufficient', '样本不足'], ['loading', '加载中'], ['single', '只有 1 只持仓'], ['three-year', '3Y（数据不足三年）']],
    scan: [['default', '运行历史'], ['running', '扫描进行中'], ['detail', '运行明细（含失败批次）'], ['empty', '还没有记录'], ['budget', '今日预算用完']],
    settings: [['configured', '已配置'], ['unconfigured', '未配置'], ['test-ok', '连接测试通过'], ['test-failed', '连接测试失败'], ['invalid-email', '邮箱格式错误']],
    v1: [['default', 'v1 草图']]
  };
  P.STATES = STATES;
  P.DRAWERS = {
    today: [['', '（不打开）'], ['overturn', '推翻'], ['weaken', '削弱'], ['uncertain', '待确认'], ['title_only', '仅依据标题'], ['processed', '已处理'], ['not_found', '找不到']]
  };
  P.stateExists = function (route, id) { return (STATES[route] || []).some(function (s) { return s[0] === id; }); };

  /* 运行时（客户端）状态：处理动作、菜单、选项卡等。刷新页面即丢失。 */
  P.runtime = { acted: {}, openMenu: null, tab: 'pending', table: false, window: '1Y', side: 'buy', qty: '100', toast: null, openUncertain: false, detailRun: null };

  function applyActed(inbox) {
    var acted = P.runtime.acted, ids = Object.keys(acted);
    if (!ids.length) { return inbox; }
    var c = JSON.parse(JSON.stringify(inbox));
    ['items', 'uncertain'].forEach(function (k) {
      c[k] = c[k].filter(function (d) {
        var a = acted[d.decisionId];
        if (!a) { return true; }
        d.action = { action: a.action, note: a.note || null, actedAt: P.now };
        c.processed.unshift(d);
        return false;
      });
    });
    c.processed = c.processed.filter(function (d) { return !(acted[d.decisionId] && acted[d.decisionId].action === 'reopen'); });
    c.summary.pendingCount = c.items.length;
    c.summary.overturnCount = c.items.filter(function (d) { return d.relation === 'overturn'; }).length;
    c.summary.weakenCount = c.items.filter(function (d) { return d.relation === 'weaken'; }).length;
    c.summary.uncertainCount = c.uncertain.length;
    c.summary.processedCount = c.processed.length;
    return c;
  }

  function bootBanners(boot, extra) {
    var b = [];
    if (!boot.configured.jevKey || !boot.configured.secEmail) {
      b.push(ui.banner('info', '尚未配置 Jev 密钥和 SEC 联系邮箱，扫描无法开始。', { actions: '<a class="c-button c-button--secondary c-button--sm" href="#/settings">去设置</a>' }));
    }
    if (boot.offline) { b.push(ui.banner('warn', '当前离线，显示的是上次的结果。')); }
    if (boot.engine.requested !== 'auto' && boot.engine.active !== boot.engine.requested) {
      b.push(ui.banner('info', '未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）。'));
    }
    if (boot.engine.requested === 'auto' && !boot.engine.jevdbAvailable && P.showFallbackBanner) {
      b.push(ui.banner('info', '未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）。'));
    }
    return b.concat(extra || []);
  }

  function holdingsBase() { return res('holdings.list', 'default'); }
  function asOf() { return holdingsBase().items[0].lastCloseDate; }

  /* ---- 各页面 ---- */
  function buildToday(id, o) {
    var boot = res('app.bootstrap', id === 'offline' ? 'offline' : id === 'unconfigured' ? 'unconfigured' : id === 'engine_fallback' ? 'engine_fallback' : 'ready');
    var invName = { pending: 'pending', empty: 'empty', loading: 'pending', scanning: 'pending', scan_failed: 'scan_failed', offline: 'offline', no_holdings: 'no_holdings', unconfigured: 'never_scanned', engine_fallback: 'pending' }[id];
    var inbox = applyActed(res('inbox.list', invName));
    var extra = [];
    if (id === 'scan_failed') {
      extra.push(ui.banner('danger', inbox.lastScan.error.message, { actions: ui.button('重试', { variant: 'secondary', small: true, action: 'scan-start' }) }));
    }
    var c = { inbox: inbox, loading: id === 'loading', openMenu: P.runtime.openMenu, openUncertain: P.runtime.openUncertain };
    if (id === 'scanning') {
      var np = window.MOCK.notifications['scan.progress'];
      c.scanning = true; c.progress = { done: np.done, total: np.total, message: np.message };
    }
    if (id === 'unconfigured') { c.scanDisabled = '请先填写 Jev 密钥和 SEC 联系邮箱'; }
    var drawer = null;
    if (o.drawer) {
      var e = ex('decision.get', o.drawer);
      drawer = e.error ? pages.drawerError(e.error) : pages.drawer(e.result);
    }
    return {
      route: 'today', boot: boot, status: inbox.dataStatus, main: pages.today(c), drawer: drawer, banners: bootBanners(boot, extra),
      dataAsOf: asOf(), lastScanAt: id === 'scan_failed' ? res('scan.history', 'default').items[0].finishedAt : (inbox.lastScan ? inbox.lastScan.finishedAt : null), engineState: id === 'engine_fallback' ? 'degraded' : null,
      scanning: id === 'scanning' ? '扫描中 ' + window.MOCK.notifications['scan.progress'].done + ' / ' + window.MOCK.notifications['scan.progress'].total : null
    };
  }

  function buildHoldings(id, o) {
    var boot = res('app.bootstrap', 'ready'), inbox = res('inbox.list', 'pending');
    var list = id === 'empty' ? res('holdings.list', 'empty') : holdingsBase();
    var c = { holdings: list, theses: [], expanded: null };
    if (id === 'expanded' || id === 'editor-new' || id === 'editor-error' || id === 'editor-too-long' || id === 'conflict') {
      c.expanded = 'ZZAR'; c.theses = res('thesis.list', 'zzar').items;
    }
    if (id === 'editor-new') { c.editor = { statement: '', kill: '' }; }
    if (id === 'editor-error') { c.editor = { statement: '   ', kill: '', errorStatement: err('thesis.create', 'empty').message }; }
    if (id === 'editor-too-long') {
      var long = new Array(120).join('控股股东长期持股，不会大幅减持。') .slice(0, 501);
      c.editor = { statement: long, kill: '', errorStatement: err('thesis.create', 'too_long').message, count: 501 };
    }
    if (id === 'conflict') { c.editing = c.theses[0].thesisId; c.banner = ui.banner('warn', err('thesis.update', 'conflict').message, { actions: ui.button('刷新', { variant: 'secondary', small: true, action: 'noop' }) }); }
    if (id === 'no-theses') { c.expanded = 'ZZEN'; c.theses = res('thesis.list', 'empty').items; }
    if (P.runtime.expanded && id === 'default') { c.expanded = P.runtime.expanded; var key = P.runtime.expanded.toLowerCase(); c.theses = (window.MOCK.examples['thesis.list'][key] || window.MOCK.examples['thesis.list'].empty).result.items; }
    if (id === 'search') { c.search = res('instruments.search', 'ze'); c.searchText = 'ze'; }
    if (id === 'search-empty') { c.search = res('instruments.search', 'empty'); c.searchText = 'qqqq'; }
    return { route: 'holdings', boot: boot, status: inbox.dataStatus, main: pages.holdings(c), banners: bootBanners(boot), dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
  }

  function estimate(side, qty, close) {
    var px = (close || 28.40) * (side === 'buy' ? 1.0005 : 0.9995);
    var amt = px * qty;
    return { price: px.toFixed(6), amount: amt.toFixed(4), fee: '0.0000' };
  }
  function buildTrading(id, o) {
    var boot = res('app.bootstrap', 'ready'), inbox = res('inbox.list', 'pending');
    var base = { route: 'trading', boot: boot, status: inbox.dataStatus, banners: bootBanners(boot), dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
    if (id === 'no_account') { base.main = pages.trading({ noAccount: true }); return base; }
    var portfolio = res('paper.portfolio', id === 'new_account' ? 'new_account' : 'default');
    var orders = id === 'new_account' ? { items: [] } : res('paper.orders', 'default');
    var side = P.runtime.side, qty = Number(P.runtime.qty) || 0;
    var c = { portfolio: portfolio, orders: orders, tab: P.runtime.tab, ticket: { symbol: 'ZZCL · Zhongzhi Cloud Ltd.', side: side, qty: String(P.runtime.qty) }, estimate: estimate(side, qty) };
    if (id === 'error-cash') {
      c.alert = '<div class="u-mb-3">' + ui.banner('danger', err('paper.order.place', 'insufficient_cash').message) + '</div>';
      c.ticket.symbol = 'ZZAR · Zenith Arc Robotics Inc.'; c.ticket.qty = '1800'; c.estimate = estimate('buy', 1800, 51.10);
    }
    if (id === 'error-position') {
      c.alert = '<div class="u-mb-3">' + ui.banner('danger', err('paper.order.place', 'insufficient_position').message) + '</div>';
      c.ticket.side = 'sell'; c.ticket.qty = '500'; c.estimate = estimate('sell', 500, 28.40);
    }
    if (id === 'no-price') { c.alert = '<div class="u-mb-3">' + ui.banner('warn', err('paper.advance', 'no_price').message, { actions: ui.button('刷新行情', { variant: 'secondary', small: true, action: 'noop' }) }) + '</div>'; }
    if (id === 'advanced') {
      var adv = res('paper.advance', 'filled');
      c.portfolio = adv.portfolio; c.orders = { items: [adv.filled[0], res('paper.orders', 'default').items[1], res('paper.orders', 'default').items[2], res('paper.orders', 'default').items[3]] };
      c.tab = 'fills'; base.toasts = [ui.toast('ok', '10月15日：1 笔成交')];
    }
    base.main = pages.trading(c);
    return base;
  }

  function buildRisk(id) {
    var boot = res('app.bootstrap', 'ready'), inbox = res('inbox.list', 'pending');
    var c = { window: P.runtime.window, table: id === 'ok-table' || P.runtime.table };
    if (id === 'loading') { c.loading = true; }
    else if (id === 'insufficient') { c.error = err('risk.compute', 'insufficient'); c.window = '6M'; }
    else if (id === 'single') { c.risk = res('risk.compute', 'single'); }
    else if (id === 'three-year') { c.risk = res('risk.compute', 'three_year'); c.window = '3Y'; }
    else { c.risk = res('risk.compute', 'ok'); }
    return { route: 'risk', boot: boot, status: inbox.dataStatus, main: pages.risk(c), banners: bootBanners(boot), dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
  }

  function buildScan(id, o) {
    var boot = res('app.bootstrap', 'ready'), inbox = res('inbox.list', 'pending');
    var hist = res('scan.history', id === 'running' ? 'running' : id === 'empty' ? 'empty' : id === 'budget' ? 'budget_exhausted' : 'default');
    var c = { history: hist, budget: hist.budget, running: id === 'running', detailRun: null };
    var drawer = null;
    if (id === 'detail') { var d = res('scan.detail', 'with_failures'); c.detailRun = d.run.runId; c.history = res('scan.history', 'default'); drawer = pages.scanDrawer(d); }
    if (id === 'budget') { c.alert = '<div class="u-mb-3">' + ui.banner('danger', err('scan.start', 'budget').message) + '</div>'; }
    if (id === 'running') { var np = window.MOCK.notifications['scan.progress']; c.alert = '<div class="u-mb-3">' + ui.banner('info', np.message + ' · ' + np.done + ' / ' + np.total) + '</div>'; }
    return { route: 'scan', boot: boot, status: hist.budget === inbox.dataStatus.budget ? inbox.dataStatus : Object.assign({}, inbox.dataStatus, { budget: hist.budget }), main: pages.scan(c), drawer: drawer, banners: bootBanners(boot), dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
  }

  function buildSettings(id) {
    var unconf = id === 'unconfigured';
    var boot = res('app.bootstrap', unconf ? 'unconfigured' : 'ready'), inbox = res('inbox.list', 'pending');
    var c = { settings: res('settings.get', unconf ? 'unconfigured' : 'configured'), secrets: res('secrets.status', unconf ? 'none' : 'configured'), configured: !unconf };
    if (id === 'test-ok') { c.test = res('settings.testConnection', 'ok'); }
    if (id === 'test-failed') { c.test = res('settings.testConnection', 'failed'); }
    if (id === 'invalid-email') { c.emailError = err('settings.update', 'invalid_email').message; c.settings = Object.assign({}, c.settings, { secContactEmail: 'not-an-email' }); }
    return { route: 'settings', boot: boot, status: inbox.dataStatus, main: pages.settings(c), banners: [], dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
  }

  function buildV1() {
    var boot = res('app.bootstrap', 'ready'), inbox = res('inbox.list', 'pending');
    return { route: 'v1', boot: boot, status: inbox.dataStatus, main: pages.v1(), banners: [], dataAsOf: asOf(), lastScanAt: inbox.lastScan.finishedAt };
  }

  var BUILDERS = { today: buildToday, holdings: buildHoldings, trading: buildTrading, risk: buildRisk, scan: buildScan, settings: buildSettings, v1: buildV1 };

  P.build = function (route, stateId, opts) {
    opts = opts || {};
    var states = STATES[route];
    if (!states) { throw new Error('未知页面: ' + route); }
    var id = stateId || states[0][0];
    if (!P.stateExists(route, id)) { throw new Error('未知状态: ' + route + ' / ' + id); }
    var ctx = BUILDERS[route](id, opts);
    ctx.platform = opts.platform || 'macos';
    ctx.toasts = (ctx.toasts || []).concat(P.runtime.toast ? [P.runtime.toast] : []);
    return pages.shell(ctx);
  };
})(window.Proto = window.Proto || {});
