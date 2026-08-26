/**
 * Lumen Phase E API client.
 * Official surface only: jobs control plane, SSE, agent reports, file/diff.
 */

export type JobStatus =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled"
  | string;

export type SteerNote = {
  ts: number;
  message: string;
};

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
  steer_notes?: SteerNote[];
  last_steer?: SteerNote | null;
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
  const raw =
    typeof process !== "undefined" ? process.env.NEXT_PUBLIC_LUMEN_API_URL : undefined;
  return (raw || "http://127.0.0.1:8080").replace(/\/$/, "");
}

export function apiKey(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_LUMEN_API_KEY) {
    return process.env.NEXT_PUBLIC_LUMEN_API_KEY;
  }
  return "";
}

function authHeaders(json = false): HeadersInit {
  const k = apiKey();
  const h: Record<string, string> = {
    Accept: "application/json",
    "X-Api-Key": k,
  };
  if (k) h.Authorization = `Bearer ${k}`;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function request<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      ...authHeaders(init?.method === "POST" && !!init.body),
      ...(init?.headers || {}),
    },
  });
  return res.json() as Promise<T>;
}

export function isTerminal(status: string): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

export async function listJobs(limit = 40) {
  return request<{ ok: boolean; jobs: Job[] }>(`/v1/jobs?limit=${limit}`);
}

export async function getJob(jobId: string) {
  return request<{ ok: boolean } & Job>(`/v1/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelJob(jobId: string) {
  return request(`/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
}

export async function pauseJob(jobId: string) {
  return request(`/v1/jobs/${encodeURIComponent(jobId)}/pause`, { method: "POST" });
}

export async function resumeJob(jobId: string) {
  return request(`/v1/jobs/${encodeURIComponent(jobId)}/resume`, { method: "POST" });
}

export async function steerJob(jobId: string, message: string) {
  return request(`/v1/jobs/${encodeURIComponent(jobId)}/steer`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function listAgentReports(limit = 30) {
  return request<{ ok: boolean; reports: AgentReport[] }>(
    `/v1/runs/agent-reports?limit=${limit}`
  );
}

export async function listJobFiles(jobId: string) {
  return request<{ ok: boolean; files: JobFile[] }>(
    `/v1/jobs/${encodeURIComponent(jobId)}/files`
  );
}

export async function getJobFile(jobId: string, path: string) {
  const q = new URLSearchParams({ path });
  return request<{ ok: boolean; path: string; content: string; truncated?: boolean }>(
    `/v1/jobs/${encodeURIComponent(jobId)}/file?${q}`
  );
}

/** Browser EventSource — api_key in query (headers not supported by EventSource). */
export function subscribeJobEvents(
  jobId: string,
  onEvent: (ev: MessageEvent) => void,
  onError?: (err: Event) => void,
  timeoutSec = 600
): EventSource {
  const key = encodeURIComponent(apiKey());
  const url = `${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/events?api_key=${key}&timeout=${timeoutSec}`;
  const es = new EventSource(url);
  es.addEventListener("job", onEvent as EventListener);
  es.addEventListener("done", onEvent as EventListener);
  es.addEventListener("error", onEvent as EventListener);
  es.onerror = onError || null;
  return es;
}
