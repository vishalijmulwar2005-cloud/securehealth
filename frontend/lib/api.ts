"use client";
/** Typed API client (UI/UX §26 lib layer). Centralizes access; never passes
 * raw ORM objects; on 401 attempts the selected refresh flow ONCE, then clears
 * protected state and returns to controlled authentication (TRD §5). */

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const ACCESS_KEY = "sh.access";
const REFRESH_KEY = "sh.refresh";

export class ApiError extends Error {
  code: string;
  fields?: { field: string; issue: string }[];
  constructor(code: string, message: string, fields?: { field: string; issue: string }[]) {
    super(message);
    this.code = code;
    this.fields = fields;
  }
}

export const tokens = {
  get access() { return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY); },
  get refresh() { return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY); },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() { localStorage.removeItem(ACCESS_KEY); localStorage.removeItem(REFRESH_KEY); },
};

async function parseError(res: Response): Promise<never> {
  let code = "INTERNAL_ERROR";
  let message = "Something went wrong";
  let fields: { field: string; issue: string }[] | undefined;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      fields = body.error.fields;
    }
  } catch { /* non-JSON error stays generic */ }
  throw new ApiError(code, message, fields);
}

async function refreshOnce(): Promise<boolean> {
  const refresh = tokens.refresh;
  if (!refresh) return false;
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) { tokens.clear(); return false; }
  const data = await res.json();
  tokens.set(data.access_token, data.refresh_token);
  return true;
}

async function request<T>(path: string, init: RequestInit & { retried?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const access = tokens.access;
  if (access) headers.Authorization = `Bearer ${access}`;
  if (init.body && typeof init.body === "string") headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401 && !init.retried && tokens.refresh) {
    if (await refreshOnce()) return request<T>(path, { ...init, retried: true });
  }
  if (!res.ok) await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function download(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${tokens.access ?? ""}` },
  });
  if (res.status === 401 && (await refreshOnce())) return download(path);
  if (!res.ok) await parseError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.includes("/files/") ? `protected-file-${Date.now()}.bin` : "protected-download.bin";
  a.click();
  URL.revokeObjectURL(url);
}

async function upload(path: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tokens.access ?? ""}` },
    body: form,
  });
  if (res.status === 401 && (await refreshOnce())) return upload(path, file);
  if (!res.ok) await parseError(res);
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload,
  download,
};
