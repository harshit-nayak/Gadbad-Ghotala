# Pehchaan AI frontend prototype

Interactive frontend for Pehchaan AI, an AI-powered real-time voice-cloning impersonation detection and prevention platform for organisations (SIH 2026). All data is mock data; the app is ready to be wired to a backend through the service layer.

## Getting started

```bash
npm install
npm run fetch:images   # downloads the 8 landing photographs into public/img (~1.5 MB)
npm run dev            # http://localhost:5173
npm run build          # static build in dist/
```

`npm run fetch:images` needs internet and is only required once per clone. The `.jpg` files are
gitignored to keep the repository small; if a file is missing the landing page falls back to the
same photograph on Unsplash's CDN, so nothing renders broken. To use your own photography, drop
files into `public/img/` with the filenames listed in `IMAGES.md`.

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # static build in dist/
```

Node 20+ recommended. The app uses hash routing, so `dist/` works on any static host. Inside sandboxed previews with no usable URL it falls back to in-memory routing automatically (`src/App.tsx`).

## Public site and login

`/` is the public landing page and `/login` is a frontend-only demo sign-in. The authenticated application lives behind a route guard (`RequireAuth` in `src/App.tsx`): opening a protected URL directly sends you to `/login` and back to that URL after signing in. Any email and password are accepted, or use "Continue to demo". "Sign out" in the header returns to the landing page.

Landing imagery is configured in `src/features/landing/imagery.ts`. Each slot renders an original duotone SVG scene from `EditorialArt.tsx`; to use real photography, put the file in `public/img/` and set `photo: '/img/name.jpg'` on that slot. The crop, grain and overlay treatment stay the same, so no component changes are needed. Use muted, warm, slightly desaturated images.

The landing module is `src/features/landing/` (`Landing.tsx` sections, `LandingNav`, `HeroVisual`, `Atmosphere` for the grain and gradient background, `landing.css`). Its palette lives in the `[data-theme='landing']` block in `src/styles/tokens.css`. Landing content lives in `src/features/landing/content.ts`. **All numbers on the landing page are placeholders (`XX`) in `metrics` and `benchmark` in that file. Replace the `value` strings there when the model team supplies measured results; no component hard-codes a figure.**

## The demo story

One incident moves through the whole organisation:

1. **Employee** (`/employee`): Priya Menon (Finance) gets a call from "Rahul Sharma, CEO". Pehchaan AI analyses the call live, raises a high-risk alert, and Priya verifies the specific request. Choosing "No, this isn't me" on Rahul's registered device confirms the impersonation, blocks the ₹20,00,000 transfer and creates incident #78421.
2. **Security** (`/security`): the dashboard shows the new incident. #78421 opens as Confirmed / Contained with weighted signals, audio, transcript, timeline and related incidents.
3. **Administrator** (`/admin`): the overview reports 1 prevented impersonation attempt today, and every chart includes the new incident.
4. **Documents** (`/documents`): the seeded `Vendor_Payment_Update.pdf` names the same payee and links back to #78421 once it exists.

### Presenter controls

Demo controls are hidden in the normal product UI: "Restart demo", the flow stepper, "Skip to alert", "Demo: answer as Rahul" and "Ring again". To show them, press **Shift + P** (ignored while typing in a field), or open the app with `?presenter` in the URL, for example `http://localhost:5173/?presenter#/employee`. Press Shift + P again to hide them. "Restart demo" resets all state.

To hide another element outside presenter mode, add the `presenter-only` class (see `src/hooks/usePresenterMode.ts`).

## Screens

| Area | Route | Screen |
| --- | --- | --- |
| Public | `/` | Landing page |
| | `/login` | Demo login |
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

## Incident reports

The Security workspace generates a real PDF from the incident's current state. On an incident, "Generate report" builds a 10-section A4 report (executive summary, incident details, risk assessment with weighted signal bars, voice analysis with a waveform and flagged regions, conversation analysis, verification, timeline, decision, recommended actions, technical appendix) and offers Download PDF, Open and JSON. Regenerating after a status change produces a report that reflects the new status.

Generation lives in `src/services/reportService.ts` (jsPDF, client-side). Replace `buildIncidentReport` with a server-rendered PDF later and the calling UI stays the same.

## Structure

```
src/
  app/          brand name (PRODUCT_NAME), navigation config
  domain/       types (API contract), risk scoring, metrics, formatting
  data/         seeded mock data: people, incident #78421, 30-day history,
                daily call stats, voice profiles, documents, audit
  services/     seam to the backend: incidentService, documentService, reportService
  state/        auth (demo sign-in), demo state (reducer + provider), demo clock
  components/   ui, layout, charts, incident, metrics, viz
  features/     landing, auth, employee, security, documents, admin
  styles/       tokens (per-area themes), base
```

- **Themes** live in `src/styles/tokens.css` and switch on `data-theme`: employee (light, pink), security (charcoal-navy, purple), documents (light neutral), admin (white and lavender, purple).
- **One source of numbers.** Security and Administrator both compute from `src/domain/metrics.ts` over the same incident list, so views never disagree.
- **Mock data is seeded** (`src/data/seed.ts`), so every load looks identical.
- **No chart, icon or CSS framework dependencies.** Charts are SVG components in `src/components/charts`.

## Connecting a backend

- `incidentService` returns the active call, the live-analysis script and creates the incident. Replace the bodies with API calls and keep the `Incident` shape from `src/domain/types.ts`.
- `documentService.analyseText` is a small rule-based analyser so pasted content gives real, explainable results in the prototype. In production, return the same `DocumentAnalysis` shape from `POST /v1/documents/analyse`. PDF and Word uploads, and website checks, use sample text because the browser prototype can't extract or fetch them.
- Replace the reducer's seeded `incidents` and `documents` with fetched data (for example with a query library) when endpoints exist.

## Notes for the research team

- Signal weights (`src/data/incident78421.ts`) and risk thresholds (`src/domain/risk.ts`, medium 40, high 70) are placeholders to be replaced with calibrated values.
- The UI shows per-call signal outputs only. It makes no claims about model accuracy.
- Only verified genuine, low-risk calls are marked as eligible to update a trusted voice profile.
- The voice embedding grid is a display projection, not the real embedding.
