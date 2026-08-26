/** Lumen API client — jobs list/poll, SSE, cancel. */

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

export async function listJobs(limit = 20): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs?limit=${limit}`, {
    headers: { "X-Api-Key": apiKey(), Authorization: `Bearer ${apiKey()}` },
    cache: "no-store",
  });
  return res.json();
}

export async function getJob(jobId: string): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}`, {
    headers: { "X-Api-Key": apiKey(), Authorization: `Bearer ${apiKey()}` },
    cache: "no-store",
  });
  return res.json();
}

export async function cancelJob(jobId: string): Promise<any> {
  const res = await fetch(`${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: { "X-Api-Key": apiKey(), Authorization: `Bearer ${apiKey()}` },
  });
  return res.json();
}

/** Browser SSE to job events endpoint. */
export function subscribeJobEvents(
  jobId: string,
  onEvent: (ev: MessageEvent) => void,
  onError?: (err: Event) => void
): EventSource {
  const url = `${apiBase()}/v1/jobs/${encodeURIComponent(jobId)}/events`;
  // EventSource cannot set custom headers; key via query only in dev when API allows,
  // production should use cookie session — for now document header limitation.
  const es = new EventSource(url);
  es.addEventListener("job", onEvent as any);
  es.addEventListener("done", onEvent as any);
  es.onerror = onError || null;
  return es;
}
