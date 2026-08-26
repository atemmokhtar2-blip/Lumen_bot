export default function HomePage() {
  return (
    <div>
      <h1>Lumen Console</h1>
      <p>Phase E — monitor runs, agents, stream progress (SSE), cancel jobs.</p>
      <ul>
        <li><a href="/runs" style={{ color: "#8ab4ff" }}>Runs / Jobs</a></li>
        <li><a href="/agents" style={{ color: "#8ab4ff" }}>Agents overview</a></li>
      </ul>
    </div>
  );
}
