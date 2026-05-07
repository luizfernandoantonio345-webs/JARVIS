/**
 * JarvisClient — thin HTTP wrapper around the JARVIS backend API.
 * Uses the native `fetch` API (Node 18+, VS Code bundles it).
 */

export class JarvisClient {
  constructor(
    private readonly baseUrl: string,
    private readonly sessionId: string,
  ) {}

  /** Send a chat message and return the plain-text response. */
  async chat(message: string): Promise<string> {
    const url = `${this.baseUrl}/chat/`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: this.sessionId }),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Backend error ${resp.status}: ${text}`);
    }

    const data = (await resp.json()) as { response?: string; error?: string };
    if (data.error) throw new Error(data.error);
    return data.response ?? "";
  }

  /** Invoke a specialized agent and return its response. */
  async agentRun(
    role: string,
    message: string,
    history: Array<{ role: string; content: string }> = [],
  ): Promise<string> {
    const url = `${this.baseUrl}/agents/${encodeURIComponent(role)}/run`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: this.sessionId,
        history,
      }),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Agent error ${resp.status}: ${text}`);
    }

    const data = (await resp.json()) as { response?: string; error?: string };
    if (data.error) throw new Error(data.error);
    return data.response ?? "";
  }
}
