import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, Film, ImagePlus, LoaderCircle, RefreshCw, Settings2, Sparkles, Download } from 'lucide-react'
import { fetchAPI } from '../api/client'

type Mode = 'adult' | 'child' | 'product'
type AssetKey = 'clothing' | 'model' | 'location'
type Asset = { media_id: string; name: string; preview?: string; error?: string }
type Draft = {
  title: string; clothing_prompt: string; model_prompt: string; location_prompt: string;
  motion_prompt: string; subject_mode: Mode; duration_seconds: number; orientation: string;
  scene_actions: string[] | null; assets: Partial<Record<AssetKey, Asset>>;
}
type Scene = { index: number; title: string; start_seconds: number; end_seconds: number; action: string; prompt: string }
type Job = { id: string; status: string; progress: number; message: string; logs: string[]; project_id?: string; final_video_url?: string }
type Output = { filename: string; stream_url: string; size_mb: number; modified: string }
type Status = { extension_connected: boolean; flow_project_id: string; video_transport: string }
const STORAGE = 'flowkit-studio-draft-v2'
const defaults: Draft = {
  title: 'Bộ sưu tập mới', clothing_prompt: 'Giữ nguyên màu sắc, họa tiết, kiểu dáng và chất liệu của trang phục trong ảnh.',
  model_prompt: 'Người mẫu trưởng thành, diện mạo tự nhiên. Giữ nguyên người mẫu nếu ảnh tham chiếu đã có người.',
  location_prompt: 'Studio sáng với nền trắng ngà, ánh sáng mềm mại và nhất quán.',
  motion_prompt: 'Người mẫu bước nhẹ hai bước, dừng lại và mỉm cười tự nhiên. Máy quay ngang tầm mắt, khung hình toàn thân.',
  subject_mode: 'adult', duration_seconds: 15, orientation: 'VERTICAL', scene_actions: null, assets: {},
}
function readDraft(): Draft {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(STORAGE) || '{}') } } catch { return defaults }
}
function message(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error)
  try {
    const detail = JSON.parse(raw.replace(/^API \d+: /, '')).detail
    return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: {msg: string}) => d.msg).join('; ') : raw
  } catch { return raw }
}
function payload(draft: Draft) {
  return { ...draft, assets: undefined, clothing_media_id: draft.assets.clothing?.media_id || '', model_media_id: draft.subject_mode === 'product' ? null : draft.assets.model?.media_id || null, location_media_id: draft.assets.location?.media_id || null }
}

export function FlowConnection() {
  const [status, setStatus] = useState<Status | null>(null)
  const [project, setProject] = useState('')
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    let active = true
    const read = () => fetchAPI<Status>('/api/studio/status').then(s => { if (active) { setStatus(s) } }).catch(() => { if (active) setStatus(null) })
    void read(); const timer = setInterval(read, 10000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  async function save() {
    setSaving(true); setNotice('')
    try {
      let id = project.trim()
      if (id.includes('/project/')) id = id.split('/project/')[1].split('/')[0].split('?')[0]
      if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id)) throw new Error('Nhập URL dự án Flow hoặc Project ID hợp lệ.')
      await fetchAPI('/api/studio/config', { method: 'POST', body: JSON.stringify({ flow_project_id: id }) })
      setStatus(s => s ? { ...s, flow_project_id: id } : s); setEditing(false); setNotice('Đã lưu dự án Flow.')
    } catch (e) { setNotice(message(e)) } finally { setSaving(false) }
  }
  return <section className="flow-connection">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2"><span className={`connection-dot ${status?.extension_connected ? 'connected' : ''}`} /><strong>{status?.extension_connected ? 'Google Flow đã kết nối' : 'Chưa kết nối Google Flow'}</strong><span className="text-xs text-muted-foreground">{status?.flow_project_id ? `Dự án ${status.flow_project_id.slice(0, 8)}` : 'Chưa chọn dự án'}</span></div>
      <button className="studio-button secondary" onClick={() => { setProject(status?.flow_project_id || ''); setEditing(!editing); setNotice('') }}><Settings2 size={14} /> Cấu hình Flow</button>
    </div>
    {editing && <div className="flex flex-wrap gap-2 mt-3"><input className="studio-input flex-1 min-w-48" aria-label="Project ID hoặc URL Google Flow" value={project} onChange={e => setProject(e.target.value)} placeholder="Dán URL dự án Google Flow" /><button className="studio-button" disabled={saving} onClick={save}>{saving ? 'Đang lưu…' : 'Lưu dự án'}</button></div>}
    {status?.flow_project_id && <p className="studio-hint mt-2">Dự án đang dùng: <a className="studio-text-button" href={`https://flow.google.com/project/${status.flow_project_id}`} target="_blank" rel="noreferrer">Mở dự án Flow ↗</a>. Tab Flow trong Chrome cần mở cùng dự án này.</p>}
    {notice && <p role="status" className="mt-2 text-sm">{notice}</p>}
  </section>
}

