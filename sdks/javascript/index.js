/**
 * Capability Maestro B2B client (Node.js / browser fetch)
 */
class MaestroClient {
  constructor(baseUrl, apiKey, { timeoutMs = 60000 } = {}) {
    this.baseUrl = String(baseUrl || "").replace(/\/$/, "");
    this.apiKey = apiKey;
    this.timeoutMs = timeoutMs;
  }

  async _request(method, path, body, auth = true) {
    const headers = { Accept: "application/json" };
    if (auth) headers["X-Api-Key"] = this.apiKey;
    const opts = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...opts, signal: ctrl.signal });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) data._status = res.status;
      return data;
    } finally {
      clearTimeout(t);
    }
  }

  health() { return this._request("GET", "/health", undefined, false); }
  me() { return this._request("GET", "/v1/me"); }
  generate(description, { wait = false } = {}) {
    return this._request("POST", "/v1/generate", { description, wait });
  }
  getJob(jobId) { return this._request("GET", `/v1/jobs/${jobId}`); }
  listJobs() { return this._request("GET", "/v1/jobs"); }
  hostStart(payload) { return this._request("POST", "/v1/hosts/start", payload || {}); }
  hostStop(payload) { return this._request("POST", "/v1/hosts/stop", payload || {}); }
  dashboard() { return this._request("GET", "/v1/dashboard"); }
}

module.exports = { MaestroClient };
