"use client";

import { useCallback, useEffect, useState } from "react";
import { cancelJob, listJobs, subscribeJobEvents } from "@/lib/api";

type Job = {
  job_id: string;
  status: string;
  progress?: number;
  message?: string;
  kind?: string;
};

export default function RunsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string>("");
  const [streamLog, setStreamLog] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs(30);
      if (data?.ok) setJobs(data.jobs || []);
      else setError(JSON.stringify(data));
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  const onCancel = async (id: string) => {
    await cancelJob(id);
    await refresh();
  };

  const onStream = (id: string) => {
    setStreamLog(`subscribing ${id}…`);
    const es = subscribeJobEvents(id, (ev) => {
      setStreamLog((prev) => prev + "\n" + (ev as MessageEvent).data);
    });
    setTimeout(() => es.close(), 120000);
  };

  return (
    <div>
      <h1>Runs</h1>
      <p>Live job list · SSE · cancel</p>
      {error && <pre style={{ color: "#f88" }}>{error}</pre>}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th align="left">job</th>
            <th align="left">status</th>
            <th align="left">progress</th>
            <th align="left">actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.job_id} style={{ borderTop: "1px solid #1e2a3a" }}>
              <td>
                <code>{j.job_id}</code>
                <div style={{ opacity: 0.7, fontSize: 12 }}>{j.kind}</div>
              </td>
              <td>{j.status}</td>
              <td>{Math.round((j.progress || 0) * 100)}%</td>
              <td style={{ display: "flex", gap: 8 }}>
                <button type="button" onClick={() => onStream(j.job_id)}>SSE</button>
                <button type="button" onClick={() => onCancel(j.job_id)}>Cancel</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {streamLog && (
        <pre style={{ marginTop: 16, background: "#111820", padding: 12, overflow: "auto" }}>{streamLog}</pre>
      )}
    </div>
  );
}
