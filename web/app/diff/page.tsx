"use client";

import { useEffect, useMemo, useState } from "react";
import { getJobFile, listJobFiles } from "@/lib/api";

export default function DiffPage() {
  const jobId = useMemo(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("job") || "";
  }, []);
  const [files, setFiles] = useState<{ path: string; size: number }[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId) return;
    listJobFiles(jobId)
      .then((d) => {
        if (d?.ok) setFiles(d.files || []);
        else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !selected) return;
    getJobFile(jobId, selected)
      .then((d) => {
        if (d?.ok) setContent(d.content || "");
        else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  }, [jobId, selected]);

  return (
    <div>
      <h1>Diff / Files</h1>
      {!jobId && <p>Pass <code>?job=job_…</code></p>}
      {error && <pre style={{ color: "#f88" }}>{error}</pre>}
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 12, minHeight: 420 }}>
        <div style={{ border: "1px solid #1e2a3a", borderRadius: 8, padding: 8, overflow: "auto" }}>
          {files.map((f) => (
            <button
              key={f.path}
              type="button"
              onClick={() => setSelected(f.path)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                background: selected === f.path ? "#1a2740" : "transparent",
                color: "#e8eef7",
                border: "none",
                padding: "6px 8px",
                cursor: "pointer",
                fontFamily: "monospace",
                fontSize: 12,
              }}
            >
              {f.path}
            </button>
          ))}
          {!files.length && <p style={{ opacity: 0.6, fontSize: 13 }}>No files (job may still be running).</p>}
        </div>
        <pre style={{ border: "1px solid #1e2a3a", borderRadius: 8, padding: 12, overflow: "auto", margin: 0 }}>
          {content || (selected ? "Loading…" : "Select a file")}
        </pre>
      </div>
    </div>
  );
}
