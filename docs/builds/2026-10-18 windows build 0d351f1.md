# Windows build, 2026-10-18 (claude-faisallaptop)

A4 from the hub's night queue: export the Windows build and smoke-run it. The build stays on the laptop; it is not uploaded or published (AGENTS.md rule 5).

| | |
|---|---|
| Commit | `main` 0d351f1 (after #10, #13, #14) |
| Preset | `Windows Desktop` (`export_presets.cfg` preset.1): release, x86_64, PCK embedded, S3TC/BPTC |
| Engine / templates | Godot 4.3-stable (`C:\Users\faisa\Tools\Godot_4.3`), export templates `4.3.stable` |
| Command | `Godot_v4.3-stable_win64_console.exe --headless --path . --export-release "Windows Desktop" <out>\ChiefAuto.exe` |
| Path | `C:\Users\faisa\Projects\chief-auto-builds\windows-0d351f1\ChiefAuto.exe` |
| Size | 227,154,672 bytes (one file, PCK embedded) |
| SHA-256 | `13658935a09d2e317b6feef149666a7daa4c63ed0300f97686eacdd6e83f37cc` |
| Export log | 0 script errors; only the known `shader_compiler.cpp:1283` custom_samplers error |

## Smoke run (laptop: RTX 5080 Laptop GPU, Vulkan Forward+, 1280x720 window)
1. **Plain launch:** `ChiefAuto.exe --print-fps`. It reaches the title, runs 25 s at a steady 60 FPS (V-Sync) with no errors in the log, and was then stopped.
2. **Scripted tour inside the release exe:** `ChiefAuto.exe --resolution 1280x720 res://tests/_tour_shot.tscn -- <dir>`. It visits all 16 areas (title, home, lot, garage, showroom, Marco, staff, 7 Office PC tabs, flagship lot and showroom) and prints `tour done`, exit 0, with no script errors. Each screen settles at 60 FPS. The worst one-second sample was 6 FPS entering the flagship showroom; the Garage entry dipped to 21 and the Showroom to 35-43. That's with the shader and pipeline caches warm from earlier runs on this laptop. Contact sheet: [2026-10-18-windows-0d351f1-tour.jpg](2026-10-18-windows-0d351f1-tour.jpg).

## Found
- The export ships `tests/` (the tour and probe scenes run from the exe), because both presets use `export_filter="all_resources"` with no exclude for `tests/*`. That's harmless, but it's test code in a player build. Proposal: add `tests/*` to both presets' `exclude_filter`, which needs Faisal's OK since it changes the release.
- `docs/` is no longer imported or packed (`docs/.gdignore` from #10/#13).

## Not tested
- Real mouse and keyboard play, a sale, paperwork, a full day end and save/load in the exe.
- A clean machine without Godot's user-dir caches, other GPUs, and the Web export.
- Code signing: the exe is unsigned, so Windows SmartScreen will warn.
