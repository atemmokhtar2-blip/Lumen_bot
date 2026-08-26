"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

type Step = {
  role?: string;
  event?: string;
  step?: string;
  detail?: string;
  ok?: boolean | null;
  status?: string;
};

const ROLE_ORDER = ["architect", "planner", "builder", "worker", "critic", "repair", "deliver", "orchestrator"];

function normalizeRole(raw: string): string {
  const r = (raw || "").toLowerCase();
  if (r.includes("architect") || r.includes("plan")) return "architect";
  if (r.includes("build") || r.includes("worker")) return "builder";
  if (r.includes("critic") || r.includes("review")) return "critic";
  if (r.includes("repair") || r.includes("fix")) return "repair";
  if (r.includes("deliver")) return "deliver";
  if (r.includes("orchestr")) return "orchestrator";
  return r || "step";
}

function extractSteps(trajectory: unknown): Step[] {
  if (!trajectory) return [];
  if (Array.isArray(trajectory)) {
    return trajectory.map((x) => {
      if (typeof x === "string") return { step: x, event: x };
      if (x && typeof x === "object") {
        const o = x as Record<string, unknown>;
        return {
          role: String(o.role || o.agent || ""),
          event: String(o.event || o.action || ""),
          step: String(o.step || o.event || o.action || ""),
          detail: String(o.detail || o.message || "").slice(0, 120),
          ok: typeof o.ok === "boolean" ? o.ok : null,
          status: String(o.status || ""),
        };
      }
      return { step: String(x) };
    });
  }
  if (typeof trajectory === "object") {
    const t = trajectory as Record<string, unknown>;
    if (Array.isArray(t.steps)) return extractSteps(t.steps);
    if (Array.isArray(t.events)) return extractSteps(t.events);
  }
  return [];
}

/**
 * Official React Flow (@xyflow/react) graph of multi-agent roles / trajectory.
 * Not a fake canvas — uses the same library as many production agent UIs.
 */
export function AgentFlowGraph({
  trajectory,
  status,
  height = 360,
}: {
  trajectory: unknown;
  status?: string;
  height?: number;
}) {
  const steps = useMemo(() => extractSteps(trajectory), [trajectory]);

  const { nodes, edges } = useMemo(() => {
    const rolesSeen: string[] = [];
    for (const s of steps) {
      const role = normalizeRole(s.role || s.step || s.event || "");
      if (role && !rolesSeen.includes(role)) rolesSeen.push(role);
    }
    // Default pipeline if trajectory empty but we have a status
    if (!rolesSeen.length) {
      rolesSeen.push("architect", "builder", "critic");
    }
    // Sort lightly by known pipeline order
    rolesSeen.sort((a, b) => {
      const ia = ROLE_ORDER.indexOf(a);
      const ib = ROLE_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    const ns: Node[] = rolesSeen.map((role, i) => {
      const related = steps.filter(
        (s) => normalizeRole(s.role || s.step || s.event || "") === role
      );
      const last = related[related.length - 1];
      const failed = related.some((s) => s.ok === false);
      const ok = related.some((s) => s.ok === true) && !failed;
      let bg = "#1a2740";
      if (failed) bg = "#3f1d1d";
      else if (ok) bg = "#14301f";
      else if (status === "running") bg = "#1a2740";

      return {
        id: role,
        position: { x: 40 + i * 200, y: 80 + (i % 2) * 40 },
        data: {
          label: `${role}${last?.event || last?.step ? `\n${(last.event || last.step || "").slice(0, 28)}` : ""}`,
        },
        style: {
          background: bg,
          color: "#e8eef7",
          border: `1px solid ${failed ? "#ef4444" : ok ? "#22c55e" : "#2a3d57"}`,
          borderRadius: 10,
          padding: 12,
          fontSize: 12,
          minWidth: 120,
          whiteSpace: "pre-wrap" as const,
        },
      };
    });

    const es: Edge[] = [];
    for (let i = 0; i < rolesSeen.length - 1; i++) {
      es.push({
        id: `e-${rolesSeen[i]}-${rolesSeen[i + 1]}`,
        source: rolesSeen[i],
        target: rolesSeen[i + 1],
        animated: status === "running" || status === "queued",
        markerEnd: { type: MarkerType.ArrowClosed, color: "#8ab4ff" },
        style: { stroke: "#3b82f6" },
      });
    }
    return { nodes: ns, edges: es };
  }, [steps, status]);

  return (
    <div style={{ height, width: "100%", borderRadius: 10, overflow: "hidden" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
      >
        <Background color="#1c2a3d" gap={18} />
        <Controls />
        <MiniMap
          style={{ background: "#0d1420" }}
          nodeColor={() => "#3b82f6"}
        />
      </ReactFlow>
    </div>
  );
}
