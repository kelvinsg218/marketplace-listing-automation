# MLA Web — frontend

Next.js (App Router) + TypeScript + Tailwind CSS 4, exported as static files (no Node server in production).

- `npm install` then `npm run dev` → http://localhost:3000 (proxies `/api` to `MLA_API_ORIGIN`, default `http://127.0.0.1:8000`)
- `npm run typecheck` · `npm run build` → `out/` (served by the API with `MLA_WEB_DIST_DIR`, or by nginx)

Design tokens: `src/app/globals.css` (`@theme`). Rules: `docs/MLA_WEB_UX_DESIGN.md`.
