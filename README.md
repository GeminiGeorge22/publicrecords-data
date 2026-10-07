# Etsy Pulse — publicrecords-data

Weekly Etsy market reports, published as a static site:

**https://geminigeorge22.github.io/publicrecords-data/**

| Report | Page | What it shows | Source |
|---|---|---|---|
| Overview | `index.html` | Headline numbers, this week's takeaways, links to every report | all below |
| Top Movers | `movers.html` | Top 10 shops (≥500 lifetime sales) by 7-day sales gain | `data/panel/<cut>/movers.csv` |
| Hot Categories | `categories.html` | Top 10 categories by combined 7-day gain, with shops gaining, typical shop and leader | `data/panel/<cut>/categories.csv` |
| Rising Shops | `rising.html` | Top 10 shops with 500–999 lifetime sales by 7-day gain | `data/panel/<cut>/rising.csv` |
| Breakouts | `breakouts.html` | Shops new to the top 10 vs the previous cut (appears automatically once two cuts exist) | two panel cuts |
| Use with AI | `ai.html` | Connect our two Actors to Claude / ChatGPT / Cursor / VS Code through Apify's MCP server (`https://mcp.apify.com?tools=publicrecords/etsy-search-scraper,publicrecords/etsy-shop-velocity`, OAuth sign-in with the visitor's Apify account); 6 use cases; demo video `assets/ai/` (real numbers from niche run mZPhcYgZOJ8SKb9fW) | Apify MCP docs |
| Niche Prices | `niche.html` | What top sellers charge (typical price, most charge $a–$b), price ranges, Bestseller share, free shipping for keywords from this week's leading movers; top 10 results per keyword in the CSV | `data/niche/<cut>/` |

**Free = top 10, custom = top 50 (t518u).** Every public file (repo `data/` and the site's CSVs) has at most 10 rows per
report (niche listings: 10 per keyword). Full cuts live only on the box (`/workspace/x-etsypulse/internal/panel-full/`,
`/workspace/x-etsypulse/internal/niche/`) and are never pushed. Under each report a "Want the top 50?" button opens `run.html`
already set up for that report (URL prefill: `type`, `q`, `category`, `f-<input id>`, `rank`/`dir`/`n`, `filter=field:op:value`).
Shop reports only get the prefilled top-50 button when `meta.json` → `custom_report.<report>.ready` says the Shop Sales Tracker
returns the gain field for enough shops (checked at export time); until then the button says plainly that it isn't ready and
offers a niche report. `build_site.py` fails the build if a public file has more than 10 rows per report or uses the banned
robot words (median, middle half, page 1, 7-day pace) in visible text, CSV headers or builder strings.

Every report page has a "What this means for sellers" block generated from the same rows, and a CSV download
(`data/<report>-<cut>.csv`, plus `-latest.csv` aliases). Nothing is estimated beyond the 7-day scaling described below.

## Pipeline

Cadence is one value: `config/publish.json` → `cadence_days` (7 = weekly on `publish_weekday`, 14 = every other week).
Free reports refresh slowly on purpose; today's numbers for any niche come from the paid Actor (site CTA → /r/site-cta).

1. **Box job** (`scripts/box_refresh.py loop`, started by `scripts/box_refresh_ensure.sh`, lock + PID in /tmp,
   status lines in `/workspace/x-etsypulse/data-refresh.log`):
   - **internal**, daily at `internal_daily_time_et`: panel export to `/workspace/x-etsypulse/internal/panel/<date>/`
     (box-only, never pushed), then re-renders the X post images (`/workspace/x-etsypulse/make_posts.py`).
   - **publish**, checked at `publish_time_et`: on `publish_weekday` when ≥ cadence_days−3 days since the last
     published cut, exports `data/panel/<date>/`, runs the niche snapshot (Apify, capped by `niche_max_usd`), commits, pushes.
2. **Panel cut**: `scripts/export_panel_cut.py [--out-root DIR]` (needs `HF_READ_TOKEN`; private HF dataset
   `Publicrecords/etsy-shop-velocity`). 7-day gain = latest public sales counter minus the read 7+ days earlier; with
   fewer than 7 days of reads the observed gain is scaled to 7 days. Same method as fleet `ops/etsy_top_movers.py` (TM-1).
3. **Niche snapshot**: `scripts/niche_snapshot.py run [--max-usd 0.45]` runs the publicrecords Etsy Search Scraper on the
   first 5 distinct categories of Top Movers (1 page each; retries thin keywords once within budget). `fetch --run-id ID...`
   rebuilds from existing runs.
4. **Site**: `scripts/build_site.py --out _site` renders every page, insights, the weekly-refresh callout (snapshot date,
   row counts, next free refresh), CSVs, `og.png`, sitemap and robots. No network at build time.
5. **Deploy**: `.github/workflows/pages.yml` rebuilds on pushes to `data/`, `scripts/`, `assets/`, `config/`, daily at
   14:00 UTC (same data → same pages) and on dispatch. No credentials are stored in GitHub.

Legacy: `data/top-movers/` + `scripts/import_cut.py` hold the original top-20 cut from fleet-orders; the site now reads `data/panel/`.

---

Etsy Pulse is published by publicrecords. The data comes from our own tools (Etsy Shop Sales Tracker panel and
Etsy Search Scraper on Apify). Not affiliated with, endorsed by, or sponsored by Etsy, Inc. Etsy is a trademark of Etsy, Inc.

## Report builder (`run.html`)

Visitors build a custom report on-site and run it on **their own Apify account** after "Sign in with Apify":
OAuth 2 authorization code + PKCE against `console-backend.apify.com` (public client `41bogEetbPU2ZVmGm`, registered via
Apify's open dynamic client registration, redirect `https://geminigeorge22.github.io/publicrecords-data/run.html`;
there is no client secret). Token exchange and Actor runs go browser → Apify directly; the token sits in
`sessionStorage` only. Apify offers a single scope (`full_api_access`), disclosed on the page.
Code: `assets/builder.js` / `assets/builder.css`; example reports use `assets/sample-*.json` (real runs).
Fallback "Rather run it inside Apify?" uses the worker tag `/r/site-run` (`?a=tracker` for the tracker) plus copyable input JSON.
Funnel counts: worker `/e/<event>` (builder-view, signin-start, signin-ok, run-start, run-ok, run-empty, csv, print, demo, fallback-*), shown in `/stats` → `events`.
