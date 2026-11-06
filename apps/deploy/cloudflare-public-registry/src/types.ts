export interface Env {
  REGISTRY_DB: D1Database;
  PACKAGE_BUCKET: R2Bucket;
  REGISTRY_BASE_URL: string;
  TOKEN_HASH_SALT: string;
}

export type Json = Record<string, unknown>;
export const MAX_ARCHIVE_BYTES = 5 * 1024 * 1024;
