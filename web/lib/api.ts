/** Lumen API client — jobs, SSE, cancel, agent reports, diff files. */

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
  };
}

export async function listJobs(limit = 20): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs?limit=${limit}`, {
    headers: headers(),
    cache: "no-store",
  });
  return res.json();
}

export async function getJob(jobId: string): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}`, {
    headers: headers(),
    cache: "no-store",
  });
  return res.json();
}

export async function cancelJob(jobId: string): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: headers(),
  });
  return res.json();
}

export async function listAgentReports(limit = 20): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/runs/agent-reports?limit=${limit}`, {
    headers: headers(),
    cache: "no-store",
  });
  return res.json();
}

export async function listJobFiles(jobId: string): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/files`, {
    headers: headers(),
    cache: "no-store",
  });
  return res.json();
}

export async function getJobFile(jobId: string, path: string): Promise<any> {
  const q = new URLSearchParams({ path });
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/file?${q}`, {
    headers: headers(),
    cache: "no-store",
  });
  return res.json();
}

/** Browser SSE — api_key via query (EventSource cannot set headers). */
export function subscribeJobEvents(
  jobId: string,
  onEvent: (ev: MessageEvent) => void,
  onError?: (err: Event) => void
): EventSource {
  const key = encodeURIComponent(apiKey());
  const url = `${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/events?api_key=${key}`;
  const es = new EventSource(url);
  es.addEventListener("job", onEvent as any);
  es.addEventListener("done", onEvent as any);
  es.addEventListener("error", onEvent as any);
  es.onerror = onError || null;
  return es;
}
