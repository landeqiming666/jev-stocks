/* 浏览器入口：渲染、事件委托、控制条。只在浏览器里运行；Node 检查不加载这个文件。 */
(function (P) {
  'use strict';
  var root, cur;

  function setBodyStage(s) {
    document.body.classList.toggle('proto-staged', !!(s.w || s.h));
  }

  function render() {
    cur = P.parseHash(location.hash);
    var html;
    try {
      html = P.build(cur.route, cur.state, { drawer: cur.drawer, platform: cur.platform });
    } catch (e) {
      root.innerHTML = '<pre class="c-card">' + P.esc(e.message) + '</pre>';
      return;
    }
    if (cur.w || cur.h) {
      html = '<div class="proto-stage" style="--stage-w:' + (cur.w || 1280) + 'px;--stage-h:' + (cur.h || 820) + 'px">' + html + '</div>';
    }
    root.innerHTML = html;
    setBodyStage(cur);
    document.documentElement.setAttribute('data-platform', cur.platform);
    var drawerTitle = document.getElementById('drawer-title');
    if (drawerTitle && P.focusDrawer) { drawerTitle.focus(); P.focusDrawer = false; }
    if (!cur.bare && P.controls) { P.controls.render(cur); }
  }

  function go(patch) {
    var next = Object.assign({}, cur, patch);
    var h = P.makeHash(next);
    if (h === location.hash) { render(); } else { location.hash = h; }
  }
  P.go = go;

  function toast(kind, text) {
    P.runtime.toast = P.ui.toast(kind, text);
    render();
    setTimeout(function () { P.runtime.toast = null; if (kind !== 'error') { render(); } }, 4000);
  }

  function closeDrawer() {
    if (!cur) { return; }
    go(P.drawerClosePatch(cur));
  }

  var actions = {
    'drawer-open': function (arg) { P.focusDrawer = true; go({ drawer: drawerFor(arg) }); },
    'drawer-close': closeDrawer,
    'act': function (arg) {
      var a = arg.split(':'); P.runtime.acted[a[0]] = { action: a[1] };
      P.runtime.openMenu = null;
      if (cur.drawer) { go({ drawer: '' }); }
      toast('ok', '已处理：' + P.ACTION_LABEL[a[1]]);
    },
    'reopen': function (arg) { P.runtime.acted[arg] = { action: 'reopen' }; if (cur.drawer) { go({ drawer: '' }); } toast('ok', '已重新打开'); },
    'menu-toggle': function (arg) { P.runtime.openMenu = P.runtime.openMenu === arg.replace('menu-', '') ? null : arg.replace('menu-', ''); render(); var m = document.getElementById(arg); if (m && P.runtime.openMenu) { m.hidden = false; } },
    'row-toggle': function (arg) { P.runtime.expanded = P.runtime.expanded === arg ? null : arg; go({ state: 'default' }); },
    'tab': function (arg) { P.runtime.tab = arg; render(); },
    'segment': function (arg) {
      var a = arg.split(':'); P.runtime[a[0]] = a[1]; render();
    },
    'toggle-table': function () { P.runtime.table = !P.runtime.table; render(); },
    'run-open': function (arg) { go({ state: 'detail' }); },
    'scan-start': function () { toast('ok', '原型：这里会调用 scan.start'); },
    'scan-cancel': function () { toast('ok', '原型：这里会调用 scan.cancel'); },
    'advance': function () { go({ state: 'advanced' }); },
    'place-order': function () { toast('ok', '原型：这里会调用 paper.order.place'); },
    'toast-close': function () { P.runtime.toast = null; render(); },
    'noop': function () { toast('ok', '原型：该操作在 React 版本里实现'); },
    'open-external': function (arg) { toast('ok', '原型：将用系统浏览器打开 ' + arg); }
  };
  function drawerFor(decisionId) {
    var all = window.MOCK.examples['decision.get'];
    var found = Object.keys(all).filter(function (k) { return all[k].result && all[k].result.decisionId === decisionId; })[0];
    if (found) { return found; }
    return 'overturn';
  }

  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) {
      if (P.runtime.openMenu) { P.runtime.openMenu = null; render(); }
      return;
    }
    if (el.tagName === 'A' && el.getAttribute('data-action') === 'open-external') { e.preventDefault(); }
    var fn = actions[el.getAttribute('data-action')];
    if (fn) { if (el.type !== 'radio') { e.stopPropagation(); } fn(el.getAttribute('data-arg') || ''); }
  });
  document.addEventListener('input', function (e) {
    if (e.target.getAttribute('data-input') === 'qty') { P.runtime.qty = e.target.value.replace(/[^\d]/g, ''); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && cur && (cur.drawer || (cur.route === 'scan' && cur.state === 'detail'))) { closeDrawer(); }
  });
  window.addEventListener('hashchange', render);

  document.addEventListener('DOMContentLoaded', function () {
    root = document.getElementById('root');
    P.now = (window.MOCK.examples['app.bootstrap'].ready.result.now) || P.now;
    render();
  });
})(window.Proto = window.Proto || {});
