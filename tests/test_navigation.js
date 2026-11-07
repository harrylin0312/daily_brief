const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');

function detail(saved, storageBlocked = false) {
  const back = {href: '../../issues/2026-11-07.html#gpt-6-cyber'};
  const document = {
    querySelector: () => ({dataset: {
      issueDate: '2026-11-07', storyId: 'gpt-6-cyber',
      homeList: '../../index.html', issueList: '../../issues/2026-11-07.html'
    }}),
    querySelectorAll: () => [back]
  };
  vm.runInNewContext(source, {
    document, URL,
    location: {href: 'https://example.org/daily_brief/stories/2026-11-07/gpt-6-cyber.html', origin: 'https://example.org'},
    sessionStorage: {getItem() {
      if (storageBlocked) throw new Error('storage unavailable');
      return JSON.stringify(saved);
    }}
  });
  return back.href;
}

test('direct/shared detail links have a static return to the original edition', () => {
  assert.equal(detail(null), '../../issues/2026-11-07.html#gpt-6-cyber');
});

test('unavailable session storage does not break navigation', () => {
  assert.equal(detail(null, true), '../../issues/2026-11-07.html#gpt-6-cyber');
});

test('return to the actual homepage or original edition is preserved', () => {
  for (const target of ['/daily_brief/', '/daily_brief/index.html', '/daily_brief/issues/2026-11-07.html']) {
    assert.equal(detail({issueDate: '2026-11-07', path: target}), target + '#gpt-6-cyber');
  }
});

test('stored navigation cannot redirect to external or unrelated pages', () => {
  for (const target of ['https://evil.example/', '//evil.example/', 'javascript:alert(1)', '/account', '/daily_brief/issues/2026-11-06.html', '/daily_brief/?other=true']) {
    assert.equal(detail({issueDate: '2026-11-07', path: target}), '../../issues/2026-11-07.html#gpt-6-cyber');
  }
});

function list(saved) {
  const handlers = {window: {}, search: {}, controls: {}, document: {}};
  const storage = new Map();
  const stateKey = 'brief:list:/daily_brief/';
  if (saved) storage.set(stateKey, JSON.stringify(saved));
  const buttons = ['all', 'tech', 'f1'].map(category => ({
    dataset: {category}, pressed: 'false',
    setAttribute(name, value) { this.pressed = value; }
  }));
  const cards = [
    {id: 'one', dataset: {category: 'tech', search: '標題與詳細文字 Daybreak'}, textContent: '可見標題', hidden: false},
    {id: 'two', dataset: {category: 'f1', search: 'F1 正式賽果'}, textContent: 'F1 正式賽果', hidden: false}
  ];
  const controls = {querySelectorAll: () => buttons, addEventListener: (name, fn) => { handlers.controls[name] = fn; }};
  const search = {value: '', addEventListener: (name, fn) => { handlers.search[name] = fn; }};
  const count = {textContent: '顯示 2 則精選'}, empty = {hidden: true};
  const main = {dataset: {issueDate: '2026-11-07'}};
  const nodes = {'[data-detail]': null, '[data-filters]': controls, 'main[data-issue-date]': main,
    '#story-search': search, '[data-result-count]': count, '[data-empty]': empty,
    '[data-interactive]': {hidden: true}, '[data-freshness]': null};
  const context = {
    document: {querySelector: key => nodes[key], querySelectorAll: () => cards,
      addEventListener: (name, fn) => { handlers.document[name] = fn; }},
    window: {addEventListener: (name, fn) => { handlers.window[name] = fn; }},
    location: {pathname: '/daily_brief/'}, scrollY: 400,
    sessionStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
    requestAnimationFrame: fn => fn(), scrollTo: options => { context.scrollY = options.top; }
  };
  vm.runInNewContext(source, context);
  return {handlers, storage, stateKey, buttons, cards, search, count, empty, context};
}

test('search includes detailed text that is absent from the visible list', () => {
  const state = list();
  state.search.value = 'Daybreak';
  state.handlers.search.input();
  assert.equal(state.count.textContent, '顯示 1 則精選');
  assert.equal(state.cards[0].hidden, false);
  assert.equal(state.cards[1].hidden, true);
});

test('list restores category, query, scroll and results after navigation', () => {
  const state = list({issueDate: '2026-11-07', category: 'f1', query: '正式', y: 300});
  state.handlers.window.pageshow();
  assert.equal(state.search.value, '正式');
  assert.equal(state.buttons[2].pressed, 'true');
  assert.equal(state.context.scrollY, 300);
  assert.equal(state.count.textContent, '顯示 1 則精選');
});

test('a new edition does not inherit the previous edition filter state', () => {
  const state = list({issueDate: '2026-11-06', category: 'f1', query: 'old', y: 999});
  state.handlers.window.pageshow();
  assert.equal(state.search.value, '');
  assert.equal(state.context.scrollY, 400);
});
