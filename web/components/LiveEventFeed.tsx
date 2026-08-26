"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeJobEvents } from "@/lib/api";

type FeedItem = {
  id: number;
  ts: number;
  status?: string;
  message?: string;
  progress?: number;
  raw: string;
};

export function LiveEventFeed({
  jobId,
  onStatus,
}: {
  jobId: string;
  onStatus?: (payload: any) => void;
}) {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [live, setLive] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    if (!jobId) return;
    setItems([]);
    setLive(true);
    const es = subscribeJobEvents(
      jobId,
      (ev) => {
        const data = (ev as MessageEvent).data || "";
        let parsed: any = {};
        try {
          parsed = JSON.parse(data);
        } catch {
          parsed = { message: data };
        }
        onStatus?.(parsed);
        seq.current += 1;
        setItems((prev) =>
          [
            {
              id: seq.current,
              ts: parsed.ts || Date.now() / 1000,
              status: parsed.status,
              message: parsed.message || parsed.error || "",
              progress: parsed.progress,
              raw: data,
            },
            ...prev,
          ].slice(0, 80)
        );
        if ((ev as MessageEvent).type === "done") setLive(false);
      },
      () => setLive(false)
    );
    return () => {
      es.close();
      setLive(false);
    };
  }, [jobId, onStatus]);

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="h2" style={{ margin: 0 }}>
          Live stream
        </h2>
        {live && (
          <span className="row muted" style={{ fontSize: 12 }}>
            <span className="live-dot" /> SSE connected
          </span>
        )}
      </div>
      <div className="timeline">
        {items.map((it) => (
          <div key={it.id} className="timeline-item">
            <div className="timeline-meta">
              {new Date((it.ts || 0) * 1000).toLocaleTimeString()} · {it.status || "event"}
              {typeof it.progress === "number"
                ? ` · ${Math.round(it.progress * 100)}%`
                : ""}
            </div>
            <div className="timeline-body">{it.message || it.raw}</div>
          </div>
        ))}
        {!items.length && <p className="muted">Waiting for events…</p>}
      </div>
    </div>
  );
}
