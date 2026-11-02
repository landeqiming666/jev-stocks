/* hash 路由：#/today?state=pending&drawer=overturn&platform=macos&bare=1&w=1280&h=820
   使用 hash 而不是真实查询串，这样从 file:// 打开时切换状态不会整页重新加载。 */
(function (P) {
  'use strict';
  var ROUTES = ['today', 'holdings', 'trading', 'risk', 'scan', 'settings', 'v1'];
  P.ROUTES = ROUTES;

  P.parseHash = function (hash) {
    var h = String(hash || '').replace(/^#\/?/, '');
    var q = h.indexOf('?');
    var path = q >= 0 ? h.slice(0, q) : h;
    var params = {};
    if (q >= 0) {
      h.slice(q + 1).split('&').forEach(function (kv) {
        if (!kv) { return; }
        var i = kv.indexOf('=');
        params[decodeURIComponent(i >= 0 ? kv.slice(0, i) : kv)] = i >= 0 ? decodeURIComponent(kv.slice(i + 1)) : '1';
      });
    }
    var route = ROUTES.indexOf(path) >= 0 ? path : 'today';
    return { route: route, state: params.state || '', drawer: params.drawer || '', platform: params.platform === 'windows' ? 'windows' : 'macos',
      bare: params.bare === '1', w: params.w ? +params.w : 0, h: params.h ? +params.h : 0 };
  };

  P.makeHash = function (s) {
    var q = [];
    if (s.state) { q.push('state=' + encodeURIComponent(s.state)); }
    if (s.drawer) { q.push('drawer=' + encodeURIComponent(s.drawer)); }
    if (s.platform && s.platform !== 'macos') { q.push('platform=' + s.platform); }
    if (s.bare) { q.push('bare=1'); }
    if (s.w) { q.push('w=' + s.w); }
    if (s.h) { q.push('h=' + s.h); }
    return '#/' + s.route + (q.length ? '?' + q.join('&') : '');
  };

  P.drawerClosePatch = function (cur) {
    if (cur && cur.route === 'scan' && cur.state === 'detail') {
      return { state: '', drawer: '' };
    }
    return { drawer: '' };
  };
})(window.Proto = window.Proto || {});
