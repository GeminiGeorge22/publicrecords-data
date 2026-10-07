# Etsy Pulse — publicrecords-data

Weekly Etsy market reports, published as a static site:

**https://geminigeorge22.github.io/publicrecords-data/**

| Report | Page | What it shows | Source |
|---|---|---|---|
| Overview | `index.html` | Headline numbers, this week's takeaways, links to every report | all below |
| Top Movers | `movers.html` | Top 50 shops (≥500 lifetime sales) by 7-day sales gain | `data/panel/<cut>/movers.csv` |
| Hot Categories | `categories.html` | Every category ranked by combined 7-day gain, with shops gaining, median shop and leader | `data/panel/<cut>/categories.csv` |
| Rising Shops | `rising.html` | Top 25 shops with 500–999 lifetime sales by 7-day gain | `data/panel/<cut>/rising.csv` |
| Breakouts | `breakouts.html` | Shops new to the top 50 vs the previous cut (appears automatically once two cuts exist) | two panel cuts |
| Niche Prices | `niche.html` | Page-1 Etsy search prices, price bands, Bestseller share, free shipping for keywords from this week's leading movers | `data/niche/<cut>/` |

Every report page has a "What this means for sellers" block generated from the same rows, and a CSV download
(`data/<report>-<cut>.csv`, plus `-latest.csv` aliases). Nothing is estimated beyond the 7-day scaling described below.

## Pipeline

1. **Panel cut** (box-side, needs `HF_READ_TOKEN` for the private HF dataset `Publicrecords/etsy-shop-velocity`):
   `python scripts/export_panel_cut.py` → `data/panel/YYYY-MM-DD/{movers,categories,rising}.csv` + `meta.json`.
   7-day gain = latest public sales counter minus the read 7+ days earlier; with fewer than 7 days of reads the
   observed gain is scaled to 7 days. Same method as fleet `ops/etsy_top_movers.py` (TM-1).
2. **Niche snapshot** (box-side, weekly, needs `APIFY_TOKEN`; ~$0.10–0.30 Apify usage):
   `python scripts/niche_snapshot.py run` runs the publicrecords Etsy Search Scraper on the first 5 distinct categories of
   Top Movers (1 page each) → `data/niche/YYYY-MM-DD/`. `fetch --run-id ID [ID...]` rebuilds from existing runs.
3. **Site**: `python scripts/build_site.py --out _site` renders every page, the insights, CSVs, `og.png` social card
   (Pillow + `scripts/fonts/Inter.ttf`), sitemap and robots. No network access at build time.
4. **Deploy**: `.github/workflows/pages.yml` rebuilds on every push to `data/`, `scripts/`, `assets/`, daily at 14:00 UTC,
   and on manual dispatch. If a repository secret `HF_READ_TOKEN` is added, the workflow exports the panel cut itself.

Legacy: `data/top-movers/` + `scripts/import_cut.py` hold the original top-20 cut from fleet-orders; the site now reads `data/panel/`.

---

Etsy Pulse is published by publicrecords. The data comes from our own tools (Etsy Shop Sales Tracker panel and
Etsy Search Scraper on Apify). Not affiliated with, endorsed by, or sponsored by Etsy, Inc. Etsy is a trademark of Etsy, Inc.
