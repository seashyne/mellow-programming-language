export interface Env {
  REGISTRY_DB: D1Database;
  PACKAGE_BUCKET: R2Bucket;
  REGISTRY_BASE_URL: string;
  TOKEN_HASH_SALT: string;
}

type Json = Record<string, unknown>;
const MAX_ARCHIVE_BYTES = 5 * 1024 * 1024;

function securityHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    ...extra,
  };
}

function json(payload: Json, status = 200): Response {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: securityHeaders(),
  });
}

async function sha256HexBytes(value: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", value.buffer as ArrayBuffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(value: string): Promise<string> {
  return sha256HexBytes(new TextEncoder().encode(value));
}

async function getTokenRecord(env: Env, bearer: string | null) {
  if (!bearer) return null;
  const tokenHash = await sha256Hex(`${env.TOKEN_HASH_SALT}:${bearer}`);
  return env.REGISTRY_DB.prepare(
    "SELECT owner, scopes_json, revoked_at FROM api_tokens WHERE token_hash = ?"
  ).bind(tokenHash).first<{ owner: string; scopes_json: string; revoked_at: string | null }>();
}

async function requirePublishToken(env: Env, req: Request) {
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

async function getRequester(env: Env, req: Request) {
  const auth = req.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7).trim() : null;
  const record = await getTokenRecord(env, bearer);
  if (!record || record.revoked_at) return null;
  return record.owner;
}

function packageVisibilityFromManifest(manifest: any): string {
  return String(manifest?.visibility || "public").toLowerCase() === "private" ? "private" : "public";
}

function packageAuthors(manifest: any): string[] {
  const source =
    manifest?.authors ??
    manifest?.author ??
    manifest?.creator ??
    manifest?.publisher ??
    manifest?.maintainer ??
    manifest?.owner;
  if (Array.isArray(source)) return source.map((item) => String(item).trim()).filter(Boolean);
  if (typeof source === "string" && source.trim()) return [source.trim()];
  return [];
}

function packageCreator(manifest: any): string {
  const authors = packageAuthors(manifest);
  return authors.length ? authors.join(", ") : "unknown";
}

function stringList(value: any): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function packageBadges(manifest: any): string[] {
  const badges = stringList(manifest?.badges);
  if (manifest?.official && !badges.includes("official")) badges.push("official");
  if (manifest?.signing && !badges.includes("verified")) badges.push("verified");
  if (manifest?.deprecated && !badges.includes("deprecated")) badges.push("deprecated");
  return badges;
}

function parseManifestJson(raw: string | null | undefined): any {
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return {}; }
}

function packageRow(r: any) {
  const manifest = parseManifestJson(r.manifest_json);
  return {
    name: r.name || r.package_name,
    latest: r.latest_version || r.version,
    description: r.description,
    visibility: r.visibility,
    authors: packageAuthors(manifest),
    creator: packageCreator(manifest),
    license: manifest?.license || "",
    keywords: stringList(manifest?.keywords),
    badges: packageBadges(manifest),
    downloads: Number(r.downloads || 0),
    published_by: r.published_by,
    published_at: r.published_at,
  };
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pageShell(title: string, body: string): Response {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)}</title><style>body{font-family:system-ui,sans-serif;margin:0;color:#17202a;background:#f7f8fb}header{background:#18212f;color:white;padding:28px 32px}header a{color:white}main{max-width:980px;margin:0 auto;padding:24px}a{color:#175cd3;text-decoration:none}a:hover{text-decoration:underline}form{display:flex;gap:8px;margin:18px 0 4px}input{flex:1;padding:10px 12px;border:1px solid #c8d0dc;border-radius:6px}button{padding:10px 14px;border:0;border-radius:6px;background:#246bfe;color:white}.pkg,.panel{background:white;border:1px solid #d9e0ea;border-radius:8px;padding:18px;margin:14px 0}.pkg h2,.panel h2{margin:0 0 8px;font-size:20px}.meta{color:#596579;font-size:14px;margin:8px 0}.badge{display:inline-block;border:1px solid #b8c4d6;border-radius:999px;padding:2px 8px;margin-right:6px;font-size:12px}code,pre{background:#eef2f7;padding:6px 8px;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.kv{margin:4px 0}.muted{color:#596579}</style></head><body>${body}</body></html>`, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
      "referrer-policy": "no-referrer",
    },
  });
}

