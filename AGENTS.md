# Agents: Chief Auto

Shared rules for every AI agent on this repo (Claude, Claude 2, ChatGPT/Codex). Faisal owns the game and approves design, art, spending and merges to `main`.

## Agents
| Agent ID | Who | Role |
|---|---|---|
| `claude-cloud` | Claude cloud session | Coordinator: hourly check-in across all of Faisal's repos, assigns tasks, relays to Faisal |
| `claude-faisal` | Claude on Faisal's desktop | Lead developer when the desktop is on |
| `claude-faisallaptop` | Claude 2 (laptop) | Code + engine tester (unknown): runs the game, tests, captures evidence |
| `chatgpt` / `Codex-faisal` | ChatGPT / Codex | Design docs, reviews, pure-logic code with tests |

## Where things live
- Memory: [docs/Memory Brief.md](docs/Memory%20Brief.md) (read first, at most 40 lines) and the wiki [docs/Wiki/Index.md](docs/Wiki/Index.md). Open `docs/` as an Obsidian vault.
- Workflow loop and token budget: the shared standard in the ORY framework repo, `docs/studio-workflow.md`.
- Board: [docs/agents/Agent Board.md](docs/agents/Agent%20Board.md) (who is on what) and [docs/agents/Task Board.md](docs/agents/Task%20Board.md) (backlog).
- Messages between agents: `docs/agents/Inbox/`, one note per message: `YYYY-MM-DD HHMM <from> to <to> - <topic>.md` with `from/to/status/task` front matter.
- Decisions for Faisal: [docs/agents/Needs Faisal.md](docs/agents/Needs%20Faisal.md). Anything you tell Faisal directly, also write here or as an inbox note `to: claude-cloud`.
- ChatGPT/Codex tasks are also posted as GitHub issues labeled `chatgpt-task`.
- Handoffs: `docs/agents/Handoffs/<date> <agent> <task>.md` (what changed, tests run, not tested, next step).

## Rules
1. `git pull` first; read your inbox notes and the board.
2. Claim a task by adding a row at the **bottom** of the Agent Board; commit and push the claim before editing. Never edit files another agent has claimed.
3. Work on a branch `<agent-id>/<task>`, open a PR. Only Faisal (or an agent he names) merges to `main`.
4. Test before every PR: the project's own tests once the game is in this repo. Say what was not tested.
5. Never delete files (archive and say so), never force-push, never publish or upload builds, never spend Meshy/PixelLab or other paid credits without Faisal's OK, never commit secrets.
6. Proposals (design, story, balance, art direction) are marked PROPOSED until Faisal approves.

## Sign your work (all agents, added 2026-10-16 at Faisal's request)
Several agents post through Faisal's GitHub account, so every agent signs everything it writes. That way nothing looks like it came from Faisal himself.
- **Commits:** the message ends with a line `Agent: <agent-id>`.
- **PRs:** the title starts with `<agent-id>:` and the description has an `Agent: <agent-id>` line.
- **Issue and PR comments:** start with `<agent-id>:`.
- **Inbox notes, board rows, handoffs:** put your agent ID in the from / agent field.
- **Never write as Faisal.** When you pass on a decision of his, quote him and say where and when he said it.

Agent IDs: `claude-cloud` (cloud coordinator), `claude-faisal` (desktop), `claude-faisallaptop` (Claude 2, laptop; subagents use `claude-faisallaptop/<role>`), `chatgpt`, `Codex-faisal`.
