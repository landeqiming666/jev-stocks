#!/usr/bin/env node
/* 原型审核回归：R10 重新打开回原分组、R11 扫描抽屉关闭、R12 Unicode 码点高亮。
   输出 JSON { errors: string[] }，供 scripts/check_proto.py 汇总。 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', 'design', 'prototype');
const sandbox = { console };
sandbox.window = sandbox;
vm.createContext(sandbox);
[
  'data/mock.js',
  'js/icons.js',
  'js/format.js',
  'js/render-ui.js',
  'js/render-pages.js',
  'js/render-pages2.js',
  'js/states.js',
  'js/router.js',
].forEach(function (f) {
  vm.runInContext(fs.readFileSync(path.join(root, f), 'utf8'), sandbox, { filename: f });
});

const P = sandbox.Proto;
const errors = [];
P.now = sandbox.MOCK.examples['app.bootstrap'].ready.result.now;

function expect(condition, message) {
  if (!condition) { errors.push(message); }
}

function buildToday() {
  return P.build('today', 'pending', { platform: 'macos' });
}

function numberAfter(html, re, label) {
  const match = html.match(re);
  if (!match) {
    errors.push('R10 找不到' + label + '计数');
    return null;
  }
  return Number(match[1]);
}

function testReopenOrdinary() {
  P.runtime.acted = {};
  const before = numberAfter(buildToday(), /今天有\s*(\d+)\s*件事需要你看一眼/, '待处理');
  const id = sandbox.MOCK.examples['inbox.list'].pending.result.items[0].decisionId;
  P.runtime.acted[id] = { action: 'still_valid' };
  const processed = numberAfter(buildToday(), /今天有\s*(\d+)\s*件事需要你看一眼/, '待处理');
  P.runtime.acted[id] = { action: 'reopen', origin: 'items' };
  const reopened = numberAfter(buildToday(), /今天有\s*(\d+)\s*件事需要你看一眼/, '待处理');
  expect(before === 3 && processed === 2 && reopened === 3,
    'R10 普通项未完成 3/1 → 2/2 → 3/1（得到 ' + [before, processed, reopened].join('/') + '）');
}

function testReopenUncertain() {
  P.runtime.acted = {};
  const id = sandbox.MOCK.examples['inbox.list'].pending.result.uncertain[0].decisionId;
  P.runtime.acted[id] = { action: 'still_valid' };
  const processed = numberAfter(buildToday(), /系统拿不准的\s*(\d+)\s*条/, '待确认');
  P.runtime.acted[id] = { action: 'reopen', origin: 'uncertain' };
  const reopened = numberAfter(buildToday(), /系统拿不准的\s*(\d+)\s*条/, '待确认');
  expect(processed === 1 && reopened === 2,
    'R10 待确认项重新打开后未回原分组（得到 ' + [processed, reopened].join('/') + '）');
}

function testDrawerClosePatch() {
  const scan = P.drawerClosePatch({ route: 'scan', state: 'detail', drawer: '' });
  const evidence = P.drawerClosePatch({ route: 'today', state: 'pending', drawer: 'overturn' });
  expect(scan.state === '' && scan.drawer === '', 'R11 扫描明细关闭未同时清空 state/drawer');
  expect(evidence.drawer === '' && !Object.prototype.hasOwnProperty.call(evidence, 'state'),
    'R11 证据抽屉关闭不应改写页面 state');

  const app = fs.readFileSync(path.join(root, 'js', 'app.js'), 'utf8');
  expect(app.includes('go(P.drawerClosePatch(cur))'), 'R11 app.js 未统一调用 drawerClosePatch');
  expect(/Escape[^\n]+closeDrawer\(\)/.test(app), 'R11 Esc 关闭未复用 closeDrawer');
}

function testUnicodeHighlight() {
  const decision = sandbox.MOCK.examples['decision.get'].overturn.result;
  decision.evidence.kind = 'sentence';
  decision.evidence.passageText = 'A😀. Revenue fell.';
  decision.evidence.sentenceStart = 4;
  decision.evidence.sentenceEnd = 17;
  const html = P.build('today', 'pending', { drawer: 'overturn', platform: 'macos' });
  const match = html.match(/<mark class="c-evidence-mark">([^<]*)<\/mark>/);
  expect(match && match[1] === 'Revenue fell.',
    'R12 Unicode 码点高亮错误（得到 ' + (match ? match[1] : '没有 mark') + '）');
}

try { testReopenOrdinary(); } catch (e) { errors.push('R10 普通项异常: ' + e.message); }
try { testReopenUncertain(); } catch (e) { errors.push('R10 待确认项异常: ' + e.message); }
try { testDrawerClosePatch(); } catch (e) { errors.push('R11 异常: ' + e.message); }
try { testUnicodeHighlight(); } catch (e) { errors.push('R12 异常: ' + e.message); }

process.stdout.write(JSON.stringify({ errors: errors }));
