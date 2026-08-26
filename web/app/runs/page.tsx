"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  const qc = useQueryClient();

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      const d = await listJobs(50);
      if (!d?.ok) throw new Error(JSON.stringify(d));
      return (d.jobs || []) as Job[];
    },
    refetchInterval: 3000,
  });

  const mutate = useMutation({
    mutationFn: async ({
      id,
      action,
    }: {
      id: string;
      action: "pause" | "resume" | "cancel";
    }) => {
      if (action === "pause") return pauseJob(id);
      if (action === "resume") return resumeJob(id);
      return cancelJob(id);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const jobs = jobsQuery.data || [];
  const terminal = (s: string) =>
    s === "succeeded" || s === "failed" || s === "cancelled";

  const counts = {
    running: jobs.filter((j) => j.status === "running").length,
    paused: jobs.filter((j) => j.status === "paused").length,
    queued: jobs.filter((j) => j.status === "queued").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Runs</h1>
          <p className="muted" style={{ margin: 0 }}>
            TanStack Query live list · JobRunner pause / resume / cancel · SSE detail
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => jobsQuery.refetch()}
          disabled={jobsQuery.isFetching}
        >
          {jobsQuery.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Running</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{counts.running}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Queued</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{counts.queued}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Paused</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{counts.paused}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="muted" style={{ fontSize: 12 }}>Failed</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{counts.failed}</div>
        </div>
      </div>

      {jobsQuery.isError && (
        <div className="error-box">
          {String((jobsQuery.error as Error)?.message || jobsQuery.error)}
        </div>
      )}

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
              const busy = mutate.isPending && mutate.variables?.id === j.job_id;
              return (
                <tr key={j.job_id}>
                  <td>
                    <a href={`/runs/${encodeURIComponent(j.job_id)}`} className="mono">
                      {j.job_id}
                    </a>
                    <div className="muted" style={{ fontSize: 12 }}>{j.kind || "—"}</div>
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
                      <a className="btn btn-ghost" href={`/diff?job=${encodeURIComponent(j.job_id)}`}>
                        Diff
                      </a>
                      {!done && !paused && (
                        <button
                          type="button"
                          className="btn"
                          disabled={busy}
                          onClick={() => mutate.mutate({ id: j.job_id, action: "pause" })}
                        >
                          Pause
                        </button>
                      )}
                      {paused && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy}
                          onClick={() => mutate.mutate({ id: j.job_id, action: "resume" })}
                        >
                          Resume
                        </button>
                      )}
                      {!done && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          disabled={busy}
                          onClick={() => mutate.mutate({ id: j.job_id, action: "cancel" })}
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
        {!jobs.length && !jobsQuery.isError && (
          <p className="muted" style={{ padding: 16 }}>
            {jobsQuery.isLoading ? "Loading jobs…" : "No jobs yet."}
          </p>
        )}
      </div>
    </div>
  );
}
