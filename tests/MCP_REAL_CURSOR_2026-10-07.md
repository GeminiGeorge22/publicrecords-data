# MCP-REAL (a) — Cursor end-to-end client test, 2026-10-07 — **FAIL**

Verdict: **FAIL.** Pass required both answers to come from SUCCEEDED runs with rows.
- Q1 ("top sellers for 'ceramic mug'"): the **Etsy Search Scraper run FAILED** — `ERROR_UPSTREAM_BLOCKED` (Etsy HTTP 403 twice, 0 rows, nothing charged). The agent answered from the Shop Velocity lookup instead (11 shop rows, lifetime sales; **no listing prices**).
- Q2 ("7-day sales of one shop"): the Shop Velocity lookup returned 1 row, but `delta_7d` / `sales_per_day` are **null** (`history_days: 1`, snapshot 49 h old, `snapshot_stale: true`), so the agent correctly said the 7-day sales are **not available**.
- The Cursor client itself worked: it connected to the Apify MCP server, discovered the tools, made real tool calls with sensible arguments, and formatted a table. The failure is on the data side (Search blocked upstream; tracker has no 7-day history).
- Per instructions, no retry/workaround was attempted after the failure.

## Setup
| Item | Value |
|---|---|
| Client | Cursor CLI `cursor-agent` 2026.10.01-e373342, headless `-p --approve-mcps --trust --output-format stream-json`, run from `/tmp` |
| Model | `Auto` (Cursor default), Cursor auth = API key from env (Mark's account) |
| MCP server | `~/.cursor/mcp.json` → `etsy-pulse` = `https://mcp.apify.com?tools=publicrecords/etsy-search-scraper,publicrecords/etsy-shop-velocity` |
| **Apify auth** | **Owner token** via `Authorization: Bearer ${env:APIFY_TOKEN}` header (env interpolation; token not in any file). **Not buyer OAuth.** |
| Tool approval | `~/.cursor/cli-config.json` permissions.allow += `Mcp(etsy-pulse:*)` (headless equivalent of a buyer clicking "Always allow" for this server) |
| Box-only fix | `GIT_SSH_COMMAND='ssh -oConnectTimeout=5'` — the CLI's startup fetch of `git@github.com:cursor/plugins.git` hangs forever on this box (SSH egress blocked); with a timeout it fails fast and the agent starts. Not relevant to a buyer's machine. |
| Side effect | Cursor auto-loaded the team's public Apify plugin; the agent read its `apify-ultimate-scraper/SKILL.md` but used only etsy-pulse tools. |

## Timeline (ET, 2026-10-07)
| Time | Event |
|---|---|
| 20:53:08.5 | Attempt 1, Q1 sent. All tool calls were rejected by the CLI's default allowlist approval mode (`User rejected MCP: …lookup_shops`, WebSearch/WebFetch also rejected). No Apify run. Agent: "I couldn't pull a current ranking." Fixed by allowlisting `Mcp(etsy-pulse:*)`. |
| 20:54:08.952 | **Q1 sent:** `Who are the top sellers on Etsy for 'ceramic mug'?` (exact prompt, no cap steering) |
| 20:54:22.046 | First rows: Shop Velocity Standby lookup served 11 shop rows (**13.1 s** after the question) |
| 20:54:28.441 | Search Scraper run `Hjfr39McJSvFrlhAx` started (origin MCP) |
| 20:54:42.808 | Search: HTTP 403 BLOCKED_001, one fresh-session retry |
| 20:54:46.249 | Search run FAILED: `ERROR_UPSTREAM_BLOCKED: 0 billed rows, every input failed: "ceramic mug" (ERROR_UPSTREAM_BLOCKED). Nothing was charged.` |
| 20:54:55.4 | Q1 answer complete (46.5 s wall clock, CLI startup included) |
| 20:55:14.055 | **Q2 sent** (resumed same session): `What were EvanilifeHandmade's sales over the last 7 days?` |
| 20:55:22.528 | Velocity lookup served 1 row (**8.5 s**) |
| 20:55:26.1 | Q2 answer complete (12.0 s) |

## Tool calls (arguments chosen by the agent)
1. `publicrecords--etsy-shop-velocity--lookup_shops` `{"keywords":["ceramic mug"],"maxShops":15}` → success, 11 rows, snapshot 2026-10-06, panel 88,247, `snapshot_stale: true`.
2. `publicrecords--etsy-search-scraper` `{"queries":["ceramic mug"],"sort":"relevance","is_best_seller":true,"maxItems":48,"maxPages":1,"waitSecs":45}` → run FAILED (blocked). **The agent set its own cap (maxItems 48, maxPages 1); it did not rely on the 0.2.10 default of 20.**
3. (Q2) `publicrecords--etsy-shop-velocity--lookup_shops` `{"shops":["EvanilifeHandmade"],"maxShops":5}` → success, 1 row, `delta_7d: null`, `sales_per_day: null`, `history_days: 1`.

## Apify runs (read back from the Apify API)
| Run | Actor | Build | Status | Charged events | Items | startedAt (UTC) | First row |
|---|---|---|---|---|---|---|---|
| `Hjfr39McJSvFrlhAx` | publicrecords/etsy-search-scraper (`JbNpPvG1Z7YtM9onP`) | 0.2.10 (`LRdhNvPXU8Yei84J8`) | **FAILED**, exit 1 | actor-start 0, listing-row 0 ($0 charged; platform usage $0.0100) | 0 (dataset `pTRmTEkoKqZPqPkrZ`) | 2026-10-08T00:54:28.441Z (finished 00:54:46.249Z) | none |
| `ugaMzwSEzwyRzWQD0` | publicrecords/etsy-shop-velocity (`iSqAcbENkn1ZdUMm1`), Standby | 0.2.14 (`bho73Ga6z3iaEoLuS`) | RUNNING (Standby server; serves many requests, ends on idle) | actor-start 3, shop-row 12 (= 11 for Q1 + 1 for Q2) at read time | rows returned in the MCP response; dataset `qYlLiLKgzCX1uFzO4` itemCount 0 | 2026-10-08T00:52:55.639Z | Q1 rows logged 00:54:22.046Z; Q2 row 00:55:22.528Z |

Standby log lines for our requests:
```
2026-10-08T00:54:21.808Z WARN  Snapshot 2026-10-06 is 49 h old — served and flagged snapshot_stale=true
2026-10-08T00:54:22.046Z INFO  Snapshot 2026-10-06: 88247 shops in panel, 11 matched, returning 11
2026-10-08T00:55:22.444Z WARN  Snapshot 2026-10-06 is 49 h old — served and flagged snapshot_stale=true
2026-10-08T00:55:22.528Z INFO  Snapshot 2026-10-06: 88247 shops in panel, 1 matched, returning 1
```
Search run log (tail):
```
2026-10-08T00:54:31.807Z INFO  proxy=apify-residential
2026-10-08T00:54:42.808Z WARN  HTTP 403 on "ceramic mug" (BLOCKED_001); one fresh-session retry within 20000ms. No charge.
2026-10-08T00:54:45.612Z WARN  ERROR_UPSTREAM_BLOCKED "ceramic mug" HTTP 403 after one fresh-session retry (BLOCKED_002). 0 charges for it.
2026-10-08T00:54:46.201Z ERROR [Status message]: ERROR_UPSTREAM_BLOCKED: 0 billed rows, every input failed: "ceramic mug" (ERROR_UPSTREAM_BLOCKED). Nothing was charged.
```

## How the answers looked
- Q1: a clean markdown table (Rank, Shop link, Sales, Reviews, Rating, Listings, Focus) of 8 shops led by EvanilifeHandmade (13,827 lifetime sales) and colleendeissdesigns (6,883), with an honest caveat that live search was blocked, it's a tracked-shop sample, and velocity isn't available. **No seller prices**: it doesn't match the AI-page demo (top sellers with what they charge).
- Q2: a short, honest "not available": one reading (2026-10-05, 13,827 lifetime sales), `delta_7d` empty. No 7-day figure.

## Findings for follow-up (owner: Master)
1. Search Scraper blocked on the MCP default path (`/market/ceramic_mug?is_best_seller=1&source=llms.txt`, apify-residential) — HTTP 403 twice.
2. Velocity snapshot is 49 h old (2026-10-06) and every row still has null `delta_7d`/`sales_per_day` (the known tracker-gains row). Any "7-day sales" claim fails until that's fixed.
3. Velocity panel reads 88,247 shops (relevant to SITE-2's manifest count).

Full transcript: `MCP_REAL_CURSOR_2026-10-07.transcript.txt` (attempt 1, Q1, Q2; tool args and results).
