# GG frontend prototype

Interactive frontend for GG, an AI-powered real-time voice-cloning impersonation detection and prevention platform for organisations (SIH 2026). All data is mock data; the app is ready to be wired to a backend through the service layer.

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # static build in dist/
```

Node 20+ recommended. The app uses hash routing, so `dist/` works on any static host. Inside sandboxed previews with no usable URL it falls back to in-memory routing automatically (`src/App.tsx`).

## The demo story

One incident moves through the whole organisation:

1. **Employee** (`/employee`): Priya Menon (Finance) gets a call from "Rahul Sharma, CEO". GG analyses the call live, raises a high-risk alert, and Priya verifies the specific request. Choosing "No, this isn't me" on Rahul's registered device confirms the impersonation, blocks the ₹20,00,000 transfer and creates incident #78421.
2. **Security** (`/security`): the dashboard shows the new incident. #78421 opens as Confirmed / Contained with weighted signals, audio, transcript, timeline and related incidents.
3. **Administrator** (`/admin`): the overview reports 1 prevented impersonation attempt today, and every chart includes the new incident.
4. **Documents** (`/documents`): the seeded `Vendor_Payment_Update.pdf` names the same payee and links back to #78421 once it exists.

### Presenter controls

Demo controls are hidden in the normal product UI: "Restart demo", the flow stepper, "Skip to alert", "Demo: answer as Rahul" and "Ring again". To show them, press **Shift + P** (ignored while typing in a field), or open the app with `?presenter` in the URL, for example `http://localhost:5173/?presenter#/employee`. Press Shift + P again to hide them. "Restart demo" resets all state.

To hide another element outside presenter mode, add the `presenter-only` class (see `src/hooks/usePresenterMode.ts`).

## Screens

| Area | Route | Screen |
| --- | --- | --- |
| Employee | `/employee/incoming` | 1 Incoming call |
| | `/employee/live` | 2 Live call analysis |
| | `/employee/alert` | 3 High risk alert |
| | `/employee/verify` | 4 Verify request |
| | `/employee/outcome` | 5 Call outcome |
| Security | `/security` | 6 Dashboard |
| | `/security/incidents` | 7 Incident list |
| | `/security/incidents/:id` | 8 Incident detail |
| | `/security/incidents/:id/analysis` | 9 Audio / transcript analysis (`?tab=signals\|audio\|transcript\|context`) |
| | `/security/profiles`, `/security/profiles/:personId` | 10 Voice profiles |
| Documents | `/documents` | 11 Document security (upload, website, paste) |
| | `/documents/:id/analysis` | 12 Document analysis |
| | `/documents/:id` | 13 Document report |
| | `/documents/history` | All analyses |
| Administrator | `/admin` | 14 Organisation overview |
| | `/admin/analytics` | 15 Analytics |
| | `/admin/reports` | 16 Reports & audit |

## Structure

```
src/
  app/          brand name (PRODUCT_NAME), navigation config
  domain/       types (API contract), risk scoring, metrics, formatting
  data/         seeded mock data: people, incident #78421, 30-day history,
                daily call stats, voice profiles, documents, audit
  services/     seam to the backend: incidentService, documentService
  state/        demo state (reducer + provider), demo clock
  components/   ui, layout, charts, incident, metrics, viz
  features/     employee, security, documents, admin
  styles/       tokens (per-area themes), base
```

- **Themes** live in `src/styles/tokens.css` and switch on `data-theme`: employee (light, pink), security (charcoal-navy, purple), documents (light neutral), admin (white and lavender, purple).
- **One source of numbers.** Security and Administrator both compute from `src/domain/metrics.ts` over the same incident list, so views never disagree.
- **Mock data is seeded** (`src/data/seed.ts`), so every load looks identical.
- **No chart, icon or CSS framework dependencies.** Charts are SVG components in `src/components/charts`.

## Sign in with Google (Supabase Auth)

When `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` are set in `.env.local` (see `.env.example`), the whole app requires sign-in. Without them it runs open.

- **Code:** `src/lib/supabase.ts` is the client and `src/state/AuthProvider.tsx` holds the session. `src/features/auth/SignIn.tsx` is the sign-in screen, and `AuthGate` in `src/App.tsx` guards the app. The account and Sign out button are in the header.
- **PKCE flow:** Google returns to `http://localhost:5173/?code=…`. supabase-js exchanges the code, and the app then restores the `#/route` you were on. PKCE is used because the implicit flow would put tokens in the URL hash, which the router uses.
- **Project:** Supabase project `gg-voice-guard` (ref `rwwmzmbmponftixtikyz`, Mumbai).
- **Setup outside the code:**
  - **Google Cloud:** an OAuth client of type "Web application". Authorized JavaScript origin `http://localhost:5173`. Authorized redirect URI `https://rwwmzmbmponftixtikyz.supabase.co/auth/v1/callback`.
  - **Supabase:** Authentication → Sign In / Providers → Google, enabled, with that client ID and secret. Authentication → URL Configuration: Site URL `http://localhost:5173`, Redirect URLs `http://localhost:5173/**`.

