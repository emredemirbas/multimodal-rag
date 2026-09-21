# Sprint 0 UX wireframes

These low-fidelity wireframes define the Sprint 1 interaction contract. Every
screen includes keyboard focus, text status, and non-color-only feedback.

## Projects

```text
┌──────────────────────────────────────────────────────────────┐
│ Tutorial Workspace                         [New project]     │
├──────────────────────────────────────────────────────────────┤
│ Projects                                                     │
│ ┌ FastAPI fundamentals ───────────────────────────── Ready ┐ │
│ │ 1 source · last opened today                         [→] │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ Empty: Create a private project to add your first tutorial.  │
│ Error: Projects could not load. [Retry]                      │
└──────────────────────────────────────────────────────────────┘
```

## Add an authorized source

```text
┌──────────────────────────────────────────────────────────────┐
│ FastAPI fundamentals / Sources                              │
├──────────────────────────────────────────────────────────────┤
│ Upload transcript                                            │
│ [ Choose SRT or VTT ]                                        │
│                                                              │
│ I confirm that I own or am authorized to process this input. │
│ [ ] Confirmation required                                    │
│                                              [Process source] │
│                                                              │
│ Processing: Normalizing transcript… 2 of 4 stages            │
│ Partial error: Frame evidence unavailable; transcript ready. │
│                                              [Retry frames]   │
└──────────────────────────────────────────────────────────────┘
```

## Ask with evidence

```text
┌───────────────────────────────┬──────────────────────────────┐
│ Chat                          │ Evidence                     │
├───────────────────────────────┼──────────────────────────────┤
│ Which endpoint checks health? │ tutorial.vtt                 │
│                               │ 00:05–00:09                   │
│ The tutorial uses GET         │ “The GET health endpoint…”   │
│ /health. [1]                  │                              │
│                               │ Frame · 00:06                 │
│ [ Ask a question… ]   [Send]  │ GET /health 200 OK            │
├───────────────────────────────┴──────────────────────────────┤
│ Unsupported: “This tutorial does not contain evidence for   │
│ that question.”                                              │
└──────────────────────────────────────────────────────────────┘
```

## Required states

- Loading: descriptive status announced through an ARIA live region.
- Empty: explains the next valid action.
- Partial failure: preserves usable transcript results and identifies retry scope.
- Error: safe message plus stable error code; never a raw provider exception.
- Success: source status and citations remain available without hover or imagery.
