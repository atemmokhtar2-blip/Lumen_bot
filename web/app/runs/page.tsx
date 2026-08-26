"use client";

import { useCallback, useEffect, useState } from "react";
import {
  cancelJob,
  listJobs,
  pauseJob,
  resumeJob,
  type Job,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ProgressBar } from "@/components/ProgressBar";

export default function RunsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs(50);
      if (data?.ok) {
        setJobs(data.jobs || []);
        setError("");
      } else setError(JSON.stringify(data));
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const act = async (id: string, fn: (id: string) => Promise<any>) => {
    setBusy(id);
    try {
      await fn(id);
      await refresh();
    } finally {
      setBusy("");
    }
  };

  const terminal = (s: string) =>
    s === "succeeded" || s === "failed" || s === "cancelled";

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Runs</h1>
          <p className="muted" style={{ margin: 0 }}>
            Jobs · live status · pause / resume / cancel · open detail
          </p>
        </div>
        <button type="button" className="btn" onClick={() => refresh()}>
          Refresh
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Message</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => {
              const done = terminal(j.status);
              const paused = j.status === "paused";
              return (
                <tr key={j.job_id}>
                  <td>
                    <a href={`/runs/${encodeURIComponent(j.job_id)}`} className="mono">
                      {j.job_id}
                    </a>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {j.kind || "—"}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={j.status} />
                  </td>
                  <td>
                    <ProgressBar value={j.progress} />
                  </td>
                  <td className="muted" style={{ maxWidth: 220 }}>
                    {(j.message || j.error || "—").slice(0, 80)}
                  </td>
                  <td>
                    <div className="row">
                      <a className="btn btn-ghost" href={`/runs/${encodeURIComponent(j.job_id)}`}>
                        Open
                      </a>
                      <a
                        className="btn btn-ghost"
                        href={`/diff?job=${encodeURIComponent(j.job_id)}`}
                      >
                        Diff
                      </a>
                      {!done && !paused && (
                        <button
                          type="button"
                          className="btn"
                          disabled={busy === j.job_id}
                          onClick={() => act(j.job_id, pauseJob)}
                        >
                          Pause
                        </button>
                      )}
                      {paused && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy === j.job_id}
                          onClick={() => act(j.job_id, resumeJob)}
                        >
                          Resume
                        </button>
                      )}
                      {!done && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          disabled={busy === j.job_id}
                          onClick={() => act(j.job_id, cancelJob)}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!jobs.length && !error && (
          <p className="muted" style={{ padding: 16 }}>
            No jobs yet.
          </p>
        )}
      </div>
    </div>
  );
}
