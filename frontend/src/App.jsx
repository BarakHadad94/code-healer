import { useState, useRef, useEffect } from 'react'
import LogFeed from './LogFeed'
import DiffView from './DiffView'

const STATUS_BADGE = {
  idle:    { label: 'Idle',    bg: '#21262d', color: '#8b949e' },
  running: { label: 'Healing', bg: '#0c2340', color: '#58a6ff' },
  success: { label: 'Healed',  bg: '#0d4429', color: '#3fb950' },
  failed:  { label: 'Failed',  bg: '#3d1212', color: '#f85149' },
  skipped: { label: 'Skipped', bg: '#2a1f00', color: '#d29922' },
}

function statusBadge(status) {
  if (status === 'running') return STATUS_BADGE.running
  if (status === 'success') return STATUS_BADGE.success
  if (status === 'skipped') return STATUS_BADGE.skipped
  if (status === 'failed') return STATUS_BADGE.failed
  return STATUS_BADGE.idle
}

function activationBadge(reason) {
  if (reason === 'self_heal') return { label: 'Self-heal', bg: '#0c2340', color: '#58a6ff' }
  if (reason === 'deep_review') return { label: 'Deep review', bg: '#2d1f4e', color: '#bc8cff' }
  if (reason === 'skipped') return { label: 'Skipped', bg: '#2a1f00', color: '#d29922' }
  return { label: '—', bg: '#21262d', color: '#8b949e' }
}

export default function App() {
  const [form, setForm] = useState({
    repo: 'demo/repo',
    file_path: 'calculator.py',
    error_log: '',
    workspace: '',
    changed_files: '',
  })
  const [logs, setLogs] = useState([])
  const [diff, setDiff] = useState('')
  const [status, setStatus] = useState('idle')
  const [runs, setRuns] = useState([])
  const wsRef = useRef(null)

  useEffect(() => {
    fetchHistory()
  }, [])

  function fetchHistory() {
    fetch('/runs')
      .then(r => r.json())
      .then(setRuns)
      .catch(() => {})
  }

  async function startHealing() {
    if (wsRef.current) wsRef.current.close()
    setLogs([])
    setDiff('')
    setStatus('running')

    let runId
    try {
      const payload = {
        ...form,
        changed_files: form.changed_files
          .split(/[\n,]/)
          .map(s => s.trim())
          .filter(Boolean),
      }
      const res = await fetch('/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      runId = data.run_id
    } catch (e) {
      setStatus('failed')
      setLogs([{ type: 'error', message: `Failed to reach backend: ${e.message}` }])
      return
    }

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${wsProto}//${window.location.host}/ws/logs/${runId}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'diff') {
        setDiff(msg.message)
      } else if (msg.type === 'done') {
        setStatus('success')
        setLogs(prev => [...prev, msg])
        fetchHistory()
      } else if (msg.type === 'skipped') {
        setStatus('skipped')
        setLogs(prev => [...prev, msg])
        fetchHistory()
      } else if (msg.type === 'error') {
        setStatus('failed')
        setLogs(prev => [...prev, msg])
        fetchHistory()
      } else {
        setLogs(prev => [...prev, msg])
      }
    }

    ws.onerror = () => {
      setStatus('failed')
      setLogs(prev => [...prev, { type: 'error', message: 'WebSocket connection lost' }])
    }
  }

  const badge = STATUS_BADGE[status]

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px' }}>
          ⚕ code-healer
        </h1>
        <span style={{
          padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
          background: badge.bg, color: badge.color,
        }}>
          {badge.label}
        </span>
      </div>

      {/* Trigger form */}
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 8, padding: 20, marginBottom: 24,
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: '#8b949e', marginBottom: 14, textTransform: 'uppercase', letterSpacing: 1 }}>
          Trigger Healing Run
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <label style={labelStyle}>
            Repo
            <input
              value={form.repo}
              onChange={e => setForm(f => ({ ...f, repo: e.target.value }))}
              placeholder="org/repo"
            />
          </label>
          <label style={labelStyle}>
            File path (workspace-relative)
            <input
              value={form.file_path}
              onChange={e => setForm(f => ({ ...f, file_path: e.target.value }))}
              placeholder="src/calculator.py"
            />
          </label>
        </div>
        <label style={{ ...labelStyle, marginBottom: 12, display: 'block' }}>
          Workspace (absolute path on server)
          <input
            value={form.workspace}
            onChange={e => setForm(f => ({ ...f, workspace: e.target.value }))}
            placeholder="/absolute/path/to/workspace"
          />
        </label>
        <label style={{ ...labelStyle, marginBottom: 12, display: 'block' }}>
          Changed files (optional — comma or newline separated, for sensitive-path detection)
          <input
            value={form.changed_files}
            onChange={e => setForm(f => ({ ...f, changed_files: e.target.value }))}
            placeholder="auth/session.py, payments/checkout.py"
          />
        </label>
        <label style={{ ...labelStyle, marginBottom: 16, display: 'block' }}>
          Error log (optional — pre-check captures pytest output automatically)
          <textarea
            rows={5}
            value={form.error_log}
            onChange={e => setForm(f => ({ ...f, error_log: e.target.value }))}
            placeholder="Leave empty — pytest runs automatically before the agent"
            style={{ resize: 'vertical' }}
          />
        </label>
        <button
          onClick={startHealing}
          disabled={status === 'running' || !form.workspace || !form.file_path}
          style={{ background: '#238636', color: '#fff' }}
        >
          {status === 'running' ? 'Healing…' : 'Start Healing'}
        </button>
      </div>

      {/* Log feed + Diff view */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
        <div>
          <SectionLabel>Agent Reasoning</SectionLabel>
          <LogFeed logs={logs} />
        </div>
        <div>
          <SectionLabel>Code Diff</SectionLabel>
          <DiffView diff={diff} />
        </div>
      </div>

      {/* Run history */}
      <div>
        <SectionLabel>Run History</SectionLabel>
        <div style={{
          background: '#161b22', border: '1px solid #30363d',
          borderRadius: 8, overflow: 'hidden',
        }}>
          {runs.length === 0 ? (
            <p style={{ padding: '20px 16px', color: '#484f58' }}>No runs yet.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #21262d' }}>
                  {['Repo', 'File', 'Status', 'Activation', 'Iterations', 'Started'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.id} style={{ borderBottom: '1px solid #21262d' }}>
                    <td style={tdStyle}>{run.repo}</td>
                    <td style={{ ...tdStyle, fontFamily: 'Cascadia Code, monospace' }}>{run.file_path}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                        ...statusBadge(run.status),
                      }}>
                        {run.status}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                        ...activationBadge(run.activation_reason),
                      }}>
                        {activationBadge(run.activation_reason).label}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, color: '#8b949e' }}>{run.iterations ?? '—'}</td>
                    <td style={{ ...tdStyle, color: '#8b949e', fontFamily: 'Cascadia Code, monospace', fontSize: 12 }}>
                      {new Date(run.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  )
}

function SectionLabel({ children }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
      {children}
    </p>
  )
}

const labelStyle = {
  fontSize: 12,
  color: '#8b949e',
  display: 'flex',
  flexDirection: 'column',
  gap: 5,
}

const thStyle = {
  padding: '10px 16px',
  textAlign: 'left',
  fontSize: 11,
  fontWeight: 600,
  color: '#8b949e',
  textTransform: 'uppercase',
  letterSpacing: 0.8,
}

const tdStyle = {
  padding: '10px 16px',
  fontSize: 13,
  color: '#e6edf3',
}
