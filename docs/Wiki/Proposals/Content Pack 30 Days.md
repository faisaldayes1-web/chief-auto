# Chief Auto — 30-day content pack

Agent: Codex-faisal
Status: PROPOSED; writing deliverable, not installed content or approved balance.
Authority: framework #30 comment 6245614403. Separate from CA-2 PR #11, now owned by Codex-faisal2.

## Baseline and integration contract

Read against main tree 1e727b663321f9818dd1c8b9299d514408a4dd08: scripts/game_state.gd MODELS, BUYER_TYPES, make_car, value, make_listing, monthly_bills, new_game; README; tests/balance_sim.gd. Source has 17 models and eight buyers despite older README counts. Preserve their names/keys and saved IDs. Rows 1–17 retain current model stats; rows 18–40 are new proposed catalogue entries. Ten buyer types means eight retained plus two new, not ten additional types. All prices below are fictional game currency, not real-market pricing.

No new class keys: economy/sport/suv/truck/exotic only. No engine or asset changes in this PR. New models need approved art and CarArt slug mappings before inclusion in random generation; do not silently substitute another model's artwork. Existing saves retain their stored parts/hidden/history values; do not reroll on load.

## Forty-model catalogue

Base is the new-price input to the existing depreciation/value function, NOT an auction bid or expected sale. Resale multiplies depreciation. Profile selects the proposed hidden-fault weighting below. Unlock continues through max_auction_base, dealership cap, membership and source-specific selection; suggested campaign encounters never override those gates.

| ID | Model | Class | Base $ | Resale | Fault profile | Status |
|---|---|---|---:|---:|---|---|
| CA01 | Hondo Civix | economy | 26000 | 1.10 | E | Existing |
| CA02 | Toyoda Camri | economy | 29000 | 1.05 | E | Existing |
| CA03 | Mazdo Miota | sport | 30000 | 1.05 | S | Existing |
| CA04 | Subaro Outbuck | suv | 32000 | 1.00 | U | Existing |
| CA05 | Forde Rangler | truck | 34000 | 1.10 | T | Existing |
| CA06 | Jeap Wrangle | suv | 36000 | 1.15 | U | Existing |
| CA07 | Dodgy Charjer | sport | 38000 | 0.90 | S | Existing |
| CA08 | Teslo Model 3 | economy | 42000 | 0.80 | V | Existing |
| CA09 | Forde Mustank | sport | 48000 | 0.95 | S | Existing |
| CA10 | Ramm 1500 | truck | 48000 | 1.00 | T | Existing |
| CA11 | Chevro Tahoma | suv | 58000 | 1.00 | U | Existing |
| CA12 | BMV M4 | sport | 80000 | 0.85 | S | Existing |
| CA13 | Rang Rovah | suv | 90000 | 0.75 | U | Existing |
| CA14 | Porsha 911 | sport | 125000 | 1.10 | S | Existing |
| CA15 | Mercedez G-Wagon | suv | 150000 | 1.05 | U | Existing |
| CA16 | Ferrano 488 | exotic | 300000 | 0.95 | X | Existing |
| CA17 | Lamborgo Aventa | exotic | 450000 | 0.95 | X | Existing |
| CA18 | Nissun Versa | economy | 19000 | 0.92 | E | Proposed new; art pending |
| CA19 | Hyunda Accentor | economy | 22000 | 0.92 | E | Proposed new; art pending |
| CA20 | Chevro Sparkle | economy | 18000 | 0.88 | E | Proposed new; art pending |
| CA21 | Forde Focused | economy | 24000 | 0.95 | E | Proposed new; art pending |
| CA22 | Volk Wagon Golfer | economy | 28000 | 1.00 | E | Proposed new; art pending |
| CA23 | Toyoda Priosa | economy | 31000 | 1.06 | V | Proposed new; art pending |
| CA24 | Hondo Fitzy | economy | 23000 | 1.08 | E | Proposed new; art pending |
| CA25 | Nissun Leef | economy | 30000 | 0.72 | V | Proposed new; art pending |
| CA26 | Kiyo Soulful | suv | 27000 | 0.94 | U | Proposed new; art pending |
| CA27 | Hyunda Tuscan | suv | 33000 | 0.96 | U | Proposed new; art pending |
| CA28 | Hondo CR-Vee | suv | 35000 | 1.08 | U | Proposed new; art pending |
| CA29 | Toyoda Ravvy | suv | 37000 | 1.10 | U | Proposed new; art pending |
| CA30 | Volk Wagon Tigra | suv | 39000 | 0.94 | U | Proposed new; art pending |
| CA31 | Chevro Colorade | truck | 33000 | 1.02 | T | Proposed new; art pending |
| CA32 | Toyoda Tacomo | truck | 39000 | 1.16 | T | Proposed new; art pending |
| CA33 | Nissun Frontline | truck | 32000 | 1.00 | T | Proposed new; art pending |
| CA34 | Forde F-150ish | truck | 46000 | 1.03 | T | Proposed new; art pending |
| CA35 | Subaro BR-Zed | sport | 32000 | 1.03 | S | Proposed new; art pending |
| CA36 | Nissun Zed | sport | 45000 | 0.98 | S | Proposed new; art pending |
| CA37 | Chevro Camero | sport | 42000 | 0.94 | S | Proposed new; art pending |
| CA38 | Porsha Caymanu | sport | 75000 | 1.05 | S | Proposed new; art pending |
| CA39 | Aston Marten Vantageous | exotic | 180000 | 0.82 | X | Proposed new; art pending |
| CA40 | McLaron 720-ish | exotic | 310000 | 0.88 | X | Proposed new; art pending |

