const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../extension/ui-video.js'), 'utf8');

for (const duration of [null, '6 giây', '8 giây']) {
  for (const alreadyOpen of [false, true]) {
    test(`preserves model and duration ${duration}, popover open=${alreadyOpen}`, async () => {
      let open = alreadyOpen;
      const clicks = [];
      const names = ['Video', 'Thành phần', '9:16', '16:9', 'x1', 'x4', 'Veo 3.1 - Lite'];
      if (duration) names.push(duration, '720p');
      const options = names.map(name => {
        let checked = ['x4', '16:9', duration, '720p'].includes(name);
        return {
          getClientRects: () => open ? [1] : [],
          getAttribute: key => key === 'aria-label' ? name : key === 'aria-checked' ? String(checked) : null,
          click: () => { clicks.push(name); checked = true; },
        };
      });
      const settings = {getClientRects: () => [1], click: () => { open = !open; }};
      const context = vm.createContext({setTimeout, document: {
        querySelectorAll: selector => selector === '[role="radio"]' ? options :
          selector === 'button.settings-trigger-button' ? [settings] : [],
      }});
      vm.runInContext(source.replace('globalThis.flowKitUI = {', 'globalThis.flowKitUI = { configureVideo,'), context);
      await context.flowKitUI.configureVideo({aspect: 'VIDEO_ASPECT_RATIO_PORTRAIT'});
      assert.deepEqual(clicks, ['Video', 'Thành phần', '9:16', 'x1']);
      assert.equal(open, false);
    });
  }
}
