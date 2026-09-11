import { AlertTriangle, Download, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useTheme } from '../context/ThemeContext'

export function MermaidDiagram({ definition, title = 'Diagrama', controls = true }: {
  definition: string
  title?: string
  controls?: boolean
}) {
  const { theme } = useTheme()
  const reactId = useId().replace(/[^a-zA-Z0-9]/g, '')
  const renderCount = useRef(0)
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const timeout = window.setTimeout(async () => {
      if (!definition.trim()) {
        setSvg(''); setError('El diagrama está vacío'); setLoading(false)
        return
      }
      setLoading(true); setError('')
      const diagramId = `mermaid-${reactId}-${++renderCount.current}`
      try {
        const { default: mermaid } = await import('mermaid')
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          suppressErrorRendering: true,
          theme: theme === 'dark' ? 'dark' : 'default',
          fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
          flowchart: { htmlLabels: false, useMaxWidth: true },
        })
        const rendered = await mermaid.render(diagramId, definition)
        if (!cancelled) setSvg(rendered.svg)
      } catch (caught) {
        document.getElementById(diagramId)?.remove()
        if (!cancelled) {
          const detail = caught instanceof Error ? caught.message.split('\n')[0] : 'Sintaxis no válida'
          setSvg(''); setError(detail || 'No se pudo representar el diagrama')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 180)
    return () => { cancelled = true; window.clearTimeout(timeout) }
  }, [definition, reactId, theme])

  const download = () => {
    if (!svg) return
    const blob = new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${svg}`], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${title.toLocaleLowerCase('es-ES').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'diagrama'}.svg`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return <figure className={`mermaid-diagram ${error ? 'has-error' : ''}`}>
    {controls && <figcaption><span>{title}</span>{svg && <button type="button" onClick={download} title="Descargar como SVG"><Download size={16} /> SVG</button>}</figcaption>}
    <div className="mermaid-canvas">
      {loading ? <span className="diagram-loading"><LoaderCircle size={23} className="spin" /> Generando diagrama…</span> : error ?
        <div className="diagram-error"><AlertTriangle size={22} /><div><strong>No se puede representar</strong><span>{error}</span></div></div> :
        <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />}
    </div>
  </figure>
}
