import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const DEFAULT_OPTIONS = {
  format: 'png',
  dpi: 150,
  tile_workers: 0,
  preview_bg_alpha: 0.55,
  track_bg_alpha: 0.75,
  background_blur_sigma: 15,
  background_brightness: 0.75,
  fit_official_divisions: false,
  smart_column_beats: true,
  column_beats: 64,
}
const EMPTY_METADATA = { name: '', charter: '', level: '', composer: '' }
const MIN_PREVIEW_SCALE = 0.5
const MAX_PREVIEW_SCALE = 4
const PREVIEW_ZOOM_STEP = 0.25

function SectionHeading({ number, children }) {
  return <div className="section-header">
    <span className="section-num">{number}</span>
    <span className="section-title">{children}</span>
    <div className="section-line" />
  </div>
}

function SegmentedControl({ value, options, onChange, ariaLabel }) {
  const activeIndex = Math.max(0, options.findIndex(option => option.value === value))
  return <div className="toggle-group" role="group" aria-label={ariaLabel}>
    <div className="toggle-base" />
    <div className="toggle-selector" style={{ transform: `translateX(${activeIndex * 100}%)` }} />
    {options.map(option => <button
      key={option.value}
      type="button"
      className={`toggle-option${value === option.value ? ' active' : ''}`}
      aria-pressed={value === option.value}
      onClick={() => onChange(option.value)}
    >
      <span className="toggle-content"><span>{option.label}</span></span>
    </button>)}
  </div>
}

function SliderField({ label, value, min, max, step, formatValue, onChange }) {
  const displayValue = formatValue ? formatValue(value) : value
  const update = nextValue => onChange(Math.max(min, Math.min(max, Number(nextValue))))
  return <div className="slider-field">
    <div className="slider-header">
      <label className="field-label" htmlFor={`slider-${label}`}>{label}</label>
      <output className="slider-value">{displayValue}</output>
    </div>
    <div className="slider-control">
      <button type="button" className="slider-btn minus" aria-label={`减少${label}`} onClick={() => update(value - step)}><span>−</span></button>
      <input
        id={`slider-${label}`}
        className="slider-native"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={event => update(event.target.value)}
        aria-label={label}
      />
      <button type="button" className="slider-btn plus" aria-label={`增加${label}`} onClick={() => update(value + step)}><span>+</span></button>
    </div>
  </div>
}

function statusLabel(status) {
  return { queued: '排队中', running: '渲染中', succeeded: '已完成', failed: '失败' }[status] || status
}

