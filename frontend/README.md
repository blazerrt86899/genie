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

## Auth (Clerk)

`@clerk/nextjs` **v7** (needs Next 15). Set up with the Clerk CLI:

```bash
npm install -g clerk
clerk auth login
clerk init --app app_3Ia08IpcDiBIMwI1FykjqEgLCMm   # links the app, writes .env.local
clerk doctor
```

- `ClerkProvider` wraps the app in `src/app/layout.tsx`, inside `<body>`,
  themed via the `appearance` prop (`src/lib/clerk-appearance.ts`). The
  `@clerk/ui` shadcn theme is **not** used — it requires Tailwind v4 (this
  project is v3) and renders Clerk components unstyled.
- `src/middleware.ts` runs bare `clerkMiddleware()` (enables `auth()` + the
  `/__clerk/*` proxy). Route protection is **resource-based**:
  `src/app/(app)/layout.tsx` calls `await auth()` and redirects to `/sign-in`.
- Sidebar shows `SignInButton`/`SignUpButton` when signed out, `UserButton` when
  signed in.

Backend JWT verification is still Phase 1 — until then the API treats every
caller as a fixed dev user (`CLAUDE.md` §7).

## Scripts

```bash
npm run dev
npm run build
npm run lint
```

## Layout

See `CLAUDE.md` §5. `hooks/useChat.ts` and most of the chat/task data flow are
stubs until Phase 1 / Phase 2.
