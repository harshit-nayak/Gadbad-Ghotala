# Document verification — frontend + docsign pipeline

This branch pairs the GG frontend prototype with `docsign`, an internal
document signing & verification tool, so the frontend's Documents tab is a
real client of the pipeline rather than a mock.

```
.
├── frontend/       React + Vite app (Employee, Security, Documents, Admin)
└── docPipeline/    docsign: signing & verification pipeline (CLI + Flask API)
```

Each half has its own README with full detail:

- [`frontend/README.md`](frontend/README.md)
- [`docPipeline/README.md`](docPipeline/README.md) — cryptographic design,
  threat model, CLI reference
- [`docPipeline/pipeline_overview.md`](docPipeline/pipeline_overview.md) —
  diagrams of the signing/verification flow

## How they connect

The frontend's Documents tab (`frontend/src/features/documents/`) talks to
docsign's Flask API (`docPipeline/src/docsign/web.py`) over HTTP:

| Frontend page | API calls |
|---|---|
| Verify | `POST /api/verify` (DB mode), `POST /api/verify/offline` (`.sig` file) |
| Sign | `POST /api/sign` |
| Admin | `GET /api/status`, `POST /api/init-ca`, `POST /api/enrol`, `GET /root_ca.pem` |

`frontend/vite.config.ts` proxies `/api` and `/root_ca.pem` to
`http://127.0.0.1:8765` in dev, so the two run as separate processes with no
CORS setup needed.

## Running both

**1. docsign backend** (needs Python ≥ 3.11, or a 3.10 interpreter that
already has `cryptography`, `keyring` and `flask` installed):

```bash
cd docPipeline
python run_server.py
```

This binds `127.0.0.1:8765`, using `docPipeline/trust`, `.ca`, `.docsign` for
CA/keystore state and `docPipeline/docsign.db` (SQLite) as the signature
registry — both created on first use (`docsign init-ca`, `docsign enrol`, or
the Admin tab). None of that runtime state is committed; see
`docPipeline/.gitignore`.

**2. Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL and go to the Documents tab.
