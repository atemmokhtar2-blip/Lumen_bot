"use client";

import { useEffect, useMemo, useState } from "react";
import { getJobFile, listJobFiles, type JobFile } from "@/lib/api";
import { MonacoViewer } from "@/components/MonacoViewer";
import { MonacoDiff } from "@/components/MonacoDiff";

export default function DiffPage() {
  const jobId = useMemo(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("job") || "";
  }, []);
  const [files, setFiles] = useState<JobFile[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [baseline, setBaseline] = useState("");
  const [mode, setMode] = useState<"view" | "diff">("view");
  const [error, setError] = useState("");
  const [jobInput, setJobInput] = useState(jobId);

  const loadFiles = (id: string) => {
    if (!id) return;
    listJobFiles(id)
      .then((d) => {
        if (d?.ok) {
          setFiles(d.files || []);
          setError("");
        } else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  };

  useEffect(() => {
    if (jobId) {
      setJobInput(jobId);
      loadFiles(jobId);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobInput || !selected) return;
    getJobFile(jobInput, selected)
      .then((d) => {
        if (d?.ok) {
          setContent(d.content || "");
          setError("");
        } else setError(JSON.stringify(d));
      })
      .catch((e) => setError(String(e?.message || e)));
  }, [jobInput, selected]);

  return (
    <div className="stack">
      <div className="card-header" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="h1">Diff / Files</h1>
          <p className="muted" style={{ margin: 0 }}>
            Monaco Editor · side-by-side DiffEditor · generated project tree
          </p>
        </div>
        <div className="row">
          <button
            type="button"
            className={`btn${mode === "view" ? " btn-primary" : ""}`}
            onClick={() => setMode("view")}
          >
            Viewer
          </button>
          <button
            type="button"
            className={`btn${mode === "diff" ? " btn-primary" : ""}`}
            onClick={() => setMode("diff")}
          >
            Side-by-side
          </button>
        </div>
      </div>

      <div className="card row">
        <label className="muted" style={{ fontSize: 13 }}>
          Job ID
        </label>
        <input
          value={jobInput}
          onChange={(e) => setJobInput(e.target.value.trim())}
          placeholder="job_…"
          style={{
            flex: 1,
            minWidth: 200,
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--text)",
            borderRadius: 8,
            padding: "8px 10px",
            fontFamily: "var(--mono)",
            fontSize: 13,
          }}
        />
        <button type="button" className="btn btn-primary" onClick={() => loadFiles(jobInput)}>
          Load files
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="grid-2">
        <div className="card" style={{ overflow: "auto", maxHeight: 560 }}>
          <h2 className="h2">Files</h2>
          {files.map((f) => (
            <button
              key={f.path}
              type="button"
              className={`file-btn${selected === f.path ? " active" : ""}`}
              onClick={() => setSelected(f.path)}
            >
              {f.path}
              <span className="muted" style={{ float: "right" }}>
                {f.size}
              </span>
            </button>
          ))}
          {!files.length && (
            <p className="muted" style={{ fontSize: 13 }}>
              No files (job may still be running or id missing).
            </p>
          )}
        </div>

        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {mode === "view" ? (
            selected ? (
              <MonacoViewer path={selected} content={content} height="560px" />
            ) : (
              <p className="muted" style={{ padding: 16 }}>
                Select a file
              </p>
            )
          ) : (
            <div>
              <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>
                <textarea
                  value={baseline}
                  onChange={(e) => setBaseline(e.target.value)}
                  placeholder="Optional baseline (left pane). Empty = empty original."
                  rows={3}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                    borderRadius: 8,
                    padding: 8,
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    resize: "vertical",
                  }}
                />
              </div>
              {selected ? (
                <MonacoDiff
                  path={selected}
                  original={baseline}
                  modified={content}
                  height="480px"
                />
              ) : (
                <p className="muted" style={{ padding: 16 }}>
                  Select a file
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
