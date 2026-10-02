# Design direction

AdvisorAI should feel premium, calm, trustworthy, healthcare-focused, AI-native and patient-first,
and extremely easy to understand. Three directions were explored before building; one was chosen.

## Directions considered

### A. "Quiet Clinic" (chosen)
Warm paper background, deep ink-teal primary, a **serif voice** for headings (Fraunces) over a clean
sans (Geist). Documents are the heroes: report-style "paper" surfaces, generous whitespace, thin
borders and very soft shadows. Colour is used as meaning, not decoration.

- Feels like a thoughtful clinic letter, not a dashboard.
- The serif gives warmth and authority without looking clinical or cold.
- Easy to keep calm when showing difficult information (uncertainty, disagreement, gaps).

### B. "Cool Slate"
Blue-grey surfaces, a bright blue accent, all-sans typography, card-grid dashboards.

- Familiar and efficient, but it reads as a generic SaaS or analytics product.
- Blue/white is the default "health app" look, which makes the product feel interchangeable.

### C. "Soft Botanical"
Sage greens, rounded blobs, friendly illustrations.

- Approachable, but risks feeling like wellness or lifestyle rather than medical records.
- Green leans toward "correct/safe", which clashes with the rule that nothing reads as right or wrong.

## Why A

It best supports the product's core promises: calm tone, document-first trust, and a visual language
that can show **uncertainty, missing information and disagreement** prominently without alarm.

## Semantic colour system

Colour never carries meaning alone; every marker pairs an icon with text. None of the clinical
hues is red or green, so nothing is read as "right" or "wrong".

| Meaning | Hue | Shown as |
| --- | --- | --- |
| From your records (patient fact) | Slate blue | Left rule + "From your records" tag |
| AI interpretation | Violet | Left rule + "AI interpretation" tag |
| Reference evidence | Teal-green | Left rule + "Reference evidence" tag |
| Uncertain | Amber | Tinted callout + "Uncertain" marker |
| Missing information | Grey-blue, **dashed edge** | Dashed callout + "Missing information" marker |
| Perspectives differ | Plum | Tinted callout + "Perspectives differ" marker |
| Emergency (urgent-care screen only) | Red | Only on the safety-gate screen |

## Principles

- No gradients, no glass, no decorative motion. Motion respects `prefers-reduced-motion`.
- Large type, plain language, short paragraphs; no walls of text.
- A persistent prototype banner and safety disclaimer on every screen.
- Mobile-first, 44px touch targets, visible focus, semantic landmarks and labelled controls.
- The report is print-friendly (chips hide, item IDs print in brackets for traceability).