## Hidden-fault tables

Keep the existing number of draws: public 0–2, salvage adds one, dealer/exotic 0–1; flood adds one. Day-one listings retain their existing protection: no hidden faults and no major/flood history. Each draw subtracts 15–35 condition points from one component when revealed; repeated draws accumulate and true condition clamps at zero. Replace only the uniform component pick with the proposed weights, after approval. Do not apply an extra blanket fault chance on top.

| Profile | engine % | transmission % | body % | interior % | tires % | Inspection clue / fictional interpretation |
|---|---:|---:|---:|---:|---:|---|
| E commuter ICE | 25 | 20 | 15 | 15 | 25 | Cold-start stumble; shift hesitation; uneven tire wear |
| S sport | 25 | 30 | 15 | 10 | 20 | Hot shift slip; patched quarter panel; brake vibration |
| U SUV | 20 | 20 | 25 | 20 | 15 | Damp trim; tailgate seam; driveline noise |
| T truck | 20 | 30 | 20 | 10 | 20 | Tow-related shift heat; bed corrosion; loaded braking |
| V electric/hybrid | 35 | 10 | 15 | 25 | 15 | Traction-system warning; charging fault; cabin electrics |
| X exotic | 30 | 25 | 15 | 20 | 10 | Service warning; clutch judder; intermittent cabin controls |

All rows total 100%. EV 'engine' means traction system for writing only; mechanics remain the five existing keys. Do not show combustion-specific engine-smoke art on EV variants without a presentation change. Clues are flavor until inspection reveals the actual stored fault; they must not promise that a clean report guarantees no future botch. A repair botch remains its own existing mechanic and is not rerolled through this table.

| History | Existing value factor when known/true | Writing rule |
|---|---:|---|
| Clean | 1.00 | No claim of perfect mechanical condition |
| Minor accident | .92 | Explain the recorded incident without inventing damage |
| Major accident | .80 | Explicitly disclose report before final agreement |
| Flood | .65 | Never replace disclosure with euphemisms like 'coastal edition' |

## Ten buyer personalities

Budget and tolerance retain current values for the first eight. Proposed new types use only existing move IDs. Each buyer gets four contexts: arrival, concern, accept, walk. Lines must be selected from actual negotiation state; an accept line cannot precede completed paperwork. No personal trait is a guarantee of credit tier or affordability.

### Bargain Hunter (`bargain`)
Budget ×0.95; tolerance 0.7; likes: discount.
- Arrival: “I brought three competing quotes. One is even real.”
- Concern: “Put the full price on one line.”
- Accept: “That discount works. Keep the mystery fees.”
- Walk: “I'll let your spreadsheet think about it.”

