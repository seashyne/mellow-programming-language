import { packageAuthors, packageBadges, packageCreator, parseManifestJson, stringList } from "./manifest";

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function pageShell(title: string, body: string): Response {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)}</title><style>body{font-family:system-ui,sans-serif;margin:0;color:#17202a;background:#f7f8fb}header{background:#18212f;color:white;padding:28px 32px}header a{color:white}main{max-width:980px;margin:0 auto;padding:24px}a{color:#175cd3;text-decoration:none}a:hover{text-decoration:underline}form{display:flex;gap:8px;margin:18px 0 4px}input{flex:1;padding:10px 12px;border:1px solid #c8d0dc;border-radius:6px}button{padding:10px 14px;border:0;border-radius:6px;background:#246bfe;color:white}.pkg,.panel{background:white;border:1px solid #d9e0ea;border-radius:8px;padding:18px;margin:14px 0}.pkg h2,.panel h2{margin:0 0 8px;font-size:20px}.meta{color:#596579;font-size:14px;margin:8px 0}.badge{display:inline-block;border:1px solid #b8c4d6;border-radius:999px;padding:2px 8px;margin-right:6px;font-size:12px}code,pre{background:#eef2f7;padding:6px 8px;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.kv{margin:4px 0}.muted{color:#596579}</style></head><body>${body}</body></html>`, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
      "referrer-policy": "no-referrer",
    },
  });
}

export function registryPage(items: any[], query: string): Response {
  const escaped = escapeHtml(query);
  const cards = items.map((item) => {
    const badges = (item.badges || []).map((b: string) => `<span class="badge">${escapeHtml(b)}</span>`).join(" ");
    const keywords = escapeHtml((item.keywords || []).join(", ") || "-");
    const name = escapeHtml(item.name);
    return `<article class="pkg"><h2><a href="/packages/${encodeURIComponent(item.name)}">${name}</a></h2><p>${escapeHtml(item.description || "")}</p><div class="meta">latest ${escapeHtml(item.latest || "-")} · by ${escapeHtml(item.creator || "unknown")} · downloads ${Number(item.downloads || 0)}</div><div>${badges}</div><div class="meta">license ${escapeHtml(item.license || "-")} · keywords ${keywords}</div><code>mellow install ${name}</code></article>`;
  }).join("") || "<p>No packages found.</p>";
  return pageShell("Mellow Registry", `<header><h1>Mellow Registry</h1><p>Browse, search, and install Mellow packages.</p></header><main><form method="get" action="/packages"><input name="q" value="${escaped}" placeholder="Search packages"><button>Search</button></form>${cards}</main>`);
}

export function packageDetailPage(pkg: any, latestRow: any, versions: string[]): Response {
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
