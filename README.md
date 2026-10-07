# publicrecords-data

Weekly **Etsy top movers** from the publicrecords Velocity panel, published as a static page:

**https://geminigeorge22.github.io/publicrecords-data/**

The page lists the 20 Etsy shops with the largest 7-day gain in sales: shop, category, 7-day sold delta and rank move versus the prior week. Only that table is published.

## How the page is built

- `data/top-movers/YYYY-MM-DD.csv`: one file per cut, public columns only (`rank, shop_name, shop_url, category, sales_7d_delta, cut_date`).
- `scripts/build_movers_page.py`: renders `_site/index.html` (plus `robots.txt` and `sitemap.xml`) from the newest CSV. Rank move is computed against the newest cut that is at least 7 days older. If there isn't one, the column shows `—` and the page says so.
- `.github/workflows/pages.yml`: builds and deploys to GitHub Pages on every push that touches `data/top-movers/`, daily at 14:00 UTC, and on manual dispatch.

## Dropping in the nightly file

From a checkout of fleet-orders and this repo:

```bash
python scripts/import_cut.py ../fleet-orders/marketer/top-movers/YYYY-MM-DD.csv
git add data/top-movers/YYYY-MM-DD.csv
git commit -m "top movers YYYY-MM-DD"
git push
```

`import_cut.py` keeps only the `top20_7d` section and the public columns. Totals, method/span fields and the other sections are not published. The push triggers the rebuild. You can also run the workflow by hand from the Actions tab (`workflow_dispatch`).

Optional: if a repository secret `FLEET_ORDERS_READ` (a read-only token for the private fleet-orders repo) is added later, the workflow imports new cuts itself before building. Without that secret the step is skipped and the in-repo CSVs are used.

## Track a shop yourself

The numbers come from the same public sales counters as the [Etsy Shop Sales Tracker](https://apify.com/publicrecords/etsy-shop-velocity) Actor on Apify. Example input: `{"shops": ["Lamoriea", "MoonberryHandmade", "JoycieLaneDesigns"]}`.

---

Published by publicrecords. Not affiliated with, endorsed by, or sponsored by Etsy, Inc.
