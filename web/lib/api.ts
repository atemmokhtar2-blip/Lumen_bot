/** Lumen API client — jobs, SSE, pause/resume/cancel, agent reports, files/diff. */

export type JobStatus =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled"
  | string;

export type Job = {
  job_id: string;
  tenant_id?: string;
  kind?: string;
  status: JobStatus;
  progress?: number;
  message?: string;
  error?: string;
  created_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  result?: Record<string, unknown>;
};

export type AgentReport = {
  state_id: string;
  status: string;
  attempts?: number;
  qa_passed?: boolean;
  findings_count?: number;
  generated_path?: string;
  trajectory?: unknown;
  errors?: string[];
  cost?: number;
  latency_ms?: number;
};

export type JobFile = { path: string; size: number };

export function apiBase(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_LUMEN_API_URL) {
    return process.env.NEXT_PUBLIC_LUMEN_API_URL.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8080";
}

export function apiKey(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_LUMEN_API_KEY) {
    return process.env.NEXT_PUBLIC_LUMEN_API_KEY;
  }
  return "";
}

function headers(): HeadersInit {
  const k = apiKey();
  return {
    "X-Api-Key": k,
    Authorization: k ? `Bearer ${k}` : "",
    Accept: "application/json",
  };
}

async function jsonFetch(url: string, init?: RequestInit): Promise<any> {
  const res = await fetch(url, {
    ...init,
    headers: { ...headers(), ...(init?.headers || {}) },
    cache: "no-store",
  });
  return res.json();
}

export async function listJobs(limit = 40): Promise<{ ok: boolean; jobs: Job[] }> {
  return jsonFetch(`${apiBase()}/v1/jobs?limit=${limit}`);
}

export async function getJob(jobId: string): Promise<{ ok: boolean } & Job> {
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelJob(jobId: string): Promise<any> {
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}

export async function pauseJob(jobId: string): Promise<any> {
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/pause`, {
    method: "POST",
  });
}

export async function resumeJob(jobId: string): Promise<any> {
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/resume`, {
    method: "POST",
  });
}

export async function listAgentReports(
  limit = 30
): Promise<{ ok: boolean; reports: AgentReport[] }> {
  return jsonFetch(`${apiBase()}/v1/runs/agent-reports?limit=${limit}`);
}

export async function listJobFiles(jobId: string): Promise<{ ok: boolean; files: JobFile[] }> {
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/files`);
}

export async function getJobFile(
  jobId: string,
  path: string
): Promise<{ ok: boolean; path: string; content: string; truncated?: boolean }> {
  const q = new URLSearchParams({ path });
  return jsonFetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/file?${q}`);
}

/** Browser SSE — api_key via query (EventSource cannot set custom headers). */
export function subscribeJobEvents(
  jobId: string,
  onEvent: (ev: MessageEvent) => void,
  onError?: (err: Event) => void,
  timeoutSec = 600
): EventSource {
  const key = encodeURIComponent(apiKey());
  const url = `${apiBase()}/v1/jobs/${encodeURIComponent(
    jobId
  )}/events?api_key=${key}&timeout=${timeoutSec}`;
  const es = new EventSource(url);
  es.addEventListener("job", onEvent as EventListener);
  es.addEventListener("done", onEvent as EventListener);
  es.addEventListener("error", onEvent as EventListener);
  es.onerror = onError || null;
  return es;
}
