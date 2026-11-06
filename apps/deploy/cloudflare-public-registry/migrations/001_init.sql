CREATE TABLE IF NOT EXISTS packages (
  name TEXT PRIMARY KEY,
  latest_version TEXT NOT NULL,
  description TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  owner TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS package_versions (
  package_name TEXT NOT NULL,
  version TEXT NOT NULL,
  description TEXT DEFAULT '',
  manifest_json TEXT NOT NULL,
  archive_key TEXT NOT NULL,
  archive_sha256 TEXT NOT NULL,
  published_by TEXT NOT NULL,
  published_at TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'public',
  PRIMARY KEY (package_name, version)
);

CREATE TABLE IF NOT EXISTS api_tokens (
  token_hash TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  scopes_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS download_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  package_name TEXT NOT NULL,
  version TEXT NOT NULL,
  downloaded_at TEXT NOT NULL,
  ip_hash TEXT
);