### Tewport Local (`local`)
Budget ×1.2; tolerance 1.3; likes: features.
- Arrival: “Will the valet remember this one?”
- Concern: “Show me the cabin, not the keychain.”
- Accept: “That's the one. Please remove the giant bow.”
- Walk: “Nice car. Wrong entrance.”

### First-Time Buyer (`first`)
Budget ×1; tolerance 1; likes: history, extras.
- Arrival: “I have a checklist. My dad has a longer checklist.”
- Concern: “Can you explain that repair in normal words?”
- Accept: “I understand the total. Let's do it.”
- Walk: “I need time to read the report.”

### Car Nerd (`nerd`)
Budget ×1.05; tolerance 0.9; likes: test_drive.
- Arrival: “Cold start first. Small talk second.”
- Concern: “Those readings don't match the description.”
- Accept: “The numbers check out. You kept the receipts.”
- Walk: “I like the car more than your explanation.”

### Safety Parent (`parent`)
Budget ×1; tolerance 1; likes: history, test_drive.
- Arrival: “Three kids. One dog. Nothing sticky, please.”
- Concern: “Show me the inspection and the back seat.”
- Accept: “Everything fits, including the budget.”
- Walk: “We'll keep looking. The dog has concerns.”

### Influencer (`influencer`)
Budget ×1.15; tolerance 0.8; likes: features, extras.
- Arrival: “Can we move that cone? It's ruining my reveal.”
- Concern: “Is that mark visible in daylight?”
- Accept: “Deal. You may wave in the background.”
- Walk: “The car needs a better angle. So does the price.”

### Lowballer (`lowballer`)
Budget ×0.85; tolerance 0.55; likes: discount.
- Arrival: “Half price, cash today. I rehearsed that.”
- Concern: “What's the lowest honest total?”
- Accept: “You held your line. I respect that.”
- Walk: “I'll be back with the same offer and sunglasses.”

### Cash Whale (`whale`)
Budget ×1.25; tolerance 1.5; likes: features, test_drive.
- Arrival: “Something quick. My accountant is parked outside.”
- Concern: “I still want the service history.”
- Accept: “Wrap up the paperwork before my accountant comes in.”
- Walk: “Expensive isn't the same as interesting.”

### Daily Commuter (`commuter`)
Budget ×1.02; tolerance 1.15; likes: history, test_drive.
- Arrival: “Forty miles each way. Make tomorrow boring.”
- Concern: “What needs repairing before Monday?”
- Accept: “Reliable and within budget. That's exciting enough.”
- Walk: “I need transport, not a weekend project.”

### Working Contractor (`contractor`)
Budget ×1.08; tolerance 1.05; likes: history, features.
- Arrival: “The truck works before I do.”
- Concern: “Show me the wear, then show me the bill.”
- Accept: “Room for the tools. Room in the budget. Sold.”
- Walk: “I can't send an invoice from the garage.”

## Marco: triggered lines

One line per event; do not interrupt active signatures or overwrite a fault disclosure. Repeat cooldown: one occurrence per day per line, except tutorial steps which fire once per save. These are copy triggers, not new reward events.

| Trigger | Line |
|---|---|
| First visit | “Welcome to Chief Auto. The sign is big. Our cash reserve is not.” |
| Before first bid | “Your maximum bid includes the repair bill you haven't met yet.” |
| First inspection | “A report costs money. A surprise costs more.” |
| Cheap mechanic selected | “Ray is family. That is a relationship, not a warranty.” |
| First botch | “Put it back on the inspection list. Optimism is not a repair.” |
| First honest sale | “A fair deal. Terrible gossip, excellent business.” |
| First walkout | “They kept their money. You kept your car. We can survive this.” |
| All slots full | “Parking spaces are inventory limits with painted lines.” |
| Hot class | “Today's hot class is on the board. Tomorrow it may just be yesterday's stock.” |
| Bidding beyond planned margin | “Winning the auction and making money are separate hobbies.” |
| History disclosed | “Tell them before the signature. Surprises belong at birthdays.” |
| First paperwork error caught | “That zero was ambitious. Fix it.” |
| Day-three check-in | “Count what you paid, what you repaired, and what you actually received.” |
| Level-three perk | “More sourcing options. Still the same bank account.” |
| Low available cash | “Leave enough for repairs and bills. The desk can stay ugly another week.” |
| First review complaint | “Read the complaint twice. Write the reply once.” |
| Staff hired | “Delegate the sale. Keep responsibility for the promise.” |
| Before monthly bill | “Rent does not care how impressive the showroom looks.” |
| No-sale day | “No sale today. Let's find out whether it was the car, the price, or the pitch.” |
| Upgrade eligible | “You qualify for the building. Check that you can also afford the morning after.” |
| Day-thirty close | “One month down. Count the cash, the stock, and the obligations. Then celebrate.” |
| Loan drawn | “Borrowed cash is not profit. Put that on the whiteboard.” |
| Repaired car returned | “The job is finished. Verify the result before pricing the car.” |
| Sale below cost | “We recovered cash. We did not invent a profit.” |

