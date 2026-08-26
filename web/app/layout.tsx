import type { ReactNode } from "react";

export const metadata = {
  title: "Lumen Console",
  description: "Runs, agents, and generation control",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#0b0f14", color: "#e8eef7" }}>
        <header style={{ padding: "12px 20px", borderBottom: "1px solid #1e2a3a", display: "flex", gap: 16 }}>
          <strong>Lumen</strong>
          <a href="/" style={{ color: "#8ab4ff" }}>Home</a>
          <a href="/runs" style={{ color: "#8ab4ff" }}>Runs</a>
          <a href="/agents" style={{ color: "#8ab4ff" }}>Agents</a>
          <a href="/diff" style={{ color: "#8ab4ff" }}>Diff</a>
        </header>
        <main style={{ padding: 20, maxWidth: 960, margin: "0 auto" }}>{children}</main>
      </body>
    </html>
  );
}
