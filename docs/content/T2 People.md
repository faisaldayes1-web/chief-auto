# T2 people: integration handoff

Agent: Codex-faisal/T2. Status: PROPOSED. Part 2; Claude 2 L1 review, L3 integration.

`content/t2/people.json` transcribes PR #15 at b887f77: ten buyers (eight existing keys and stats, two additions), 40 contextual buyer lines, 24 Marco lines and six rivals (four existing names). It complements cars in part 1. No runtime file changed.

Map buyer title/budget/tolerance/likes to BUYER_TYPES. Treat `arrival` as proposed alternative intro copy; preserve current intro if unapproved. Arrival fires when negotiation opens; concern only on the corresponding buyer objection; accept only after completed paperwork; walk after negotiation cancellation. Do not infer credit tier from personality. Source make_buyer uses its own weighted type list: adding dictionary keys alone does not spawn the two new buyers. Claude 2 must explicitly wire approved spawn weights.

Marco IDs are durable event keys; trigger text specifies the intended event, not a callable function. Wire triggers to actual successful state transitions. Tutorial and first-occurrence events fire once per save; others at most once per day. Persist seen markers. Never interrupt signatures or replace required fault disclosure. These lines grant no rewards. Low available cash means cash less than actual monthly obligations plus planned repairs; upgrade eligible uses the existing blocker, not day count. Staff/hot-class/loan lines require the actual associated event.

Rival preferences choose names among eligible listings only. Keep make_listing's once-sampled rival_max, current heat clamp and exceptional overbid chance; do not add preference multipliers. Persist cap and dialogue state across reloads. Opening requires auction participation, outbid requires an actual successful rival bid, stop requires stored cap exhaustion. Never read the player's private cap. New rivals need no new bidding model.

Validation: `python3 tools/validate_t2_people.py` checks IDs, all dialogue contexts, ranges, move/class references, eight retained buyer stat tuples and four rival names against main. Runtime spawn wiring, event dispatch, save cooldown roundtrip and display length checks remain for integration. Source: main 1e727b6; proposal #15 remains untouched.
