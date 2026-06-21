import { useEffect, useRef } from 'react'

const TYPE_STYLES = {
  log:   { color: '#e6edf3' },
  done:  { color: '#3fb950', fontWeight: 600 },
  error: { color: '#f85149', fontWeight: 600 },
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
      height: 380,
      overflowY: 'auto',
      fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.6,
    }}>
      {logs.length === 0 ? (
        <span style={{ color: '#484f58' }}>Waiting for healing run…</span>
      ) : (
        logs.map((msg, i) => (
          <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...TYPE_STYLES[msg.type] }}>
            <span style={{ color: '#484f58', userSelect: 'none' }}>{'› '}</span>
            {msg.message}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  )
}