function registryPage(items: any[], query: string): Response {
  const escaped = escapeHtml(query);
  const cards = items.map((item) => {
    const badges = (item.badges || []).map((b: string) => `<span class="badge">${escapeHtml(b)}</span>`).join(" ");
    const keywords = escapeHtml((item.keywords || []).join(", ") || "-");
    const name = escapeHtml(item.name);
    return `<article class="pkg"><h2><a href="/packages/${encodeURIComponent(item.name)}">${name}</a></h2><p>${escapeHtml(item.description || "")}</p><div class="meta">latest ${escapeHtml(item.latest || "-")} · by ${escapeHtml(item.creator || "unknown")} · downloads ${Number(item.downloads || 0)}</div><div>${badges}</div><div class="meta">license ${escapeHtml(item.license || "-")} · keywords ${keywords}</div><code>mellow install ${name}</code></article>`;
  }).join("") || "<p>No packages found.</p>";
  return pageShell("Mellow Registry", `<header><h1>Mellow Registry</h1><p>Browse, search, and install Mellow packages.</p></header><main><form method="get" action="/packages"><input name="q" value="${escaped}" placeholder="Search packages"><button>Search</button></form>${cards}</main>`);
}

function packageDetailPage(pkg: any, latestRow: any, versions: string[]): Response {
  const manifest = parseManifestJson(latestRow?.manifest_json);
  const name = String(pkg.name || "");
  const badges = packageBadges(manifest).map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join(" ");
  const dependencies = manifest?.dependencies && typeof manifest.dependencies === "object" ? manifest.dependencies : {};
  const dependencyRows = Object.entries(dependencies).map(([dep, spec]) => `<li><code>${escapeHtml(dep)}</code> ${escapeHtml(spec)}</li>`).join("") || "<li>None</li>";
  const signing = manifest?.signing || {};
  const readme = manifest?.readme || manifest?.readme_text || manifest?.documentation || "";
  const changelog = manifest?.changelog || manifest?.release_notes || "";
  const versionLinks = versions.map((version) => `<a href="/api/v1/packages/${encodeURIComponent(name)}/versions/${encodeURIComponent(version)}">${escapeHtml(version)}</a>`).join(", ");
  const keywords = stringList(manifest?.keywords).map(escapeHtml).join(", ") || "-";
  const signatureStatus = signing?.signature_b64 ? `signed (${escapeHtml(signing?.algorithm || "unknown")})` : "unsigned";
  return pageShell(`${name} · Mellow Registry`, `<header><a href="/packages">← All packages</a><h1>${escapeHtml(name)}</h1><p>${escapeHtml(pkg.description || manifest?.description || "")}</p></header><main><section class="panel"><div>${badges}</div><div class="grid"><div><div class="kv"><strong>Latest</strong> ${escapeHtml(pkg.latest_version || "-")}</div><div class="kv"><strong>Creator</strong> ${escapeHtml(packageCreator(manifest))}</div><div class="kv"><strong>License</strong> ${escapeHtml(manifest?.license || "-")}</div></div><div><div class="kv"><strong>Downloads</strong> ${Number(latestRow?.downloads || 0)}</div><div class="kv"><strong>Published</strong> ${escapeHtml(latestRow?.published_at || "-")}</div><div class="kv"><strong>Signature</strong> ${signatureStatus}</div></div></div><p class="meta">keywords ${keywords}</p><pre>mellow install ${escapeHtml(name)}</pre></section><section class="panel"><h2>Versions</h2><p>${versionLinks || "No public versions."}</p></section><section class="panel"><h2>Dependencies</h2><ul>${dependencyRows}</ul></section><section class="panel"><h2>README</h2>${readme ? `<pre>${escapeHtml(readme)}</pre>` : `<p class="muted">${escapeHtml(manifest?.description || pkg.description || "No README supplied in the package manifest.")}</p>`}</section><section class="panel"><h2>Changelog</h2>${changelog ? `<pre>${escapeHtml(changelog)}</pre>` : `<p class="muted">No changelog supplied for this release.</p>`}</section><section class="panel"><h2>Verification</h2><p>${signatureStatus}</p><p><a href="/api/v1/packages/${encodeURIComponent(name)}/versions/${encodeURIComponent(pkg.latest_version)}/signature">View signature metadata</a></p></section></main>`);
}

