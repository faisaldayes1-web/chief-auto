PROPOSED — LOCAL ONLY. Agent: Codex-faisal2. 2026-10-18. No remote push, public issue comment, PR, store submission or release. Faisal must approve pushing to this public repository.

Source snapshot: chief-auto main 0d351f1d1e5d62c0ebc97e45dce049b47e9ef8f4. Source issue #9.

# Chief Auto — candidate patch notes

Version/date: UNASSIGNED. PROPOSED local notes for merged visual/layout fixes, not a release announcement.

## Player-facing draft

- Notifications now stack in a dedicated area to reduce overlap with screen titles and controls.
- Adjusted showroom layout so the activity panel leaves vehicle price information clear.
- Notifications no longer obscure Marco's head in the advisor view.
- Retouched the dark band in Jeff's hair across the affected portrait variants.

## Internal provenance

Merged #13 supplies toast/layout changes (c1cf2d8, f619153); merged #14 supplies the portrait retouch (a389ab1 and subsequent integration). Current main also includes the windowed playtest evidence through #10; that is evidence, not another user-facing mechanic. The handoff explicitly corrects the old “Marco framing” diagnosis: overlapping notifications caused the apparent crop, so do not advertise a new camera or model re-render.

Exclude #12's proposed persistent/prewarmed 3D views from these notes: the first-visit hitch claim was not independently reproduced in the warm-cache review and its VRAM cost is held for Faisal. Do not promise faster loading, reduced VRAM, a redesigned flagship showroom or every visual issue fixed.

Owner-reported smoke/tour results are historical. Real mouse-driven start-to-sale/paperwork/day-end, candidate exports, web behavior and broader window/device acceptance remain separate. Known shader-compiler and synchronization messages need owner disposition, not an invented “all errors fixed” bullet. Assign a release version only after the chosen build and full change list are approved. No tag, push, export or publication here.
