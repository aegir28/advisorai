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

Sign in with **Continue with Google** (simulated: it opens a fake account chooser), then confirm the
consent step once.

## Experience

The product is designed so the complexity lives in the system, not the interface. A patient sees a
few calm screens; the detail is there when they choose to open it.

**Main navigation (three places):** Home · Cases · Profile
(a top bar on desktop, a bottom bar on mobile).

**Inside a case (five places):** Overview · Analysis · Report · Questions · Second opinion.

| Screen | Route |
| --- | --- |
| Landing | `/` |
| Sign in / Create your space (Google, consent) | `/login`, `/signup`, `/welcome` |
| Home | `/home` |
| All cases | `/cases` |
| New case: intent → what your doctor said → urgent-symptom check | `/cases/new` |
| Add reports | `/cases/[caseId]/upload` |
| Overview (short summary, one primary action) | `/cases/[caseId]` |
| Analysis: calm 5-stage progress, then a hub | `/cases/[caseId]/analysis` |
| ... timeline, specialist perspectives, supporting evidence, where information differs, how we pulled it together | `/cases/[caseId]/analysis/{timeline,perspectives,evidence,differences,summary}` |
| Report (8 groups that expand; 19 sections underneath) | `/cases/[caseId]/report` |
| Questions (current doctor / second-opinion doctor, trackable) | `/cases/[caseId]/questions` |
| Second opinion: upload → we're reviewing it → your comparison | `/cases/[caseId]/second-opinion` |
| Profile (account, reading comfort, prototype data) | `/profile` |

Every case screen can open the traceability drawer through a deep link: `?evidence=<itemId>`.
For example `/cases/c_9f2/report?evidence=syn_8`.

## Demo cases (all fictional)

- `c_9f2`: **Heart treatment.** A full case; perspectives differ on timing.
- `c_k21`: **Knee pain (missing information).** The MRI report is missing, one file is unreadable,
  one value is uncertain, and one perspective did not finish.
- `c_m77`: **Head scan reports (conflicting reports).** An MRI report and a discharge summary
  describe the same scan differently. Both stay visible; nothing is resolved for the reader.

On the Add reports step, the *sample case* panel lets you pick a case and force a partial or failed
analysis. In *new case*, the last step has a *Demo: show me the urgent-care screen* button.

## Architecture

```
src/
  app/            routes (App Router): (public), (app), cases/[caseId]/..., welcome
  components/
    ui/           shadcn/ui primitives
    layout/       app shell, banner, disclaimer bar, page headings
    case/         case frame (title + 5 tabs), case row, documents, urgent-care screen, results gate
    medical/      EvidenceChip, TraceDrawer, TimelineView, DisagreementMatrix,
                  PerspectiveCard, ClaimRow, QuestionList, RunProgress, ComparisonView, markers
    report/       SectionRenderer (any section from JSON) and ReportView (the 8 patient groups)
  config/brand.ts the product name, in one place
  domain/types.ts typed domain models (mirror case.v1, specialist_report.v1, ...)
  features/       auth (mock Google + consent), case data hooks, trace context, settings
  i18n/           typed message catalogue (English; ready for Hindi/Hinglish)
  lib/api/        the AdvisorApi interface and the single switch point
  lib/analysis-groups.ts  maps the 14 internal steps to 5 patient-facing stages
  mocks/          synthetic scenarios, builders and the in-browser mock API
```

### What changed in the patient experience, and what did not

The **experience** is simple; the **architecture** is untouched. The internal 14-step workflow, the
specialist agents, verification, cross-review and traceability all still exist in the data. The UI
only decides how much of it to show:

- The report keeps all 19 blueprint sections in its JSON. `ReportView` groups them into eight
  patient-friendly sections, and `SectionRenderer` still renders each one.
- `RunProgress` shows five stages (via `groupRun`) instead of the internal steps.
- The traceability drawer shows document, page, original text, related finding and verification
  status first, with the complete trail one click away.

### Mock data behind an API-shaped abstraction

Screens never import mock data. They call feature hooks (`src/features/case/hooks.ts`), which call
`api` from `src/lib/api`, which implements the `AdvisorApi` interface. Today `api` is the mock in
`src/mocks/mock-api.ts`. When the FastAPI backend exists, an HTTP implementation of the same
interface replaces it in **one file** (`src/lib/api/index.ts`). See
[`../docs/frontend-data-contract.md`](../docs/frontend-data-contract.md).

### Principles baked in

- One primary action per screen; details only when asked for.
- Every report sentence carries an item ID and a **Source** chip that opens the traceability drawer.
- Statements are labelled **from your records / AI interpretation / reference evidence**.
- Uncertainty, missing information and disagreement always stay visible, with icon **and** text.
- No majority vote, no winner, no scores, and no red/green "right or wrong" colouring.
- The urgent-symptom check runs before any case or analysis exists.
- A persistent prototype banner and safety disclaimer (a bottom bar on desktop; the banner plus a
  page footer on mobile).
- Mobile-first, keyboard-accessible, reduced-motion aware, with print styles for the report.

## Naming

The product name lives in `src/config/brand.ts`. Change it there.
