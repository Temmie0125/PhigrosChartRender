import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

function App() {
  const [file, setFile] = useState(null)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [options, setOptions] = useState({ dpi: 150, preview_bg_alpha: 0.55, track_bg_alpha: 0.75 })

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

  async function submit(event) {
    event.preventDefault()
    if (!file) return setError('请选择 JSON、PEZ 或 ZIP 文件')
    setError(''); setJob(null)
    const body = new FormData(); body.append('file', file)
    Object.entries(options).forEach(([key, value]) => body.append(key, value))
    try {
      const response = await fetch(`${API_BASE}/api/v1/jobs`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '任务创建失败')
      setJob(data)
    } catch (err) { setError(err.message) }
  }

  return <main className="page">
    <section className="card">
      <h1>Phigros 谱面预览</h1>
      <p className="muted">上传谱面 JSON、PEZ 或 ZIP，异步生成预览图。</p>
      <form onSubmit={submit}>
        <label className="dropzone">
          <input type="file" accept=".json,.pez,.zip" onChange={e => setFile(e.target.files?.[0] || null)} />
          <span>{file ? file.name : '点击选择或拖入谱面文件'}</span>
        </label>
        <div className="options">
          <label>DPI <input type="number" min="72" max="600" value={options.dpi} onChange={e => setOptions({...options, dpi: e.target.value})} /></label>
          <label>预览背景透明度 <input type="number" min="0" max="1" step="0.05" value={options.preview_bg_alpha} onChange={e => setOptions({...options, preview_bg_alpha: e.target.value})} /></label>
          <label>轨道透明度 <input type="number" min="0" max="1" step="0.05" value={options.track_bg_alpha} onChange={e => setOptions({...options, track_bg_alpha: e.target.value})} /></label>
        </div>
        <details><summary>高级设置</summary><p className="muted">高级渲染参数将在后续版本开放。</p></details>
        <button type="submit" disabled={!file || (job && ['queued', 'running'].includes(job.status))}>开始渲染</button>
      </form>
      {error && <p className="error">{error}</p>}
      {job && <div className="result"><p>状态：{job.status}（{job.progress}%）</p>{job.error && <p className="error">{job.error}</p>}{job.status === 'succeeded' && <><img src={`${API_BASE}${job.result_url}`} /><a className="download" href={`${API_BASE}${job.result_url}`} download="preview.png">下载 PNG</a></>}</div>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App />)
