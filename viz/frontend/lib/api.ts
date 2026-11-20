/**
 * The only place the frontend talks to the Python experiment service.
 *
 * Calls happen on the server (React Server Components / route handlers), so the
 * browser never needs the service to be reachable, and no CORS is required in
 * deployment. Every call returns an error string instead of throwing: a page
 * whose data is missing renders that reason rather than a blank screen or an
 * invented number.
 */

const API_URL = process.env.EXPERIMENT_API_URL ?? "http://127.0.0.1:8000";

export type Result<T> = { data: T; error: null } | { data: null; error: string };

export const HINT =
  "start it with `make api` (uvicorn on 127.0.0.1:8000), or set EXPERIMENT_API_URL";

export async function apiGet<T>(path: string): Promise<Result<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    if (!response.ok) {
      return { data: null, error: `${path} returned HTTP ${response.status}` };
    }
    return { data: (await response.json()) as T, error: null };
  } catch {
    return {
      data: null,
      error: `Cannot reach the experiment service at ${API_URL} — ${HINT}.`,
    };
  }
}