export default function StudioPage() {
  const [draft, setDraft] = useState<Draft>(readDraft)
  const [scenes, setScenes] = useState<Scene[]>([])
  const [reviewed, setReviewed] = useState(false)
  const [tab, setTab] = useState<'setup' | 'scenes'>('setup')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [jobId, setJobId] = useState(() => localStorage.getItem('flowkit-studio-job') || '')
  const [job, setJob] = useState<Job | null>(null)
  const [outputs, setOutputs] = useState<Output[]>([])
  const [outputError, setOutputError] = useState('')
  const running = (!!jobId && !job) || job?.status === 'PROCESSING'
  const locked = !!busy || running
  useEffect(() => {
    const assets = Object.fromEntries(Object.entries(draft.assets).map(([k, a]) => [k, { media_id: a?.media_id, name: a?.name }]))
    try { localStorage.setItem(STORAGE, JSON.stringify({ ...draft, assets })) } catch { /* Draft remains usable when storage is full. */ }
  }, [draft])
  useEffect(() => {
    let active = true
    fetchAPI<{ videos: Output[] }>('/api/studio/outputs').then(r => { if (active) setOutputs(r.videos) }).catch(e => { if (active) setOutputError(message(e)) })
    return () => { active = false }
  }, [job?.status])
  useEffect(() => {
    if (!jobId) return
    let active = true
    const poll = async () => {
      try {
        const result = await fetchAPI<Job>(`/api/studio/jobs/${jobId}`)
        if (!active) return
        setJob(result)
        if (result.status !== 'PROCESSING') { clearInterval(timer); localStorage.removeItem('flowkit-studio-job') }
      } catch (e) {
        if (!active) return
        setError(message(e))
        if (String(e).includes('404')) { setJobId(''); localStorage.removeItem('flowkit-studio-job'); clearInterval(timer) }
      }
    }
    const timer = setInterval(poll, 2500); void poll()
    return () => { active = false; clearInterval(timer) }
  }, [jobId])
  function update(values: Partial<Draft>) { setDraft(d => ({ ...d, ...values })); setReviewed(false); setError('') }
  function mode(subject_mode: Mode) {
    update({ subject_mode, scene_actions: null,
      model_prompt: subject_mode === 'child' ? 'Một mẫu nhí khoảng 7–9 tuổi, diện mạo tự nhiên, mặc trang phục vừa vặn phù hợp độ tuổi.' : defaults.model_prompt,
      motion_prompt: subject_mode === 'product' ? 'Trang phục được trưng bày trên giá treo. Máy quay di chuyển chậm, thể hiện rõ màu sắc và đường may.' : subject_mode === 'child' ? 'Bé đứng tự nhiên, bước nhẹ hai bước, mỉm cười và vẫy tay. Máy quay cố định ngang tầm mắt, khung hình toàn thân.' : defaults.motion_prompt,
    })
  }
  async function upload(key: AssetKey, file?: File) {
    if (!file) return
    setBusy(key); setError('')
    try {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Chọn ảnh JPG, PNG hoặc WebP.')
      if (file.size > 15 * 1024 * 1024) throw new Error('Ảnh vượt quá 15 MB.')
      const encoded = await new Promise<string>((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = () => reject(new Error('Không đọc được ảnh')); r.readAsDataURL(file) })
      update({ assets: { ...draft.assets, [key]: { media_id: '', name: file.name, preview: encoded } } })
      await sendAsset(key, { media_id: '', name: file.name, preview: encoded })
    } catch (e) { setError(message(e)) } finally { setBusy('') }
  }
  async function sendAsset(key: AssetKey, asset: Asset) {
    if (!asset.preview) { setError('Chọn lại ảnh từ máy để gửi sang Flow.'); return }
    setBusy(key)
    setDraft(d => ({ ...d, assets: { ...d.assets, [key]: { ...asset, error: undefined } } }))
    try {
      const result = await fetchAPI<{ media_id: string }>('/api/studio/upload-image', { method: 'POST', body: JSON.stringify({ image_base64: asset.preview, file_name: asset.name }), signal: AbortSignal.timeout(60000) })
      if (!result.media_id) throw new Error('Flow chưa trả về mã ảnh. Hãy kiểm tra tab Flow rồi gửi lại.')
      setDraft(d => ({ ...d, assets: { ...d.assets, [key]: { ...asset, media_id: result.media_id, error: undefined } } }))
    } catch (e) {
      const detail = e instanceof DOMException && e.name === 'TimeoutError' ? 'Gửi ảnh quá thời gian chờ. Kiểm tra tab Flow rồi thử lại.' : message(e)
      setDraft(d => ({ ...d, assets: { ...d.assets, [key]: { ...asset, media_id: '', error: detail } } }))
    } finally { setBusy('') }
  }
  async function preview() {
    setBusy('preview'); setError('')
    try { const result = await fetchAPI<{ scenes: Scene[] }>('/api/studio/plan', { method: 'POST', body: JSON.stringify(payload(draft)) }); setScenes(result.scenes); setReviewed(true); setTab('scenes') }
    catch (e) { setError(message(e)) } finally { setBusy('') }
  }
  async function generate() {
    setBusy('generate'); setError('')
    try {
      if (!draft.assets.clothing?.media_id) throw new Error('Hãy gửi ảnh trang phục sang Flow trước.')
      if (pendingAssets) throw new Error('Còn ảnh chưa gửi sang Flow. Gửi lại hoặc gỡ ảnh đó trước khi tạo video.')
      const result = await fetchAPI<{job_id: string}>('/api/studio/generate-advanced', { method: 'POST', body: JSON.stringify(payload(draft)) })
      setJob(null); setJobId(result.job_id); localStorage.setItem('flowkit-studio-job', result.job_id)
    } catch (e) { setError(message(e)) } finally { setBusy('') }
  }
  const roles: [AssetKey, string, string][] = [['clothing', 'Ảnh trang phục', 'Bắt buộc · JPG, PNG, WebP'], ['model', 'Ảnh người mẫu', 'Tùy chọn · giữ cùng nhân vật'], ['location', 'Ảnh bối cảnh', 'Tùy chọn · giữ cùng không gian']]
  const pendingAssets = roles.some(([key]) => !(key === 'model' && draft.subject_mode === 'product') && draft.assets[key] && !draft.assets[key]?.media_id)
  return <div className="studio-page">
    <div className="studio-heading"><div><div className="studio-eyebrow">KHÔNG GIAN SÁNG TẠO</div><h1>Studio thời trang <Sparkles size={24} /></h1><p>Từ ảnh trang phục đến câu chuyện của bộ sưu tập.</p></div><Link className="studio-button secondary" to="/projects">Quản lý dự án <ArrowRight size={15} /></Link></div>
    <FlowConnection />
    {error && <div className="studio-error" role="alert">{error}</div>}
    <div className="studio-layout">
      <div className="studio-workspace">
        <div className="studio-tabs" role="tablist" aria-label="Các bước tạo video"><button role="tab" aria-selected={tab === 'setup'} onClick={() => setTab('setup')}>01 <span>Thiết lập</span></button><button role="tab" aria-selected={tab === 'scenes'} onClick={() => setTab('scenes')}>02 <span>Kịch bản từng cảnh</span>{reviewed && <Check size={14} />}</button></div>
        {tab === 'setup' ? <fieldset disabled={locked} className="space-y-5">
          <section className="studio-card"><div className="studio-section-title"><span>01</span><h2>Bộ sưu tập của bạn</h2></div><label className="studio-label">Tên video<input className="studio-input" value={draft.title} onChange={e => update({title: e.target.value})} /></label><div className="studio-field-grid mt-4"><label className="studio-label">Tỷ lệ khung hình<select className="studio-input" value={draft.orientation} onChange={e => update({orientation: e.target.value})}><option value="VERTICAL">9:16 · Video dọc</option><option value="HORIZONTAL">16:9 · Video ngang</option></select></label><label className="studio-label">Thời lượng<select className="studio-input" value={draft.duration_seconds} onChange={e => {update({duration_seconds: Number(e.target.value), scene_actions: null}); setScenes([])}}>{[15, 30, 60].map(n => <option key={n} value={n}>{n} giây · {n / 5} cảnh</option>)}</select></label></div></section>
          <section className="studio-card"><div className="studio-section-title"><span>02</span><h2>Ảnh tham chiếu</h2></div><p className="studio-hint">Dùng cùng bộ ảnh cho mọi cảnh. Ảnh mẫu đang mặc bộ đồ giúp giữ diện mạo nhất quán hơn ảnh chỉ có quần áo.</p><div className="studio-assets">{roles.map(([key, title, hint]) => <div key={key}><label className={`studio-upload ${draft.assets[key] ? 'has-image' : ''}`}>
            {draft.assets[key]?.preview ? <img src={draft.assets[key]?.preview} alt={title} /> : <ImagePlus size={29} />}
            <span>{busy === key ? 'Đang tải lên…' : draft.assets[key]?.name || 'Chọn ảnh'}</span><input type="file" accept="image/jpeg,image/png,image/webp" aria-label={title} onChange={e => { void upload(key, e.target.files?.[0]); e.target.value = '' }} />
          </label><h3>{title}</h3><p className="studio-hint">{hint}</p>{draft.assets[key] && <div className="studio-asset-status" aria-live="polite"><p>{busy === key ? 'Đã chọn ảnh · đang gửi sang Flow…' : draft.assets[key]?.media_id ? '✓ Đã gửi sang Flow' : 'Đã chọn ảnh · chưa gửi sang Flow'}</p>{draft.assets[key]?.error && <p className="studio-asset-error" role="alert">{draft.assets[key]?.error}</p>}{!draft.assets[key]?.media_id && draft.assets[key]?.preview && <button type="button" className="studio-text-button" onClick={() => void sendAsset(key, draft.assets[key]!)}>Gửi lại sang Flow</button>}{!draft.assets[key]?.media_id && !draft.assets[key]?.preview && <p>Chọn lại file để gửi ảnh.</p>}</div>}{draft.assets[key] && <button className="studio-text-button" onClick={() => { const assets = {...draft.assets}; delete assets[key]; update({assets}) }}>Gỡ ảnh</button>}</div>)}</div><label className="studio-label mt-4">Mô tả trang phục<textarea className="studio-input" rows={3} value={draft.clothing_prompt} onChange={e => update({clothing_prompt: e.target.value})} /></label></section>
          <section className="studio-card"><div className="studio-section-title"><span>03</span><h2>Nhân vật & bối cảnh</h2></div><div className="studio-mode">{(['adult','child','product'] as Mode[]).map(m => <button key={m} aria-pressed={draft.subject_mode === m} onClick={() => mode(m)}>{m === 'adult' ? 'Mẫu trưởng thành' : m === 'child' ? 'Mẫu nhí' : 'Chỉ sản phẩm'}</button>)}</div>{draft.subject_mode !== 'product' && <label className="studio-label mt-4">Mô tả người mẫu<textarea className="studio-input" rows={3} value={draft.model_prompt} onChange={e => update({model_prompt: e.target.value})} /></label>}<label className="studio-label mt-4">Không gian & ánh sáng<textarea className="studio-input" rows={3} value={draft.location_prompt} onChange={e => update({location_prompt: e.target.value})} /></label></section>
          <section className="studio-card"><div className="studio-section-title"><span>04</span><h2>Chuyển động & góc máy</h2></div><label className="studio-label">Chỉ dẫn chung cho mọi cảnh<textarea className="studio-input" rows={4} value={draft.motion_prompt} onChange={e => update({motion_prompt: e.target.value, scene_actions: null})} /></label><p className="studio-hint mt-2">Bạn có thể chỉnh chuyển động riêng cho từng cảnh ở bước tiếp theo.</p></section>
        </fieldset> : <section className="studio-card"><div className="studio-section-title"><span>02</span><h2>Kịch bản {draft.duration_seconds / 5} cảnh</h2></div><p className="studio-hint">Mô tả nhân vật, trang phục và bối cảnh được giữ trong mọi prompt. Chỉnh hành động bên dưới rồi bấm “Xem lại kịch bản” để kiểm tra bản cuối.</p>{!scenes.length ? <div className="studio-empty"><Film size={32} /><p>Thiết lập bộ sưu tập rồi xem trước kịch bản.</p><button className="studio-button" disabled={locked} onClick={preview}>Tạo bản xem trước</button></div> : scenes.map((scene, i) => <div className="studio-scene" key={i}><div className="flex justify-between items-center mb-3"><h3>{scene.title}</h3><span className="studio-badge">{scene.start_seconds}–{scene.end_seconds}s</span></div><label className="studio-label">Chuyển động cảnh {i + 1}<textarea className="studio-input" rows={3} disabled={locked} value={draft.scene_actions?.[i] ?? scene.action} onChange={e => {const actions = [...(draft.scene_actions || scenes.map(s => s.action))]; actions[i] = e.target.value; update({scene_actions: actions})}} /></label><details className="mt-3"><summary>Prompt đầy đủ {reviewed ? 'sẽ gửi' : '(cần cập nhật bản xem trước)'}</summary><pre className="studio-prompt">{scene.prompt}</pre></details></div>)}</section>}
        <div className="studio-actionbar"><span>{draft.duration_seconds / 5} cảnh × 5 giây <span className="studio-hint">· {draft.orientation === 'VERTICAL' ? '9:16' : '16:9'}</span></span><div className="flex gap-2"><button className="studio-button secondary" disabled={locked} onClick={preview}>{busy === 'preview' && <LoaderCircle size={14} className="animate-spin" />}{reviewed ? 'Cập nhật kịch bản' : 'Xem lại kịch bản'}</button><button className="studio-button" disabled={locked || !reviewed || !draft.assets.clothing?.media_id || pendingAssets} onClick={generate}>{busy === 'generate' || running ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}{running ? 'Đang tạo video…' : 'Tạo video'}</button></div></div>
      </div>
      <aside className="studio-result"><section className="studio-card"><div className="flex items-center justify-between mb-4"><h2>Video thành phẩm</h2><span className="studio-badge">{draft.duration_seconds}s</span></div>{job?.final_video_url ? <video className="studio-player" src={job.final_video_url} controls /> : <div className="studio-preview"><div className="preview-film"><Film size={31} /></div><h3>{running ? 'Đang tạo bộ sưu tập của bạn' : 'Sẵn sàng cho ý tưởng mới'}</h3><p>{running ? 'Các cảnh được xử lý lần lượt rồi ghép thành video.' : 'Tải ảnh, duyệt kịch bản và bắt đầu tạo video.'}</p></div>}{job && <div className="mt-4"><div className="flex justify-between mb-2 text-xs"><span>{job.status === 'COMPLETED' ? 'Hoàn thành' : job.status === 'FAILED' ? 'Tạo video chưa thành công' : 'Tiến độ xử lý'}</span><span>{job.progress}%</span></div><progress max={100} value={job.progress} className="studio-progress" /><p className="text-sm mt-2" role="status">{job.message}</p>{job.project_id && <Link className="studio-text-button" to={`/projects/${job.project_id}?tab=pipeline`}>Xem chi tiết từng cảnh →</Link>}<details className="mt-3"><summary>Nhật ký xử lý</summary><pre className="studio-log">{job.logs.join('\n')}</pre></details></div>}{job?.final_video_url && <a className="studio-button mt-4" href={job.final_video_url} download><Download size={16} /> Tải video</a>}</section><section className="studio-card mt-5"><div className="flex justify-between items-center mb-4"><h2>Video gần đây</h2><button aria-label="Làm mới video gần đây" className="studio-text-button" onClick={() => {setOutputError(''); void fetchAPI<{videos: Output[]}>('/api/studio/outputs').then(r => setOutputs(r.videos)).catch(e => setOutputError(message(e)))}}><RefreshCw size={15} /></button></div>{outputError && <p role="alert">{outputError}</p>}{outputs.length ? outputs.slice(0, 6).map(o => <a className="studio-output" key={o.stream_url} href={o.stream_url} target="_blank" rel="noreferrer"><span className="output-icon"><Film size={18} /></span><span className="min-w-0"><strong>{o.filename}</strong><small>{o.modified} · {o.size_mb} MB</small></span><ArrowRight size={14} /></a>) : <p className="studio-hint py-6 text-center">Video hoàn thành sẽ xuất hiện tại đây.</p>}<Link className="studio-text-button mt-3" to="/gallery">Mở thư viện video →</Link></section><p className="studio-hint px-1 mt-4">Giữ tab dự án Google Flow mở và ô prompt trống khi tạo. Lỗi hoặc từ chối nội dung từ Flow sẽ được hiển thị trong nhật ký.</p></aside>
    </div>
  </div>
}
