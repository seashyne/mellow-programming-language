export function isSafePackageName(name: string): boolean {
  return /^[a-z0-9][a-z0-9._\-@/]{0,127}$/i.test(name);
}

export function isSafeVersion(version: string): boolean {
  return /^[0-9A-Za-z][0-9A-Za-z.+\-]{0,63}$/.test(version);
}

export function parseNamespaceOwner(name: string): string | null {
  if (name.startsWith("@") && name.includes("/")) {
    const slash = name.indexOf("/");
    const owner = name.slice(1, slash).trim().toLowerCase();
    return owner || null;
  }
  return null;
}
