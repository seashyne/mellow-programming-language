# MellowLang v1.5.6

- Added Cloudflare-compatible HTTP headers for registry requests.
- Added clearer auth/login error detail and hints.
- Normalized auth probe responses for whoami/login.
- Switched CLI package init to lazy-load to avoid runpy warning.
- Applied the same client headers to package downloads.