## AutoBidz rival dealers

Keep the four existing RIVALS names. Two proposed additions bring flavor variety to six. This table proposes bounded flavor/selection preferences, not omniscient bidding. Sample and save a rival's cap once per listing using the current make_listing formula; no reacting to the player's private maximum, no extra heat multiplier, no reroll after reload. A 'stop' line only appears once the stored cap is reached. Preferences affect which eligible listing gets a name, not spawn gates.

| Dealer | Preferred class | Opening / outbid / stop |
|---|---|---|
| Tustin Tony (existing) | economy, truck | “I know a buyer for that.” / “Make it one more increment.” / “My buyer suddenly got less enthusiastic.” |
| Irvine Imports (existing) | sport, exotic | “Service records first.” / “We can carry that inventory.” / “That margin doesn't survive transport.” |
| Costa Mesa Motors (existing) | economy, suv | “Something sensible for once.” / “Still within our number.” / “Enjoy the paperwork.” |
| Huntington Hank (existing) | truck, suv | “Could fit a board in that.” / “One more. Then lunch.” / “Lunch wins.” |
| Mesa Fleet Desk (new) | economy, truck | “Utility, mileage, price.” / “Within allocation.” / “Allocation exhausted.” |
| PCH Collector (new) | sport, exotic | “Interesting specification.” / “There's still room in the collection.” / “Not at museum prices.” |

## Days 1–30: proposed economy targets

These are a test scenario and tuning targets, not simulated results or guaranteed player earnings. Preserve source start cash $15,000; Corner Lot 3 slots, $2,500 monthly base rent; Street Showroom $75,000 at level 3 plus its $4,500 rent reserve; Flagship $350,000 at level 8 plus $25,000 rent reserve. Day count does not unlock buildings. Keep salary, ads, loan interest and liabilities from monthly_bills; the schedule below excludes discretionary upgrades and financing/add-ons to expose the base car loop.

Model: a rolling stock of two cars bought at $5,000 each after the initial setup; average realised sale $6,500, repair/detail/report $500, hence $1,000 gross contribution per completed turn. Starting post-stock cash $5,000. Each sale replaces one car at the same $5,000 and increases cash $1,000. This isolates cash conservation; it is not a claim every generated car sells at that price. An unsold car stays inventory and does not count as earnings. Daily reserve accrual is a planning envelope of $200, not an extra game debit; total $6,000 covers a hypothetical bill, and must be replaced with the actual monthly_bills total. If actual obligations exceed it, reduce purchasing immediately.

