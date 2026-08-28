# Migracja na standard deploy — plan wykonawczy

> Spec: `docs/superpowers/specs/2026-08-28-migracja-na-standard-vercel-render-supabase-design.md`

## Status (2026-08-28)

- [x] Wiring repo (AGENTS.md, .cursor/rules, CI, ADR, docs/technical)
- [x] `/api/health`, `/api/health/ready`
- [x] pgvector zamiast Qdrant
- [x] Rate limit w Postgresie
- [x] Supabase Storage adapter + factory
- [x] Supabase Auth (JWKS) + legacy dev fallback
- [x] Zadania czatu w tle (`POST /v1/chat` → 202, `GET /v1/jobs/{id}`)
- [x] Flaga `VIDEO_GENERATION_ENABLED=false`
- [x] Frontend: Supabase, ApiPulse, polling jobów, vercel.json
- [ ] Wdrożenie: Supabase project, Render, Vercel, DNS Cloudflare
- [x] Usunięcie artefaktów GCP (`deploy/gcp/`, `nginx/`, root `docker-compose.yml`)
- [ ] README — sekcja deploy → nowy stack
