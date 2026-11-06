import type { Env } from "./types";
import { MAX_ARCHIVE_BYTES } from "./types";
import { json, readJson, securityHeaders } from "./http";
import { getRequester, getTokenRecord, requirePublishToken, sha256Hex, sha256HexBytes } from "./auth";
import {
  packageAuthors,
  packageBadges,
  packageCreator,
  packageRow,
  packageVisibilityFromManifest,
  parseManifestJson,
  stringList,
} from "./manifest";
import { escapeHtml, pageShell, registryPage, packageDetailPage } from "./pages";
import { isSafePackageName, isSafeVersion, parseNamespaceOwner } from "./validation";

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
