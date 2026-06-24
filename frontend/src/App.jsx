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
  const [selectedRun, setSelectedRun] = useState(null)
  const [historicalDiff, setHistoricalDiff] = useState('')
  const [activationReason, setActivationReason] = useState(null)
  const [demoWorkspaces, setDemoWorkspaces] = useState(null)
  const [runsLoading, setRunsLoading] = useState(true)
  const [runsError, setRunsError] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    fetchHistory()
    fetch('/demo/workspaces').then(r => r.json()).then(setDemoWorkspaces).catch(() => {})
  }, [])

  function fetchHistory() {
    setRunsLoading(true)
    setRunsError(false)
    fetch('/runs')
      .then(r => { if (!r.ok) throw new Error(); return r.json() })
      .then(data => { setRuns(data); setRunsLoading(false) })
      .catch(() => { setRunsError(true); setRunsLoading(false) })
  }

  async function handleRunClick(run) {
    if (selectedRun?.id === run.id) {
      setSelectedRun(null)
      setHistoricalDiff('')
      return
    }
    setSelectedRun(run)
    try {
      const res = await fetch(`/runs/${run.id}/diff`)
      const data = await res.json()
      setHistoricalDiff(data.diff || '')
    } catch {
      setHistoricalDiff('')
    }
  }

  async function startHealing() {
    if (wsRef.current) wsRef.current.close()
    setLogs([])
    setDiff('')
    setStatus('running')
    setActivationReason(null)

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
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${res.status}`)
      }
      const data = await res.json()
      runId = data.run_id
    } catch (e) {
      setStatus('failed')
      setLogs([{ type: 'error', message: `Could not start run: ${e.message}` }])
      return
    }

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${wsProto}//${window.location.host}/ws/logs/${runId}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'activation') {
        setActivationReason(msg.message)
      } else if (msg.type === 'diff') {
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

    ws.onclose = (event) => {
      // A clean close (1000) means the server already sent a terminal
      // message (done/error/skipped) and the UI is already up to date.
      if (event.code === 1000) return
      setStatus(prev => (prev === 'running' ? 'failed' : prev))
      setLogs(prev => [
        ...prev,
        { type: 'error', message: 'Connection closed before the run finished streaming — refresh to see the final result in Run History.' },
      ])
      fetchHistory()
    }
  }

  const badge = STATUS_BADGE[status]

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px' }}>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        paddingBottom: 20, marginBottom: 24,
        borderBottom: '1px solid #21262d',
      }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.5px' }}>
          ⚕ code-healer
        </h1>
        <span style={{
          padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
          background: badge.bg, color: badge.color,
        }}>
          {badge.label}
        </span>
        {activationReason && (() => {
          const ab = activationBadge(activationReason)
          return (
            <span style={{
              padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
              background: ab.bg, color: ab.color,
            }}>
              {ab.label}
            </span>
          )
        })()}
      </div>

      {/* Trigger form */}
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 8, padding: 20, marginBottom: 24,
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: '#8b949e', marginBottom: 14, textTransform: 'uppercase', letterSpacing: 1 }}>
          Trigger Healing Run
        </h2>

        {demoWorkspaces && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {[
              {
                label: '⚡ Self-heal',
                title: 'Scenario A — broken calculator, agent fixes it',
                fields: { repo: 'demo/repo', file_path: 'calculator.py', workspace: demoWorkspaces.broken, changed_files: '', error_log: '' },
              },
              {
                label: '🔍 Deep review',
                title: 'Scenario B — tests pass, sensitive auth path touched',
                fields: { repo: 'demo/repo', file_path: 'auth/session.py', workspace: demoWorkspaces.clean, changed_files: 'auth/session.py', error_log: '' },
              },
              {
                label: '✓ Skip',
                title: 'Scenario C — tests pass, no sensitive paths',
                fields: { repo: 'demo/repo', file_path: 'utils.py', workspace: demoWorkspaces.clean, changed_files: '', error_log: '' },
              },
            ].map(({ label, title, fields }) => (
              <button
                key={label}
                title={title}
                onClick={() => setForm(fields)}
                style={{ background: '#21262d', color: '#8b949e', border: '1px solid #30363d', fontSize: 12, padding: '4px 12px' }}
              >
                {label}
              </button>
            ))}
          </div>
        )}

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
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <SectionLabel style={{ marginBottom: 0 }}>Agent Reasoning</SectionLabel>
            {status === 'running' && !activationReason && (
              <span style={{ fontSize: 11, color: '#d29922' }}>Pre-check running…</span>
            )}
            {status === 'running' && activationReason && (
              <span style={{ fontSize: 11, color: '#58a6ff' }}>Agent running…</span>
            )}
          </div>
          <LogFeed logs={logs} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <SectionLabel style={{ marginBottom: 0 }}>Code Diff</SectionLabel>
            {selectedRun && (
              <span style={{ fontSize: 11, color: '#8b949e' }}>
                — {selectedRun.file_path} · {new Date(selectedRun.created_at).toLocaleString()}
                <button
                  onClick={() => { setSelectedRun(null); setHistoricalDiff('') }}
                  style={{
                    marginLeft: 8, background: 'none', border: 'none',
                    color: '#58a6ff', cursor: 'pointer', fontSize: 11, padding: 0,
                  }}
                >
                  ✕ live
                </button>
              </span>
            )}
          </div>
          <DiffView diff={selectedRun ? historicalDiff : diff} />
        </div>
      </div>

      {/* Run history */}
      <div>
        <SectionLabel>Run History</SectionLabel>
        <div style={{
          background: '#161b22', border: '1px solid #30363d',
          borderRadius: 8, overflow: 'hidden',
        }}>
          {runsLoading ? (
            <p style={{ padding: '20px 16px', color: '#484f58' }}>Loading…</p>
          ) : runsError ? (
            <p style={{ padding: '20px 16px', color: '#f85149' }}>
              Could not load run history — is the backend running?
            </p>
          ) : runs.length === 0 ? (
            <p style={{ padding: '20px 16px', color: '#484f58' }}>
              No runs yet — pick a preset above and click Start Healing.
            </p>
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
                  <tr
                    key={run.id}
                    onClick={() => handleRunClick(run)}
                    style={{
                      borderBottom: '1px solid #21262d',
                      cursor: 'pointer',
                      background: selectedRun?.id === run.id ? '#1c2128' : 'transparent',
                    }}
                    onMouseEnter={e => { if (selectedRun?.id !== run.id) e.currentTarget.style.background = '#161b22' }}
                    onMouseLeave={e => { e.currentTarget.style.background = selectedRun?.id === run.id ? '#1c2128' : 'transparent' }}
                  >
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

function SectionLabel({ children, style }) {
  return (
    <p style={{ fontSize: 12, fontWeight: 600, color: '#6e7681', textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, ...style }}>
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
