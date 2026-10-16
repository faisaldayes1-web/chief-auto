# Chief Auto: Dealership Simulator

A comedy car dealership sim set at OC Chief Auto in Tewport Beach, Canioria. Win cars on the auction PC, get them fixed, sell them in the showroom, sign the paperwork, and grow the dealership under the eye of Marco, the CEO and financial advisor.

This is the first playable prototype of the core loop. Built with [Godot 4.3](https://godotengine.org/download/archive/4.3-stable/) (free), targeting Steam first and mobile later.

## What's in the prototype

- **Office PC:** AutoBidz, a browser-style auction site. Live bidding against rival dealers, Buy It Now, haggling, and a history + inspection report that reveals hidden problems.
- **Garage:** pick a mechanic per job. Better mechanics unlock with level and botch less often. Botched jobs leave hidden faults that buyers can find.
- **Showroom:** set your asking price, then sell it yourself or let Jeff try.
- **Sales minigame:** five buyer types, an interest meter, patience, and seven moves (test drive, history report, discounts, stretching the truth, and more). Buyers pay for the car's real condition, so hidden problems lead to counteroffers.
- **Paperwork:** sign three documents against a timer, catch errors, and upsell add-ons.
- **Marco:** advisor screen with dealership stats, perks that unlock at levels 3, 5 and 8, and market tips (one car class is hot each day).
- **Progression:** XP from profit, levels, daily rent, a daily sales goal, reputation, and auto-save.

## Running it

1. Install Godot 4.3 (standard version, not .NET).
2. Open Godot, choose **Import**, and select `project.godot` in this folder.
3. Press **F5** to play.

To make builds, install the 4.3 export templates in Godot (Editor > Manage Export Templates), then use Project > Export. Presets for Web and Windows are included.

## Project layout

| Path | What it is |
| --- | --- |
| `scripts/game_state.gd` | Autoloaded `Game` singleton: money, level, cars, data tables (models, mechanics, buyers, perks), save/load |
| `scripts/main.gd` | Every screen and the core loop: title, lot, auction PC, garage, showroom, sales minigame, paperwork, Marco |
| `scripts/ui.gd` | Theme and small UI helpers |
| `assets/` | Backgrounds from the OC Chief Auto concept art, logo, fallback font (DejaVu Sans) |

Balance numbers (prices, repair costs, odds) are first guesses and live in `game_state.gd` and `main.gd`.
