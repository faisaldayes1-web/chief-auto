# CA-2 Visual Audit — PROPOSED

Agent: Codex-faisal
Task: CA-2 / issue #5 · 2026-10-16 · LIGHT static audit

Recommendations are PROPOSED for Faisal. No game assets, scripts, engine settings or dependencies changed. No engine/device tests run by Codex-faisal. Paid generation: none; credits spent: 0.

## Evidence baseline and integration

Audited game content on main `1e727b663321f9818dd1c8b9299d514408a4dd08`, through claimed branch `Codex-faisal/ca-2-visual-audit` at `6a7ec1907427bdcfb497b84a02b7a270b68c842a`. Pulled branch and checked live GitHub records and Agent Board before editing; CA-2 is owned by Codex-faisal. Other agents' rows and files remain untouched.

Live [PR #1](https://github.com/faisaldayes1-web/chief-auto/pull/1) and [PR #2](https://github.com/faisaldayes1-web/chief-auto/pull/2) are both closed/merged. Git ancestry confirms #1 head `227d45edf3465adc90da3015021d950ae823a5b6` is an ancestor of #2 head `f9357f57f30aa5434f6da96a200b1865d620fc9e`. Their API base SHA is `338651e134ef2e49c225b37c418026f18c46f83d`; do not confuse ancestry with the PR base field. Main includes the integrated game. The Task Board introduction describing two open, unmerged PRs is stale.

Comparing those exact heads: assets have 211 additions, 61 modifications, no deletions. #2 adds `assets/cars3d_hd/` (absent at #1), baked hall resources, and changes car renders, credits and world renders. No differences in `assets/cc0/`, `people/`, `deskview/`, `home/`, `icons/` or `fonts/`. This is a cumulative evolution, not two competing asset sets requiring a merge. No merge performed.

[Claude 2's PR #10](https://github.com/faisaldayes1-web/chief-auto/pull/10) remains open at `93bba98f47222c7b6becc04b2897ef4bc5d2c7de`. Its [report and 16 screenshots](https://github.com/faisaldayes1-web/chief-auto/blob/93bba98f47222c7b6becc04b2897ef4bc5d2c7de/docs/playtests/2026-10-16-claude-faisallaptop/README.md) are attributed evidence from claude-faisallaptop, not a Codex test pass. That run used main `1e727b6`, Godot 4.3, a 1280×720 scripted windowed tour on an RTX 5080 laptop with other engines running. It bypassed real input. The reported smoke pass, 60 FPS after settling, first-load freezes and import errors have not been reproduced here.

## Inventory and static results

Paths below are repository-relative and refer to the baseline above. Counts exclude `.import` sidecars unless stated. Source reads, image header/decode checks and binary glTF JSON inspection were used; no renderer was launched.

| Category | Exact evidence | Finding / boundary |
|---|---|---|
| Car catalogue | `scripts/game_state.gd:22–40` | **17**, not the older task's 16. All 17 have a standard GLB and side/quarter detail+paint maps. |
| Car 3D | `assets/cars3d/*.glb` (17), `assets/cars3d_hd/*.glb` (13); `scripts/car3d_view.gd:183–189` | Desktop selects HD when present, otherwise standard. Chevro Tahoma, Dodgy Charjer, Jeap Wrangle and Teslo Model 3 have no HD variant. This is supported fallback, not a broken reference; compare their detail with the other 13 in CA-3. |
| Car 2D | `assets/cars/<slug>_{detail,paint,q_detail,q_paint}.png` | All 17 side pairs are 600×240; all 17 quarter pairs are 1280×720. All 34 detail/paint pairs match dimensions. No per-car canvas resolution outlier found. The directory also holds 204 lot PNGs (272 total including 68 main maps). Lighting, tint and silhouettes still need in-engine comparison. |
| Amna / Jeff | `assets/people/amna_*`, `jeff_*` | Each has body, portrait and angry/happy/neutral face maps. Bodies 324×600 / 301×600; portraits both 480×600; faces all 256×256. Cropped body widths are not evidence of a resolution defect. Source portraits inspected; Jeff hair needs closer in-engine inspection per Claude 2. |
| Other characters | `assets/people/` (141 PNGs), `assets/people3d/` (8 GLBs, 24 textures); `tools/people3d.py:1` | Generator identifies Microsoft Rocketbox as source; no dedicated Rocketbox notice was found in tracked Markdown/text licence records. Material existence does not establish correct hair opacity or framing. |
| Desk / home | `assets/deskview/` (14 PNGs + JSON), `assets/home/` (3 PNGs), `assets/world/bg_desk*.jpg`, `bg_apartment*.jpg` | Desk canvases include four 2560×1440 layers and separately cropped props; home props are 387×160, 173×204, 210×188. World folder has 44 2560×1440 images. Different crop sizes are intentional-looking, not automatically inconsistent quality; small home props require zoom checks. PR10 screenshots 02 and 08–14 cover the composed views. |
| Furniture | `assets/cc0/models/{sofa_02,modern_arm_chair_01,modern_coffee_table_01,bar_chair_round_01,modern_ceiling_lamp_01,pachira_aquatica_01,calathea_orbifolia_01}/`; `assets/cc0/CREDITS.md` | Seven glTF models with buffers and textures resolve. Furniture source attribution exists. PR10 05/16 show assembled showroom; no missing furniture texture proven by static checks. |
| HDRI / PBR | `assets/cc0/sky/`, `assets/cc0/textures/`, `assets/cc0/CREDITS.md`; `scripts/car3d_view.gd:13–14` | Two HDRs plus tone-mapped reflection/background JPGs; 12 texture JPGs at 1024² and 3 at 2048². Credits map five material families and two HDRIs to Poly Haven. Different HDR/JPG desktop/web paths need renderer comparison, not blanket resolution normalization. Full bake sources are documented as external to repo. |
| UI icons | `assets/icons/` (33 SVGs + `cash.png`); `assets/icons/bank.svg:1` | Sample SVG uses 48×48 / 24-unit viewBox, white 1.8-width rounded strokes. Raster cash is a style exception to review at actual UI size. No separate icon origin/notice found; confirm original authorship before calling it third-party or unlicensed. |
| Fonts | `scripts/ui.gd:22–25,49–55`; `assets/fonts/` | Barlow Medium and Barlow Condensed Semibold WOFF2, DejaVu Sans fallback TTF; all exist with import sidecars. Barlow OFL notice is present. No separate DejaVu notice found in tracked Markdown/text records; inspect embedded metadata and export packaging before concluding omission. |

Car slugs checked: `bmv_m4`, `chevro_tahoma`, `dodgy_charjer`, `ferrano_488`, `forde_mustank`, `forde_rangler`, `hondo_civix`, `jeap_wrangle`, `lamborgo_aventa`, `mazdo_miota`, `mercedez_g_wagon`, `porsha_911`, `ramm_1500`, `rang_rovah`, `subaro_outbuck`, `teslo_model_3`, `toyoda_camri`.

Static checks: 680 PNG/JPG files decoded without errors; 844 import sidecars had no missing declared source file; 38 GLBs and 7 glTFs had no missing external image/buffer URI; 37 complete literal `res://` references in scripts/scenes/shaders/project file resolved. The literal scan excludes templates and cannot prove dynamic resource loading. Import cache paths under `.godot/` are generated, so their absence in a clean clone is not a broken source. These checks do not validate GPU rendering, material semantics or shader compilation.

## Ranked CA-3 fix list

Priority combines impact and estimated effort. Estimates are relative, not commitments. Each item requires a separate claimed implementation scope; this audit grants no asset replacement or paid generation approval.

| Rank | Finding and evidence | Impact × effort; proposed acceptance |
|---|---|---|
| 1 | Known shader import/compiler error: PR10 report item 10 and Task Board CA-1. `shaders/world_look.gdshader:22–24,31,37–38` passes built-in `TEXTURE` into `world_at(sampler2D...)`, matching the reported custom-sampler error pattern. | High × small/medium. **Candidate cause, not confirmed.** Claude 2 isolate failing shader in Godot, fix only after reproduction; import/smoke logs clean and day/night/bloom before/after captures on desktop and web renderer. |
| 2 | Readability/layout: PR10 04 garage toasts obscure heading; 05/16 showroom activity covers left price tag; 06 Marco head is clipped and toasts overlap status heading. These are visible in supplied screenshot evidence. | Medium × small. Reserve safe UI space, correct portrait framing; capture at 1280×720 plus narrower/wider window with simultaneous toasts. All headings, prices and full intended face visible. |
| 3 | Provenance gaps: `assets/cars/CREDITS.md` explicitly says Ferrano licence NOT yet verified despite blanket CC-BY statement; `tools/people3d.py:1` says Rocketbox MIT without a bundled dedicated notice found; DejaVu and icons need packaging/origin checks. | High release impact × small research, unknown replacement effort. Assemble per-asset source/version/author/licence and changes; get Faisal approval for credit edits. Do not label assets cleared or regenerate them based on this audit. See source limitations below. |
| 4 | First lot/garage entry freezes 1–3 s, reported by Claude 2 (PR10 item 1); causal attribution to shader compilation is unproven and other engines were running. | Medium × medium. Repeat clean first/second entry with profiling and normal input before choosing warmup or asset changes. Record timings, GPU/backend and before/after. |
| 5 | Desktop detail consistency: four standard-only cars above; procedural Dodgy/Teslo/Jeap versus sourced/restyled cars (`assets/cars/CREDITS.md`). Source detail layers show differing trim/wheel complexity; they omit paint by design and are **not final composites**. | Medium × medium/large. Same lighting, paint, distance and camera for all 17 in garage and side/quarter views. Decide target detail with Faisal; do not invent missing textures from transparent paint regions. |
| 6 | Jeff dark hair band (PR10 07) and garage black backdrop (04), reported by Claude 2; source material adjustment code acknowledges placeholder colours (`scripts/car3d_view.gd:389–421`). | Low/medium × medium. Inspect opacity/materials and background composition; distinguish intentional shadow from mesh/alpha defect. Fix only reproducible issue and capture comparison. |
| 7 | Explicit stand-ins: Chevro uses Prado, Toyoda uses Malibu, Subaro uses Volvo; credits describe this. Office bezel is blurry / browser frame widths jump (PR10 item 8). | Low/medium × medium. Faisal decides whether stand-ins need replacement; first improve stable browser framing and legibility. No paid art requested. |
| 8 | Tier showroom similarity, tiny sign spelling, and HUD mismatch in PR10 items 4/5/9 are unresolved. | Low/unconfirmed × small investigation. Verify tiers, inspect sign at native resolution, and run normal saved-game flow. HUD may be tour initialization. Do not file these as confirmed asset defects. |

## Credit and source limitations

Car credits provide 14 named source entries and three procedural models, with modifications described. The Ferrano source URL was attempted live on 2026-10-16 but inaccessible through the web reader; its licence remains **unverified**, not disproven. Other Sketchfab licences were not individually revalidated in this light audit. Poly Haven credit mappings were read from the repository, not independently re-certified.

The [DejaVu upstream licence page](https://dejavu-fonts.github.io/License.html) was accessible and specifies inclusion of the relevant notices. The upstream Rocketbox `/blob/master/LICENSE` attempt returned 404; that path failure does not establish the project's licence. Resolve the correct upstream version/notice in CA-3 before packaging. Repository searches establish a documentation gap, not a legal conclusion. No third-party licence files were changed.

## Validation and engine handoff

Codex-faisal checked ancestry, live PR state, asset inventory, raster decodability, car map dimensions, model external URIs, import source paths and complete literal resources. Contact-sheet inspection covered car quarter detail layers, Amna/Jeff portraits and Claude 2 screenshots 02/04/05/06/07/09; the full set of 16 is linked above, not claimed as individually inspected at native resolution.

**Not run:** Godot launch/import/smoke, gameplay/input, actual sale, paperwork/day-end, device/export tests, performance profiling, paid generation or builds. Claude 2's existing tour also excludes real mouse/keyboard, title-to-intro, sale/paperwork/day-end and Web/Windows exports.

**Next owner: claude-faisallaptop (CA-3).** Reproduce ranks 1–2 first; inspect all 17 cars under controlled lighting; check Amna/Jeff expressions and hair, furniture/PBR/HDR across renderers, desk/home scaling and icons/fonts at actual size; perform a normal sale and full day. Record before/after screenshots and exact engine/backend/device. Coordinator may reconcile stale Task Board prose separately. Faisal retains art, spending and merge decisions.

## Superseding fix ownership — 2026-10-18

Agent: Codex-faisal2. Owner transferred #11 in comment 6245578084. Acknowledged Claude 2 comment 6247965637: ranks 1, 6 and 7 already have implementations in #19–#21. Do not duplicate these fixes.

| Rank | Existing implementation | Remaining boundary |
|---|---|---|
| 1 | #19 at 3e9ccc8e98c1b21cc75610c6f34ff9139a10265f: shader TEXTURE correction | Open PR, not merged; review and renderer evidence remain with Claude 2. |
| 6 | #20 at 62374670591f4d2454aa8a6c71284f2d6112e99d: garage black box | Open PR; Jeff hair is a separate subfinding, with prior CA-3 evidence. Do not call all material questions resolved. |
| 7 | #21 at c65fe95fdf04562dacc7e78473a122336257e83e: Office PC browser width | Open PR; car stand-in/provenance decisions remain separate and unresolved by browser layout. |

The historical instruction to reproduce rank 1 first is superseded: review the existing implementation rather than start competing work. No new shader, garage or browser code is authorized by this audit. Remaining asset/provenance and controlled-composition acceptance stays proposed.

Integrated fetched main 0d351f1d1e5d62c0ebc97e45dce049b47e9ef8f4 locally without textual conflicts. This does not include unmerged #19–#21 and makes no engine pass claim. Local branch codex/t4-ca11 stays private: public repository prevents a private PR/comment update under the current instruction.

Signed: Codex-faisal2.

### Local validation of the reconciled audit

Codex-faisal2: Godot 4.3 headless import exited 0 but reproduced the known custom-sampler shader error at shader_compiler.cpp:1283; therefore import is not clean. After import generated the global-class cache, tests/smoke_test.gd printed `smoke test: OK` (exit 0), with that same shader diagnostic. The first smoke attempt before import failed to resolve PersonArt/CarArt and was interrupted; it is not a game regression verdict. Logs remain private beside the worktree: t4-ca11-import.log and t4-ca11-smoke-after-import.log. No rendering or manual gameplay pass is claimed. This corroborates the existing rank-1 boundary, not a competing fix.

### Push authorization — 2026-10-18

Agent: Codex-faisal2. Faisal, relayed in this chat by the hub: “Yes: Codex-faisal2 may push its PR updates and issue notes to the existing public crowns-of-the-wildwood and chief-auto repos. Normal PR work only; nothing else becomes public.” This supersedes the local-only hold above. Only this existing PR branch and signed issue note are being updated; no release, build upload or new repository.
