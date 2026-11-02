/* 原型专用：状态切换控制条（proto-* 类名）。?bare=1 时不渲染。React 不复制。 */
(function (P) {
  'use strict';
  var esc = P.esc;
  var collapsed = false;
  P.controls = {
    render: function (s) {
      var bar = document.getElementById('proto-bar');
      if (!bar) { bar = document.createElement('div'); bar.id = 'proto-bar'; document.body.appendChild(bar); }
      var states = P.STATES[s.route] || [];
      var drawers = P.DRAWERS[s.route];
      var cur = s.state || (states[0] && states[0][0]);
      bar.className = 'proto-bar';
      bar.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
      bar.innerHTML = '<div class="proto-bar__head"><span>原型控制条</span><button type="button" class="proto-bar__toggle" data-proto="collapse" aria-expanded="' + (!collapsed) + '">' + (collapsed ? '展开' : '收起') + '</button></div>' +
        '<div class="proto-bar__body">' +
        '<label>页面状态<select data-proto="state" aria-label="页面状态">' + states.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === cur ? ' selected' : '') + '>' + esc(x[1]) + '</option>'; }).join('') + '</select></label>' +
        (drawers ? '<label>证据抽屉<select data-proto="drawer" aria-label="证据抽屉">' + drawers.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === s.drawer ? ' selected' : '') + '>' + esc(x[1]) + '</option>'; }).join('') + '</select></label>' : '') +
        '<div class="proto-bar__row" role="group" aria-label="平台">' + ['macos', 'windows'].map(function (p) { return '<button type="button" data-proto="platform" data-v="' + p + '" class="' + (s.platform === p ? 'is-active' : '') + '">' + (p === 'macos' ? 'macOS' : 'Windows') + '</button>'; }).join('') + '</div>' +
        '<div class="proto-bar__row" role="group" aria-label="窗口尺寸">' + [[0, 0, '适应'], [1280, 820, '1280×820'], [1024, 700, '1024×700']].map(function (z) {
          var on = (s.w || 0) === z[0]; return '<button type="button" data-proto="size" data-w="' + z[0] + '" data-h="' + z[1] + '" class="' + (on ? 'is-active' : '') + '">' + z[2] + '</button>'; }).join('') + '</div>' +
        '<div class="proto-bar__hint">地址栏可直接写 <code>#/today?state=empty&amp;bare=1</code>。示例数据全部虚构。</div></div>';
      var wm = document.getElementById('proto-wm');
      if (!wm) { wm = document.createElement('div'); wm.id = 'proto-wm'; wm.className = 'proto-watermark'; wm.textContent = '原型示例数据'; document.body.appendChild(wm); }
    },
    bind: function () {
      document.addEventListener('change', function (e) {
        var k = e.target.getAttribute && e.target.getAttribute('data-proto');
        if (k === 'state') { P.go({ state: e.target.value }); }
        if (k === 'drawer') { P.focusDrawer = !!e.target.value; P.go({ drawer: e.target.value }); }
      });
      document.addEventListener('click', function (e) {
        var el = e.target.closest && e.target.closest('[data-proto]');
        if (!el) { return; }
        var k = el.getAttribute('data-proto');
        if (k === 'platform') { P.go({ platform: el.getAttribute('data-v') }); }
        if (k === 'size') { P.go({ w: +el.getAttribute('data-w'), h: +el.getAttribute('data-h') }); }
        if (k === 'collapse') { collapsed = !collapsed; P.go({}); }
      });
    }
  };
  P.controls.bind();
})(window.Proto = window.Proto || {});
