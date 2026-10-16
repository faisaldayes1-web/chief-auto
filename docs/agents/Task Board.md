# Task Board: Chief Auto

**Chief Auto: Dealership Simulator** (Godot). Faisal, 2026-10-16: "still almost finished, but I need to fix assets and visuals."

State on 2026-10-16:
- `main` holds only the README and agent docs.
- The game lives in two open, unmerged PRs that overlap heavily: the same 16 cars, the same README and `.gitignore`.
  - **#1** `claude/core-loop-prototype`: about 198 commits. Cars, UI icons, fonts, desk view, Amna/Jeff characters, home scene.
  - **#2** `claude/project-thread-8qrsxv`: about 211 commits, updated 2026-10-16 05:39. Cars, showroom furniture, HDRIs, PBR textures, credits.
- Don't push to either PR branch; another session may still be using #2.

## Open
- [ ] **CA-1 Integrate the game onto one branch** (`claude-faisallaptop`):
  - Make a new branch `claude-faisallaptop/ca-1-int` from `main`. Merge #2, then #1, with merge commits.
  - Resolve overlaps, keeping the newer or better asset and listing every choice.
  - Godot: a headless import with no script errors, then play the core loop (dealership, sell a car, the desk view) and take screenshots.
  - Open one PR to `main` for Faisal. Archive anything replaced, never delete it.
- [ ] **CA-2 Asset + visuals audit** (`chatgpt`, read-only, can start now from the PR branches):
  - List every asset category (cars 3D/2D, characters, furniture, HDRI/PBR, UI icons, fonts).
  - Flag problems: missing or broken textures, mismatched styles or resolutions across the 16 car sprites, placeholder art, missing credits or licences.
  - Write a ranked fix list in `docs/agents/Visual Audit.md` (PROPOSED). GitHub issue labeled `chatgpt-task`.
- [ ] **CA-3 Asset + visuals fix pass** (`claude-faisallaptop`, after CA-1, using CA-2 and Faisal's own list):
  - Fix the top items in Godot, with before/after screenshots per item.
  - Credits only with Faisal's OK.
- [ ] **CA-4 Faisal's visual notes** (Faisal): what looks wrong to you (screens, cars, characters, UI)? Screenshots are welcome.

## Done
- CA-0 Locate the project: it is in PRs #1 and #2 (2026-10-16).
