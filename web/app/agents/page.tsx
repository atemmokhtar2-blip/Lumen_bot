"use client";

import { useEffect, useState } from "react";
import { listAgentReports } from "@/lib/api";

export default function AgentsPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listAgentReports(25)
      .then((d) => {
        if (d?.ok) setReports(d.reports || []);
        else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  }, []);

  return (
    <div>
      <h1>Agents</h1>
      <p>Planner · Worker · Critic · Repair — recent orchestration reports</p>
      {error && <pre style={{ color: "#f88" }}>{error}</pre>}
      <div style={{ display: "grid", gap: 12 }}>
        {reports.map((r) => (
          <div key={r.state_id} style={{ border: "1px solid #1e2a3a", borderRadius: 8, padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <code>{r.state_id}</code>
              <span>{r.status}</span>
            </div>
            <div style={{ opacity: 0.8, fontSize: 13, marginTop: 6 }}>
              attempts={r.attempts} · qa={String(r.qa_passed)} · findings={r.findings_count}
            </div>
            {r.generated_path && (
              <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>{r.generated_path}</div>
            )}
            {r.trajectory && (
              <pre style={{ background: "#111820", padding: 8, marginTop: 8, overflow: "auto", maxHeight: 120 }}>
                {JSON.stringify(r.trajectory, null, 2)}
              </pre>
            )}
            {(r.errors || []).length > 0 && (
              <ul style={{ color: "#f88", fontSize: 13 }}>
                {(r.errors || []).slice(0, 5).map((e: string, i: number) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {!reports.length && !error && <p style={{ opacity: 0.6 }}>No agent reports yet.</p>}
      </div>
    </div>
  );
}
