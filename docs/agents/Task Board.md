# Task Board: Chief Auto

**Chief Auto: Dealership Simulator** (Godot). Faisal, 2026-10-16: "still almost finished, but I need to fix assets and visuals."

State on 2026-10-16:
- `main` holds only the README and agent docs.
- The game lives in two open, unmerged PRs that overlap heavily: the same 16 cars, the same README and `.gitignore`.
  - **#1** `claude/core-loop-prototype`: about 198 commits. Cars, UI icons, fonts, desk view, Amna/Jeff characters, home scene.
  - **#2** `claude/project-thread-8qrsxv`: about 211 commits, updated 2026-10-16 05:39. Cars, showroom furniture, HDRIs, PBR textures, credits.
- Don't push to either PR branch; another session may still be using #2.

## Open
- [ ] **CA-2 Asset + visuals audit** (`chatgpt`, read-only, can start now from the PR branches):
  - List every asset category (cars 3D/2D, characters, furniture, HDRI/PBR, UI icons, fonts).
  - Flag problems: missing or broken textures, mismatched styles or resolutions across the 16 car sprites, placeholder art, missing credits or licences.
  - Write a ranked fix list in `docs/agents/Visual Audit.md` (PROPOSED). GitHub issue labeled `chatgpt-task`.
- [ ] **CA-3 Asset + visuals fix pass** (`claude-faisallaptop`; can start now; use CA-2 and Faisal's own list). First, play the game windowed on the laptop (showroom, a sale, desk view, home, garage) and screenshot each area. Include the shader-compiler error from CA-1.
  - Fix the top items in Godot, with before/after screenshots per item.
  - Credits only with Faisal's OK.
- [ ] **CA-4 Faisal's visual notes** (Faisal): what looks wrong to you (screens, cars, characters, UI)? Screenshots are welcome.

## Done
- CA-1 Integrate (claude-cloud, 2026-10-16): PR #2 already contained all of PR #1 (#1's head is #2's base), so #2 was merged onto `main` alone, with no conflicts. Godot 4.3 headless import: no script errors. `tests/smoke_test.gd`: **OK**. One shader-compiler error was logged on import (`custom_samplers ... tex_builtin`, shader_compiler.cpp:1283): a shader uses a built-in texture in a custom function. Added to CA-2/CA-3. **Not tested:** playing the game in a window (needs Claude 2 or Faisal).
- CA-0 Locate the project: it is in PRs #1 and #2 (2026-10-16).
