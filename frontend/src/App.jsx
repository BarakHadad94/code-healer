import { useState, useRef, useEffect } from 'react'
import LogFeed from './LogFeed'
import DiffView from './DiffView'

function formatIsraelTime(isoStr) {
  const s = String(isoStr)
  // Backend naive UTC datetime lacks a Z suffix — add it so JS parses as UTC
  const utc = /Z|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z'
  return new Date(utc).toLocaleString('en-GB', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

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
  // Stored per-browser only (sessionStorage) — never shipped in the JS bundle.
  // Lets the deployer unlock triggering on a public deployment without exposing
  // the key to every visitor. Unused/blank when TRIGGER_API_KEY isn't set (local dev).
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem('ch_api_key') || '')
  const wsRef = useRef(null)
  const reasoningRef = useRef(null)
  const historyPollRef = useRef(null)
  const runStatusRef = useRef('idle')

  // Keep runStatusRef in sync so interval callbacks don't see stale status
  useEffect(() => { runStatusRef.current = status }, [status])

  useEffect(() => {
    setRunsLoading(true)
    fetchHistory()
    fetchDemoWorkspaces()
    return () => { if (historyPollRef.current) clearInterval(historyPollRef.current) }
  }, [])

  function fetchDemoWorkspaces(retries = 25, delay = 1000) {
    fetch('/demo/workspaces')
      .then(r => r.json())
      .then(setDemoWorkspaces)
      .catch(() => {
        if (retries > 0) setTimeout(() => fetchDemoWorkspaces(retries - 1, delay), delay)
      })
  }

  function fetchHistory() {
    fetch('/runs')
      .then(r => { if (!r.ok) throw new Error(); return r.json() })
      .then(data => { setRuns(data); setRunsLoading(false); setRunsError(false) })
      .catch(() => { setRunsError(true); setRunsLoading(false) })
  }

  function startHistoryPoll(runId) {
    if (historyPollRef.current) clearInterval(historyPollRef.current)
    let ticks = 0
    historyPollRef.current = setInterval(() => {
      ticks++
      fetch('/runs')
        .then(r => r.json())
        .then(data => {
          setRuns(data)
          setRunsLoading(false)
          setRunsError(false)
          const run = data.find(r => r.id === runId)
          const done = run && run.status !== 'running'
          const timedOut = ticks > 90  // 3-minute safety net
          if (done || timedOut) {
            clearInterval(historyPollRef.current)
            historyPollRef.current = null
            // If the WS dropped mid-run, update the live-view status from DB truth
            if (done) {
              setStatus(prev => {
                if (prev !== 'running') return prev  // WS already delivered the final status
                return run.status === 'success' ? 'success' : run.status === 'skipped' ? 'skipped' : 'failed'
              })
            } else {
              // Timed out without a DB update — mark failed so the button re-enables
              setStatus(prev => prev === 'running' ? 'failed' : prev)
            }
          }
        })
        .catch(() => {})
    }, 2000)
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
    setSelectedRun(null)
    setHistoricalDiff('')
    // Scroll to reasoning section once — internal box scrolls on its own after that
    setTimeout(() => reasoningRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)

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
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
        },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        if (res.status === 401) throw new Error('Invalid or missing API key — enter it above to unlock triggering')
        throw new Error(err.detail || `Server error ${res.status}`)
      }
      const data = await res.json()
      runId = data.run_id
      startHistoryPoll(runId)
    } catch (e) {
      setStatus('failed')
      setLogs([{ type: 'error', message: `Could not start run: ${e.message}` }])
      return
    }

    // In dev mode, connect directly to the backend to avoid the Vite proxy.
    // Proxied WebSocket connections can drop mid-run when the proxy times out
    // during long Anthropic API calls. In production the same-host path is used.
    const wsBase = import.meta.env.DEV
      ? 'ws://localhost:8000'
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    const ws = new WebSocket(`${wsBase}/ws/logs/${runId}`)
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
      } else if (msg.type === 'skipped') {
        setStatus('skipped')
        setLogs(prev => [...prev, msg])
      } else if (msg.type === 'error') {
        setStatus('failed')
        setLogs(prev => [...prev, msg])
      } else if (msg.type === 'history-ready') {
        fetchHistory()
      } else if (msg.type === 'keepalive') {
        // server heartbeat — ignore
      } else {
        setLogs(prev => [...prev, msg])
      }
    }

    ws.onerror = () => {
      // Don't set 'failed' yet — the run may still complete in the background.
      // startHistoryPoll will update status when the DB has the final result.
      setLogs(prev => [...prev, { type: 'log', message: '[Live stream lost — tracking completion in background…]' }])
    }

    ws.onclose = (event) => {
      if (event.code === 1000) return  // normal close — history-ready already refreshed history
      // Abnormal close: stream dropped (proxy timeout, network blip, etc.)
      // The background task continues running; the poll will deliver the final status.
      fetchHistory()
      setLogs(prev => [
        ...prev,
        { type: 'log', message: '[Live stream dropped — result will appear in Run History when complete]' },
      ])
    }
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px' }}>

      {/* Header */}
      <div style={{
        paddingBottom: 20, marginBottom: 24,
        borderBottom: '1px solid #21262d',
      }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.5px' }}>
          ⚕ code-healer
        </h1>
      </div>

      {/* Trigger form */}
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 8, padding: 20, marginBottom: 24,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', letterSpacing: 1 }}>
            Trigger Healing Run
          </h2>
          <input
            type="password"
            value={apiKey}
            onChange={e => {
              setApiKey(e.target.value)
              sessionStorage.setItem('ch_api_key', e.target.value)
            }}
            placeholder="API key (only needed if deployment requires one)"
            title="Only stored in this browser tab's session — never sent anywhere except /trigger on this site"
            style={{ fontSize: 11, width: 260, padding: '4px 8px' }}
          />
        </div>

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
            File path (workspace-relative)
            <input
              value={form.file_path}
              onChange={e => setForm(f => ({ ...f, file_path: e.target.value }))}
              placeholder="calculator.py"
            />
          </label>
          <label style={labelStyle}>
            Changed files (for sensitive-path detection)
            <input
              value={form.changed_files}
              onChange={e => setForm(f => ({ ...f, changed_files: e.target.value }))}
              placeholder="auth/session.py"
            />
          </label>
        </div>
        <label style={{ ...labelStyle, marginBottom: 16, display: 'block' }}>
          Workspace (absolute path on server)
          <input
            value={form.workspace}
            onChange={e => setForm(f => ({ ...f, workspace: e.target.value }))}
            placeholder="/absolute/path/to/workspace"
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
      <div ref={reasoningRef} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <SectionLabel style={{ marginBottom: 0 }}>
              {selectedRun ? 'Run Detail' : 'Agent Reasoning'}
            </SectionLabel>
            {!selectedRun && status === 'running' && !activationReason && (
              <span style={{ fontSize: 11, color: '#d29922' }}>Pre-check running…</span>
            )}
            {!selectedRun && status === 'running' && activationReason && (
              <span style={{ fontSize: 11, color: '#58a6ff' }}>Agent running…</span>
            )}
            {selectedRun && (
              <button
                onClick={() => { setSelectedRun(null); setHistoricalDiff('') }}
                style={{ background: 'none', border: 'none', color: '#58a6ff', cursor: 'pointer', fontSize: 11, padding: 0, fontWeight: 400 }}
              >
                ✕ back to live
              </button>
            )}
          </div>
          {selectedRun ? <RunDetail run={selectedRun} /> : <LogFeed logs={logs} />}
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <SectionLabel style={{ marginBottom: 0 }}>Code Diff</SectionLabel>
            {selectedRun && (
              <span style={{ fontSize: 11, color: '#8b949e' }}>
                — {selectedRun.file_path} · {formatIsraelTime(selectedRun.created_at)}
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
          {runsLoading && runs.length === 0 ? (
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
                      {formatIsraelTime(run.created_at)}
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

function RunDetail({ run }) {
  const ab = activationBadge(run.activation_reason)
  const sb = statusBadge(run.status)
  return (
    <div style={{
      background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
      padding: '20px 24px', height: 400, overflowY: 'auto',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 13,
    }}>
      <p style={{ fontSize: 11, color: '#6e7681', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }}>Historical Run</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: sb.bg, color: sb.color }}>
          {run.status}
        </span>
        <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: ab.bg, color: ab.color }}>
          {ab.label}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <DetailRow label="File" value={run.file_path} mono />
        <DetailRow label="Repo" value={run.repo} />
        {run.iterations != null && <DetailRow label="Iterations" value={run.iterations} />}
        {run.fix_branch && <DetailRow label="Fix branch" value={run.fix_branch} mono />}
        {run.input_tokens > 0 && (
          <DetailRow
            label="Token usage"
            value={`in: ${run.input_tokens}  out: ${run.output_tokens}  ·  ~$${run.estimated_cost_usd?.toFixed(4)}`}
          />
        )}
        <DetailRow label="Started" value={formatIsraelTime(run.created_at)} />
      </div>
    </div>
  )
}

function DetailRow({ label, value, mono }) {
  return (
    <div>
      <span style={{ color: '#6e7681', fontSize: 11, display: 'inline-block', width: 100 }}>{label}</span>
      <span style={{
        color: '#e6edf3',
        fontFamily: mono ? 'Cascadia Code, Fira Code, Consolas, monospace' : 'inherit',
        fontSize: mono ? 12 : 13,
      }}>
        {value}
      </span>
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
