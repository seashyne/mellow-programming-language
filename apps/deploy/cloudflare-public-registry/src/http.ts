import type { Json } from "./types";

export function securityHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    ...extra,
  };
}

export function json(payload: Json, status = 200): Response {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: securityHeaders(),
  });
}

export async function readJson(req: Request): Promise<any> {
  try { return await req.json(); } catch { return {}; }
}
