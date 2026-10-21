PROPOSED — FOR PR REVIEW. Agent: Codex-faisal2. 2026-10-18. Faisal authorized normal release-copy PR updates and source-issue notes in this existing repository via the hub relay in this chat. This authorization does not publish a storefront, build, press kit or game release.

Source snapshot: chief-auto main 0d351f1d1e5d62c0ebc97e45dce049b47e9ef8f4. Source issue #9.

# Chief Auto — achievement description candidates

Correction to the initial inventory: scripts/steam_bridge.gd already defines thirteen achievement API IDs, local persistence and conditional Steam delivery. Source presence does not establish actual Steam-client acceptance. The existing catalog is listed below; the original eight supplemental concepts remain separately PROPOSED and do not replace it. These eight entries are PROPOSED editorial concepts tied to existing core-loop actions, not stable API IDs, implemented unlocks, approved new progression or a promise of platform achievements. Labels below are local draft references only. No numeric balance change or reward is proposed.

## Existing catalog — proposed wording, stable IDs retained

| Existing ID | Existing name | Source-aligned candidate description |
|---|---|---|
| FIRST_CAR | First Wheels | Get your first car for the dealership. |
| FIRST_SALE | Sold! | Complete your first car sale. |
| BIG_MARGIN | Margin Call | Make $10,000 profit on one sale. |
| EXOTIC_SALE | Supercar Dealer | Sell an exotic car. |
| FIVE_STARS | Five Stars on Yolp | Receive a five-star customer review. |
| FIRST_HIRE | Team Player | Hire your first salesperson. |
| LEVEL_5 | Rising Dealer | Reach dealership level 5. |
| LEVEL_10 | Tewport Legend | Reach dealership level 10. |
| TIER_2 | Moving Up | Upgrade to the second dealership. |
| TIER_3 | Flagship | Open the flagship dealership. |
| FIFTY_SALES | Volume Dealer | Sell 50 cars. |
| MILLIONAIRE | Seven Figures | Hold $1,000,000 in cash. |
| FIRST_MONTH | Open for Business | Make it to November. |

FIRST_CAR's live source check accepts owned cars or a prior sale, so the candidate avoids promising an auction-only predicate. MILLIONAIRE checks Game.money rather than an independently named bank account. State polling, local save/retry and actual Steam delivery retain their existing implementation and require separate acceptance; this prose does not certify them. No API identifier, threshold, trigger or reward changes.

## Original supplemental concepts — historical proposal, not catalog replacements

| Draft ref | Candidate name | Proposed description | Future owner evidence required |
|---|---|---|---|
| CA-D01 | Keys on the Desk | Complete your first car purchase. | Successful transaction and ownership transfer; not a bid attempt. |
| CA-D02 | Ready for the Floor | Complete a repair job on a car you own. | Authoritative completed job; queued or cancelled work does not qualify. |
| CA-D03 | Let's Make a Deal | Complete your first vehicle sale. | Actual finalized sale and inventory/money settlement; not a favorable conversation. |
| CA-D04 | Signed and Settled | Complete the paperwork for a vehicle deal. | Successfully finalized documents, not opening or timing out the paperwork screen. |
| CA-D05 | A Good Day's Work | Meet a daily sales goal. | Current existing goal completion at authoritative day end; no new target amount. |
| CA-D06 | Learning the Trade | Reach dealership level 3. | Persisted level from eligible progression; no debug/tour seed. |
| CA-D07 | Finding Your Rhythm | Reach dealership level 5. | Same persisted level source; do not confuse a staff skill with dealership level. |
| CA-D08 | Room to Grow | Reach dealership level 8. | Same persisted level source; no new lot, perk or reward guaranteed by this copy. |

## Adoption boundary

The names describe accomplishments without rewarding deception, adding no-loss constraints or inventing timers. Purchase, repair, sale, paperwork and day-end events may overlap; any later implementation must explicitly choose distinct predicates and exactly-once credit rather than unlock from opening a screen. No draft claims to certify an error-free sale or automatically profitable business.

Faisal must approve any supplemental catalog additions and their platform scope before assigning new IDs, icons or integration; preserve the thirteen existing API names. The owner then establishes normal-play eligibility, event authority, save/reload and retry/duplicate behavior. Scripted tour/test seed state must not unlock player progress. No new counters, unlock calls, store entries, images, saves or API work are included. These descriptions remain proposed for review.
