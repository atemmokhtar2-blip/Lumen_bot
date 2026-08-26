"use client";

import { useState } from "react";
import {
  cancelJob,
  isTerminal,
  pauseJob,
  resumeJob,
  steerJob,
  type Job,
} from "@/lib/api";

type Props = {
  job: Job;
  onChanged?: () => void;
  showSteer?: boolean;
};

/**
 * Phase E intervention controls: Pause · Resume · Cancel · Steer.
 * Thin UI over JobRunner API — no local fake state machines.
 */
export function JobControls({ job, onChanged, showSteer = false }: Props) {
  const [busy, setBusy] = useState(false);
  const [steerText, setSteerText] = useState("");
  const [err, setErr] = useState("");

  const done = isTerminal(job.status);
  const paused = job.status === "paused";

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr("");
    try {
      await fn();
      onChanged?.();
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row">
        {!done && !paused && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => run(() => pauseJob(job.job_id))}
          >
            Pause
          </button>
        )}
        {paused && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => run(() => resumeJob(job.job_id))}
          >
            Resume
          </button>
        )}
        {!done && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => run(() => cancelJob(job.job_id))}
          >
            Cancel
          </button>
        )}
        <a className="btn btn-ghost" href={`/diff?job=${encodeURIComponent(job.job_id)}`}>
          Diff
        </a>
      </div>

      {showSteer && !done && (
        <div className="row" style={{ alignItems: "stretch" }}>
          <input
            value={steerText}
            onChange={(e) => setSteerText(e.target.value)}
            placeholder="Steer: e.g. focus on payment handlers only"
            maxLength={2000}
            disabled={busy}
            style={{
              flex: 1,
              minWidth: 180,
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--text)",
              borderRadius: 8,
              padding: "8px 10px",
              fontSize: 13,
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && steerText.trim()) {
                e.preventDefault();
                const msg = steerText.trim();
                setSteerText("");
                run(() => steerJob(job.job_id, msg));
              }
            }}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !steerText.trim()}
            onClick={() => {
              const msg = steerText.trim();
              if (!msg) return;
              setSteerText("");
              run(() => steerJob(job.job_id, msg));
            }}
          >
            Steer
          </button>
        </div>
      )}

      {showSteer && (job.steer_notes || []).length > 0 && (
        <div className="muted" style={{ fontSize: 12 }}>
          Last steers:{" "}
          {(job.steer_notes || [])
            .slice(-3)
            .map((n) => n.message)
            .join(" · ")}
        </div>
      )}

      {err && <div className="error-box">{err}</div>}
    </div>
  );
}
