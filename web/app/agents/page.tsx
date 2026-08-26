"use client";

import { useEffect, useState } from "react";
import { listAgentReports, type AgentReport } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

function trajectoryItems(t: unknown): { role?: string; event?: string; detail?: string }[] {
  if (!t) return [];
  if (Array.isArray(t)) {
    return t.map((x) => {
      if (typeof x === "string") return { event: x };
      if (x && typeof x === "object") {
        const o = x as Record<string, unknown>;
        return {
          role: String(o.role || o.agent || ""),
          event: String(o.event || o.action || o.step || ""),
          detail: String(o.detail || o.message || o.note || JSON.stringify(o)).slice(0, 240),
        };
      }
      return { event: String(x) };
    });
  }
  if (typeof t === "object") {
    return Object.entries(t as Record<string, unknown>).map(([k, v]) => ({
      role: k,
      detail: typeof v === "string" ? v : JSON.stringify(v).slice(0, 240),
    }));
  }
  return [{ detail: String(t) }];
}

export default function AgentsPage() {
  const [reports, setReports] = useState<AgentReport[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string>("");

  useEffect(() => {
    listAgentReports(40)
      .then((d) => {
        if (d?.ok) setReports(d.reports || []);
        else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  }, []);

  return (
    <div className="stack">
      <div>
        <h1 className="h1">Agents</h1>
        <p className="muted" style={{ margin: 0 }}>
          Planner · Worker · Critic · Repair — orchestration trajectory window
        </p>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="stack">
        {reports.map((r) => {
          const items = trajectoryItems(r.trajectory);
          const expanded = open === r.state_id;
          return (
            <div key={r.state_id} className="card">
              <div className="card-header">
                <div className="row">
                  <code className="mono">{r.state_id}</code>
                  <StatusBadge status={r.status} />
                </div>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setOpen(expanded ? "" : r.state_id)}
                >
                  {expanded ? "Hide trajectory" : "Show trajectory"}
                </button>
              </div>
              <div className="row muted" style={{ fontSize: 13 }}>
                <span>attempts={r.attempts ?? "—"}</span>
                <span>qa={String(r.qa_passed)}</span>
                <span>findings={r.findings_count ?? 0}</span>
                {typeof r.cost === "number" && <span>cost={r.cost}</span>}
                {typeof r.latency_ms === "number" && <span>{r.latency_ms}ms</span>}
              </div>
              {r.generated_path && (
                <div className="mono muted" style={{ marginTop: 6, fontSize: 12 }}>
                  {r.generated_path}
                </div>
              )}
              {expanded && (
                <div className="timeline" style={{ marginTop: 14 }}>
                  {items.map((it, i) => (
                    <div key={i} className="timeline-item">
                      <div className="timeline-meta">
                        {[it.role, it.event].filter(Boolean).join(" · ") || "step"}
                      </div>
                      <div className="timeline-body">{it.detail || "—"}</div>
                    </div>
                  ))}
                  {!items.length && (
                    <pre
                      style={{
                        background: "#0a1018",
                        padding: 10,
                        borderRadius: 8,
                        overflow: "auto",
                        maxHeight: 200,
                        fontSize: 12,
                      }}
                    >
                      {JSON.stringify(r.trajectory, null, 2) || "No trajectory"}
                    </pre>
                  )}
                </div>
              )}
              {(r.errors || []).length > 0 && (
                <ul style={{ color: "#fca5a5", fontSize: 13, marginTop: 10 }}>
                  {(r.errors || []).slice(0, 6).map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
        {!reports.length && !error && (
          <p className="muted">No agent reports yet. Run a multi-agent generation first.</p>
        )}
      </div>
    </div>
  );
}
