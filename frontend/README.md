# Genie Frontend

Next.js 14 (App Router) + Tailwind + Zustand + TanStack Query. See root
`CLAUDE.md` for the full spec.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local     # works as-is against a local backend
npm run dev                          # http://localhost:3000
```

`/` redirects to `/chat`. The sidebar shows a live **backend connected**
indicator (calls `GET /health` on `NEXT_PUBLIC_API_URL`).

## Auth

Clerk is optional in dev. Leave `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` blank to run
in public mode (matches the backend dev-user bypass, `CLAUDE.md` §7). Set the
Clerk env vars to enable `<SignIn/>` / `<SignUp/>` and route protection.

## Scripts

```bash
npm run dev
npm run build
npm run lint
```

## Layout

See `CLAUDE.md` §5. `hooks/useChat.ts` and most of the chat/task data flow are
stubs until Phase 1 / Phase 2.
