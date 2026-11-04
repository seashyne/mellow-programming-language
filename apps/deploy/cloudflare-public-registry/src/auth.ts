import type { Env } from "./types";
import { json } from "./http";

export async function sha256HexBytes(value: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", value.buffer as ArrayBuffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256Hex(value: string): Promise<string> {
  return sha256HexBytes(new TextEncoder().encode(value));
}

export async function getTokenRecord(env: Env, bearer: string | null) {
  if (!bearer) return null;
  const tokenHash = await sha256Hex(`${env.TOKEN_HASH_SALT}:${bearer}`);
  return env.REGISTRY_DB.prepare(
    "SELECT owner, scopes_json, revoked_at FROM api_tokens WHERE token_hash = ?"
  ).bind(tokenHash).first<{ owner: string; scopes_json: string; revoked_at: string | null }>();
}

export async function requirePublishToken(env: Env, req: Request) {
  const auth = req.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7).trim() : null;
  const record = await getTokenRecord(env, bearer);
  if (!record || record.revoked_at) return { ok: false, response: json({ ok: false, error: "invalid publish token" }, 401) };
  let scopes: string[] = [];
  try {
    scopes = JSON.parse(record.scopes_json || "[]") as string[];
  } catch {
    return { ok: false, response: json({ ok: false, error: "invalid token scopes" }, 500) };
  }
  if (!scopes.includes("publish")) return { ok: false, response: json({ ok: false, error: "token missing publish scope" }, 403) };
  return { ok: true, owner: record.owner };
}

export async function getRequester(env: Env, req: Request) {
  const auth = req.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7).trim() : null;
  const record = await getTokenRecord(env, bearer);
  if (!record || record.revoked_at) return null;
  return record.owner;
}
