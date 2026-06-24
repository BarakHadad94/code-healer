import { useEffect, useRef } from 'react'

function styleForMsg(msg) {
  if (msg.type === 'done')  return { color: '#3fb950', fontWeight: 600 }
  if (msg.type === 'error') return { color: '#f85149', fontWeight: 600 }
  if (msg.type === 'skipped') return { color: '#d29922', fontWeight: 600 }
  const text = msg.message || ''
  if (text.startsWith('[Tool]'))   return { color: '#79c0ff' }
  if (text.startsWith('[Result]')) return { color: '#6e7681', fontSize: 12 }
  if (text.startsWith('['))        return { color: '#8b949e', fontSize: 12 }
  if (text.startsWith('---'))      return { color: '#3d444d', fontSize: 12 }
  return { color: '#e6edf3' }
}

export default function LogFeed({ logs }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div style={{
      background: '#161b22',
      border: '1px solid #30363d',
      borderRadius: 8,
      padding: '12px 16px',
      height: 400,
      overflowY: 'auto',
      fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.65,
    }}>
      {logs.length === 0 ? (
        <span style={{ color: '#3d444d' }}>Waiting for healing run…</span>
      ) : (
        logs.map((msg, i) => (
          <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...styleForMsg(msg) }}>
            <span style={{ color: '#3d444d', userSelect: 'none' }}>{'› '}</span>
            {msg.message}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  )
}
