"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  cancelJob,
  getJob,
  pauseJob,
  resumeJob,
  type Job,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ProgressBar } from "@/components/ProgressBar";
import { LiveEventFeed } from "@/components/LiveEventFeed";

export default function JobDetailPage() {
  const params = useParams();
  const jobId = String(params?.jobId || "");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await getJob(jobId);
      if (data?.ok === false) setError(JSON.stringify(data));
      else {
        setJob(data as Job);
        setError("");
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, [jobId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  const onStatus = useCallback((payload: any) => {
    if (!payload?.status) return;
    setJob((prev) =>
      prev
        ? {
            ...prev,
            status: payload.status,
            progress: payload.progress ?? prev.progress,
            message: payload.message ?? prev.message,
            error: payload.error ?? prev.error,
          }
        : prev
    );
  }, []);

  const act = async (fn: (id: string) => Promise<any>) => {
    setBusy(true);
    try {
      await fn(jobId);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const status = job?.status || "";
  const done =
    status === "succeeded" || status === "failed" || status === "cancelled";
  const paused = status === "paused";

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Job</h1>
          <code className="mono muted">{jobId}</code>
        </div>
        <div className="row">
          <a className="btn" href="/runs">
            ← Runs
          </a>
          <a className="btn" href={`/diff?job=${encodeURIComponent(jobId)}`}>
            Diff
          </a>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row">
            {job && <StatusBadge status={job.status} />}
            <span className="muted">{job?.kind || ""}</span>
          </div>
          <div className="row">
            {!done && !paused && (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => act(pauseJob)}
              >
                Pause
              </button>
            )}
            {paused && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => act(resumeJob)}
              >
                Resume
              </button>
            )}
            {!done && (
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => act(cancelJob)}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <ProgressBar value={job?.progress} />
        </div>
        <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>
          {job?.message || job?.error || "—"}
        </p>
      </div>

      <LiveEventFeed jobId={jobId} onStatus={onStatus} />
    </div>
  );
}
