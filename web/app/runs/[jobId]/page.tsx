"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getJob, type Job } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ProgressBar } from "@/components/ProgressBar";
import { LiveEventFeed } from "@/components/LiveEventFeed";
import { JobControls } from "@/components/JobControls";

export default function JobDetailPage() {
  const params = useParams();
  const jobId = String(params?.jobId || "");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await getJob(jobId);
      if ((data as any)?.ok === false) setError(JSON.stringify(data));
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
            last_steer: payload.last_steer ?? prev.last_steer,
          }
        : prev
    );
  }, []);

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Job</h1>
          <code className="mono muted">{jobId}</code>
        </div>
        <a className="btn" href="/runs">
          ← Runs
        </a>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row">
            {job && <StatusBadge status={job.status} />}
            <span className="muted">{job?.kind || ""}</span>
          </div>
        </div>
        <ProgressBar value={job?.progress} />
        <p className="muted" style={{ margin: 0 }}>
          {job?.message || job?.error || "—"}
        </p>
        {job && (
          <JobControls job={job} onChanged={refresh} showSteer />
        )}
      </div>

      {jobId && <LiveEventFeed jobId={jobId} onStatus={onStatus} />}
    </div>
  );
}
