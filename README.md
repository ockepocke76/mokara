# Mokara

Monte Carlo BTC/portfolio simulator — successor to the Streamlit-based
`mymontecarlo` (mokara.ai), rebuilt as FastAPI + Next.js.

- **[PORT_PLAN.md](PORT_PLAN.md)** — architecture, decisions, and the wave-by-wave build tracker. Start here.
- `api/` — FastAPI + the simulation engine (copied from `mymontecarlo@pre-port-detangled`)
- `web/` — Next.js App Router + TypeScript + Tailwind + shadcn/ui + Better Auth

## Ground rule

This repo was started fresh so its history contains **no secrets** — the old
repo's history is burned (leaked DB password, RSA keys). Configuration comes
from environment variables only; commit `.env.example` updates, never `.env`.
