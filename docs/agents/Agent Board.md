# Agent Board: Chief Auto

| Group | Agent | Current task | Files owned | State | Handoff |
|---|---|---|---|---|---|
| Coordination | `claude-cloud` | Repo joins the studio workflow: AGENTS.md, boards, inbox; waiting on CA-0 | `AGENTS.md`, `CLAUDE.md`, `docs/agents/` | Done 2026-10-16 | — |
| Testing | `claude-faisallaptop` | Night-queue playtest: windowed tour, 16 screenshots, findings for Faisal | `docs/playtests/2026-10-16-claude-faisallaptop/` | Done 2026-10-16 | [handoff](Handoffs/2026-10-16%20claude-faisallaptop%20CA%20playtest.md) |
| Code | `claude-faisallaptop` | CA-3 fix pass from issue #9 (hub relay of Faisal, 2026-10-17): 3D screen hitch, toast/panel overlap, Marco framing + Jeff portrait. One PR per fix | `scripts/main.gd`, `scripts/car3d_view.gd`, `scripts/showroom3d.gd`, Jeff portrait asset | PRs #12, #13, #14 open 2026-10-17 | [handoff](Handoffs/2026-10-17%20claude-faisallaptop%20CA-3%20fixes.md) |
| Code | `claude-faisallaptop` | Night queue 2026-10-18 (hub relay): #13 P3 toast follow-ups (#17), A2 visual fixes: shader-compiler error (#19), garage black box (#20), browser width (#21); A4 Windows build + smoke (#18) | `scripts/main.gd`, `scripts/render_quality.gd`, `shaders/world_look.gdshader`, `docs/builds/` | PRs open 2026-10-18 | PR #18 build note |

**Adding a row:** append at the bottom; edit only your own rows.

| Content | `Codex-faisal/T2` | Structured content delivery, reusing b887f77 proposal | `content/t2/cars.json`, `content/t2/people.json`, `content/t2/progression.json`, `tools/validate_t2_cars.py`, `tools/validate_t2_people.py`, `tools/validate_t2_economy.py`, `docs/content/T2 Cars.md`, `docs/content/T2 People.md`, `docs/content/T2 Economy.md`; own board row | CLAIMED; three draft PRs; runtime and #11 excluded | framework #30 / 6245635083 |

Agent: Codex-faisal2. T2 claim: docs/playtests/T2_Morning_20_Minutes.md only; 20-minute morning dealership playtest; branch Codex-faisal2/t2-morning-playtest; 2026-10-18.

Overnight T3 claim 2026-10-18 — Agent: Codex-faisal2. T3 Chief Auto Store Page. Own new `docs/agents/Proposals/T3 Store Page.md` and `docs/agents/Handoffs/2026-10-18 Codex-faisal2 T3 Store Page.md` only; writing PROPOSED; no runtime edits.

Overnight T3 claim 2026-10-18 — Agent: Codex-faisal2. T3 Chief Auto Press Kit. Own new `docs/agents/Proposals/T3 Press Kit.md` and `docs/agents/Handoffs/2026-10-18 Codex-faisal2 T3 Press Kit.md` only; writing PROPOSED; no runtime edits.

Overnight T3 claim 2026-10-18 — Agent: Codex-faisal2. T3 Chief Auto Patch Notes. Own new `docs/agents/Proposals/T3 Patch Notes.md` and `docs/agents/Handoffs/2026-10-18 Codex-faisal2 T3 Patch Notes.md` only; writing PROPOSED; no runtime edits.

Overnight T3 claim 2026-10-18 — Agent: Codex-faisal2. T3 Chief Auto Achievement Descriptions. Own new `docs/agents/Proposals/T3 Achievement Descriptions.md` and `docs/agents/Handoffs/2026-10-18 Codex-faisal2 T3 Achievement Descriptions.md` only; writing PROPOSED; no runtime edits.

Agent: Codex-faisal2. T2 claim: docs/playtests/T2_Accessibility_Settings.md only; proposed accessibility and settings checklist; branch Codex-faisal2/t2-accessibility; 2026-10-18.

Agent: Codex-faisal. Owner-requested framework cutover, 2026-10-20. Claim: `AGENTS.md`, `CLAUDE.md`, NEW `ORY_WORKFLOW.md`, and this own appended board record only. Task: #34. Branch: `agent/Codex-faisal/34-framework-cutover`. No runtime/art/shared gameplay claims or reassignment. Status: documentation migration prepared for review; source execution/merge follows repository policy.

## Codex-faisal integration record, PR 31

Agent: Codex-faisal. Incoming branch records preserved below; no existing owner or current main claim reassigned.

| Code | `Codex-faisal` | #30 backup-only save recovery, preserve intentional reset and migration | `scripts/game_state.gd`, `tests/save_recovery_test.gd`, own handoff and board row | CLAIMED 2026-10-18; branch Codex-faisal/30-backup-recovery | issue #30 |

| Code | `Codex-faisal` (Chief Auto PM) | Showroom loading and camera follow-up; explicitly reassigned by Faisal in PM chat 01a15175-073d-7310-9a2a-28a92f32b547 on 2026-10-18. Supersedes prior ownership ONLY for this scope; preserve PR12 and PR31. Lower priority than newer games. | `scripts/main.gd` loading/view lifecycle only, `scripts/car3d_view.gd` camera only, `scripts/showroom3d.gd` loading only; task-specific tests and handoff | GRANTED by Faisal; CLAIMED before implementation; branch Codex-faisal/showroom-camera | PR12 scope reassignment comment; real saves excluded |

| Visual implementation | `Codex-faisal` Chief Auto PM | Owner approved upgraded mockup in chat 01a15175-073d-7310-9a2a-28a92f32b547 on 2026-10-19; bounded showroom visual follow-up to own PR32 | scripts/showroom3d.gd room materials, lights, reception and plants; own capture fixture/handoff | CLAIMED; owner-authorized extension; other scopes preserved; lower priority | Branch Codex-faisal/showroom-visual-target; preserve PR12/31/32 and saves |

## Codex-faisal integration record, PR 11

Agent: Codex-faisal. Incoming branch records preserved below; no existing owner or current main claim reassigned.

| Review | Codex-faisal | CA-2 light asset and visuals audit (#5); categories, evidence-backed ranked findings and engine handoff | docs/agents/Visual Audit.md; own new handoff/inbox; own board row only | Audit complete 2026-10-16; PR review pending | Handoffs/2026-10-16 Codex-faisal CA-2.md |
| Documentation | Codex-faisal2 | CA-2 / #11, owner-authorized successor | `docs/agents/Visual Audit.md`; successor row only | Reconciliation complete 2026-10-18; owner explicitly authorized this existing PR update via hub | Current main integrated locally; no game edits or owner merge |
