export default function AgentsPage() {
  return (
    <div>
      <h1>Agents</h1>
      <p>
        Orchestrator roles: Planner · Worker · Critic · Repair. Live trajectory lands in run reports
        under the API job result when generation finishes.
      </p>
      <ul>
        <li>Planner — execution plan</li>
        <li>Worker / Cline — code tools</li>
        <li>Critic — findings + code intelligence</li>
        <li>Repair — deterministic + LLM repair</li>
      </ul>
      <p style={{ opacity: 0.75 }}>Diff view: use job result.generated_path artifacts in Runs when available.</p>
    </div>
  );
}
