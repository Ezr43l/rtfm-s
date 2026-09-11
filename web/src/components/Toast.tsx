import { CircleAlert, CircleCheck, X } from 'lucide-react'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'

export type ToastTone = 'success' | 'error'

export function Toast({ message, tone, onDismiss, duration = 3000 }: {
  message: string
  tone: ToastTone
  onDismiss: () => void
  duration?: number
}) {
  useEffect(() => {
    const timeout = window.setTimeout(onDismiss, duration)
    return () => window.clearTimeout(timeout)
  }, [duration, onDismiss])

  return createPortal(
    <div
      className={`floating-toast ${tone}`}
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      aria-atomic="true"
    >
      {tone === 'success' ? <CircleCheck size={21} /> : <CircleAlert size={21} />}
      <span>{message}</span>
      <button type="button" onClick={onDismiss} aria-label="Cerrar aviso"><X size={17} /></button>
    </div>,
    document.body,
  )
}
