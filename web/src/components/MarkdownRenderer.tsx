import { Children, isValidElement, type ComponentProps, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MermaidDiagram } from './MermaidDiagram'

function MarkdownPre({ children, ...props }: ComponentProps<'pre'>) {
  const child = Children.toArray(children)[0]
  if (isValidElement<{ className?: string; children?: ReactNode }>(child) && child.props.className?.split(' ').includes('language-mermaid')) {
    const definition = String(child.props.children || '').replace(/\n$/, '')
    return <MermaidDiagram definition={definition} title="Diagrama Mermaid" />
  }
  return <pre {...props}>{children}</pre>
}

export function MarkdownRenderer({ content, className = 'markdown-body' }: { content: string; className?: string }) {
  return <div className={className}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre: MarkdownPre,
        a: ({ href, children, ...props }) => {
          const external = Boolean(href && /^(https?:)?\/\//i.test(href))
          return <a href={href} {...props} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>{children}</a>
        },
        img: ({ alt, ...props }) => <img {...props} alt={alt || ''} loading="lazy" decoding="async" />,
      }}
    >{content}</ReactMarkdown>
  </div>
}
