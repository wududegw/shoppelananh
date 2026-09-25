// Use Flow's visible composer. Submission is never retried automatically.
(() => {
  if (globalThis.flowKitUI?.version === 16) return;
  let busy = false;
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const shown = e => !!e?.getClientRects().length;
  const enabled = e => shown(e) && !e.disabled;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const label = e => clean(e.getAttribute('aria-label') || e.querySelector('.toggle-text')?.textContent || e.textContent);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)].filter(shown);
  const editor = () => all('div.ProseMirror[contenteditable="true"]')[0];
  const settings = () => all('button.settings-trigger-button');
  const radio = name => all('[role="radio"]').find(e => label(e) === name);
  const key = url => { try { const u = new URL(url); return u.origin + u.pathname; } catch { return ''; } };
  const mediaId = url => { try { return new URL(url).pathname.split('/').filter(Boolean).pop(); } catch { return ''; } };
  const thumbs = () => all('img.thumbnail').filter(e => /video/i.test(e.alt));
  const reason = 'Mở trang project Flow, đóng khung trò chuyện Agent (dấu ×), để hiện ô tạo ở dưới cùng rồi thử lại.';
  function probe() {
    const ready = settings().length === 1 && !!editor() && !location.pathname.includes('/edit/');
    const input = editor();
    return {version: 16, ready, reason: ready ? '' : reason, path: location.pathname,
      promptState: {textLength: clean(input?.textContent).length, renderedLength: clean(input?.innerText).length,
        paragraphs: input?.querySelectorAll('p').length || 0, breaks: input?.querySelectorAll('br').length || 0}};
  }
  async function waitFor(read, message, timeout = 15000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const value = read();
      if (value) return value;
      await pause(300);
    }
    throw new Error(message);
  }
  async function click(names, selector = 'button,[role="button"]') {
    const found = await waitFor(() => {
      const matches = all(selector).filter(e => enabled(e) && names.includes(label(e)));
      if (matches.length > 1) throw new Error(`Có nhiều nút ${names.join('/')}; chưa gửi tạo`);
      return matches[0];
    }, `Không tìm thấy nút ${names.join('/')}`);
    found.click();
    await pause(250);
  }
  async function select(names) {
    const option = await waitFor(() => names.map(radio).find(enabled), `Flow không có lựa chọn ${names.join('/')}`);
    if (option.getAttribute('aria-checked') !== 'true') option.click();
    await waitFor(() => names.map(radio).some(e => e?.getAttribute('aria-checked') === 'true'), `Không chọn được ${names.join('/')}`);
  }
  async function insertPrompt(prompt) {
    // ProseMirror may split multiline insertText into paragraphs: textContent
    // joins them without separators. Send the same words as one paragraph.
    const expected = clean(prompt);
    if (!expected) throw new Error('Prompt trống; chưa gửi yêu cầu');
    const input = editor();
    if (!input || clean(input.innerText || input.textContent)) throw new Error('Ô prompt đang có nội dung; chưa gửi yêu cầu');
    input.focus();
    const range = document.createRange();
    range.selectNodeContents(input);
    range.collapse(false);
    const selection = document.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    // The command's boolean is not a reliable acknowledgement. Check the
    // editor after its update instead; never insert a second time on failure.
    document.execCommand('insertText', false, expected);
    await waitFor(() => {
      const current = editor();
      return current && clean(current.innerText || current.textContent) === expected;
    }, 'Không nhập được prompt; chưa gửi yêu cầu', 3000);
  }
  globalThis.flowKitUI = {
    version: 16,
    async run(params) {
      if (params.mode === 'probe') return probe();
      if (busy) return {error: 'UI_VIDEO: Tab đang tạo video khác'};
      if (params.mode === 'refresh') {
        if (!probe().ready || clean(editor()?.textContent) || all('button').some(e => ['Xoá câu lệnh', 'Clear prompt'].includes(label(e)))) return {error: 'UI_VIDEO: Hãy mở project và lưu hoặc xoá nội dung đang soạn trước khi tạo'};
        // RPC uploads are not pushed into the page's cached asset list.
        setTimeout(() => location.reload(), 400);
        return {refreshing: true};
      }
      busy = true;
      let submitted = false;
      try {
        if (location.pathname.replace(/\/+$/, '').toLowerCase() !== `/project/${params.projectId.toLowerCase()}`) throw new Error(reason);
        await waitFor(() => probe().ready, reason);
        if (clean(editor().textContent)) throw new Error('Ô prompt đang có nội dung; hãy lưu hoặc xoá trước khi chạy tool');
        if (all('button').some(e => ['Xoá câu lệnh', 'Clear prompt'].includes(label(e)))) throw new Error('Ô tạo đang có ảnh được chọn; hãy lưu hoặc xoá lựa chọn trước khi chạy tool');
        // A user may have left this popover open. Never toggle it closed by accident.
        if (!radio('Video')) { settings()[0].click(); await waitFor(() => radio('Video'), 'Không mở được cài đặt video'); }
        await select(['Video']);
        await select(['Thành phần', 'Ingredients']);
        await select([params.aspect === 'VIDEO_ASPECT_RATIO_LANDSCAPE' ? '16:9' : '9:16']);
        await select(['720p']);
        await select(['6 giây', '6 seconds', '6s']);
        await select(['x1']);
        settings()[0].click();
        await waitFor(() => !radio('Video'), 'Không đóng được bảng cài đặt');
        const images = params.images?.length ? params.images : [{imageId: params.imageId, imageName: params.imageName}];
        if (images.length > 3) throw new Error('Tối đa 3 ảnh tham chiếu cho Studio');
        for (const asset of images) {
        await click(['Thêm thành phần vào ô nhập câu lệnh', 'Add assets to prompt']);
        const source = await waitFor(() => {
          const matches = all('[role="option"]').filter(e => {
            const img = e.querySelector('img');
            const name = clean(e.querySelector('.asset-title')?.textContent);
            return img && ((asset.imageName && name === asset.imageName) || mediaId(img.src) === asset.imageId);
          });
          if (matches.length > 1) throw new Error('Có nhiều ảnh nguồn trùng tên; hãy tải lại ảnh trong Studio');
          return matches[0];
        }, 'Không tìm thấy ảnh nguồn. Hãy tải lại ảnh trong Studio để gắn tên riêng, sau đó thử lại');
        source.click();
        await pause(400);
        if (all('[role="option"]').length) await click(['Thêm vào câu lệnh', 'Add to prompt']);
        await waitFor(() => !all('[role="option"]').length, 'Không đóng được danh sách thành phần');
        }
        await insertPrompt(params.prompt);
        const before = new Set(thumbs().map(e => key(e.src)));
        const priorFailures = (document.body.innerText.match(/Không thành công|Generation failed/g) || []).length;
        const generate = await waitFor(() => all('button').find(e => enabled(e) && ['Bắt đầu tạo', 'Start generation', 'Generate'].includes(label(e))), 'Nút tạo chưa sẵn sàng');
        submitted = true;
        generate.click();
        const thumb = await waitFor(() => {
          const pageText = clean(document.body.innerText);
          const failures = (pageText.match(/Không thành công|Generation failed/g) || []).length;
          if (failures > priorFailures) {
            const failure = pageText.match(/(?:Không thành công|Generation failed).{0,600}/)?.[0] || 'Flow báo tạo không thành công';
            throw new Error(failure.split(/refresh|undo|delete_forever/)[0].trim());
          }
          const fresh = thumbs().filter(e => !before.has(key(e.src)));
          if (fresh.length > 1) throw new Error('Có nhiều video mới; dừng để tránh lấy nhầm clip');
          return fresh[0];
        }, 'Chưa nhận clip sau 8 phút; kiểm tra Flow trước khi thử lại', 480000);
        // Desktop Flow uses a canvas editor rather than an HTML video element.
        // The generated thumbnail's UUID identifies the media record; the
        // backend reads its signed video URL using the non-generation RPC.
        const parsed = new URL(thumb.src);
        const mid = mediaId(thumb.src);
        if (parsed.hostname !== 'flow-content.google' || !/^\/image\/[0-9a-f-]{36}$/i.test(parsed.pathname)) throw new Error('Không đọc được mã clip mới; không gửi tạo lại');
        thumb.click();
        await waitFor(() => location.pathname.includes('/edit/') && clean(document.body.innerText).includes(clean(params.prompt)), 'Prompt của clip không khớp; dừng để tránh lấy nhầm kết quả', 30000);
        const result = {mediaId: mid};
        try { await click(['Nút quay lại để quay về trang trước', 'Back button to return to previous page']); }
        catch { result.warning = 'Đã tạo clip; hãy quay lại project trước cảnh tiếp theo'; }
        return result;
      } catch (error) {
        return {error: `UI_VIDEO: ${error.message}${submitted ? ' (Có thể đã gửi tạo; không tự thử lại.)' : ''}`};
      } finally { busy = false; }
    },
  };
})();
