const LINE_STYLES = {
  added:    { background: '#0d4429', color: '#3fb950', borderLeft: '3px solid #3fb950' },
  removed:  { background: '#3d1212', color: '#f85149', borderLeft: '3px solid #f85149' },
  hunk:     { background: '#0c2340', color: '#79c0ff', borderLeft: '3px solid #1f6feb' },
  filename: { background: '#1c2128', color: '#8b949e', borderLeft: '3px solid #30363d', fontStyle: 'italic' },
  context:  { background: 'transparent', color: '#8b949e', borderLeft: '3px solid transparent' },
}

function classifyLine(line) {
  if (line.startsWith('+')) return 'added'
  if (line.startsWith('-')) return 'removed'
  if (line.startsWith('@@')) return 'hunk'
  return 'context'
}

function parseDiff(raw) {
  const lines = raw.split('\n')
  const fileCount = lines.filter(l => l.startsWith('diff --git ')).length
  const multiFile = fileCount > 1

  const out = []
  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      if (multiFile) {
        // "diff --git a/foo/bar.py b/foo/bar.py" → "foo/bar.py"
        const m = line.match(/^diff --git a\/.+ b\/(.+)$/)
        out.push({ type: 'filename', content: m ? m[1] : line })
      }
    } else if (
      line.startsWith('--- ') ||
      line.startsWith('+++ ') ||
      line.startsWith('index ')
    ) {
      // always strip these — redundant with the filename header above
    } else {
      out.push({ type: classifyLine(line), content: line })
    }
  }
  return out
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

  const rows = parseDiff(diff)

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
      {rows.map((row, i) => (
        <div
          key={i}
          style={{
            padding: row.type === 'filename' ? '4px 16px' : '0 16px',
            whiteSpace: 'pre',
            fontSize: row.type === 'filename' ? 11 : 13,
            ...LINE_STYLES[row.type],
          }}
        >
          {row.content || ' '}
        </div>
      ))}
    </div>
  )
}
