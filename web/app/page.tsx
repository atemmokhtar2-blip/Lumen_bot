export default function HomePage() {
  return (
    <div className="stack">
      <div>
        <h1 className="h1">Lumen Console</h1>
        <p className="muted">
          Phase E — production-grade control plane for agent runs: live SSE, pause /
          resume / cancel, agent trajectory, Monaco code and diff.
        </p>
      </div>
      <div className="row">
        <a className="btn btn-primary" href="/runs">
          Open Runs
        </a>
        <a className="btn" href="/agents">
          Agents
        </a>
        <a className="btn" href="/diff">
          Diff Viewer
        </a>
      </div>
      <div className="card">
        <h2 className="h2">Capabilities</h2>
        <ul className="muted" style={{ lineHeight: 1.7, margin: 0, paddingLeft: 18 }}>
          <li>
            <strong style={{ color: "var(--text)" }}>Runs</strong> — list jobs, live progress,
            open detail with SSE timeline
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Control</strong> — Pause · Resume · Cancel
            (official JobRunner API)
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Agents</strong> — Planner / Worker / Critic
            trajectory reports
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Diff</strong> — Monaco Editor + side-by-side
            DiffEditor on generated files
          </li>
        </ul>
      </div>
    </div>
  );
}
