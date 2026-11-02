/* 页面渲染（一）：外壳、今日、证据抽屉、持仓。纯函数。 */
(function (P) {
  'use strict';
  var ui = P.ui, esc = P.esc, icon = P.icon, F = P.fmt;
  var pages = P.pages = P.pages || {};

  var MARKET_STATE = { open: '开盘中', pre: '盘前', after: '盘后', closed: '已收盘', holiday: '休市' };
  var NAV = [
    { id: 'today', label: '今日', icon: 'sun' }, { id: 'holdings', label: '持仓', icon: 'briefcase' },
    { id: 'trading', label: '交易', icon: 'arrow-left-right' }, { id: 'risk', label: '风险', icon: 'activity' },
    { id: 'scan', label: '扫描', icon: 'radar' }
  ];
  P.NAV = NAV;
  var FILE_PART = { '主文档': '主文档', 'EX-99.1': 'EX-99.1（新闻稿附件）', '标题': '仅标题' };

  /* ---------- 外壳 ---------- */
  pages.shell = function (c) {
    var st = c.status, boot = c.boot, platform = c.platform || 'macos';
    var market = '美股 ' + MARKET_STATE[st.marketState] + (st.nextOpenAt && st.marketState !== 'open' ? ' · 下次开盘 ' + F.dateTime(st.nextOpenAt) : '');
    var top = '<header class="l-top" data-tauri-drag-region><span class="l-top__brand">投资逻辑哨兵</span><span class="l-top__market">' + esc(market) + '</span><span class="l-top__spacer"></span>' +
      (st.offline ? ui.tag('离线', 'warn', 'wifi-off') : '') + ui.engine({ active: boot.engine.active, modelId: boot.engine.modelId, state: c.engineState || st.engine.state }) + '</header>';
    var nav = '<nav class="l-nav" aria-label="主导航">' + NAV.map(function (n) {
      var on = n.id === c.route;
      return '<a class="l-nav__item' + (on ? ' is-active' : '') + '" href="#/' + n.id + '"' + (on ? ' aria-current="page"' : '') + ' title="' + n.label + '" aria-label="' + n.label + '">' + icon(n.icon, 20) + '<span class="l-nav__label">' + n.label + '</span></a>';
    }).join('') + '<span class="l-nav__spacer"></span>' +
      '<a class="l-nav__item' + (c.route === 'settings' ? ' is-active' : '') + '" href="#/settings"' + (c.route === 'settings' ? ' aria-current="page"' : '') + ' title="设置" aria-label="设置">' + icon('settings', 20) + '<span class="l-nav__label">设置</span></a></nav>';
    var statusBits = ['数据截至 ' + F.date(c.dataAsOf), c.lastScanAt ? '最近扫描 ' + F.time(c.lastScanAt) : '尚未扫描',
      '今日 ' + F.tokens(st.budget.usedTokens) + ' / ' + F.tokens(st.budget.limitTokens) + ' tokens'];
    var status = '<footer class="l-status">' + statusBits.map(esc).join('<span class="l-status__sep" aria-hidden="true">·</span>') + '<span class="l-status__spacer"></span>' +
      (c.scanning ? '<span>' + esc(c.scanning) + '</span>' : '<span>仅记录与提醒，不构成投资建议</span>') + '</footer>';
    var drawerOpen = !!c.drawer;
    return '<div class="l-app" data-platform="' + platform + '" data-route="' + c.route + '" data-ready="true">' + top + nav +
      '<div class="l-body"><div class="l-content"><div class="l-banners">' + (c.banners || []).join('') + '</div>' +
      '<main class="l-main" id="main"><div class="l-main__inner' + '">' + c.main + '</div></main></div>' +
      (drawerOpen ? c.drawer : '') + '<div class="l-scrim" data-action="drawer-close"' + (drawerOpen ? '' : ' hidden') + '></div></div>' + status +
      (c.toasts && c.toasts.length ? '<div class="c-toast-stack">' + c.toasts.join('') + '</div>' : '') + '</div>';
  };

  /* ---------- 今日 ---------- */
  function cardActions(d, openMenu) {
    var id = d.decisionId;
    return '<footer class="c-decision__actions">' +
      ui.button('查看原文', { variant: 'secondary', action: 'drawer-open', arg: id }) +
      ui.button('仍然成立', { variant: 'secondary', action: 'act', arg: id + ':still_valid' }) +
      ui.button('修正逻辑', { variant: 'secondary', action: 'act', arg: id + ':revise' }) +
      ui.iconButton('more-horizontal', '更多处理方式', { action: 'menu-toggle', arg: 'menu-' + id, expanded: openMenu ? 'true' : 'false', 'aria-controls': 'menu-' + id, haspopup: 'menu' }) +
      ui.menu('menu-' + id, [{ label: '准备卖出', action: 'act', arg: id + ':exit_intent' }, { label: '忽略', action: 'act', arg: id + ':ignore' }]) + '</footer>';
  }
  function evidenceLine(d) {
    var e = d.evidence, prefix = '';
    if (d.contentStatus === 'title_only') { prefix = '仅依据标题：'; }
    else if (e.kind === 'passage') { prefix = '未能定位到单句：'; }
    return '<p class="c-decision__evidence"><span class="c-decision__label">证据：</span>' + esc(prefix) + esc(e.text) + '</p>';
  }
  pages.decisionCard = function (d, o) {
    o = o || {};
    var ins = d.instrument;
    var stale = d.thesisCurrentVersion > d.thesisVersion;
    return '<article class="c-card c-decision" aria-labelledby="t-' + d.decisionId + '">' +
      '<header class="c-decision__head">' + ui.market(ins.market) +
      '<h3 class="c-decision__title" id="t-' + d.decisionId + '"><span class="u-mono">' + esc(ins.symbol) + '</span> <span class="c-decision__name">' + esc(ins.name) + '</span></h3>' +
      ui.verdict(d.relation) + ui.prob(d.headline) + (stale ? '<span class="c-decision__flag">' + ui.tag('逻辑已更新', 'info') + '</span>' : '') + '</header>' +
      '<p class="c-decision__thesis"><span class="c-decision__label">你写过：</span>' + esc(d.thesisStatement) + '</p>' + evidenceLine(d) +
      '<p class="c-decision__meta">' + esc(d.event.formType) + ' · ' + F.dateTime(d.event.publishedAt) + ' · ' + esc(d.event.title.replace(/^[^:]+:\s*/, '')) + '</p>' +
      cardActions(d, o.menuOpen) + '</article>';
  };
  var ACTION_LABEL = { still_valid: '仍然成立', revise: '修正逻辑', exit_intent: '准备卖出', ignore: '忽略', reopen: '重新打开' };
  P.ACTION_LABEL = ACTION_LABEL;
  function processedRow(d) {
    var a = d.action;
    return '<li class="c-processed"><div class="c-processed__main"><div class="c-processed__line">' + ui.market(d.instrument.market) + ' <span class="u-mono">' + esc(d.instrument.symbol) + '</span> ' +
      ui.verdict(d.relation) + ' <span class="u-text-2">' + esc(ACTION_LABEL[a.action]) + (a.note ? ' · ' + esc(a.note) : '') + '</span></div>' +
      '<div class="u-small u-muted">' + F.dateTime(a.actedAt) + '</div></div>' + ui.button('重新打开', { variant: 'text', action: 'reopen', arg: d.decisionId }) + '</li>';
  }
  function groupBlock(title, count, bodyHtml, open) {
    return '<details class="c-group"' + (open ? ' open' : '') + '><summary class="c-group__summary">' + icon('chevron-right') + esc(title) + '（' + count + '）</summary><div class="c-group__body">' + bodyHtml + '</div></details>';
  }

  pages.today = function (c) {
    var inbox = c.inbox, s = inbox.summary, st = inbox.dataStatus;
    var date = F.dateLong(P.now) + ' ' + F.weekday(P.now) + ' · 美股 ' + MARKET_STATE[st.marketState];
    var scanBtn = c.scanning ? ui.button('取消扫描', { variant: 'secondary', action: 'scan-cancel' }) :
      ui.button('立即扫描', { variant: 'primary', action: 'scan-start', disabled: c.scanDisabled, title: c.scanDisabled || null });
    var sub = !inbox.lastScan ? '尚未扫描' : (inbox.lastScan.status === 'failed' ? '上次扫描失败 ' : '上次扫描 ') + F.time(inbox.lastScan.finishedAt);
    var head = function (title, hiddenH1) {
      return '<header class="p-page__head"><div><p class="p-page__eyebrow">' + esc(date) + '</p>' + (title ? '<h1 class="p-page__title">' + esc(title) + '</h1>' : hiddenH1 ? '<h1 class="u-visually-hidden">今日</h1>' : '') + '</div>' +
        '<div class="p-page__actions"><span class="p-page__sub">' + esc(sub) + '</span>' + scanBtn + '</div></header>';
    };
    if (c.loading) {
      return '<section class="p-today">' + head('今天有哪些事需要你看一眼') + ui.skeletonCards(3) + '</section>';
    }
    var progress = c.progress ? '<div class="c-card p-today__scan"><div class="u-row u-row--between"><strong>正在扫描</strong><span class="u-small u-muted">' + esc(c.progress.message) + '</span></div>' +
      ui.progress(c.progress.done, c.progress.total, '判定进度', c.progress.done + ' / ' + c.progress.total) + '</div>' : '';
    var processed = inbox.processed.length ? groupBlock('已处理', inbox.processed.length, '<ul>' + inbox.processed.map(processedRow).join('') + '</ul>', false) : '';

    if (s.pendingCount === 0 && s.uncertainCount === 0 && !inbox.lastScan) {
      if (inbox.setup.holdings === 0) {
        return '<section class="p-today">' + head(null, true) + ui.empty({ title: '先添加第一只标的', text: '在“持仓”里添加你关注的美股，并为它写下买入的理由。系统只会盯着有逻辑的标的。',
          action: '<a class="c-button c-button--primary" href="#/holdings">去持仓</a>' }) + '</section>';
      }
      return '<section class="p-today">' + head(null, true) + ui.empty({ title: '还没有扫描过', text: '已有 ' + inbox.setup.scannableInstruments + ' 只标的写了逻辑。点“立即扫描”，系统会读取它们最近的披露，看看有没有动摇你判断的内容。' }) + '</section>';
    }
    if (s.pendingCount === 0) {
      var ls = inbox.lastScan;
      var st2 = ls ? '已检查 ' + ls.stats.instruments + ' 只标的、' + ls.stats.filings + ' 份披露、' + ls.stats.passages + ' 个段落，上次扫描 ' + F.dateTime(ls.finishedAt) : '';
      var unc = inbox.uncertain.length ? groupBlock('系统拿不准的', inbox.uncertain.length, '<div class="p-today__list">' + inbox.uncertain.map(function (d) { return pages.decisionCard(d); }).join('') + '</div>', false) : '';
      return '<section class="p-today p-today--empty">' + head(null) + progress + ui.empty({ display: true, title: '今天没有需要处理的变化', text: st2 }) + unc + processed + '</section>';
    }
    var shown = inbox.items.slice(0, 5), rest = inbox.items.slice(5);
    var list = '<div class="p-today__list">' + shown.map(function (d) { return pages.decisionCard(d, { menuOpen: c.openMenu === d.decisionId }); }).join('') + '</div>' +
      (rest.length ? groupBlock('其余 ' + rest.length + ' 条', rest.length, '<div class="p-today__list">' + rest.map(function (d) { return pages.decisionCard(d); }).join('') + '</div>', false).replace('（' + rest.length + '）', '') : '');
    var unc2 = inbox.uncertain.length ? groupBlock('系统拿不准的 ' + inbox.uncertain.length + ' 条', inbox.uncertain.length, '<div class="p-today__list">' + inbox.uncertain.map(function (d) { return pages.decisionCard(d, { menuOpen: c.openMenu === d.decisionId }); }).join('') + '</div>', c.openUncertain).replace('（' + inbox.uncertain.length + '）', '') : '';
    return '<section class="p-today">' + head('今天有 ' + s.pendingCount + ' 件事需要你看一眼') + progress + list + unc2 + processed + '</section>';
  };

  /* ---------- 证据抽屉 ---------- */
  function passageHtml(e) {
    if (e.kind === 'sentence') {
      return esc(e.passageText.slice(0, e.sentenceStart)) + '<mark class="c-evidence-mark">' + esc(e.passageText.slice(e.sentenceStart, e.sentenceEnd)) + '</mark>' + esc(e.passageText.slice(e.sentenceEnd));
    }
    return esc(e.passageText);
  }
  var PROB_ROWS = [['relevant', '相关'], ['against', '削弱'], ['contradicts', '矛盾'], ['killMet', '失效条件'], ['supports', '支持']];
  pages.drawer = function (d) {
    var e = d.evidence, ins = d.instrument, ev = d.event;
    var isDemo = /^us:0009990/.test(ev.eventId);
    var note = d.contentStatus === 'title_only' ? '仅依据标题判定' : e.kind === 'passage' ? '未能定位到单句，以下为整段原文' : '';
    var head = ui.verdict(d.relation) + ui.prob(d.headline);
    var body = '<div><h2 class="c-drawer__title" id="drawer-title" tabindex="-1"><span class="u-mono">' + esc(ins.symbol) + '</span> · ' + esc(ins.name) + '</h2></div>' +
      '<section class="c-drawer__sec"><h3>披露</h3>' + ui.kv([['标题', ev.title], ['类型', ev.formType], ['发布时间', F.dateTime(ev.publishedAt)], ['来源文件', FILE_PART[e.filePart] || e.filePart]]) +
      (isDemo ? '<p class="c-note">这是演示数据，没有真实原文。</p>' : '<a class="c-link" href="' + esc(ev.url) + '" rel="noopener" data-action="open-external" data-arg="' + esc(ev.url) + '">在 SEC 查看原文' + icon('external-link') + '</a><p class="c-note">将用系统浏览器打开 www.sec.gov</p>') + '</section>' +
      '<section class="c-drawer__sec"><h3>原文段落</h3>' + (note ? '<p class="c-note">' + esc(note) + '</p>' : '') + '<p class="c-passage">' + passageHtml(e) + '</p></section>' +
      '<section class="c-drawer__sec"><h3>你的逻辑</h3><blockquote class="c-quote">' + esc(d.thesisStatement) + '</blockquote>' +
      (d.killCondition ? '<p class="u-small u-text-2">失效条件：' + esc(d.killCondition) + '</p>' : '<p class="u-small u-muted">未设置失效条件</p>') +
      (d.thesisCurrentVersion > d.thesisVersion ? '<p class="u-small u-muted">判定时是第 ' + d.thesisVersion + ' 版，你已将逻辑更新到第 ' + d.thesisCurrentVersion + ' 版。</p>' : '') + '</section>' +
      '<section class="c-drawer__sec"><h3>概率</h3>' + ui.barlist(PROB_ROWS.map(function (r) {
        var v = d.probabilities[r[0]];
        return { label: r[1], value: v, fraction: v, text: F.prob(v) };
      }), '五个问题的概率') + '</section>' +
      '<p class="c-note">' + esc((d.engine === 'jevdb' ? 'JEVDB 加速' : 'Jev 直连') + ' · ' + d.modelId + ' · 问题集 ' + d.questionSetVersion) + '</p>';
    var foot;
    if (d.action && d.action.action !== 'reopen') {
      foot = '<p>已处理：<strong>' + esc(ACTION_LABEL[d.action.action]) + '</strong>' + (d.action.note ? ' · ' + esc(d.action.note) : '') + ' · ' + F.dateTime(d.action.actedAt) + '</p>' +
        '<div class="c-drawer__actions">' + ui.button('重新打开', { variant: 'secondary', action: 'reopen', arg: d.decisionId }) + '</div>';
    } else {
      foot = ui.field({ id: 'act-note', label: '备注（可选）', placeholder: '写一句话，之后复盘时会看到', max: 200, input: 'note' }) +
        '<div class="c-drawer__actions">' + ui.button('仍然成立', { variant: 'primary', action: 'act', arg: d.decisionId + ':still_valid' }) +
        ui.button('修正逻辑', { variant: 'secondary', action: 'act', arg: d.decisionId + ':revise' }) +
        ui.button('准备卖出', { variant: 'secondary', action: 'act', arg: d.decisionId + ':exit_intent' }) +
        ui.button('忽略', { variant: 'text', action: 'act', arg: d.decisionId + ':ignore' }) + '</div>';
    }
    return ui.drawer({ head: head, body: body, foot: foot });
  };
  pages.drawerError = function (err) {
    return ui.drawer({ head: '', body: '<h2 class="c-drawer__title" id="drawer-title" tabindex="-1">无法显示</h2>' + ui.banner('danger', err.message) });
  };

  /* ---------- 持仓 ---------- */
  var HOLD_STATUS = { guarded: ['守护中', 'ok'], attention: ['有待处理', 'warn'], unguarded: ['没有逻辑', 'none'] };
  function thesisCard(t) {
    var ld = t.lastDecision;
    return '<div class="c-thesis"><p>' + esc(t.statement) + '</p>' + (t.killCondition ? '<p class="c-thesis__kill">失效条件：' + esc(t.killCondition) + '</p>' : '') +
      '<div class="c-thesis__meta"><span>第 ' + t.version + ' 版 · 共 ' + t.versionCount + ' 版</span><span>创建于 ' + F.date(t.createdAt) + '</span>' +
      (ld ? '<span>最近判定</span>' + ui.verdict(ld.relation) : '<span>还没有判定</span>') + '</div>' +
      '<div class="c-thesis__actions">' + ui.button('编辑', { variant: 'text', small: true, action: 'editor-open', arg: t.thesisId }) +
      ui.button('版本历史', { variant: 'text', small: true, action: 'noop' }) + ui.button('归档', { variant: 'text', small: true, action: 'noop' }) + '</div></div>';
  }
  var TEMPLATES = ['管理层持续回购并维持分红', '核心产品收入保持两位数增长', '控股股东长期持股'];
  pages.editor = function (o) {
    return '<div class="c-editor" aria-label="逻辑编辑器">' +
      ui.field({ id: 'statement', label: '逻辑', textarea: true, value: o.statement, error: o.errorStatement, max: 500, count: o.count != null ? o.count : null,
        help: '系统按字面理解你写的内容。数字和比例请写进“失效条件”，例如“减持超过 2%”。', placeholder: '写下你买入它的理由，一句话说清楚', input: 'statement' }) +
      ui.field({ id: 'kill', label: '失效条件（可选）', value: o.kill, max: 300, placeholder: '例如：控股股东减持超过 2%', input: 'kill' }) +
      '<div class="c-editor__actions">' + ui.button('保存', { variant: 'primary', action: 'editor-save' }) + ui.button('取消', { variant: 'text', action: 'editor-cancel' }) + '</div></div>';
  };
  pages.holdingRow = function (h, open, detailHtml) {
    var i = h.instrument, stt = HOLD_STATUS[h.status], watch = Number(h.quantity) === 0;
    var dc = h.dayChangePct, up = dc > 0, cls = dc == null ? '' : up ? 'u-up' : dc < 0 ? 'u-down' : '';
    var row = '<tr class="c-table__click' + (open ? ' is-selected' : '') + '" data-action="row-toggle" data-arg="' + esc(i.symbol) + '">' +
      '<td><div class="c-table__symbol">' + ui.iconButton(open ? 'chevron-down' : 'chevron-right', (open ? '收起 ' : '展开 ') + i.symbol, { small: true, expanded: open ? 'true' : 'false', 'aria-controls': open ? 'detail-' + i.symbol : null }) +
      '<div class="c-table__symbol-text"><span><strong class="u-mono">' + esc(i.symbol) + '</strong> <span class="u-text-2">' + esc(i.name) + '</span></span><span class="c-table__sub">' + esc(i.nameZh || '') + ' · ' + esc(i.exchange) + '</span></div></div></td>' +
      '<td class="c-table__num">' + (watch ? '关注' : F.qty(h.quantity)) + '</td>' +
      '<td class="c-table__num">' + (h.avgCost ? F.money(h.avgCost) : '—') + '</td>' +
      '<td class="c-table__num">' + (h.lastClose != null ? F.money(h.lastClose) : '—') + '</td>' +
      '<td class="c-table__num ' + cls + '">' + (dc != null ? F.pct(dc, 1, true) : '—') + '</td>' +
      '<td class="c-table__num">' + (watch ? '—' : F.money(h.marketValue)) + '</td>' +
      '<td class="c-table__num">' + h.thesisCount + ' 条</td>' +
      '<td>' + ui.tag(stt[0], stt[1]) + (h.pendingCount ? ' <span class="u-small u-muted">' + h.pendingCount + ' 条</span>' : '') + '</td></tr>';
    if (open) { row += '<tr class="c-table__detail" id="detail-' + esc(i.symbol) + '"><td colspan="8">' + detailHtml + '</td></tr>'; }
    return row;
  };

  pages.holdings = function (c) {
    var holdings = c.holdings.items;
    var toolbar = '<div class="p-holdings__toolbar"><div class="u-grow"><div class="c-combobox">' + ui.search({ id: 'add-instrument', label: '添加标的', placeholder: '代码、英文名或中文名', value: c.searchText || '', input: 'search', expanded: c.search ? 'true' : 'false' }) +
      (c.search ? '<div class="c-combobox__list" id="add-instrument-list" role="listbox" aria-label="搜索结果">' + (c.search.items.length ? c.search.items.map(function (it, k) {
        var have = holdings.some(function (h) { return h.instrument.instrumentId === it.instrumentId; });
        return '<div class="c-combobox__option' + (k === 0 ? ' is-active' : '') + '" role="option" aria-selected="' + (k === 0) + '"><span class="u-mono"><strong>' + esc(it.symbol) + '</strong></span><span class="u-grow u-truncate">' + esc(it.name) + ' · ' + esc(it.nameZh || '') + '</span><span class="u-small u-muted">' + esc(it.exchange) + '</span>' + (have ? ui.tag('已添加') : '') + '</div>';
      }).join('') : '<div class="c-combobox__empty">没有找到匹配的美股标的</div>') + '</div>' : '') + '</div>' +
      ui.button('刷新行情', { variant: 'secondary', icon: 'refresh-cw', action: 'prices-refresh' }) + '</div><span class="p-page__sub">行情截至 ' + F.date(c.holdings.items.length ? holdings[0].lastCloseDate : P.now) + '</span></div>';
    var head = '<header class="p-page__head"><div><h1 class="p-page__title">持仓</h1></div></header>';
    if (!holdings.length) {
      return '<section class="p-holdings">' + head + toolbar + ui.empty({ title: '先添加第一只标的', text: '搜索你持有或关注的美股，然后为它写下买入的理由。没有逻辑的标的不会被扫描。' }) + '</section>';
    }
    var rows = holdings.map(function (h) {
      var open = c.expanded === h.instrument.symbol;
      var detail = '';
      if (open) {
        var ths = c.theses || [];
        detail = ths.map(function (t) { return c.editing === t.thesisId ? pages.editor({ statement: t.statement, kill: t.killCondition || '' }) : thesisCard(t); }).join('');
        if (c.banner) { detail = c.banner + detail; }
        if (c.editor && !c.editing) { detail += pages.editor(c.editor); }
        if (!ths.length && !c.editor) {
          detail += '<div class="c-card"><h2 class="c-card__title">没有逻辑的持仓不会被守护</h2><p class="u-text-2">写一条你买入它的理由，系统才会拿它去对照新披露。可以先从下面的模板开始，再改成你自己的话。</p>' +
            '<div class="c-templates">' + TEMPLATES.map(function (t) { return ui.button(t, { variant: 'secondary', small: true, action: 'template', arg: t }); }).join('') + '</div></div>';
        } else if (!c.editor) {
          detail += '<div class="c-editor__actions">' + ui.button('添加逻辑', { variant: 'secondary', icon: 'plus', action: 'editor-new', disabled: ths.length >= 5, title: ths.length >= 5 ? '每只股票最多 5 条有效逻辑' : null }) + '</div>';
        }
      }
      return pages.holdingRow(h, open, detail);
    }).join('');
    var table = '<div class="c-card c-card--flush"><div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">标的</th><th scope="col" class="c-table__num">持仓</th><th scope="col" class="c-table__num">成本</th>' +
      '<th scope="col" class="c-table__num">最近收盘</th><th scope="col" class="c-table__num">日涨跌</th><th scope="col" class="c-table__num">市值</th><th scope="col" class="c-table__num">逻辑</th><th scope="col">状态</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';
    return '<section class="p-holdings">' + head + toolbar + table + '</section>';
  };
})(window.Proto = window.Proto || {});
