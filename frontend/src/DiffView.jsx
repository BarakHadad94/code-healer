const LINE_STYLES = {
  added:   { background: '#0d4429', color: '#3fb950', borderLeft: '3px solid #3fb950' },
  removed: { background: '#3d1212', color: '#f85149', borderLeft: '3px solid #f85149' },
  hunk:    { background: '#0c2340', color: '#79c0ff', borderLeft: '3px solid #1f6feb' },
  file:    { background: '#21262d', color: '#8b949e', borderLeft: '3px solid #30363d' },
  context: { background: 'transparent', color: '#8b949e', borderLeft: '3px solid transparent' },
}

function classifyLine(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'file'
  if (line.startsWith('+')) return 'added'
  if (line.startsWith('-')) return 'removed'
  if (line.startsWith('@@')) return 'hunk'
  return 'context'
}

export default function DiffView({ diff }) {
  if (!diff) {
    return (
      <div style={{
        background: '#161b22',
        border: '1px solid #30363d',
        borderRadius: 8,
        padding: '12px 16px',
        height: 400,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#3d444d',
        fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace',
        fontSize: 13,
      }}>
        Diff will appear here after healing
      </div>
    )
  }

  const lines = diff.split('\n').filter(l => !l.startsWith('--- ') && !l.startsWith('+++ '))

  return (
    <div style={{
      background: '#161b22',
      border: '1px solid #30363d',
      borderRadius: 8,
      height: 400,
      overflowY: 'auto',
      fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.6,
    }}>
      {lines.map((line, i) => {
        const type = classifyLine(line)
        return (
          <div key={i} style={{ padding: '0 16px', whiteSpace: 'pre', ...LINE_STYLES[type] }}>
            {line || ' '}
          </div>
        )
      })}
    </div>
  )
}
