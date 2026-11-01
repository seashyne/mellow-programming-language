-- Replace the values before running.
INSERT OR REPLACE INTO api_tokens (token_hash, owner, scopes_json, created_at)
VALUES (
  'replace-with-sha256-of-salt-colon-token',
  'admin',
  '["publish","read"]',
  CURRENT_TIMESTAMP
);
