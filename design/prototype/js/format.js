/* 格式化。时区固定为 Asia/Shanghai，这样截图和测试与运行机器的时区无关。
   React 的 lib/format.ts 实现同样的函数；那边的时区取用户本机，测试里用环境变量 TZ 固定。 */
(function (P) {
  'use strict';
  var TZ = 'Asia/Shanghai';
  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  var fmtParts = new Intl.DateTimeFormat('en-US', {
    timeZone: TZ, year: 'numeric', month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  });

  function parts(iso) {
    var o = {};
    fmtParts.formatToParts(new Date(iso)).forEach(function (p) { o[p.type] = p.value; });
    return { y: +o.year, m: +o.month, d: +o.day, H: o.hour, M: o.minute };
  }
  function dateOnly(s) { var a = String(s).split('-'); return { y: +a[0], m: +a[1], d: +a[2] }; }
  function isDateOnly(s) { return /^\d{4}-\d{2}-\d{2}$/.test(String(s)); }
  function nowYear() { return parts(P.now).y; }
  function group(intStr) { return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  function fixed(value, places) {
    var n = Number(value);
    if (!isFinite(n)) { return '—'; }
    var s = Math.abs(n).toFixed(places);
    var bits = s.split('.');
    return (n < 0 ? '-' : '') + group(bits[0]) + (bits[1] ? '.' + bits[1] : '');
  }

  P.now = P.now || '2026-11-02T00:35:00Z';
  P.tz = TZ;

  P.fmt = {
    dateTime: function (iso) {
      var p = parts(iso);
      return (p.y === nowYear() ? '' : p.y + '年') + p.m + '月' + p.d + '日 ' + p.H + ':' + p.M;
    },
    time: function (iso) { var p = parts(iso); return p.H + ':' + p.M; },
    date: function (s) {
      var p = isDateOnly(s) ? dateOnly(s) : parts(s);
      return (p.y === nowYear() ? '' : p.y + '年') + p.m + '月' + p.d + '日';
    },
    dateLong: function (s) {
      var p = isDateOnly(s) ? dateOnly(s) : parts(s);
      return p.y + '年' + p.m + '月' + p.d + '日';
    },
    weekday: function (s) {
      var p = isDateOnly(s) ? dateOnly(s) : parts(s);
      return '星期' + WEEK[new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay()];
    },
    isoDate: function (s) {
      var p = isDateOnly(s) ? dateOnly(s) : parts(s);
      return p.y + '-' + (p.m < 10 ? '0' : '') + p.m + '-' + (p.d < 10 ? '0' : '') + p.d;
    },
    money: function (dec, places) { return '$' + fixed(dec, places == null ? 2 : places); },
    signedMoney: function (dec) { var n = Number(dec); return (n > 0 ? '+' : n < 0 ? '-' : '') + '$' + fixed(Math.abs(n), 2); },
    num: function (v, places) { return fixed(v, places == null ? 2 : places); },
    int: function (v) { return fixed(v, 0); },
    qty: function (dec) {
      var n = Number(dec);
      return Math.abs(n - Math.round(n)) < 1e-9 ? fixed(n, 0) : fixed(n, 4);
    },
    price: function (v) { return fixed(v, 2); },
    price4: function (dec) { return fixed(dec, 4); },
    pct: function (v, places, signed) {
      var n = Number(v) * 100;
      var s = fixed(Math.abs(n), places == null ? 1 : places) + '%';
      return (signed ? (n > 0 ? '+' : n < 0 ? '-' : '') : (n < 0 ? '-' : '')) + s;
    },
    prob: function (v) { return Number(v).toFixed(2); },
    tokens: function (v) { return fixed(v, 0); },
    usd6: function (dec) { return '$' + Number(dec).toFixed(4); }
  };
})(window.Proto = window.Proto || {});
