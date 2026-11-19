const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
let Workspace;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../custom_components/custom_integration_translator/frontend/workspace.js'), 'utf8'), {
  setTimeout() { return 0; }, clearTimeout() {},
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
  c.selected.clear();
  c.updateRows();
  assert.match(html(c), /No phrases found/);
  assert.equal(c.root.querySelector("[data-page='-1']").disabled, true);
  assert.equal(c.root.querySelector("[data-page='1']").disabled, true);
});

test('overview distinguishes partial and entirely missing translations', () => {
  const c = workspace();
  c.items = [{domain:'partial',name:'Partial',missing:2,count:5}, {domain:'all',name:'All',missing:2,count:2}];
  assert.match(c.listView(), /2 missing of 5/);
  assert.match(c.listView(), /All 2 missing/);
  c.ha.language = 'de';
  assert.match(c.listView(), /2 fehlen von 5/);
  assert.match(c.listView(), /Alle 2 fehlen/);
});
test('friendly names are protected by default and per-integration edits survive reopening', async () => {
  const c = workspace();
  c.settings.terms = 'ACME';
  c.call = async action => action === 'detail' ? {domain:'example',name:'Friendly Name',rows:[]} : {available:false,reason:'unsupported'};
  await c.detail('example');
  assert.equal(c.terms, 'ACME\nFriendly Name');
  c.termPreferences.set('example', 'Personal choice');
  await c.detail('example');
  assert.equal(c.terms, 'Personal choice');
});
test('quota forecast distinguishes finite, unlimited and unavailable accounts', () => {
  const c = workspace();
  c.estimate = {selected_phrases:2,unique_phrases:1,words:3,characters:50};
  c.quota = {available:true,character_count:900,character_limit:1000,characters_remaining:100};
  c.updateUsage();
  assert.match(c.root.querySelector('#usage').textContent, /after this selection: 50/);
  c.quota.unlimited = true;
  c.updateUsage();
  assert.match(c.root.querySelector('#usage').textContent, /no fixed character limit/);
  assert.doesNotMatch(c.root.querySelector('#usage').textContent, /after this selection/);
  c.quota = {available:false,reason:'unsupported'};
  c.updateUsage();
  assert.match(c.root.querySelector('#usage').textContent, /Remaining usage is unknown/);
});

function withServices(component, fallback = false) {
  component.settings = {
    languages: ['de'], recoverable: [], fallback, provider: 'deepl_translator',
    providers: [
      {key: 'deepl_translator', name: 'DeepL', languages: ['de', 'fr'], error: null},
      {key: 'google_translator', name: 'Google', languages: ['de', 'pt'], error: null},
    ],
  };
  component.provider = 'deepl_translator';
  return component;
}
test('the service picker appears only when several services are set up', () => {
  const c = workspace();
  assert.equal(c.providerPicker(), '');
  withServices(c);
  assert.match(c.providerPicker(), /id="provider"/);
  assert.match(c.providerPicker(), /<option value="google_translator">Google/);
  assert.match(c.providerPicker(), /<option value="deepl_translator" selected>DeepL/);
  c.settings.providers[1].error = 'Google is unavailable';
  assert.match(c.providerPicker(), /disabled>Google – Google is unavailable/);
});
test('languages follow the chosen service, or all of them when another may take over', () => {
  const c = withServices(workspace());
  assert.deepEqual(Array.from(c.supportedLanguages()), ['de', 'fr']);
  c.provider = 'google_translator';
  assert.deepEqual(Array.from(c.supportedLanguages()), ['de', 'pt']);
  c.settings.fallback = true;
  assert.deepEqual(Array.from(c.supportedLanguages()).sort(), ['de', 'fr', 'pt']);
  c.settings.providers = [];
  assert.deepEqual(Array.from(c.supportedLanguages()), ['de']);
});
test('choosing a service that lacks the language asks for another language', () => {
  const c = withServices(workspace());
  c.lang = 'fr';
  c.render = () => {};
  c.loadUsage = () => {};
  c.change({target:{id:'provider', value:'google_translator'}});
  assert.equal(c.provider, 'google_translator');
  assert.equal(c.lang, '');
  assert.equal(c.item, null);
  c.lang = 'de';
  c.item = {rows:[], domain:'example'};
  c.queueEstimate = () => {};
  let reloaded = false;
  c.loadUsage = () => { reloaded = true; };
  c.change({target:{id:'provider', value:'deepl_translator'}});
  assert.equal(c.lang, 'de');
  assert.ok(reloaded, 'the balance of the newly chosen service is requested');
});
test('the translation request names the chosen service and the result says who translated', async () => {
  const c = withServices(workspace(250));
  c.provider = 'google_translator';
  c.selected = new Set([1]);
  let request;
  c.call = async (action, data) => { request = {action, data}; return {provider:'google_translator', provider_name:'Google'}; };
  c.detail = async () => {};
  c.run = work => work();
  await c.click({target:{closest() { return {id:'translate', dataset:{}}; }}});
  assert.equal(request.data.provider, 'google_translator');
  assert.match(c.message, /Saved 1 phrases \(Google\)/);
});
test('the balance is labelled with its service and says when it was counted by the integration', () => {
  const c = withServices(workspace());
  c.estimate = {selected_phrases:1,unique_phrases:1,words:1,characters:20};
  c.quota = {available:true,estimated:true,provider_name:'Google',character_count:100,character_limit:500,characters_remaining:400};
  c.updateUsage();
  const text = c.root.querySelector('#usage').textContent;
  assert.match(text, /Google budget: 400 of 500 characters remaining this month \(counted by the integration\)/);
  assert.match(text, /after this selection: 380/);
  c.quota = {available:true,estimated:true,provider_name:'Google',unlimited:true,character_count:7};
  c.updateUsage();
  assert.match(c.root.querySelector('#usage').textContent, /Google: 7 characters counted this month, no monthly limit set/);
  c.quota = {available:true,provider_name:'DeepL',character_count:900,character_limit:1000,characters_remaining:100};
  c.updateUsage();
  assert.match(c.root.querySelector('#usage').textContent, /DeepL account: 100 of 1000 characters remaining/);
});
