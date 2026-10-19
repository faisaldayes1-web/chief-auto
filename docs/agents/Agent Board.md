# Agent Board: Chief Auto

| Group | Agent | Current task | Files owned | State | Handoff |
|---|---|---|---|---|---|
| Coordination | `claude-cloud` | Repo joins the studio workflow: AGENTS.md, boards, inbox; waiting on CA-0 | `AGENTS.md`, `CLAUDE.md`, `docs/agents/` | Done 2026-10-16 | — |
| Testing | `claude-faisallaptop` | Night-queue playtest: windowed tour, 16 screenshots, findings for Faisal | `docs/playtests/2026-10-16-claude-faisallaptop/` | Done 2026-10-16 | [handoff](Handoffs/2026-10-16%20claude-faisallaptop%20CA%20playtest.md) |
| Code | `claude-faisallaptop` | CA-3 fix pass from issue #9 (hub relay of Faisal, 2026-10-17): 3D screen hitch, toast/panel overlap, Marco framing + Jeff portrait. One PR per fix | `scripts/main.gd`, `scripts/car3d_view.gd`, `scripts/showroom3d.gd`, Jeff portrait asset | PRs #12, #13, #14 open 2026-10-17 | [handoff](Handoffs/2026-10-17%20claude-faisallaptop%20CA-3%20fixes.md) |
| Code | `claude-faisallaptop` | Night queue 2026-10-18 (hub relay): #13 P3 toast follow-ups (#17), A2 visual fixes: shader-compiler error (#19), garage black box (#20), browser width (#21); A4 Windows build + smoke (#18) | `scripts/main.gd`, `scripts/render_quality.gd`, `shaders/world_look.gdshader`, `docs/builds/` | PRs open 2026-10-18 | PR #18 build note |

**Adding a row:** append at the bottom; edit only your own rows.

| Content | `Codex-faisal/T2` | Structured content delivery, reusing b887f77 proposal | `content/t2/cars.json`, `content/t2/people.json`, `content/t2/progression.json`, `tools/validate_t2_cars.py`, `tools/validate_t2_people.py`, `tools/validate_t2_economy.py`, `docs/content/T2 Cars.md`, `docs/content/T2 People.md`, `docs/content/T2 Economy.md`; own board row | CLAIMED; three draft PRs; runtime and #11 excluded | framework #30 / 6245635083 |

| Code | `Codex-faisal` | #30 backup-only save recovery, preserve intentional reset and migration | `scripts/game_state.gd`, `tests/save_recovery_test.gd`, own handoff and board row | CLAIMED 2026-10-18; branch Codex-faisal/30-backup-recovery | issue #30 |

| Code | `Codex-faisal` (Chief Auto PM) | Showroom loading and camera follow-up; explicitly reassigned by Faisal in PM chat 01a15175-073d-7310-9a2a-28a92f32b547 on 2026-10-18. Supersedes prior ownership ONLY for this scope; preserve PR12 and PR31. Lower priority than newer games. | `scripts/main.gd` loading/view lifecycle only, `scripts/car3d_view.gd` camera only, `scripts/showroom3d.gd` loading only; task-specific tests and handoff | GRANTED by Faisal; CLAIMED before implementation; branch Codex-faisal/showroom-camera | PR12 scope reassignment comment; real saves excluded |
