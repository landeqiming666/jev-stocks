/* 组件渲染函数：纯函数，输入数据，返回 HTML 字符串。DOM 结构与 docs/03-界面设计规范.md 第 5 节一致。
   React 组件必须输出同样的结构与类名。所有动态文字都经过 esc()。 */
(function (P) {
  'use strict';
  var icon = P.icon;
  var F = P.fmt;

  var esc = P.esc = function (s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };
  function attrs(o) {
    var s = '';
    if (!o) { return s; }
    Object.keys(o).forEach(function (k) {
      var v = o[k];
      if (v === false || v == null) { return; }
      s += v === true ? ' ' + k : ' ' + k + '="' + esc(v) + '"';
    });
    return s;
  }

  var ui = P.ui = {};

  /* ---- 按钮 ---- */
  ui.button = function (label, o) {
    o = o || {};
    var cls = 'c-button c-button--' + (o.variant || 'secondary') + (o.small ? ' c-button--sm' : '') + (o.loading ? ' is-loading' : '');
    var a = { type: 'button', 'class': cls, 'data-action': o.action, 'data-arg': o.arg, id: o.id, title: o.title,
      disabled: o.disabled, 'aria-busy': o.loading ? 'true' : null, 'aria-expanded': o.expanded, 'aria-controls': o['aria-controls'], 'aria-haspopup': o.haspopup };
    return '<button' + attrs(a) + '>' + (o.icon ? icon(o.icon) : '') + (label ? esc(label) : '') + '</button>';
  };
  ui.iconButton = function (name, label, o) {
    o = o || {};
    var a = { type: 'button', 'class': 'c-button c-button--icon' + (o.small ? ' c-button--sm' : ''), 'aria-label': label, title: label,
      'data-action': o.action, 'data-arg': o.arg, id: o.id, 'aria-expanded': o.expanded, 'aria-controls': o['aria-controls'], 'aria-haspopup': o.haspopup, disabled: o.disabled };
    return '<button' + attrs(a) + '>' + icon(name) + '</button>';
  };

  /* ---- 标签 ---- */
  var V = {
    overturn: { cls: 'over', label: '推翻', icon: 'alert-triangle' },
    weaken: { cls: 'weak', label: '削弱', icon: 'arrow-down' },
    support: { cls: 'hold', label: '支持', icon: 'check' },
    none: { cls: 'none', label: '无关', icon: 'minus' },
    uncertain: { cls: 'unsure', label: '待确认', icon: 'help-circle' }
  };
  P.verdictMeta = V;
  ui.verdict = function (rel) {
    var v = V[rel];
    return '<span class="c-verdict c-verdict--' + v.cls + '">' + icon(v.icon) + v.label + '</span>';
  };
  ui.prob = function (n) {
    return '<span class="c-prob" title="Jev 回答“是”的概率">' + F.prob(n) + '</span>';
  };
  ui.market = function (m) { return '<span class="c-market">' + ({ us: '美股', cn: 'A股', hk: '港股' }[m] || esc(m)) + '</span>'; };
  ui.tag = function (text, kind, ic) {
    return '<span class="c-tag' + (kind ? ' c-tag--' + kind : '') + '">' + (ic ? icon(ic) : '') + esc(text) + '</span>';
  };
  ui.engine = function (e) {
    var label = e.active === 'jevdb' ? 'JEVDB 加速' : e.active === 'jev_direct' ? 'Jev 直连' : '未配置';
    var degraded = e.state === 'degraded';
    return '<span class="c-engine' + (degraded ? ' is-degraded' : '') + '" title="' + esc(degraded ? '已从 JEVDB 降级为 Jev 直连（同一模型）' : '语义引擎') + '">' +
      (degraded ? icon('info') : '') + esc(label) + ' · ' + esc(e.modelId) + '</span>';
  };

  /* ---- 提示条、Toast ---- */
  ui.banner = function (kind, text, o) {
    o = o || {};
    var ic = kind === 'danger' ? 'alert-triangle' : kind === 'warn' ? 'alert-triangle' : 'info';
    var role = kind === 'danger' ? 'alert' : 'status';
    return '<div class="c-banner c-banner--' + kind + '" role="' + role + '"' + (o.id ? ' id="' + o.id + '"' : '') + '>' +
      icon(ic) + '<div class="c-banner__body">' + esc(text) + '</div>' + (o.actions ? '<div class="c-banner__actions">' + o.actions + '</div>' : '') + '</div>';
  };
  ui.toast = function (kind, text) {
    return '<div class="c-toast' + (kind === 'error' ? ' c-toast--error' : '') + '" role="' + (kind === 'error' ? 'alert' : 'status') + '">' +
      icon(kind === 'error' ? 'alert-triangle' : 'check') + '<div class="c-toast__text">' + esc(text) + '</div>' +
      ui.iconButton('x', '关闭提示', { small: true, action: 'toast-close' }) + '</div>';
  };

  /* ---- 表单 ---- */
  ui.field = function (o) {
    var id = 'f-' + o.id;
    var tag = o.textarea ? 'textarea' : 'input';
    var describedby = [];
    if (o.help) { describedby.push(id + '-help'); }
    if (o.error) { describedby.push(id + '-err'); }
    var common = { id: id, name: o.id, 'class': o.textarea ? 'c-textarea' : 'c-input' + (o.num ? ' c-input--num' : ''),
      placeholder: o.placeholder, 'aria-describedby': describedby.join(' ') || null, 'aria-invalid': o.error ? 'true' : null,
      type: o.textarea ? null : (o.type || 'text'), value: o.textarea ? null : o.value, disabled: o.disabled, inputmode: o.inputmode,
      'data-input': o.input };
    var control = o.textarea ? '<textarea' + attrs(common) + '>' + esc(o.value || '') + '</textarea>' : '<input' + attrs(common) + '>';
    var meta = '';
    if (o.help || o.max) {
      var len = o.value ? Array.from(String(o.value).trim()).length : 0;
      meta = '<div class="c-field__meta"><span' + (o.help ? ' id="' + id + '-help" class="c-field__help"' : '') + '>' + esc(o.help || '') + '</span>' +
        (o.max ? '<span class="c-field__count">' + (o.count != null ? o.count : len) + ' / ' + o.max + '</span>' : '') + '</div>';
    }
    return '<div class="c-field' + (o.error ? ' has-error' : '') + '"><label class="c-field__label" for="' + id + '">' + esc(o.label) + '</label>' +
      control + meta + (o.error ? '<p class="c-field__error" id="' + id + '-err" role="alert">' + esc(o.error) + '</p>' : '') + '</div>';
  };
  ui.search = function (o) {
    return '<div class="c-search">' + icon('search') + '<input class="c-input" type="search" id="' + o.id + '" aria-label="' + esc(o.label) + '" placeholder="' + esc(o.placeholder) +
      '" value="' + esc(o.value || '') + '" data-input="' + (o.input || '') + '"' + (o.expanded != null ? ' role="combobox" aria-expanded="' + o.expanded + '"' + (o.expanded === 'true' ? ' aria-controls="' + o.id + '-list"' : '') : '') + '></div>';
  };
  ui.radio = function (name, value, title, hint, checked) {
    return '<label class="c-radio' + (checked ? ' is-checked' : '') + '"><input type="radio" name="' + name + '" value="' + value + '"' + (checked ? ' checked' : '') +
      ' data-action="radio" data-arg="' + name + ':' + value + '"><span><span class="c-radio__title">' + esc(title) + '</span><br><span class="c-radio__hint">' + esc(hint) + '</span></span></label>';
  };
  ui.segmented = function (name, items, active, label) {
    return '<div class="c-segmented" role="radiogroup" aria-label="' + esc(label) + '">' + items.map(function (it) {
      var on = it.value === active;
      return '<button type="button" class="c-segmented__item' + (on ? ' is-active' : '') + '" role="radio" aria-checked="' + on + '" data-action="segment" data-arg="' + name + ':' + it.value + '"' + (it.disabled ? ' disabled' : '') + (it.title ? ' title="' + esc(it.title) + '"' : '') + '>' + esc(it.label) + '</button>';
    }).join('') + '</div>';
  };

  /* ---- 空状态、骨架、进度 ---- */
  ui.empty = function (o) {
    return '<div class="c-empty' + (o.display ? ' c-empty--display' : '') + (o.left ? ' c-empty--left' : '') + '"><div class="c-empty__art" aria-hidden="true"></div>' +
      '<' + (o.display ? 'h1' : 'h2') + ' class="c-empty__title">' + esc(o.title) + '</' + (o.display ? 'h1' : 'h2') + '>' +
      (o.text ? '<p class="c-empty__text">' + esc(o.text) + '</p>' : '') + (o.action || '') + '</div>';
  };
  ui.skeletonCards = function (n) {
    var s = '';
    for (var i = 0; i < n; i++) { s += '<div class="c-skeleton c-skeleton--card"></div>'; }
    return '<div class="c-skeleton-stack" aria-busy="true" aria-label="加载中">' + s + '</div>';
  };
  ui.progress = function (done, total, left, right, tone) {
    var pct = total > 0 ? Math.min(100, Math.round(done / total * 1000) / 10) : 0;
    return '<div class="c-progress' + (tone ? ' is-' + tone : '') + '"><div class="c-progress__label"><span>' + esc(left) + '</span><span class="u-mono">' + esc(right) + '</span></div>' +
      '<div class="c-progress__track" role="progressbar" aria-valuemin="0" aria-valuemax="' + total + '" aria-valuenow="' + done + '" aria-label="' + esc(left) + '"><span class="c-progress__fill" style="--w:' + pct + '%"></span></div></div>';
  };
  ui.metric = function (label, value, hint) {
    return '<div class="c-metric"><span class="c-metric__label">' + esc(label) + '</span><span class="c-metric__value">' + esc(value) + '</span>' +
      (hint ? '<span class="c-metric__hint">' + esc(hint) + '</span>' : '') + '</div>';
  };
  ui.kv = function (rows) {
    return '<dl class="c-kv">' + rows.map(function (r) { return '<dt>' + esc(r[0]) + '</dt><dd>' + (r[2] ? r[1] : esc(r[1])) + '</dd>'; }).join('') + '</dl>';
  };

  /* ---- 菜单 ---- */
  ui.menu = function (id, items) {
    return '<div class="c-menu" role="menu" id="' + id + '" hidden>' + items.map(function (it) {
      return '<button type="button" class="c-menu__item" role="menuitem" data-action="' + it.action + '" data-arg="' + esc(it.arg || '') + '">' + esc(it.label) + '</button>';
    }).join('') + '</div>';
  };

  /* ---- 条形与热力图 ---- */
  ui.barlist = function (rows, label) {
    return '<ul class="c-barlist" aria-label="' + esc(label) + '">' + rows.map(function (r) {
      var na = r.value == null;
      return '<li class="c-barlist__row"><span class="c-barlist__label">' + esc(r.label) + '</span><span class="c-barlist__track"><span class="c-barlist__fill" style="--w:' +
        (na ? 0 : Math.round(r.fraction * 1000) / 10) + '%"></span></span><span class="c-barlist__value' + (na ? ' is-na' : '') + '">' + (na ? '未设置' : esc(r.text)) + '</span></li>';
    }).join('') + '</ul>';
  };

  ui.heatmap = function (symbols, matrix) {
    var n = symbols.length, cell = 56, gap = 2, left = 56, top = 28;
    var w = left + n * (cell + gap), h = top + n * (cell + gap);
    var s = '<svg class="c-heatmap" role="img" aria-label="相关系数热图，' + n + ' 只标的" viewBox="0 0 ' + w + ' ' + h + '">';
    symbols.forEach(function (sym, i) {
      s += '<text class="c-heatmap__label" x="' + (left + i * (cell + gap) + cell / 2) + '" y="' + (top - 10) + '" text-anchor="middle">' + esc(sym) + '</text>';
      s += '<text class="c-heatmap__label" x="' + (left - 8) + '" y="' + (top + i * (cell + gap) + cell / 2 + 4) + '" text-anchor="end">' + esc(sym) + '</text>';
    });
    matrix.forEach(function (row, i) {
      row.forEach(function (v, j) {
        var diag = i === j;
        var k = v == null ? 0 : Math.round(Math.min(1, Math.abs(v)) * 70);
        var cls = 'c-heatmap__cell' + (diag ? ' is-diag' : v != null && v < 0 ? ' is-neg' : ' is-pos');
        var x = left + j * (cell + gap), y = top + i * (cell + gap);
        s += '<g class="' + cls + '"><title>' + esc(symbols[i] + ' 与 ' + symbols[j] + '：' + (v == null ? '无数据' : v.toFixed(2))) + '</title>' +
          '<rect class="c-heatmap__rect" x="' + x + '" y="' + y + '" width="' + cell + '" height="' + cell + '" rx="4" style="--k:' + k + '%"/>' +
          '<text class="c-heatmap__value" x="' + (x + cell / 2) + '" y="' + (y + cell / 2) + '">' + (v == null ? '—' : v.toFixed(2)) + '</text></g>';
      });
    });
    return s + '</svg>';
  };
  ui.legend = function () {
    return '<div class="c-legend"><span class="u-mono">−1</span><span class="c-legend__bar" aria-hidden="true"></span><span class="u-mono">+1</span><span>颜色深浅表示相关程度</span></div>';
  };

  /* ---- 抽屉外壳 ---- */
  ui.drawer = function (o) {
    return '<aside class="l-drawer c-drawer" role="dialog" aria-modal="false" aria-labelledby="drawer-title" id="drawer">' +
      '<div class="c-drawer__head"><div class="u-grow">' + (o.head || '') + '</div>' + ui.iconButton('x', '关闭', { action: 'drawer-close' }) + '</div>' +
      '<div class="c-drawer__body">' + o.body + '</div>' + (o.foot ? '<div class="c-drawer__foot">' + o.foot + '</div>' : '') + '</aside>';
  };
})(window.Proto = window.Proto || {});
