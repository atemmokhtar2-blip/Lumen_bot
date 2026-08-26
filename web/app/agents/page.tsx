"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listAgentReports, type AgentReport } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { AgentFlowGraph } from "@/components/AgentFlowGraph";

export default function AgentsPage() {
  const [selected, setSelected] = useState<AgentReport | null>(null);

  const q = useQuery({
    queryKey: ["agent-reports"],
    queryFn: async () => {
      const d = await listAgentReports(40);
      if (!d?.ok) throw new Error(JSON.stringify(d));
      return d.reports || [];
    },
    refetchInterval: 5000,
  });

  const reports = q.data || [];

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Agents</h1>
          <p className="muted" style={{ margin: 0 }}>
            Official stack: TanStack Query (live) · React Flow graph · trajectory from multi_agent
            reports
          </p>
        </div>
        <button type="button" className="btn" onClick={() => q.refetch()} disabled={q.isFetching}>
          {q.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {q.isError && <div className="error-box">{String((q.error as Error)?.message || q.error)}</div>}

      <div className="card">
        <h2 className="h2">Pipeline graph</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          Select a report — graph is rendered with <code>@xyflow/react</code> (React Flow).
        </p>
        <AgentFlowGraph
          trajectory={selected?.trajectory}
          status={selected?.status}
          height={340}
        />
      </div>

      <div className="stack">
        {reports.map((r) => {
          const active = selected?.state_id === r.state_id;
          return (
            <button
              key={r.state_id}
              type="button"
              className="card"
              onClick={() => setSelected(r)}
              style={{
                textAlign: "left",
                cursor: "pointer",
                borderColor: active ? "var(--accent)" : undefined,
                background: active ? "var(--accent-soft)" : undefined,
              }}
            >
              <div className="card-header">
                <div className="row">
                  <code className="mono">{r.state_id}</code>
                  <StatusBadge status={r.status} />
                </div>
                <span className="muted" style={{ fontSize: 12 }}>
                  {active ? "Selected" : "Click to graph"}
                </span>
              </div>
              <div className="row muted" style={{ fontSize: 13 }}>
                <span>attempts={r.attempts ?? "—"}</span>
                <span>qa={String(r.qa_passed)}</span>
                <span>findings={r.findings_count ?? 0}</span>
                {typeof r.cost === "number" && <span>cost={r.cost}</span>}
              </div>
              {r.generated_path && (
                <div className="mono muted" style={{ marginTop: 6, fontSize: 12 }}>
                  {r.generated_path}
                </div>
              )}
              {(r.errors || []).length > 0 && (
                <ul style={{ color: "#fca5a5", fontSize: 13, marginTop: 8, marginBottom: 0 }}>
                  {(r.errors || []).slice(0, 3).map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </button>
          );
        })}
        {!reports.length && !q.isLoading && !q.isError && (
          <p className="muted">No agent reports yet. Run MULTI_AGENT_ORCHESTRATOR generation.</p>
        )}
        {q.isLoading && <p className="muted">Loading reports via TanStack Query…</p>}
      </div>
    </div>
  );
}
