// UI transport: uses Flow's own composer, never mints or replays CAPTCHA tokens.
(() => {
  if (globalThis.flowKitUI?.version === 3) return;
  let busy = false;
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = e => e && e.getClientRects().length && !e.disabled;
  const label = e => (e.getAttribute('aria-label') || e.querySelector('.toggle-text')?.textContent || e.querySelector('.settings-summary')?.textContent || e.textContent || '').replace(/\s+/g, ' ').trim();
  async function waitFor(read, message, timeout = 15000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const value = read();
      if (value) return value;
      await pause(300);
    }
    throw new Error(message);
  }
  async function click(names, selector = 'button,[role="button"]', structural = null) {
    const matches = () => {
      const byStructure = structural ? [...document.querySelectorAll(structural)].filter(visible) : [];
      if (byStructure.length) return byStructure;
      return [...document.querySelectorAll(selector)].filter(e => visible(e) && names.includes(label(e)));
    };
    const found = await waitFor(() => {
      const foundMatches = matches();
      if (foundMatches.length > 1) throw new Error(`Có ${foundMatches.length} nút khớp ${names.join('/')}: ${foundMatches.slice(0, 4).map(label).join(' | ')}`);
      return foundMatches[0];
    }, `Không tìm thấy nút ${names.join('/')}`);
    found.click();
    await pause(250);
  }
  const thumbnails = () => [...document.querySelectorAll('img.thumbnail')].filter(visible);
  const mediaId = url => new URL(url).pathname.split('/').filter(Boolean).pop();
  globalThis.flowKitUI = {
    version: 3,
    async run(params) {
      if (busy) return {error: 'UI_VIDEO: Tab đang tạo video khác'};
      busy = true;
      let submitted = false;
      try {
        if (location.pathname !== `/project/${params.projectId}`) throw new Error('Hãy mở đúng trang project Flow, đóng trình chỉnh sửa video');
        const editor = await waitFor(() => document.querySelector('div.ProseMirror[contenteditable="true"]'), 'Không tìm thấy ô prompt');
        if (editor.textContent.trim()) throw new Error('Ô prompt đang có nội dung; hãy lưu hoặc xoá trước khi chạy tool');
        // Refuse to overwrite a manually prepared image selection.
        if ([...document.querySelectorAll('button')].some(e => visible(e) && label(e) === 'Thành phần')) throw new Error('Ô prompt đang có ảnh được chọn; hãy xoá lựa chọn trước khi chạy tool');
        await click(['Điều kiện kích hoạt cài đặt', 'Settings'], 'button.settings-trigger-button,[aria-label="Điều kiện kích hoạt cài đặt"],[aria-label="Settings"]');
        await click(['Video'], '[role="radio"]');
        await click(['Thành phần', 'Ingredients'], '[role="radio"]');
        await click([params.aspect === 'VIDEO_ASPECT_RATIO_LANDSCAPE' ? '16:9' : '9:16'], '[role="radio"]');
        await click(['720p'], '[role="radio"]');
        await click(['6 giây', '6 seconds', '6s'], '[role="radio"]');
        await click(['x1'], '[role="radio"]');
        await click(['Điều kiện kích hoạt cài đặt', 'Settings'], 'button.settings-trigger-button,[aria-label="Điều kiện kích hoạt cài đặt"],[aria-label="Settings"]');
        await click(['Thêm thành phần vào ô nhập câu lệnh', 'Add assets to prompt']);
        const option = await waitFor(() => [...document.querySelectorAll('[role="option"]')].find(e => {
          const img = e.querySelector('img');
          return visible(e) && img && mediaId(img.src) === params.imageId;
        }), 'Ảnh nguồn không có trong danh sách đang hiển thị của project Flow');
        option.click();
        await pause(300);
        editor.focus();
        if (!document.execCommand('insertText', false, params.prompt) || editor.textContent.trim() !== params.prompt.trim()) throw new Error('Không nhập được prompt; chưa gửi yêu cầu');
        const before = new Set(thumbnails().map(e => mediaId(e.src)));
        // Mark uncertain before clicking: never automatically repeat a paid submit.
        submitted = true;
        await click(['Bắt đầu tạo', 'Start generation', 'Generate']);
        const thumb = await waitFor(() => {
          const fresh = thumbnails().filter(e => !before.has(mediaId(e.src)));
          if (fresh.length > 1) throw new Error('Có nhiều kết quả mới; dừng để tránh gán nhầm clip');
          return fresh[0];
        }, 'Chưa nhận được clip sau 8 phút. Kiểm tra Flow trước khi thử lại', 480000);
        thumb.click();
        const video = await waitFor(() => [...document.querySelectorAll('video')].find(e => e.readyState >= 1 && e.duration >= 5 && e.currentSrc), 'Không đọc được video hoặc clip ngắn hơn 5 giây', 60000);
        const url = video.currentSrc;
        const parsed = new URL(url);
        if (parsed.protocol !== 'https:' || parsed.hostname !== 'flow-content.google' || !parsed.pathname.startsWith('/video/')) throw new Error('URL kết quả không phải video Flow');
        const result = {url, mediaId: mediaId(url), duration: video.duration};
        await click(['Nút quay lại để quay về trang trước', 'Back button to return to previous page']);
        return result;
      } catch (error) {
        return {error: `UI_VIDEO: ${error.message}${submitted ? ' (Có thể đã gửi tạo; không tự thử lại.)' : ''}`};
      } finally {
        busy = false;
      }
    },
  };
})();
