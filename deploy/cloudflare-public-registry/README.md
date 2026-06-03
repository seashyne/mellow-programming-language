# Mellow Public Registry on Cloudflare

This folder is the deployable starter for the public Mellow package registry.

## Services
- **Workers**: API runtime
- **R2**: package archive storage
- **D1**: registry metadata

## Deploy
1. Create the D1 database and R2 bucket.
2. Update `wrangler.toml` with the real binding IDs.
3. Run the migration:
   - `npm install`
   - `npm run db:migrate`
4. Seed a publish token row in D1 using the helper SQL in `scripts/seed_token.sql`.
5. Deploy: `npm run deploy`

## Expected client setup
```bash
mellow pkg registry https://registry.mellowlang.org
mellow login --token <publish-token>
mellow publish ./physics2d
mellow install physics2d
```
