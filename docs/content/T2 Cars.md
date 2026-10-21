# T2 cars: integration handoff

Agent: Codex-faisal/T2. Status: PROPOSED, fictional game balance.

Reuses the authorized lane's [PR #15](https://github.com/faisaldayes1-web/chief-auto/pull/15) proposal at b887f77; does not replace or edit that session's files. Source runtime: main 1e727b6. This is part 1 of three structured deliveries for Claude 2 L3, with review requested from Claude 2 L1.

`content/t2/cars.json` contains 40 models, including all 17 current MODELS tuples in their original order, plus six weighted component tables. CA IDs identify catalogue entries, never generated vehicle/save IDs. `base` is the existing depreciation input, not an auction bid. Existing saves keep their stored model, parts, history and hidden faults; never reroll on load.

The file is not auto-loaded. After design approval, adapt each row to `[model, cls, base, resale]` in MODELS and associate its fault profile by catalogue ID. Keep source selection gates in make_car/max_auction_base. New rows have art_ready=false; approve assets and explicit CarArt mappings before enabling them. No substituted artwork is authorized. Engine implementation remains with Claude 2.

For each existing fault draw, sample an integer 0–99 over cumulative weights in PARTS order. Preserve source draw counts, additive flood draw, additive repeated component damage, 15–35 damage and zero clamp. Day-one protection overrides all draws. Botches remain independent. Clues are flavor, not proof of a revealed defect. V-profile engine means traction system; electric/hybrid presentation needs a separate check. Disclose known history using existing factors: Clean 1, Minor accident .92, Major accident .80, Flood .65.

Validation: `python3 tools/validate_t2_cars.py` checks counts, IDs, references, component probability totals, ranges and every retained tuple against source. No runtime behavior changes. Runtime integration still needs save roundtrip, day-one protection, inspection/botch and EV presentation tests. New art and design approval remain outstanding.
