export function ProgressBar({ value }: { value?: number }) {
  const pct = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return (
    <div className="row" style={{ gap: 10, minWidth: 120 }}>
      <div className="progress" style={{ flex: 1 }}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="muted" style={{ fontSize: 12, minWidth: 36 }}>
        {pct}%
      </span>
    </div>
  );
}