| Day | Lesson / content encounter | Target sales that day | Cumulative sales | Model cash before actual bills | Accrued reserve | Spendable after reserve |
|---|---|---:|---:|---:|---:|---:|
| 1 | Protected first listing and tutorial | 1 | 1 | $6000 | $200 | $5800 |
| 2 | Inspect a used commuter | 1 | 2 | $7000 | $400 | $6600 |
| 3 | Price versus total cost | 1 | 3 | $8000 | $600 | $7400 |
| 4 | First bargain buyer | 0 | 3 | $8000 | $800 | $7200 |
| 5 | Parent and history report | 1 | 4 | $9000 | $1000 | $8000 |
| 6 | First rival stop line | 1 | 5 | $10000 | $1200 | $8800 |
| 7 | Review stock age | 0 | 5 | $10000 | $1400 | $8600 |
| 8 | Commuter introduction | 1 | 6 | $11000 | $1600 | $9400 |
| 9 | Mechanic quality comparison | 1 | 7 | $12000 | $1800 | $10200 |
| 10 | Ten-day ledger review | 1 | 8 | $13000 | $2000 | $11000 |
| 11 | Contractor and truck fit | 1 | 9 | $14000 | $2200 | $11800 |
| 12 | Walk away from an auction | 1 | 10 | $15000 | $2400 | $12600 |
| 13 | Disclose a known fault | 1 | 11 | $16000 | $2600 | $13400 |
| 14 | One deliberate no-buy day | 0 | 11 | $16000 | $2800 | $13200 |
| 15 | Half-month bill preview | 1 | 12 | $17000 | $3000 | $14000 |
| 16 | Compare buyer priorities | 1 | 13 | $18000 | $3200 | $14800 |
| 17 | Refresh a stale asking price | 1 | 14 | $19000 | $3400 | $15600 |
| 18 | Repair-versus-sell decision | 1 | 15 | $20000 | $3600 | $16400 |
| 19 | Staff sale attribution | 1 | 16 | $21000 | $3800 | $17200 |
| 20 | Twenty-day margin review | 1 | 17 | $22000 | $4000 | $18000 |
| 21 | Hot-class demand lesson | 0 | 17 | $22000 | $4200 | $17800 |
| 22 | No impulsive desk purchase | 1 | 18 | $23000 | $4400 | $18600 |
| 23 | Inspect a salvage candidate, optional | 1 | 19 | $24000 | $4600 | $19400 |
| 24 | Reconcile true condition | 1 | 20 | $25000 | $4800 | $20200 |
| 25 | Recheck monthly obligations | 1 | 21 | $26000 | $5000 | $21000 |
| 26 | Clear slow stock honestly | 1 | 22 | $27000 | $5200 | $21800 |
| 27 | No-credit cash-flow check | 1 | 23 | $28000 | $5400 | $22600 |
| 28 | Prepare first monthly settlement | 0 | 23 | $28000 | $5600 | $22400 |
| 29 | Reserve actual bills | 1 | 24 | $29000 | $5800 | $23200 |
| 30 | Month close; choose next goal | 1 | 25 | $30000 | $6000 | $24000 |

At day 30 the model has $30,000 cash before bills, $10,000 inventory at cost, and $25,000 cumulative trading contribution. If actual bills are exactly $6,000, closing cash is $24,000 and net assets $34,000: initial $15,000 + $25,000 contribution − $6,000 bills. No showroom upgrade is implied. Do not subtract the planning reserve again after paying the bill.

Stress cases: ten sales instead of 25 gives $15,000 cash before bills and $9,000 after the illustrative bill; five extra $1,000 repair overruns reduces that to $4,000. No sales leaves $5,000 liquid against the illustrative $6,000 bill, so use the existing loan/recovery mechanics and record debt, not free money. Reject a tune that requires misleading buyers or speculative finance income to survive. Proposed milestone targets: tutorial in days 1–3; reliable stock turn by day 10; full bill preview by day 20; solvent month end before optional expansion. Actual levels follow existing XP, not a daily scripted grant.

## Acceptance and handoff

Review before implementation: approve the 23 new model names/art requirements, two buyer types, fault weighting, dialogue and economy targets. Implement only approved rows under a separate engine claim. Preserve historic buyer keys and 17 existing model stats; define migration for any later rename. Register new slugs before enabling catalogue rows. Test day-one hidden-fault exclusion, all six profile sums, deterministic reload, repeated faults clamped at zero, EV presentation, disclosure/repair botch interactions, buyer move IDs and save roundtrip. Run the existing balance_sim for 30 and 120 days across fixed seeds in an isolated user-data directory: it calls reset_save, so never run it against the owner's save. Report insolvency rate, profit excluding loans, inventory-at-cost, stock age and actual monthly bills; compare source baseline versus proposed settings. Run smoke/import and a real buy→inspect→repair→sell→paperwork→month-close playthrough after integration.

Writing validation by Codex-faisal: 40 unique model rows (17 retained + 23 proposed), ten unique buyer IDs, six 100% profiles, 30 consecutive day rows and cash reconciliation checked. No Godot, gameplay, exported build, market-price research or art generation was performed. Meshy 0; PixelLab 0. Independent exact-head review required; PROPOSED until approved.
