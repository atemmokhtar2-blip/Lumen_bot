"use client";

import { useQuery } from "@tanstack/react-query";
import { listAgentReports, listJobs } from "@/lib/api";

export default function HomePage() {
  const jobsQ = useQuery({
    queryKey: ["jobs-home"],
    queryFn: async () => {
      const d = await listJobs(30);
      return d?.ok ? d.jobs || [] : [];
    },
    refetchInterval: 4000,
  });
  const agentsQ = useQuery({
    queryKey: ["agents-home"],
    queryFn: async () => {
      const d = await listAgentReports(20);
      return d?.ok ? d.reports || [];
    },
    refetchInterval: 6000,
  });

  const jobs = jobsQ.data || [];
  const agents = agentsQ.data || [];
  const running = jobs.filter((j) => j.status === "running").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="stack">
      <div>
        <h1 className="h1">Lumen Console</h1>
        <p className="muted">
          Phase E stack: TanStack Query, React Flow, Monaco, SSE, JobRunner controls.
        </p>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Jobs</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{jobs.length}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Running</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{running}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Failed</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{failed}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Agent reports</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{agents.length}</div>
        </div>
      </div>

      <div className="row">
        <a className="btn btn-primary" href="/runs">Runs</a>
        <a className="btn" href="/agents">Agents + Graph</a>
        <a className="btn" href="/diff">Monaco Diff</a>
      </div>

      <div className="card">
        <h2 className="h2">Official tools in this console</h2>
        <ul className="muted" style={{ lineHeight: 1.75, margin: 0, paddingLeft: 18 }}>
          <li><code>@tanstack/react-query</code> — server-state, refetch, mutations</li>
          <li><code>@xyflow/react</code> — agent pipeline graph (React Flow)</li>
          <li><code>@monaco-editor/react</code> — code viewer + DiffEditor</li>
          <li><code>EventSource</code> + <code>JobRunner</code> — SSE, pause/resume/cancel</li>
        </ul>
      </div>
    </div>
  );
}
