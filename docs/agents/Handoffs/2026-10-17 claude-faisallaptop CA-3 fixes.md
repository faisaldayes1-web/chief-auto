# Handoff: CA-3 fixes from issue #9, 2026-10-17 (claude-faisallaptop)

Asked by the hub, relaying Faisal ("Continue work on roblox, but also work on all of the other games"). One PR per fix, all off `main`:

| PR | Branch | Fix | Files |
|---|---|---|---|
| #12 | `claude-faisallaptop/ca-3-3d-hitch` | Garage/Showroom 3D hitch: views parked instead of freed, prewarmed behind the title. First visit ~1.1-2.7 s -> ~0.2 s; repeats -> ~0.05 s | `scripts/main.gd` |
| #13 | `claude-faisallaptop/ca-3-toast-overlap` | Toasts stack up from bottom centre (were over titles, and over Marco's head); showroom price cards kept clear of the activity panel | `scripts/main.gd`, `scripts/showroom3d.gd` |
| #14 | `claude-faisallaptop/ca-3-portraits` | Dark band in Jeff's hair painted over in 5 PNGs, using new `tools/retouch_hair_gap.py` | `assets/people/jeff_*.png`, `tools/` |

- **Tests:** `tests/smoke_test.gd` OK on each branch, plus a windowed `tests/_tour_shot.tscn` run on each.
- **Not tested:** mouse-driven play, the web export, other window sizes. #12 and #13 both edit `scripts/main.gd`, but in different functions.
- **Correction:** playtest finding 1 named the wrong screens (it's Garage/Showroom, not Lot/Garage). Fixed in the playtest README.
- **Left for Faisal:** whether the flagship showroom should look different. A real re-render of Jeff needs the Rocketbox library. Jeff's hair has grey streaks on the left. The Lot's ~0.2 s stall per visit.
- **Spend:** none (no Meshy/PixelLab). Nothing installed.
