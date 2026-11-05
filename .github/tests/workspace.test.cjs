const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
let Workspace;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../custom_components/custom_integration_translator/frontend/workspace.js'), 'utf8'), {
  HTMLElement: class { attachShadow() { this.shadowRoot = {addEventListener() {}}; } },
  customElements: {get() {}, define(name, component) { Workspace = component; }},
});
function workspace(count = 10001) {
  const component = new Workspace();
  component.ha = {language:'en'};
  component.lang = 'de';
  component.settings = {languages:['de']};
  component.item = {domain:'example', source_language:'en', revision:'version', rows:Array.from({length:count}, (_, index) => ({
    path:['labels', 'key' + index], source:'Open device ' + index,
    target:index % 2 ? 'Gerät ' + index : null,
  }))};
  const elements = new Map();
  component.root = {querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, {});
    return elements.get(selector);
  }};
  component.select('missing');
  return component;
}
function html(component) { return component.root.querySelector('#phrases').innerHTML; }
test('large catalogs render at most 100 rows and preserve selections across pages', () => {
  const c = workspace();
  assert.equal(c.selected.size, 5001);
  c.updateRows();
  assert.equal((html(c).match(/class="phrase"/g) || []).length, 100);
  assert.match(html(c), /data-row="0" checked/);
  c.change({target:{dataset:{row:'0'}, checked:false}});
  c.page = 100;
  c.updateRows();
  assert.equal((html(c).match(/class="phrase"/g) || []).length, 1);
  assert.match(html(c), /data-row="10000" checked/);
  assert.equal(c.root.querySelector("[data-page='1']").disabled, true);
  c.page = 0;
  c.updateRows();
  assert.doesNotMatch(html(c), /data-row="0" checked/);
  assert.equal(c.selected.size, 5000);
});
test('search covers source, target and keys; bulk selection spans all matching pages', () => {
  const c = workspace(250);
  c.search = 'GERÄT';
  c.page = 100;
  c.updateRows();
  assert.equal(c.page, 1);
  assert.equal(c.matchingRows().length, 125);
  assert.equal(c.selected.size, 125, 'search must not change existing selections');
  c.select('all');
  assert.equal(c.selected.size, 125);
  assert.ok([...c.selected].every(index => index % 2));
  c.search = 'labels › key200';
  assert.deepEqual(Array.from(c.matchingRows()), [200]);
  c.select('missing');
  assert.deepEqual(Array.from(c.selected), [200]);
  c.search = 'open device 201';
  c.select('missing');
  assert.equal(c.selected.size, 0);
  c.search = 'does not exist';
  c.updateRows();
  assert.match(html(c), /No matching phrases/);
  assert.equal(c.page, 0);
  assert.match(c.root.querySelector('#page-status').textContent, /0–0 of 0/);
  c.select('none');
  assert.equal(c.selected.size, 0);
});
test('translation submits selected keys from every page, including hidden search results', async () => {
  const c = workspace(250);
  c.selected = new Set([2, 202]);
  c.search = 'key2';
  c.terms = 'ACME';
  let request;
  c.call = async (action, data) => { request = {action, data}; };
  c.detail = async () => {};
  c.run = work => work();
  await c.click({target:{closest() { return {id:'translate', dataset:{}}; }}});
  assert.equal(request.action, 'translate');
  assert.deepEqual(JSON.parse(JSON.stringify(request.data.paths)), [['labels','key2'], ['labels','key202']]);
  assert.equal(request.data.revision, 'version');
});
test('phrase content remains escaped and an empty source has no pages to navigate', () => {
  const c = workspace(1);
  c.item.rows[0].source = '<img src=x onerror=alert(1)>';
  c.updateRows();
  assert.doesNotMatch(html(c), /<img/);
  assert.match(html(c), /&lt;img/);
  c.item.rows = [];
  c.updateRows();
  assert.match(html(c), /No phrases found/);
  assert.equal(c.root.querySelector("[data-page='-1']").disabled, true);
  assert.equal(c.root.querySelector("[data-page='1']").disabled, true);
});
