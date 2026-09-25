const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../extension/ui-video.js'), 'utf8');
function fixture() {
  let clicked = 0;
  const settings = {disabled: false, getClientRects: () => [1], click: () => clicked++};
  const editor = {textContent: '', getClientRects: () => [1], querySelectorAll: () => []};
  const context = vm.createContext({
    setTimeout,
    location: {pathname: '/project/test'},
    document: {querySelectorAll: selector => selector === 'button.settings-trigger-button' ? [settings] : selector === 'div.ProseMirror[contenteditable="true"]' ? [editor] : []},
  });
  // Expose one private selector solely in the VM, without version-dependent rewriting.
  vm.runInContext(source.replace('globalThis.flowKitUI = {', 'globalThis.flowKitUI = { label,'), context);
  return {context, editor, clicks: () => clicked};
}
test('radio icon text does not contaminate the translated label', () => {
  const {context} = fixture();
  assert.equal(context.flowKitUI.label({getAttribute: () => null, querySelector: () => ({textContent:'Video'}), textContent:'videocamVideo'}), 'Video');
});
test('structural probe finds composer without matching translated settings text', async () => {
  const {context} = fixture();
  assert.equal((await context.flowKitUI.run({mode:'probe'})).ready, true);
  context.location.pathname = '/project/test/edit/clip';
  assert.equal((await context.flowKitUI.run({mode:'probe'})).ready, false);
});
test('existing draft is never overwritten or submitted', async () => {
  const {context, editor, clicks} = fixture();
  editor.textContent = 'User draft';
  const result = await context.flowKitUI.run({projectId:'test'});
  assert.match(result.error, /UI_VIDEO/);
  assert.equal(editor.textContent, 'User draft');
  assert.equal(clicks(), 0);
});
test('same version is not reinstalled', () => {
  const {context} = fixture();
  const installed = context.flowKitUI;
  vm.runInContext(source, context);
  assert.equal(context.flowKitUI, installed);
});
