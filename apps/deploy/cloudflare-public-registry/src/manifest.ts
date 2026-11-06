export function packageVisibilityFromManifest(manifest: any): string {
  return String(manifest?.visibility || "public").toLowerCase() === "private" ? "private" : "public";
}

export function packageAuthors(manifest: any): string[] {
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

export function packageCreator(manifest: any): string {
  const authors = packageAuthors(manifest);
  return authors.length ? authors.join(", ") : "unknown";
}

export function stringList(value: any): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

export function packageBadges(manifest: any): string[] {
  const badges = stringList(manifest?.badges);
  if (manifest?.official && !badges.includes("official")) badges.push("official");
  if (manifest?.signing && !badges.includes("verified")) badges.push("verified");
  if (manifest?.deprecated && !badges.includes("deprecated")) badges.push("deprecated");
  return badges;
}

export function parseManifestJson(raw: string | null | undefined): any {
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return {}; }
}

export function packageRow(r: any) {
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
