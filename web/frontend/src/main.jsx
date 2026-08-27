import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const DEFAULT_OPTIONS = { format: 'png', dpi: 150, preview_bg_alpha: 0.55, track_bg_alpha: 0.75, background_blur_sigma: 15, background_brightness: 0.75 }
const EMPTY_METADATA = { name: '', charter: '', level: '', composer: '' }

function App() {
  const [file, setFile] = useState(null)
  const [metadata, setMetadata] = useState(EMPTY_METADATA)
  const [metadataLoaded, setMetadataLoaded] = useState(false)
  const [metadataLoading, setMetadataLoading] = useState(false)
  const [job, setJob] = useState(null)
  const [submittedFormat, setSubmittedFormat] = useState('png')
  const [error, setError] = useState('')
  const [options, setOptions] = useState(DEFAULT_OPTIONS)
  const metadataRequest = useRef(0)

  useEffect(() => {
    if (!job || ['succeeded', 'failed'].includes(job.status)) return undefined
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/jobs/${job.id}`)
        const next = await response.json()
        if (!response.ok) throw new Error(next.detail || '任务查询失败')
        setJob(next)
      } catch (err) { setError(err.message) }
    }, 1000)
    return () => clearInterval(timer)
  }, [job])

  async function loadMetadata(nextFile) {
    const request = ++metadataRequest.current
    setMetadata(EMPTY_METADATA); setMetadataLoaded(false); setMetadataLoading(true); setError('')
    const body = new FormData(); body.append('file', nextFile)
    try {
      const response = await fetch(`${API_BASE}/api/v1/charts/metadata`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '无法读取谱面元数据')
      if (request === metadataRequest.current) {
        setMetadata({ name: data.name || '', charter: data.charter || '', level: data.level || '', composer: data.composer || '' })
        setMetadataLoaded(true)
      }
    } catch (err) {
      if (request === metadataRequest.current) setError(err.message)
    } finally {
      if (request === metadataRequest.current) setMetadataLoading(false)
    }
  }

  function applyFile(nextFile) {
    setFile(nextFile); setJob(null)
    if (nextFile) loadMetadata(nextFile)
    else { metadataRequest.current += 1; setMetadata(EMPTY_METADATA); setMetadataLoaded(false) }
  }

  function handleFileChange(event) { applyFile(event.target.files?.[0] || null) }
  function handleDrop(event) {
    event.preventDefault()
    applyFile(event.dataTransfer.files?.[0] || null)
  }

  function updateMetadata(field, value) { setMetadata(current => ({ ...current, [field]: value })) }
  function resetAdvanced() { setOptions(current => ({ ...current, dpi: DEFAULT_OPTIONS.dpi, preview_bg_alpha: DEFAULT_OPTIONS.preview_bg_alpha, track_bg_alpha: DEFAULT_OPTIONS.track_bg_alpha, background_blur_sigma: DEFAULT_OPTIONS.background_blur_sigma, background_brightness: DEFAULT_OPTIONS.background_brightness })) }

  async function submit(event) {
    event.preventDefault()
    if (!file) return setError('请选择 JSON、PEZ 或 ZIP 文件')
    if (!metadataLoaded) return setError('请等待谱面元数据加载完成后再渲染')
    setError(''); setJob(null); setSubmittedFormat(options.format)
    const body = new FormData(); body.append('file', file)
    Object.entries(options).forEach(([key, value]) => body.append(key, value))
    Object.entries(metadata).forEach(([key, value]) => body.append(key, value))
    try {
      const response = await fetch(`${API_BASE}/api/v1/jobs`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '任务创建失败')
      setJob(data)
    } catch (err) { setError(err.message) }
  }

  const busy = job && ['queued', 'running'].includes(job.status)
  return <main className="page">
    <section className="card">
      <div className="eyebrow">RPE PREVIEW RENDERER</div>
      <h1>Phigros 谱面预览</h1>
      <p className="muted intro">加载谱面后可修改渲染图信息，并选择合适的输出格式。</p>
      <form onSubmit={submit}>
        <label className="dropzone" onDragOver={event => event.preventDefault()} onDrop={handleDrop}>
          <input type="file" accept=".json,.pez,.zip" onChange={handleFileChange} />
          <span className="upload-icon">↑</span><strong>{file ? file.name : '点击选择或拖入谱面文件'}</strong><small>支持 JSON、PEZ、ZIP</small>
        </label>
        {file && <section className="panel metadata-panel">
          <div className="panel-heading"><div><h2>谱面元数据</h2><p className="muted">这些内容会显示在渲染图底部信息栏中。</p></div>{metadataLoading && <span className="loading">读取中…</span>}</div>
          <div className="metadata-grid">
            <label>谱面名称<input value={metadata.name} maxLength="200" onChange={e => updateMetadata('name', e.target.value)} placeholder="例如：SONG NAME" disabled={metadataLoading} /></label>
            <label>谱师<input value={metadata.charter} maxLength="200" onChange={e => updateMetadata('charter', e.target.value)} placeholder="Charter" disabled={metadataLoading} /></label>
            <label>难度<input value={metadata.level} maxLength="80" onChange={e => updateMetadata('level', e.target.value)} placeholder="例如：AT 14" disabled={metadataLoading} /></label>
            <label>曲师<input value={metadata.composer} maxLength="200" onChange={e => updateMetadata('composer', e.target.value)} placeholder="Composer" disabled={metadataLoading} /></label>
          </div>
        </section>}
        <section className="panel format-panel">
          <div className="panel-heading"><div><h2>输出设置</h2><p className="muted">PNG 图像质量更高但体积大；JPG 兼容性更好、文件更小。</p></div></div>
          <label>输出格式<select value={options.format} onChange={e => setOptions({...options, format: e.target.value})}><option value="png">PNG（默认）</option><option value="jpg">JPG（兼容性好）</option></select></label>
        </section>
        <details className="advanced">
          <summary><span>高级设置</span><small>通常保持默认；修改可能影响渲染效果或耗时</small></summary>
          <div className="advanced-content"><div className="notice">高级参数直接影响画布清晰度、背景处理与轨道可读性。遇到渲染异常时，请先恢复默认值。</div>
            <div className="advanced-grid">
              <label>DPI<input type="number" min="72" max="600" step="1" value={options.dpi} onChange={e => setOptions({...options, dpi: e.target.value})} /><small>输出清晰度，范围 72–600</small></label>
              <label>预览背景透明度<input type="number" min="0" max="1" step="0.05" value={options.preview_bg_alpha} onChange={e => setOptions({...options, preview_bg_alpha: e.target.value})} /><small>越高越暗，0 为关闭</small></label>
              <label>轨道透明度<input type="number" min="0" max="1" step="0.05" value={options.track_bg_alpha} onChange={e => setOptions({...options, track_bg_alpha: e.target.value})} /><small>越高轨道区分越明显</small></label>
              <label>曲绘模糊强度<input type="number" min="0" max="100" step="1" value={options.background_blur_sigma} onChange={e => setOptions({...options, background_blur_sigma: e.target.value})} /><small>0 为不模糊</small></label>
              <label>曲绘亮度<input type="number" min="0" max="2" step="0.05" value={options.background_brightness} onChange={e => setOptions({...options, background_brightness: e.target.value})} /><small>1 为原始亮度</small></label>
            </div><button type="button" className="secondary" onClick={resetAdvanced}>恢复高级设置默认值</button>
          </div>
        </details>
        <button className="primary" type="submit" disabled={!file || !metadataLoaded || metadataLoading || busy}>{busy ? '渲染中…' : '开始渲染'}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {job && <div className="result"><div className="status-line"><span>状态：{job.status === 'queued' ? '排队中' : job.status === 'running' ? '渲染中' : job.status === 'succeeded' ? '已完成' : '失败'}</span><span>{job.progress}%</span></div><div className="progress"><i style={{ width: `${job.progress}%` }} /></div>{job.error && <p className="error">{job.error}</p>}{job.status === 'succeeded' && <><img src={`${API_BASE}${job.result_url}`} /><a className="download" href={`${API_BASE}${job.result_url}`} download={`preview.${submittedFormat}`}>下载 {submittedFormat.toUpperCase()}</a></>}</div>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App />)