function App() {
  const [file, setFile] = useState(null)
  const [metadata, setMetadata] = useState(EMPTY_METADATA)
  const [metadataLoaded, setMetadataLoaded] = useState(false)
  const [metadataLoading, setMetadataLoading] = useState(false)
  const [job, setJob] = useState(null)
  const [submittedFormat, setSubmittedFormat] = useState('png')
  const [error, setError] = useState('')
  const [options, setOptions] = useState(DEFAULT_OPTIONS)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const metadataRequest = useRef(0)
  const previewRef = useRef(null)
  const dragRef = useRef(null)
  const [previewScale, setPreviewScale] = useState(1)
  const [previewPan, setPreviewPan] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (!job || ['succeeded', 'failed'].includes(job.status)) return undefined
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/jobs/${job.id}`)
        const next = await response.json()
        if (!response.ok) throw new Error(next.detail || '任务查询失败')
        setJob(next)
      } catch (err) {
        setError(err.message)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [job])

  async function loadMetadata(nextFile) {
    const request = ++metadataRequest.current
    setMetadata(EMPTY_METADATA)
    setMetadataLoaded(false)
    setMetadataLoading(true)
    setError('')
    const body = new FormData()
    body.append('file', nextFile)
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
    setFile(nextFile)
    setJob(null)
    if (nextFile) {
      loadMetadata(nextFile)
    } else {
      metadataRequest.current += 1
      setMetadata(EMPTY_METADATA)
      setMetadataLoaded(false)
    }
  }

  function handleFileChange(event) { applyFile(event.target.files?.[0] || null) }

  function handleDrop(event) {
    event.preventDefault()
    applyFile(event.dataTransfer.files?.[0] || null)
  }

  function updateMetadata(field, value) {
    setMetadata(current => ({ ...current, [field]: value }))
  }

  function updateOption(field, value) {
    setOptions(current => ({ ...current, [field]: value }))
  }

  function resetAdvanced() {
    setOptions(current => ({
      ...current,
      dpi: DEFAULT_OPTIONS.dpi,
      tile_workers: DEFAULT_OPTIONS.tile_workers,
      preview_bg_alpha: DEFAULT_OPTIONS.preview_bg_alpha,
      track_bg_alpha: DEFAULT_OPTIONS.track_bg_alpha,
      background_blur_sigma: DEFAULT_OPTIONS.background_blur_sigma,
      background_brightness: DEFAULT_OPTIONS.background_brightness,
      fit_official_divisions: DEFAULT_OPTIONS.fit_official_divisions,
    }))
  }

  async function submit(event) {
    event.preventDefault()
    if (!file) return setError('请选择 JSON、PEZ 或 ZIP 文件')
    if (!metadataLoaded) return setError('请等待谱面元数据加载完成后再渲染')
    setError('')
    setJob(null)
    setSubmittedFormat(options.format)
    const body = new FormData()
    body.append('file', file)
    Object.entries(options).forEach(([key, value]) => body.append(key, value))
    Object.entries(metadata).forEach(([key, value]) => body.append(key, value))
    try {
      const response = await fetch(`${API_BASE}/api/v1/jobs`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '任务创建失败')
      setJob(data)
    } catch (err) {
      setError(err.message)
    }
  }

  const busy = job && ['queued', 'running'].includes(job.status)
  const previewUrl = job?.status === 'succeeded' && job.result_url ? `${API_BASE}${job.result_url}` : null

  useEffect(() => {
    setPreviewScale(1)
    setPreviewPan({ x: 0, y: 0 })
  }, [previewUrl])

  function resetPreview() {
    setPreviewScale(1)
    setPreviewPan({ x: 0, y: 0 })
  }

  function zoomPreview(nextScale, anchor) {
    const clampedScale = Math.max(MIN_PREVIEW_SCALE, Math.min(MAX_PREVIEW_SCALE, nextScale))
    if (anchor && previewRef.current && previewScale !== clampedScale) {
      const rect = previewRef.current.getBoundingClientRect()
      const pointX = anchor.x - rect.left - rect.width / 2
      const pointY = anchor.y - rect.top - rect.height / 2
      setPreviewPan(current => ({
        x: pointX - ((pointX - current.x) / previewScale) * clampedScale,
        y: pointY - ((pointY - current.y) / previewScale) * clampedScale,
      }))
    }
    setPreviewScale(clampedScale)
  }

  function handlePreviewWheel(event) {
    if (!previewUrl) return
    event.preventDefault()
    zoomPreview(previewScale * (event.deltaY < 0 ? 1.1 : 0.9), { x: event.clientX, y: event.clientY })
  }

  function handlePreviewPointerDown(event) {
    if (!previewUrl || event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, startPan: previewPan }
  }

  function handlePreviewPointerMove(event) {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    setPreviewPan({ x: drag.startPan.x + event.clientX - drag.startX, y: drag.startPan.y + event.clientY - drag.startY })
  }

  function handlePreviewPointerUp(event) {
    if (dragRef.current?.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    dragRef.current = null
  }

  return <main className="app-shell">
    <div className="grid-bg" aria-hidden="true" />
    <div className="accent-line accent-line-1" aria-hidden="true" />
    <div className="accent-line accent-line-2" aria-hidden="true" />

    <header className="top-bar">
      <div className="logo">PHIGROS</div>
      <div className="version">谱面渲染器 v2.0</div>
    </header>

    <div className="viewport">
      <div className="stage">
        <section className="preview-zone" aria-label="谱面预览">
          <div
            ref={previewRef}
            className={`preview-placeholder${busy ? ' scanning' : ''}${previewUrl ? ' has-result' : ''}`}
            onWheel={handlePreviewWheel}
            onPointerDown={handlePreviewPointerDown}
            onPointerMove={handlePreviewPointerMove}
            onPointerUp={handlePreviewPointerUp}
            onPointerCancel={handlePreviewPointerUp}
          >
            {previewUrl ? <img className="preview-image" src={previewUrl} alt="谱面渲染结果" draggable="false" style={{ transform: `translate3d(${previewPan.x}px, ${previewPan.y}px, 0) scale(${previewScale})` }} /> : <div className="preview-content">
              <div className="preview-icon" aria-hidden="true"><span>♪</span></div>
              <div className="preview-text">{job?.status === 'failed' ? '渲染失败' : busy ? '正在生成预览' : '尚未载入谱面'}</div>
            </div>}
          </div>
          <div className="preview-toolbar" aria-label="预览缩放控制">
            <button type="button" className="preview-control" aria-label="缩小预览" title="缩小" disabled={!previewUrl || previewScale <= MIN_PREVIEW_SCALE} onClick={() => zoomPreview(previewScale - PREVIEW_ZOOM_STEP)}>−</button>
            <span className="preview-zoom-value" aria-live="polite">{Math.round(previewScale * 100)}%</span>
            <button type="button" className="preview-control" aria-label="放大预览" title="放大" disabled={!previewUrl || previewScale >= MAX_PREVIEW_SCALE} onClick={() => zoomPreview(previewScale + PREVIEW_ZOOM_STEP)}>+</button>
            <button type="button" className="preview-control reset-preview" aria-label="重置预览" title="重置" disabled={!previewUrl} onClick={resetPreview}>↺</button>
          </div>
        </section>

        <section className="control-zone">
          <div className="control-inner">
            <form onSubmit={submit}>
              <section className="section">
                <SectionHeading number="01">谱面文件</SectionHeading>
                <label
                  className={`upload-box${file ? ' active' : ''}`}
                  onDragOver={event => event.preventDefault()}
                  onDrop={handleDrop}
                >
                  <input type="file" accept=".json,.pez,.zip" onChange={handleFileChange} />
                  <span className="upload-inner">
                    <span className="upload-label">选择谱面文件</span>
                    <span className="upload-hint">支持 JSON / PEZ / ZIP</span>
                    {file && <span className="file-name">{file.name}</span>}
                  </span>
                </label>
              </section>

              <section className="section">
                <SectionHeading number="02">谱面信息</SectionHeading>
                <div className="field-group">
                  <div className="field">
                    <label className="field-label" htmlFor="metadata-name">曲名</label>
                    <input id="metadata-name" className="field-input" value={metadata.name} maxLength="200" onChange={event => updateMetadata('name', event.target.value)} placeholder="请输入曲名" disabled={!file || metadataLoading} />
                  </div>
                  <div className="field-row">
                    <div className="field">
                      <label className="field-label" htmlFor="metadata-charter">谱师</label>
                      <input id="metadata-charter" className="field-input" value={metadata.charter} maxLength="200" onChange={event => updateMetadata('charter', event.target.value)} placeholder="谱师名" disabled={!file || metadataLoading} />
                    </div>
                    <div className="field">
                      <label className="field-label" htmlFor="metadata-level">难度</label>
                      <input id="metadata-level" className="field-input" value={metadata.level} maxLength="80" onChange={event => updateMetadata('level', event.target.value)} placeholder="如 AT 14" disabled={!file || metadataLoading} />
                    </div>
                  </div>
                  <div className="field">
                    <label className="field-label" htmlFor="metadata-composer">曲师</label>
                    <input id="metadata-composer" className="field-input" value={metadata.composer} maxLength="200" onChange={event => updateMetadata('composer', event.target.value)} placeholder="曲师名" disabled={!file || metadataLoading} />
                  </div>
                  {metadataLoading && <span className="loading">读取谱面信息中…</span>}
                </div>
              </section>

              <section className="section">
                <SectionHeading number="03">输出设置</SectionHeading>
                <div className="field-group">
                  <div className="field">
                    <span className="field-label">图片格式</span>
                    <SegmentedControl
                      value={options.format}
                      options={[{ value: 'png', label: 'PNG' }, { value: 'jpg', label: 'JPG' }]}
                      onChange={value => updateOption('format', value)}
                      ariaLabel="图片格式"
                    />
                  </div>
                  <div className="field">
                    <span className="field-label">分栏模式</span>
                    <SegmentedControl
                      value={options.smart_column_beats ? 'auto' : 'manual'}
                      options={[{ value: 'auto', label: '智能' }, { value: 'manual', label: '手动' }]}
                      onChange={value => updateOption('smart_column_beats', value === 'auto')}
                      ariaLabel="分栏模式"
                    />
                  </div>
                  {!options.smart_column_beats && <div className="field custom-column-field">
                    <label className="field-label" htmlFor="column-beats">每栏拍数</label>
                    <input id="column-beats" className="field-input" type="number" min="16" max="128" step="4" value={options.column_beats} onChange={event => updateOption('column_beats', Number(event.target.value))} />
                    <span className="field-hint">范围 16–128，以 4 拍为一档</span>
                  </div>}
                </div>
              </section>

              <section className="section">
                <SectionHeading number="04">渲染参数</SectionHeading>
                <SliderField label="DPI" value={options.dpi} min={72} max={600} step={1} onChange={value => updateOption('dpi', value)} />
                <SliderField label="分块并发" value={options.tile_workers} min={0} max={32} step={1} formatValue={value => Number(value) === 0 ? '自动' : value} onChange={value => updateOption('tile_workers', value)} />
                <SliderField label="背景模糊" value={options.background_blur_sigma} min={0} max={100} step={1} onChange={value => updateOption('background_blur_sigma', value)} />
                <SliderField label="背景亮度" value={options.background_brightness} min={0} max={2} step={0.05} formatValue={value => Number(value).toFixed(2)} onChange={value => updateOption('background_brightness', value)} />
              </section>

              <section className="collapse-section">
                <button type="button" className={`collapse-trigger${advancedOpen ? ' active' : ''}`} onClick={() => setAdvancedOpen(open => !open)} aria-expanded={advancedOpen}>
                  <span className="collapse-icon">▶</span>
                  <span>高级选项</span>
                  <span className="collapse-caption">透明度与官谱拟合</span>
                </button>
                {advancedOpen && <div className="collapse-content active">
                  <div className="info-note">以下参数会直接影响渲染质量与耗时，如果出现异常请恢复默认值。</div>
                  <SliderField label="预览层不透明度" value={options.preview_bg_alpha} min={0} max={1} step={0.05} formatValue={value => Number(value).toFixed(2)} onChange={value => updateOption('preview_bg_alpha', value)} />
                  <SliderField label="轨道层不透明度" value={options.track_bg_alpha} min={0} max={1} step={0.05} formatValue={value => Number(value).toFixed(2)} onChange={value => updateOption('track_bg_alpha', value)} />
                  <label className="experimental-toggle">
                    <input type="checkbox" checked={options.fit_official_divisions} onChange={event => updateOption('fit_official_divisions', event.target.checked)} />
                    <span><strong>启用官谱分音拟合（实验性）</strong><small>仅建议用于官谱转换得到的 RPE 谱面，可能改变 Note 位置。</small></span>
                  </label>
                  <button type="button" className="reset-btn" onClick={resetAdvanced}>恢复高级设置默认值</button>
                </div>}
              </section>

              <div className="divider" />
              <button className="action-btn" type="submit" disabled={!file || !metadataLoaded || metadataLoading || busy}><span>{busy ? '渲染中…' : '开始渲染'}</span></button>
            </form>

            {error && <p className="error" role="alert">{error}</p>}
            {job && <div className="status-bar" aria-live="polite">
              <div className="status-row"><span className="status-label">状态</span><span className="status-value">{statusLabel(job.status)}</span></div>
              <div className="status-row"><span className="status-label">进度</span><span className="status-value">{job.progress}%</span></div>
              <div className="progress-track"><div className="progress-bar" style={{ width: `${job.progress}%` }} /></div>
              {job.error && <p className="error">{job.error}</p>}
              {previewUrl && <a className="download-btn" href={previewUrl} download={`preview.${submittedFormat}`}><span>下载结果</span></a>}
            </div>}
          </div>
        </section>
      </div>
    </div>
  </main>
}

createRoot(document.getElementById('root')).render(<App />)