## Live detection backend

The employee call screens are wired to the deepfake detector in `call-monitor/backend`.

```powershell
.\run_backend.ps1      # model + /ws/audio + /ws/monitor on :8000
.\run_frontend.ps1     # this app on :5173
.\run_client.ps1       # captures the WhatsApp call and streams it to the backend
```

- `src/services/detectionFeed.ts` subscribes to `ws://<host>:8000/ws/monitor` (override with `VITE_DETECTION_WS`) and reconnects on its own. The backend broadcasts `session_start`, every `verdict` and `session_summary` there. A page opened mid-call gets the session so far.
- When the capture client starts a session, `/employee` jumps straight to live analysis. The risk ring, band and the "AI-generated voice" check come from the model's session risk. A `high` band opens the alert, and the backend only reports `high` for sustained evidence.
- The alert, and the incident created at the end of the call, use the model's score and reasons. The caller identity, request, transcript and the other signals are still mock data, because no model produces them yet.
- A call that ends at low risk closes without creating an incident.
- If the backend is unreachable, the rail shows "Detector offline" and the original simulated demo runs.
- **Audio check** (`/security/audio`, "Audio check" in the Security sidebar) scores an uploaded recording. The browser decodes the file (WAV, MP3, M4A, OGG, WebM; up to 30 minutes) and resamples it to 16 kHz mono. It streams the audio to `POST /analyse`, which runs the same VAD, windows, model and risk rules as a live call and streams back one result per window. The page shows the verdict, a timeline of per-window verdicts over the detected speech, and a player: click a window to hear it.
- **Capture client** (top tab, `/client`) mirrors the desktop capture client's window: status, session, risk meter, chunk stats, the verdict/event log, device pickers, chunk length, WhatsApp auto-detect and "Scan active audio apps". Start, Stop and settings changes apply to the client window too. The client serves this through a local API on `127.0.0.1:8001` (`client/control_server.py`, port `CLIENT_CONTROL_PORT`). That API answers only pages served from localhost, because it can start the microphone. Allow other origins with `CLIENT_CONTROL_ORIGINS`, and point this app elsewhere with `VITE_CLIENT_URL`.
- **Incident report** (`/report`) is offered once the synthetic-voice risk reaches 70%: a "Create incident report" button on the high-risk alert and on Audio check results, and a banner on the Capture client tab. It has three steps:
  1. The person fills in call details: who called, what they asked, whether money or information was shared.
  2. These are merged with the model evidence (risk, per-window verdicts, timeline, detector) into a report they can print, save as PDF or download as HTML.
  3. A step-by-step "what to do now" checklist, tailored to what happened: 1930 and the bank first if money was lost, verifying through a known channel, securing accounts, saving evidence, cybercrime.gov.in or Sanchar Saathi Chakshu, WhatsApp report and block, the security team (CERT-In), and warning people. Sources are listed in `src/features/report/guidance.ts`.
  Data stays in the browser's sessionStorage.
- The backend defaults to port 8000 on the host serving this page. Override it with `VITE_BACKEND_URL`.
- Replay a file without a phone call: `cd call-monitor\backend; .\.venv\Scripts\python scripts\simulate_call.py <audio> --realtime`.

## Connecting a backend

- `incidentService` returns the active call, the live-analysis script and creates the incident. Replace the bodies with API calls and keep the `Incident` shape from `src/domain/types.ts`.
- `documentService.analyseText` is a small rule-based analyser so pasted content gives real, explainable results in the prototype. In production, return the same `DocumentAnalysis` shape from `POST /v1/documents/analyse`. PDF and Word uploads, and website checks, use sample text because the browser prototype can't extract or fetch them.
- Replace the reducer's seeded `incidents` and `documents` with fetched data (for example with a query library) when endpoints exist.

## Notes for the research team

- Signal weights (`src/data/incident78421.ts`) and risk thresholds (`src/domain/risk.ts`, medium 40, high 70) are placeholders to be replaced with calibrated values.
- The UI shows per-call signal outputs only. It makes no claims about model accuracy.
- Only verified genuine, low-risk calls are marked as eligible to update a trusted voice profile.
- The voice embedding grid is a display projection, not the real embedding.
