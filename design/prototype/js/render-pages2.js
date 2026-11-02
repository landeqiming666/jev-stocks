/* 页面渲染（二）：交易、风险、扫描、设置、v1 草图。纯函数。 */
(function (P) {
  'use strict';
  var ui = P.ui, esc = P.esc, icon = P.icon, F = P.fmt;
  var pages = P.pages = P.pages || {};

  /* ---------- 交易 ---------- */
  var ORDER_STATUS = { pending: ['待成交', 'info'], filled: ['已成交', 'ok'], rejected: ['已拒绝', 'danger'], cancelled: ['已取消', 'none'] };
  function orderRow(o) {
    var st = ORDER_STATUS[o.status], f = o.fills[0];
    return '<tr><td><span class="u-mono"><strong>' + esc(o.instrument.symbol) + '</strong></span></td><td>' + (o.side === 'buy' ? '买入' : '卖出') + '</td>' +
      '<td class="c-table__num">' + F.int(o.quantity) + '</td><td>开盘市价</td>' +
      '<td class="c-table__num">' + (f ? F.num(f.price, 4) : o.estimate ? '≈ ' + F.num(o.estimate.price, 4) : '—') + '</td>' +
      '<td>' + ui.tag(st[0], st[1]) + (o.rejectReason ? '<div class="p-trading__reject">' + esc(o.rejectReason.message) + '</div>' : '') + '</td>' +
      '<td class="c-table__num">' + F.date(o.createdClockDate) + '</td></tr>';
  }
  function ordersTable(list, empty) {
    if (!list.length) { return '<p class="u-muted u-p-0">' + esc(empty) + '</p>'; }
    return '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">标的</th><th scope="col">方向</th><th scope="col" class="c-table__num">数量</th><th scope="col">类型</th>' +
      '<th scope="col" class="c-table__num">价格</th><th scope="col">状态</th><th scope="col" class="c-table__num">下单日</th></tr></thead><tbody>' + list.map(orderRow).join('') + '</tbody></table></div>';
  }
  function fillsTable(orders) {
    var rows = [];
    orders.forEach(function (o) { o.fills.forEach(function (f) { rows.push([o, f]); }); });
    if (!rows.length) { return '<p class="u-muted">还没有成交。试着下一笔单，然后点“下一交易日”。</p>'; }
    return '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">成交日</th><th scope="col">标的</th><th scope="col">方向</th><th scope="col" class="c-table__num">数量</th><th scope="col" class="c-table__num">价格</th><th scope="col" class="c-table__num">金额</th><th scope="col" class="c-table__num">费用</th></tr></thead><tbody>' +
      rows.map(function (r) { return '<tr><td>' + F.date(r[1].filledOn) + '</td><td class="u-mono"><strong>' + esc(r[0].instrument.symbol) + '</strong></td><td>' + (r[0].side === 'buy' ? '买入' : '卖出') + '</td><td class="c-table__num">' + F.int(r[1].quantity) +
        '</td><td class="c-table__num">' + F.num(r[1].price, 4) + '</td><td class="c-table__num">' + F.money(r[1].amount) + '</td><td class="c-table__num">' + F.money(r[1].fee) + '</td></tr>'; }).join('') + '</tbody></table></div>';
  }
  function positionsTable(ps) {
    if (!ps.length) { return '<p class="u-muted">现在没有持仓。</p>'; }
    return '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">标的</th><th scope="col" class="c-table__num">数量</th><th scope="col" class="c-table__num">成本</th><th scope="col" class="c-table__num">收盘</th><th scope="col" class="c-table__num">市值</th><th scope="col" class="c-table__num">浮动盈亏</th></tr></thead><tbody>' +
      ps.map(function (p) { var up = Number(p.unrealizedPnl) >= 0; return '<tr><td class="u-mono"><strong>' + esc(p.instrument.symbol) + '</strong></td><td class="c-table__num">' + F.int(p.quantity) + '</td><td class="c-table__num">' + F.num(p.avgCost, 4) +
        '</td><td class="c-table__num">' + F.price(p.lastClose) + '</td><td class="c-table__num">' + F.money(p.marketValue) + '</td><td class="c-table__num ' + (up ? 'u-up' : 'u-down') + '">' + F.signedMoney(p.unrealizedPnl) + ' (' + F.pct(p.unrealizedPnlPct, 1, true) + ')</td></tr>'; }).join('') + '</tbody></table></div>';
  }

  pages.trading = function (c) {
    var head = '<header class="p-page__head"><div><h1 class="p-page__title">交易</h1></div></header>';
    if (c.noAccount) {
      return '<section class="p-trading">' + head + '<div class="c-card u-maxw-520"><h2 class="c-card__title">创建模拟账户</h2><p class="u-text-2">模拟账户用“回放时钟”练习下单：你选一个过去的交易日作为起点，点“下一交易日”往前推，系统按当天开盘价撮合。</p>' +
        '<div class="p-stack">' + ui.field({ id: 'acc-name', label: '账户名称', value: '回放账户 A', max: 30 }) + ui.field({ id: 'acc-cash', label: '初始现金（美元）', value: '100,000.00', num: true }) +
        ui.field({ id: 'acc-start', label: '回放起始日', value: '2026-09-01', help: '只能选交易日，且需要有行情数据' }) + '<div>' + ui.button('创建账户', { variant: 'primary', action: 'noop' }) + '</div></div></div></section>';
    }
    var p = c.portfolio, a = p.account;
    var bar = '<div class="p-trading__account"><div class="u-grow"><label class="u-small u-muted" for="acc-select">账户</label><select class="c-select u-w-180" id="acc-select"><option>' + esc(a.name) + '</option></select>' +
      '<span>回放日期 <span class="p-trading__clock">' + F.isoDate(a.clockDate) + '（' + F.weekday(a.clockDate).replace('星期', '周') + '）</span></span></div>' +
      ui.button('下一交易日', { variant: 'primary', icon: 'play', action: 'advance' }) + ui.button('重置账户', { variant: 'danger', action: 'reset-open' }) + '</div>';
    var metrics = '<div class="c-metrics">' + ui.metric('现金', F.money(p.cash)) + ui.metric('冻结资金', F.money(p.reservedCash), p.pendingOrders + ' 笔待成交') + ui.metric('持仓市值', F.money(sum(p.positions))) + ui.metric('权益', F.money(p.equity), '截至 ' + F.date(p.asOf)) + '</div>';
    var est = c.estimate;
    var ticket = '<div class="c-card p-trading__ticket"><h2 class="c-card__title">下单</h2>' +
      ui.field({ id: 'order-symbol', label: '标的', value: c.ticket.symbol, disabled: true }) +
      '<div><div class="c-field__label u-mb-1">方向</div>' + ui.segmented('side', [{ value: 'buy', label: '买入' }, { value: 'sell', label: '卖出' }], c.ticket.side, '买卖方向') + '</div>' +
      ui.field({ id: 'order-qty', label: '数量（股）', value: c.ticket.qty, num: true, inputmode: 'numeric', input: 'qty', error: c.ticket.error ? null : null }) +
      ui.field({ id: 'order-type', label: '类型', value: '开盘市价单', disabled: true, help: '暂不支持限价单' }) +
      '<div class="p-trading__estimate">' + ui.kv([['预估价', '$' + F.num(est.price, 4)], ['预估金额', F.money(est.amount)], ['预估费用', F.money(est.fee)]]) + '<p class="c-note u-mt-2">按下一个交易日开盘价成交，价格可能与预估不同。</p></div>' +
      ui.button('提交订单', { variant: 'primary', action: 'place-order' }) + '</div>';
    var tabs = '<div class="c-card c-card--flush"><div class="c-card__pad-x">' + '<div class="c-tabs" role="tablist" aria-label="交易记录">' + [['pending', '挂单'], ['fills', '成交'], ['positions', '持仓'], ['history', '历史订单']].map(function (t) {
      var on = t[0] === c.tab;
      return '<button type="button" class="c-tabs__tab' + (on ? ' is-active' : '') + '" role="tab" aria-selected="' + on + '" data-action="tab" data-arg="' + t[0] + '">' + t[1] + '</button>';
    }).join('') + '</div></div><div class="c-card__pad" role="tabpanel">' + tabBody(c) + '</div></div>';
    var fee = '<p class="c-note u-mt-3">监管费率为占位值（0），实际成交费用可能不同。仅记录与提醒，不构成投资建议。</p>';
    return '<section class="p-trading">' + head + (c.alert || '') + bar + metrics + '<div class="p-trading__main">' + ticket + '<div>' + tabs + fee + '</div></div></section>';
  };
  function sum(ps) { return ps.reduce(function (t, p) { return t + Number(p.marketValue); }, 0).toFixed(4); }
  function tabBody(c) {
    var os = c.orders.items;
    if (c.tab === 'pending') { return ordersTable(os.filter(function (o) { return o.status === 'pending'; }), '没有待成交的订单。'); }
    if (c.tab === 'fills') { return fillsTable(os); }
    if (c.tab === 'positions') { return positionsTable(c.portfolio.positions); }
    return ordersTable(os, '还没有订单。');
  }

  /* ---------- 风险 ---------- */
  pages.risk = function (c) {
    var head = '<header class="p-page__head"><div><h1 class="p-page__title">风险</h1></div></header>';
    var controls = '<div class="p-risk__controls"><div class="u-grow">' + ui.segmented('window', [{ value: '6M', label: '6M' }, { value: '1Y', label: '1Y' }, { value: '3Y', label: '3Y' }], c.window, '统计窗口') +
      ui.segmented('currency', [{ value: 'USD', label: '美元' }, { value: 'CNY', label: '人民币', disabled: true, title: 'v1 提供人民币口径' }], 'USD', '口径') + '</div>' +
      ui.button('表格视图', { variant: c.table ? 'primary' : 'secondary', action: 'toggle-table' }) + '</div>';
    if (c.loading) {
      return '<section class="p-risk">' + head + controls + '<div class="c-metrics"><div class="c-skeleton c-skeleton--card"></div><div class="c-skeleton c-skeleton--card"></div><div class="c-skeleton c-skeleton--card"></div><div class="c-skeleton c-skeleton--card"></div></div></section>';
    }
    if (c.error) {
      return '<section class="p-risk">' + head + controls + ui.empty({ title: c.error.message, text: '请先刷新行情，或换一个更长的窗口。', action: ui.button('去刷新行情', { variant: 'secondary', icon: 'refresh-cw', action: 'noop' }) }) + '</section>';
    }
    var r = c.risk, w = r.window;
    var top3 = r.topWeights.reduce(function (t, x) { return t + x.weight; }, 0);
    var metrics = '<div class="c-metrics">' + ui.metric('年化波动率', F.pct(r.annualizedVol, 1)) + ui.metric('最大回撤', F.pct(r.maxDrawdown, 1), '按当前权重回看') +
      ui.metric('有效持仓数', F.num(r.effectiveHoldings, 2)) + ui.metric('前三大权重占比', F.pct(top3, 1), r.topWeights.map(function (x) { return x.symbol; }).join(' · ')) + '</div>';
    var warns = r.warnings.map(function (t) { return ui.banner('warn', t); }).join('');
    var n = r.correlation.symbols.length;
    var heat;
    if (n < 2) {
      heat = '<p class="u-text-2">至少需要 2 只持仓才能显示相关性。</p>';
    } else if (c.table) {
      heat = '<div class="c-table-wrap"><table class="c-table"><caption class="u-visually-hidden">相关系数表</caption><thead><tr><th scope="col"></th>' + r.correlation.symbols.map(function (s) { return '<th scope="col" class="c-table__num">' + esc(s) + '</th>'; }).join('') + '</tr></thead><tbody>' +
        r.correlation.matrix.map(function (row, i) { return '<tr><th scope="row">' + esc(r.correlation.symbols[i]) + '</th>' + row.map(function (v) { return '<td class="c-table__num">' + (v == null ? '—' : v.toFixed(2)) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>';
    } else {
      heat = '<div class="p-risk__heat">' + ui.heatmap(r.correlation.symbols, r.correlation.matrix) + ui.legend() + '</div>';
    }
    var bars = ui.barlist(r.svd.explained.map(function (v, i) { return { label: '第 ' + (i + 1) + ' 主成分', value: v, fraction: v, text: F.pct(v, 1) }; }), '主成分解释方差');
    var loadings = '<h3 class="c-card__subtitle u-mt-4 u-mb-1">第一主成分载荷</h3><ul class="p-risk__loadings">' + r.svd.loadings.map(function (l) { return '<li><span class="u-mono">' + esc(l.symbol) + '</span><span class="u-mono">' + l.value.toFixed(2) + '</span></li>'; }).join('') + '</ul>';
    var excl = r.excluded.length ? ' · 未计入：' + r.excluded.map(function (e) { return e.symbol + '（' + e.reason + '）'; }).join('、') : '';
    return '<section class="p-risk">' + head + controls + warns + metrics + '<div class="p-grid-2 p-risk__body"><div class="c-card"><h2 class="c-card__title">相关系数</h2>' + heat + '</div>' +
      '<div class="c-card"><h2 class="c-card__title">风险方向（SVD）</h2><p class="c-note u-mb-3">解释方差占比，越靠前的主成分越能代表组合共同的波动来源。</p>' + bars + loadings + '</div></div>' +
      '<p class="p-risk__foot">观测 ' + w.observations + ' 个共同交易日 · ' + F.isoDate(w.from) + ' 至 ' + F.isoDate(w.to) + ' · 价格已复权' + esc(excl) + '</p></section>';
  };

  /* ---------- 扫描 ---------- */
  var RUN_STATUS = { succeeded: ['成功', 'ok'], partial: ['部分成功', 'warn'], failed: ['失败', 'danger'], cancelled: ['已取消', 'none'], interrupted: ['已中断', 'none'], running: ['进行中', 'info'], queued: ['排队中', 'info'] };
  var BATCH_STATUS = { succeeded: ['成功', 'ok'], failed: ['失败', 'danger'], pending: ['待执行', 'info'], cancelled: ['已取消', 'none'] };
  pages.scan = function (c) {
    var b = c.budget, pct = b.limitTokens ? b.usedTokens / b.limitTokens : 0;
    var tone = pct >= 1 ? 'danger' : pct >= 0.8 ? 'warn' : '';
    var cost = (b.usedTokens * 0.042 / 1e6);
    var head = '<header class="p-page__head"><div><h1 class="p-page__title">扫描</h1></div><div class="p-page__actions">' +
      (c.running ? ui.button('取消扫描', { variant: 'secondary', action: 'scan-cancel' }) : ui.button('立即扫描', { variant: 'primary', action: 'scan-start', disabled: pct >= 1, title: pct >= 1 ? '今日预算已用完' : null })) + '</div></header>';
    var budget = '<div class="c-card p-scan__budget"><div class="u-row u-row--between"><strong>今日预算</strong><span class="u-small u-muted">估算 $' + cost.toFixed(4) + ' · 重置于 ' + F.dateTime(b.resetAt) + '</span></div>' +
      ui.progress(b.usedTokens, b.limitTokens, pct >= 1 ? '今日预算已用完' : '今日已用', F.tokens(b.usedTokens) + ' / ' + F.tokens(b.limitTokens) + ' tokens', tone) + '</div>';
    if (!c.history.items.length) {
      return '<section class="p-scan">' + head + budget + ui.empty({ title: '还没有扫描记录', text: '点“立即扫描”，系统会读取有逻辑的标的最近的披露。' }) + '</section>';
    }
    var rows = c.history.items.map(function (r) {
      var s = r.stats, st = RUN_STATUS[r.status], sel = c.detailRun === r.runId;
      return '<tr class="c-table__click' + (sel ? ' is-selected' : '') + '" data-action="run-open" data-arg="' + r.runId + '"><td>' + F.dateTime(r.startedAt) + '</td><td>' + ui.tag(st[0], st[1]) + '</td>' +
        '<td class="c-table__num">' + s.instruments + '</td><td class="c-table__num">' + s.filings + '</td><td class="c-table__num">' + s.passages + '</td><td class="c-table__num">' + s.decisions + '</td>' +
        '<td class="c-table__num">' + s.requests + '</td><td class="c-table__num">' + F.tokens(s.inputTokens) + '</td><td class="c-table__num">' + F.usd6(s.estCostUsd) + '</td>' +
        '<td class="c-table__num">' + (r.finishedAt ? (s.durationMs / 1000).toFixed(0) + ' 秒' : '进行中') + '</td><td>' + (r.engine === 'jevdb' ? 'JEVDB' : 'Jev 直连') + '</td></tr>';
    }).join('');
    var table = '<div class="c-card c-card--flush"><div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">开始时间</th><th scope="col">状态</th><th scope="col" class="c-table__num">标的</th><th scope="col" class="c-table__num">披露</th>' +
      '<th scope="col" class="c-table__num">段落</th><th scope="col" class="c-table__num">判定</th><th scope="col" class="c-table__num">请求</th><th scope="col" class="c-table__num">tokens</th><th scope="col" class="c-table__num">估算费用</th><th scope="col" class="c-table__num">耗时</th><th scope="col">引擎</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';
    return '<section class="p-scan">' + head + (c.alert || '') + budget + table + '</section>';
  };
  pages.scanDrawer = function (detail) {
    var r = detail.run, s = r.stats, st = RUN_STATUS[r.status];
    var body = '<div><h2 class="c-drawer__title" id="drawer-title" tabindex="-1">扫描明细</h2></div>' +
      '<section class="c-drawer__sec"><h3>范围与统计</h3>' + ui.kv([['窗口', F.dateTime(r.windowStart) + ' 至 ' + F.dateTime(r.windowEnd)], ['引擎', (r.engine === 'jevdb' ? 'JEVDB 加速' : 'Jev 直连') + ' · ' + r.modelId],
        ['标的', s.instruments + ' 只（' + s.skippedNoThesis + ' 只因没有逻辑被跳过）'], ['披露 / 段落', s.filings + ' / ' + s.passages], ['判定', s.decisions + ' 条（缓存命中 ' + s.cachedDecisions + '）'],
        ['tokens / 费用', F.tokens(s.inputTokens) + ' / ' + F.usd6(s.estCostUsd)]]) + (r.error ? ui.banner('warn', r.error.message) : '') + '</section>' +
      '<section class="c-drawer__sec"><h3>批次（' + detail.batches.length + '）</h3><ul class="p-stack">' + detail.batches.map(function (b) {
        var bs = BATCH_STATUS[b.status];
        return '<li class="c-card c-card--tight"><div class="u-row u-row--between"><span class="u-mono"><strong>' + esc(b.instrumentId.replace('us:', '')) + '</strong></span>' + ui.tag(bs[0], bs[1]) + '</div>' +
          '<p class="u-small u-text-2 u-clamp-2">' + esc(b.eventTitle) + '</p><p class="u-small u-muted">尝试 ' + b.attempts + ' 次 · ' + F.tokens(b.inputTokens) + ' tokens</p>' +
          (b.error ? '<p class="u-small u-danger">' + esc(b.error.message) + '</p><div>' + ui.button('重试', { variant: 'secondary', small: true, icon: 'refresh-cw', action: 'retry-batch', arg: b.batchId }) + '</div>' : '') + '</li>';
      }).join('') + '</ul></section>';
    return ui.drawer({ head: ui.tag(st[0], st[1]), body: body });
  };

  /* ---------- 设置 ---------- */
  pages.settings = function (c) {
    var s = c.settings, keyOk = c.secrets.jevKey, cfgd = c.configured;
    var key = keyOk ? '<div class="p-settings__row"><div><strong>Jev 密钥</strong><div class="u-small u-muted">密钥存放在系统钥匙串里，界面不会再显示它。</div></div><div class="u-row">' + ui.tag('已保存', 'ok', 'check') + ui.button('替换', { variant: 'secondary', small: true, action: 'noop' }) + ui.button('清除', { variant: 'danger', small: true, action: 'noop' }) + '</div></div>' :
      '<div class="p-settings__row"><div class="c-field u-maxw-360"><label class="c-field__label" for="f-jev-key">Jev 密钥</label><input class="c-input" id="f-jev-key" type="password" autocomplete="off" placeholder="粘贴你的 Jev 密钥"><p class="c-field__meta"><span>保存后只显示“已保存”，不会再回显。</span></p></div>' + ui.button('保存', { variant: 'primary', action: 'noop' }) + '</div>';
    var email = '<div class="p-settings__row">' + ui.field({ id: 'sec-email', label: 'SEC 联系邮箱', value: s.secContactEmail || '', placeholder: 'name@example.com', error: c.emailError, help: 'SEC 要求访问时声明联系方式。邮箱只会出现在发给 SEC 的请求头里。' }) + ui.button('保存', { variant: 'primary', action: 'noop' }) + '</div>';
    var engine = ui.radio('engine', 'auto', '自动（推荐）', '优先使用 JEVDB，不可用时改用 Jev 直连（同一模型）', s.engine === 'auto') + ui.radio('engine', 'jevdb', 'JEVDB', '只使用 JEVDB 扩展；不可用时报错，不降级', s.engine === 'jevdb') + ui.radio('engine', 'jev_direct', 'Jev 直连', '只使用官方 SDK 直连', s.engine === 'jev_direct');
    var test = c.test ? '<ul class="p-stack u-mt-3">' + c.test.checks.map(function (k) {
      return '<li class="u-row">' + ui.tag(k.ok ? (k.name === 'JEVDB' ? '可用' : '正常') : (k.name === 'JEVDB' ? '不可用' : '未通过'), k.ok ? 'ok' : (k.name === 'JEVDB' ? 'none' : 'danger'), k.ok ? 'check' : 'x') + '<strong>' + esc(k.name) + '</strong><span class="u-text-2 u-grow">' + esc(k.message) + '</span><span class="u-mono u-muted">' + (k.latencyMs != null ? k.latencyMs + ' ms' : '') + '</span></li>';
    }).join('') + '</ul>' + (c.test.ok ? '' : '<div class="u-mt-3">' + ui.banner('danger', '连接测试未通过，请根据上面的说明处理。') + '</div>') : '';
    var domains = '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">域名</th><th scope="col">用途</th><th scope="col">发送的内容</th></tr></thead><tbody>' + s.allowedDomains.map(function (d) { return '<tr><td class="u-mono">' + esc(d.domain) + '</td><td>' + esc(d.purpose) + '</td><td class="u-text-2">' + esc(d.sends) + '</td></tr>'; }).join('') + '</tbody></table></div>';
    var warnCfg = !cfgd ? ui.banner('warn', '尚未配置 Jev 密钥和 SEC 联系邮箱，扫描无法开始。') : '';
    return '<section class="p-settings"><header class="p-page__head"><div><h1 class="p-page__title">设置</h1></div></header>' + warnCfg +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">密钥与联系方式</h2>' + key + email + '</div>' +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">语义引擎</h2><div class="u-mt-3">' + engine + '</div><div class="p-settings__row u-mt-3"><div><strong>模型</strong><div class="u-small u-muted u-mono">' + esc(s.modelId) + '（固定版本，不使用别名）</div></div>' + ui.button('测试连接', { variant: 'secondary', icon: 'refresh-cw', action: 'test-connection' }) + '</div>' + test + '</div>' +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">预算</h2><div class="p-settings__row">' + ui.field({ id: 'budget', label: '每日 token 上限', value: F.int(s.dailyTokenBudget), num: true, help: '≈ $' + (s.dailyTokenBudget * 0.042 / 1e6).toFixed(3) + ' / 天（按 $0.042 / 百万 tokens 估算）' }) + '</div>' +
      '<div class="p-settings__row">' + ui.field({ id: 'lookback', label: '首次扫描回看天数', value: String(s.firstScanLookbackDays), num: true, help: '1 至 30 天' }) + '</div></div>' +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">隐私与外联</h2><p class="u-text-2 u-mt-2 u-mb-3">持仓数量、成本、备注永远不会离开本机。本应用只会访问下列域名：</p>' + domains + '</div>' +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">演示数据</h2><div class="p-settings__row"><div><strong>' + (s.demoDataLoaded ? '已载入演示数据' : '未载入演示数据') + '</strong><div class="u-small u-muted">演示数据是虚构的公司，不会与真实数据混淆。</div></div>' +
      '<div class="u-row">' + ui.button('载入演示数据', { variant: 'secondary', action: 'noop', disabled: s.demoDataLoaded }) + ui.button('清除演示数据', { variant: 'danger', action: 'noop', disabled: !s.demoDataLoaded }) + '</div></div></div>' +
      '<div class="c-card p-settings__group"><h2 class="c-card__title">关于</h2>' + ui.kv([['版本', '0.1.0（MVP-0 原型）'], ['协议版本', '1.0'], ['声明', '仅记录与提醒，不构成投资建议。']]) + '</div></section>';
  };

  /* ---------- v1 草图 ---------- */
  pages.v1 = function () {
    var notice = '<div class="p-v1__notice"><strong>ZZAR 的投资逻辑被推翻</strong><p class="u-text-2">8-K：控股股东拟减持 4.5%</p></div>';
    var tray = '<div class="p-v1__tray" role="presentation"><div><strong>今天有 3 件事</strong></div><div>打开投资逻辑哨兵</div><div>立即扫描</div><div>退出</div></div>';
    var steps = '<div class="p-v1__steps">' + ['选择市场并添加标的', '写下第一条逻辑', '配置密钥与推送'].map(function (t, i) { return '<div class="p-v1__step' + (i === 0 ? ' is-active' : '') + '"><span class="u-mono u-muted">' + (i + 1) + '</span><br>' + t + '</div>'; }).join('') + '</div>';
    var tl = '<ol class="c-timeline"><li class="c-timeline__node"><strong>10月28日</strong> 判定 ZZBK · 削弱 0.72</li><li class="c-timeline__node"><strong>10月28日</strong> 你的处理：仍然成立</li><li class="c-timeline__node"><strong>9月8日</strong> 写下逻辑（第 1 版）</li></ol>';
    return '<section class="p-v1"><header class="p-page__head"><div><h1 class="p-page__title">v1 草图</h1><p class="p-page__eyebrow">这些只用于对齐 v1 的预期，MVP-0 的工作包不得实现它们。</p></div></header><div class="p-v1__grid">' +
      '<div class="c-card"><div class="p-v1__tag">' + ui.tag('v1', 'info') + '</div><h2 class="c-card__title">复盘页</h2><div class="p-v1__chart">K 线与事件标记（lightweight-charts）</div><div class="u-mt-4">' + tl + '</div></div>' +
      '<div class="c-card"><div class="p-v1__tag">' + ui.tag('v1', 'info') + '</div><h2 class="c-card__title">首次启动引导</h2><div class="u-mt-3">' + steps + '</div></div>' +
      '<div class="c-card"><div class="p-v1__tag">' + ui.tag('v1', 'info') + '</div><h2 class="c-card__title">托盘菜单（macOS 菜单栏）</h2><div class="u-mt-3">' + tray + '</div></div>' +
      '<div class="c-card"><div class="p-v1__tag">' + ui.tag('v1', 'info') + '</div><h2 class="c-card__title">系统通知</h2><div class="u-mt-3">' + notice + '</div></div></div></section>';
  };
})(window.Proto = window.Proto || {});
