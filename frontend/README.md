# AdvisorAI frontend (Phase 1 prototype)

Next.js 15 (App Router) · TypeScript · Tailwind CSS v4 · shadcn/ui · Lucide icons.

A complete clickable prototype of the AdvisorAI journey on **mocked, fictional data**. Nothing leaves
the browser: there is no backend, no AI call and no real authentication.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

Sign in with **"Skip ahead as a demo user"**, or use any email and the demo code `123456`.

## Journey and routes

| Step | Route |
| --- | --- |
| Landing | `/` |
| Sign in / Sign up (email code, consent checkbox) | `/login`, `/signup` |
| Dashboard | `/dashboard` |
| Create case + **safety gate** (urgent-care screen) | `/cases/new` |
| Upload documents | `/cases/[caseId]/upload`, `/documents` |
| Processing (progress, partial and failed states) | `/cases/[caseId]/analysis` |
| Case overview | `/cases/[caseId]` |
| Timeline | `/cases/[caseId]/timeline` |
| Specialist perspectives | `/cases/[caseId]/perspectives` |
| Evidence and verification | `/cases/[caseId]/evidence` |
| Cross-agent review | `/cases/[caseId]/review` |
| AI synthesis | `/cases/[caseId]/synthesis` |
| 19-section patient report (print-friendly) | `/cases/[caseId]/report` |
| Questions (trackable) | `/cases/[caseId]/questions` |
| Second opinion and comparison | `/cases/[caseId]/second-opinion`, `/comparison` |
| Profile, settings | `/profile`, `/settings` |

Every case screen can open the traceability drawer through a deep link: `?evidence=<itemId>`.
For example `/cases/c_9f2/report?evidence=syn_8`.

## Demo cases (all fictional)

- `c_9f2`: **Heart and diabetes.** A full case; perspectives differ on timing.
- `c_k21`: **Missing information.** The MRI report is missing, one file is unreadable, one value is
  uncertain, and one perspective did not finish.
- `c_m77`: **Conflicting reports.** An MRI report and a discharge summary describe the same scan
  differently. Both stay visible; nothing is resolved for the reader.

On the upload step, *Prototype controls* lets you force a partial or failed analysis. On the
new-case form, *Demo: show me the urgent-care screen* shows the safety gate.

## Architecture

```
src/
  app/            routes (App Router): (public), (app), cases/[caseId]/...
  components/
    ui/           shadcn/ui primitives
    layout/       shell, banner, disclaimer bar, header
    case/         case frame, status, documents, urgent-care screen, results gate
    medical/      EvidenceChip, TraceDrawer, TimelineView, DisagreementMatrix,
                  PerspectiveCard, ClaimRow, QuestionList, RunProgress, ComparisonView, markers
    report/       SectionRenderer (renders any report section from JSON)
  config/brand.ts the product name, in one place
  domain/types.ts typed domain models (mirror case.v1, specialist_report.v1, ...)
  features/       auth (mock), case data hooks, trace context, settings
  i18n/           typed message catalogue (English; ready for Hindi/Hinglish)
  lib/api/        the AdvisorApi interface and the single switch point
  mocks/          synthetic scenarios, builders and the in-browser mock API
```

### Mock data behind an API-shaped abstraction

Screens never import mock data. They call feature hooks (`src/features/case/hooks.ts`), which call
`api` from `src/lib/api`, which implements the `AdvisorApi` interface. Today `api` is the mock in
`src/mocks/mock-api.ts`. When the FastAPI backend exists, an HTTP implementation of the same
interface replaces it in **one file** (`src/lib/api/index.ts`). See
[`../docs/frontend-data-contract.md`](../docs/frontend-data-contract.md).

### Principles baked in

- Every report sentence carries an item ID and a **Source** chip that opens the traceability drawer.
- Statements are labelled **from your records / AI interpretation / reference evidence**.
- Uncertainty, missing information and disagreement always stay visible, with icon **and** text.
- No majority vote, no winner, no scores, and no red/green "right or wrong" colouring.
- The safety gate runs before any case or analysis exists.
- A persistent prototype banner and safety disclaimer appear on every screen.
- Mobile-first, keyboard-accessible, reduced-motion aware, with print styles for the report.

## Naming

The product name lives in `src/config/brand.ts`. Change it there.
