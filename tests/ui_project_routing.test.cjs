const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../extension/background.js'), 'utf8');
const handler = source.slice(source.indexOf('async function handleUiVideo('), source.indexOf('\nfunction sendToAgent('));
const projectId = '0bacdad5-f72e-44f1-834a-8d51c368b528';
const url = `https://flow.google.com/project/${projectId}`;
async function run(tabs, result = {ready: true}) {
  const calls = [], replies = [], logs = [];
  const context = vm.createContext({URL, flowUrls: ['https://flow.google.com/*'],
    chrome: {tabs: {query: async () => tabs}, scripting: {executeScript: async args => {
      calls.push(args); return [{result}];
    }}},
    addRequestLog: entry => logs.push(entry),
    updateRequestLog: (id, update) => Object.assign(logs.find(e => e.id === id), update),
    sendToAgent: reply => replies.push(reply),
  });
  vm.runInContext(handler, context);
  await context.handleUiVideo({id: 'request', params: {projectId, mode: 'probe'}});
  return {calls, reply: replies[0], logs};
}
test('routes to matching project, ignoring active wrong project and discarded duplicate', async () => {
  const out = await run([{id: 1, url: url + 'extra', active: true},
    {id: 2, url, discarded: true}, {id: 3, url: url + '/?hl=vi'}]);
  assert.equal(out.calls[0].target.tabId, 3);
  assert.equal(out.reply.status, 200);
  assert.equal(out.logs[0].type, 'UI:probe');
  assert.equal(out.logs[0].status, 'success');
});
test('missing project returns explicit pre-injection code and a visible log', async () => {
  const out = await run([{id: 1, url: url + '/edit/clip'}, {id: 2, url: url + 'extra'}]);
  assert.equal(out.calls.length, 0);
  assert.equal(out.reply.code, 'UI_PROJECT_TAB_UNAVAILABLE');
  assert.match(out.reply.error, /profile Chrome/);
  assert.equal(out.logs[0].status, 'failed');
});
test('discarded tab instructs user to wake it without injecting', async () => {
  const out = await run([{id: 1, url, discarded: true}]);
  assert.equal(out.calls.length, 0);
  assert.match(out.reply.error, /đang ngủ/);
});
test('uncertain page failures never carry the safe routing code', async () => {
  const out = await run([{id: 1, url}], {error: 'Timeout after submit'});
  assert.equal(out.reply.code, undefined);
  assert.equal(out.reply.status, 502);
});
