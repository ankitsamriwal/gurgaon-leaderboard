import { useAuthStore } from "../store/auth";
import type { ApiError } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setSession, user, clearSession } = useAuthStore.getState();
  if (!refreshToken || !user) return null;

  const resp = await fetch(`${API_BASE}/auth/token/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) {
    clearSession();
    return null;
  }
  const body = await resp.json();
  setSession({ accessToken: body.access_token, refreshToken: body.refresh_token, user });
  return body.access_token as string;
}

/** Fetch wrapper: attaches the bearer token, retries once through
 * app/services/auth.py's refresh rotation on a 401, and unwraps
 * docs/02-api-spec.md's {"error": {"code","message"}} shape into a typed
 * error instead of a generic HTTP failure. */
export async function apiFetch<T>(path: string, init: RequestInit = {}, _retried = false): Promise<T> {
  const { accessToken } = useAuthStore.getState();
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (resp.status === 401 && !_retried) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiFetch<T>(path, init, true);
  }

  if (!resp.ok) {
    let body: ApiError | null = null;
    try {
      body = await resp.json();
    } catch {
      // non-JSON error body
    }
    throw new ApiRequestError(
      resp.status,
      body?.error?.code ?? "UNKNOWN_ERROR",
      body?.error?.message ?? resp.statusText,
    );
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export function wsUrl(path: string): string {
  const base = new URL(API_BASE);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = path;
  return base.toString();
}

export function formatPaise(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