async function readJson(req: Request): Promise<any> {
  try { return await req.json(); } catch { return {}; }
}

function isSafePackageName(name: string): boolean {
  return /^[a-z0-9][a-z0-9._\-@/]{0,127}$/i.test(name);
}

function isSafeVersion(version: string): boolean {
  return /^[0-9A-Za-z][0-9A-Za-z.+\-]{0,63}$/.test(version);
}

function parseNamespaceOwner(name: string): string | null {
  if (name.startsWith("@") && name.includes("/")) {
    const slash = name.indexOf("/");
    const owner = name.slice(1, slash).trim().toLowerCase();
    return owner || null;
  }
  return null;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/$/, "") || "/";

    if (req.method === "GET" && path === "/") {
      return json({ ok: true, service: "mellow-public-registry", baseUrl: env.REGISTRY_BASE_URL, endpoints: ["/health", "/api/v1/auth/whoami", "/api/v1/packages/search"] });
    }

    if (path === "/health") {
      return json({ ok: true, service: "mellow-public-registry", baseUrl: env.REGISTRY_BASE_URL, storage: "Cloudflare R2 + D1" });
    }

    if (req.method === "GET" && path === "/api/v1/auth/whoami") {
      const auth = req.headers.get("authorization") || "";
      const bearer = auth.startsWith("Bearer ") ? auth.slice(7).trim() : null;
      const record = await getTokenRecord(env, bearer);
      if (!record || record.revoked_at) return json({ ok: false, error: "invalid publish token" }, 401);
      let scopes: string[] = [];
      try {
        scopes = JSON.parse(record.scopes_json || "[]");
      } catch {
        return json({ ok: false, error: "invalid token scopes" }, 500);
      }
      return json({ ok: true, username: record.owner, scopes });
    }

    if (req.method === "GET" && path === "/api/v1/packages/search") {
      const q = (url.searchParams.get("q") || "").toLowerCase().slice(0, 100);
      const requester = await getRequester(env, req);
      const rows = await env.REGISTRY_DB.prepare(
        `SELECT p.name, p.latest_version, p.description, p.owner, v.manifest_json, v.published_by, v.published_at, COALESCE(v.visibility, 'public') as visibility,
                (SELECT COUNT(*) FROM download_events d WHERE d.package_name = p.name) as downloads
         FROM packages p
         LEFT JOIN package_versions v ON v.package_name = p.name AND v.version = p.latest_version
         WHERE (? = '' OR lower(p.name) LIKE ? OR lower(p.description) LIKE ? OR lower(v.manifest_json) LIKE ?)
           AND (COALESCE(v.visibility, 'public') = 'public' OR p.owner = ?)
         ORDER BY p.name LIMIT 100`
      ).bind(q, `%${q}%`, `%${q}%`, `%${q}%`, requester || '').all<any>();
      return json({ ok: true, query: q, count: rows.results.length, items: rows.results.map(packageRow) });
    }

    if (req.method === "GET" && path === "/packages") {
      const q = (url.searchParams.get("q") || "").toLowerCase().slice(0, 100);
      const requester = await getRequester(env, req);
      const rows = await env.REGISTRY_DB.prepare(
        `SELECT p.name, p.latest_version, p.description, p.owner, v.manifest_json, v.published_by, v.published_at, COALESCE(v.visibility, 'public') as visibility,
                (SELECT COUNT(*) FROM download_events d WHERE d.package_name = p.name) as downloads
         FROM packages p
         LEFT JOIN package_versions v ON v.package_name = p.name AND v.version = p.latest_version
         WHERE (? = '' OR lower(p.name) LIKE ? OR lower(p.description) LIKE ? OR lower(v.manifest_json) LIKE ?)
           AND (COALESCE(v.visibility, 'public') = 'public' OR p.owner = ?)
         ORDER BY p.name LIMIT 100`
      ).bind(q, `%${q}%`, `%${q}%`, `%${q}%`, requester || '').all<any>();
      return registryPage(rows.results.map(packageRow), q);
    }

    const packagePage = path.match(/^\/packages\/([^/]+)$/);
    if (req.method === "GET" && packagePage) {
      const name = decodeURIComponent(packagePage[1]);
      const requester = await getRequester(env, req);
      const pkg = await env.REGISTRY_DB.prepare("SELECT name, latest_version, description, owner FROM packages WHERE name = ?").bind(name).first<any>();
      if (!pkg) return pageShell("Package not found", `<header><h1>Package not found</h1></header><main><p>${escapeHtml(name)} does not exist.</p><p><a href="/packages">Back to packages</a></p></main>`);
      const latestRow = await env.REGISTRY_DB.prepare("SELECT manifest_json, published_by, published_at, COALESCE(visibility, 'public') as visibility, (SELECT COUNT(*) FROM download_events d WHERE d.package_name = package_versions.package_name) as downloads FROM package_versions WHERE package_name = ? AND version = ?").bind(name, pkg.latest_version).first<any>();
      if ((latestRow?.visibility || "public") === "private" && pkg.owner !== requester) {
        return pageShell("Package not found", `<header><h1>Package not found</h1></header><main><p>${escapeHtml(name)} does not exist.</p><p><a href="/packages">Back to packages</a></p></main>`);
      }
      const versions = await env.REGISTRY_DB.prepare("SELECT version FROM package_versions WHERE package_name = ? AND (COALESCE(visibility, 'public') = 'public' OR published_by = ?) ORDER BY version").bind(name, requester || "").all<{ version: string }>();
      return packageDetailPage(pkg, latestRow, versions.results.map((row) => row.version));
    }

    const authorProfile = path.match(/^\/api\/v1\/authors\/([^/]+)$/);
    if (req.method === "GET" && authorProfile) {
      const author = decodeURIComponent(authorProfile[1]).toLowerCase();
      const requester = await getRequester(env, req);
      const rows = await env.REGISTRY_DB.prepare(
        `SELECT p.name, p.latest_version, p.description, p.owner, v.manifest_json, v.published_by, v.published_at, COALESCE(v.visibility, 'public') as visibility,
                (SELECT COUNT(*) FROM download_events d WHERE d.package_name = p.name) as downloads
         FROM packages p
         LEFT JOIN package_versions v ON v.package_name = p.name AND v.version = p.latest_version
         WHERE (COALESCE(v.visibility, 'public') = 'public' OR p.owner = ?)
         ORDER BY p.name LIMIT 500`
      ).bind(requester || '').all<any>();
      const items = rows.results.map(packageRow).filter((item) => [item.creator, item.published_by, ...(item.authors || [])].some((v) => String(v || "").toLowerCase().includes(author)));
      return json({ ok: true, author: decodeURIComponent(authorProfile[1]), count: items.length, items });
    }

    const pkgMeta = path.match(/^\/api\/v1\/packages\/([^/]+)$/);
    if (req.method === "GET" && pkgMeta) {
      const name = decodeURIComponent(pkgMeta[1]);
      const requester = await getRequester(env, req);
      const pkg = await env.REGISTRY_DB.prepare("SELECT name, latest_version, description, owner FROM packages WHERE name = ?").bind(name).first<any>();
      if (!pkg) return json({ ok: false, error: `package not found: ${name}` }, 404);
      const latestRow = await env.REGISTRY_DB.prepare("SELECT manifest_json, published_by, published_at, COALESCE(visibility, 'public') as visibility, (SELECT COUNT(*) FROM download_events d WHERE d.package_name = package_versions.package_name) as downloads FROM package_versions WHERE package_name = ? AND version = ?").bind(name, pkg.latest_version).first<any>();
      if ((latestRow?.visibility || 'public') === 'private' && pkg.owner !== requester) return json({ ok: false, error: `package not found: ${name}` }, 404);
      const versions = await env.REGISTRY_DB.prepare("SELECT version FROM package_versions WHERE package_name = ? AND (COALESCE(visibility, 'public') = 'public' OR published_by = ?) ORDER BY version").bind(name, requester || '').all<{ version: string }>();
      const manifest = parseManifestJson(latestRow?.manifest_json);
      return json({ ok: true, name, latest: pkg.latest_version, versions: versions.results.map((v) => v.version), authors: packageAuthors(manifest), creator: packageCreator(manifest), license: manifest?.license || "", keywords: stringList(manifest?.keywords), badges: packageBadges(manifest), downloads: Number(latestRow?.downloads || 0), published_by: latestRow?.published_by, published_at: latestRow?.published_at, metadata: { ...pkg, visibility: latestRow?.visibility || 'public', authors: packageAuthors(manifest), creator: packageCreator(manifest), published_by: latestRow?.published_by, published_at: latestRow?.published_at, downloads: Number(latestRow?.downloads || 0) } });
    }

    const pkgVersion = path.match(/^\/api\/v1\/packages\/([^/]+)\/versions\/([^/]+)$/);
    if (req.method === "GET" && pkgVersion) {
      const name = decodeURIComponent(pkgVersion[1]);
      const version = decodeURIComponent(pkgVersion[2]);
      const requester = await getRequester(env, req);
      const row = await env.REGISTRY_DB.prepare(
        "SELECT package_name, version, description, manifest_json, archive_sha256, published_by, published_at, COALESCE(visibility, 'public') as visibility FROM package_versions WHERE package_name = ? AND version = ?"
      ).bind(name, version).first<any>();
      if (!row) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      if (row.visibility === 'private' && row.published_by !== requester) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      const manifest = parseManifestJson(row.manifest_json);
      return json({ ok: true, name, version, manifest, sha256: row.archive_sha256, published_by: row.published_by, published_at: row.published_at, description: row.description, visibility: row.visibility, authors: packageAuthors(manifest), creator: packageCreator(manifest), license: manifest?.license || "", keywords: stringList(manifest?.keywords), badges: packageBadges(manifest) });
    }

    const pkgSignature = path.match(/^\/api\/v1\/packages\/([^/]+)\/versions\/([^/]+)\/signature$/);
    if (req.method === "GET" && pkgSignature) {
      const name = decodeURIComponent(pkgSignature[1]);
      const version = decodeURIComponent(pkgSignature[2]);
      const requester = await getRequester(env, req);
      const row = await env.REGISTRY_DB.prepare(
        "SELECT package_name, version, manifest_json, archive_sha256, published_by, published_at, COALESCE(visibility, 'public') as visibility FROM package_versions WHERE package_name = ? AND version = ?"
      ).bind(name, version).first<any>();
      if (!row) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      if (row.visibility === 'private' && row.published_by !== requester) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      const manifest = parseManifestJson(row.manifest_json);
      const signing = manifest?.signing || {};
      return json({ ok: true, name, version, manifest, sha256: row.archive_sha256, signed: Boolean(signing?.signature_b64), algorithm: signing?.algorithm, signature_b64: signing?.signature_b64, public_key_pem: signing?.public_key_pem, creator: packageCreator(manifest), authors: packageAuthors(manifest), published_by: row.published_by, published_at: row.published_at });
    }

    const pkgDownload = path.match(/^\/api\/v1\/packages\/([^/]+)\/download\/([^/]+)$/);
    if (req.method === "GET" && pkgDownload) {
      const name = decodeURIComponent(pkgDownload[1]);
      const version = decodeURIComponent(pkgDownload[2]);
      const requester = await getRequester(env, req);
      const row = await env.REGISTRY_DB.prepare(
        "SELECT archive_key, published_by, COALESCE(visibility, 'public') as visibility FROM package_versions WHERE package_name = ? AND version = ?"
      ).bind(name, version).first<any>();
      if (!row) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      if (row.visibility === 'private' && row.published_by !== requester) return json({ ok: false, error: `version not found: ${name}@${version}` }, 404);
      const object = await env.PACKAGE_BUCKET.get(row.archive_key);
      if (!object) return json({ ok: false, error: "archive missing from storage" }, 404);
      const ip = req.headers.get("cf-connecting-ip") || req.headers.get("x-forwarded-for") || "";
      const ipHash = ip ? await sha256Hex(`${env.TOKEN_HASH_SALT}:${ip}`) : "";
      await env.REGISTRY_DB.prepare("INSERT INTO download_events (package_name, version, downloaded_at, ip_hash) VALUES (?, ?, ?, ?)").bind(name, version, new Date().toISOString(), ipHash).run();
      return new Response(object.body, {
        headers: securityHeaders({
          "content-type": "application/octet-stream",
          "content-disposition": `attachment; filename="${name}-${version}.mpkg"`,
          "cache-control": "public, max-age=300",
        }),
      });
    }

    if (req.method === "POST" && path === "/api/v1/packages/publish") {
      const auth = await requirePublishToken(env, req);
      if (!auth.ok) return auth.response as Response;
      const body = await readJson(req);
      const manifest = body.manifest || {};
      const name = String(manifest.name || '').trim();
      const version = String(manifest.version || '').trim();
      const archiveB64 = String(body.archive_b64 || '');
      const claimedSha256 = String(body.sha256 || '').trim().toLowerCase();
      const visibility = packageVisibilityFromManifest(manifest);
      if (!name || !version || !archiveB64) return json({ ok: false, error: 'manifest.name, manifest.version and archive_b64 are required' }, 400);
      if (!isSafePackageName(name)) return json({ ok: false, error: 'invalid package name' }, 400);
      if (!isSafeVersion(version)) return json({ ok: false, error: 'invalid package version' }, 400);
      const namespaceOwner = parseNamespaceOwner(name);
      if (namespaceOwner && namespaceOwner !== String(auth.owner || '').toLowerCase()) {
        return json({ ok: false, error: `namespace ownership mismatch: ${name}`, detail: `token owner ${auth.owner} cannot publish into @${namespaceOwner}` }, 403);
      }
      const pkgOwner = await env.REGISTRY_DB.prepare('SELECT owner FROM packages WHERE name = ?').bind(name).first<{ owner: string }>();
      if (pkgOwner && pkgOwner.owner !== auth.owner) {
        return json({ ok: false, error: `package ownership mismatch: ${name}`, detail: `${name} is owned by ${pkgOwner.owner}` }, 403);
      }
      let archive: Uint8Array;
      try {
        archive = Uint8Array.from(atob(archiveB64), (c) => c.charCodeAt(0));
      } catch {
        return json({ ok: false, error: 'invalid archive_b64' }, 400);
      }
      if (archive.byteLength === 0 || archive.byteLength > MAX_ARCHIVE_BYTES) {
        return json({ ok: false, error: `archive must be between 1 and ${MAX_ARCHIVE_BYTES} bytes` }, 400);
      }
      const sha256 = await sha256HexBytes(archive);
      if (claimedSha256 && claimedSha256 !== sha256) {
        return json({ ok: false, error: 'archive checksum mismatch' }, 400);
      }
      const archiveKey = `${name}/${version}/${name}-${version}.mpkg`;
      const existing = await env.REGISTRY_DB.prepare(
        'SELECT published_by FROM package_versions WHERE package_name = ? AND version = ?'
      ).bind(name, version).first<{ published_by: string }>();
      if (existing) {
        return json({ ok: false, error: `version already exists: ${name}@${version}` }, 409);
      }
      await env.PACKAGE_BUCKET.put(archiveKey, archive, { httpMetadata: { contentType: 'application/octet-stream' } });
      const now = new Date().toISOString();
      await env.REGISTRY_DB.prepare(
        `INSERT INTO packages (name, latest_version, description, created_at, updated_at, owner)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(name) DO UPDATE SET
           latest_version=excluded.latest_version,
           description=excluded.description,
           updated_at=excluded.updated_at,
           owner=CASE WHEN packages.owner IS NULL OR packages.owner = '' THEN excluded.owner ELSE packages.owner END`
      ).bind(name, version, String(manifest.description || ''), now, now, auth.owner).run();
      await env.REGISTRY_DB.prepare(
        `INSERT INTO package_versions (package_name, version, description, manifest_json, archive_key, archive_sha256, published_by, published_at, visibility)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(name, version, String(manifest.description || ''), JSON.stringify(manifest), archiveKey, sha256, auth.owner, now, visibility).run();
      return json({ ok: true, name, version, latest: version, published_by: auth.owner, archive_key: archiveKey, sha256, visibility, authors: packageAuthors(manifest), creator: packageCreator(manifest) });
    }

    return json({ ok: false, error: 'not found', path }, 404);
  },
};
