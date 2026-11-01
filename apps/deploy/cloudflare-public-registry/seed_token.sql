-- Replace with your own token hash before importing into remote D1.
DELETE FROM api_tokens WHERE owner='your-owner';

INSERT INTO api_tokens (token_hash, owner, scopes_json, created_at, revoked_at)
VALUES ('replace-with-token-hash', 'your-owner', '["publish"]', CURRENT_TIMESTAMP, NULL);
