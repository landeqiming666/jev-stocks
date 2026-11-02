#!/usr/bin/env node
/* 用 Node 渲染原型的每个（页面，状态，抽屉），输出 JSON：{ "页面:状态[:抽屉]": "<html>" }。
   只加载纯函数脚本（不加载 app.js、proto-controls.js），不需要浏览器。
   用法：node scripts/proto_render.js [--platform windows]   由 scripts/check_proto.py 调用。 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', 'design', 'prototype');
const platform = process.argv.includes('--platform') ? process.argv[process.argv.indexOf('--platform') + 1] : 'macos';

const sandbox = { console };
sandbox.window = sandbox;
vm.createContext(sandbox);
['data/mock.js', 'js/icons.js', 'js/format.js', 'js/render-ui.js', 'js/render-pages.js', 'js/render-pages2.js', 'js/states.js'].forEach(function (f) {
  vm.runInContext(fs.readFileSync(path.join(root, f), 'utf8'), sandbox, { filename: f });
});
const P = sandbox.Proto;
P.now = sandbox.MOCK.examples['app.bootstrap'].ready.result.now;

const out = {};
const errors = [];
Object.keys(P.STATES).forEach(function (route) {
  P.STATES[route].forEach(function (s) {
    const key = route + ':' + s[0];
    try { out[key] = P.build(route, s[0], { platform: platform }); } catch (e) { errors.push(key + ' → ' + e.message); }
  });
});
(P.DRAWERS.today || []).forEach(function (d) {
  if (!d[0]) { return; }
  const key = 'today:pending:' + d[0];
  try { out[key] = P.build('today', 'pending', { drawer: d[0], platform: platform }); } catch (e) { errors.push(key + ' → ' + e.message); }
});

process.stdout.write(JSON.stringify({ pages: out, errors: errors, used: Array.from(collectExamples()) }));

function collectExamples() {
  // 返回 mock 里存在的 方法/示例 名，供 Python 检查“状态引用的示例都存在”
  const s = new Set();
  const ex = sandbox.MOCK.examples;
  Object.keys(ex).forEach(function (m) { Object.keys(ex[m]).forEach(function (n) { s.add(m + '/' + n); }); });
  return s;
}
