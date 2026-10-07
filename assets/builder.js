/* Etsy Pulse report builder.
 * Runs publicrecords Actors on the visitor's own Apify account after "Sign in with Apify" (OAuth 2 authorization code + PKCE,
 * public client registered through Apify's open dynamic client registration; no client secret exists).
 * The access token lives only in this tab's sessionStorage and only ever goes to api.apify.com. Nothing is sent to our servers
 * except anonymous funnel counts (/e/<event>?t=<report type>).
 */
(function () {
  "use strict";
  var CFG = {
    clientId: "41bogEetbPU2ZVmGm",
    authUrl: "https://console.apify.com/authorize/oauth",
    tokenUrl: "https://console-backend.apify.com/oauth/apps/token",
    api: "https://api.apify.com/v2",
    worker: "https://publicrecords-redirect.publicrecords.workers.dev",
  };
  var ACTORS = {
    search: { id: "JbNpPvG1Z7YtM9onP", name: "Etsy Search Scraper", store: "https://apify.com/publicrecords/etsy-search-scraper",
      start: 0.005, unit: 0.006, unitName: "listing" },
    tracker: { id: "iSqAcbENkn1ZdUMm1", name: "Etsy Shop Sales Tracker", store: "https://apify.com/publicrecords/etsy-shop-velocity",
      start: 0.005, unit: 0.003, unitName: "shop", platform: 0.02 },
  };
  var BLOCKS = {
    kpis: "Headline numbers", takeaways: "Plain-English takeaways", prices: "Price bands chart", badges: "Badges chart",
    bestprice: "Bestseller vs the rest", shops: "Top shops chart", shoptable: "Shop leaderboard", compare: "Keyword comparison",
    velocity: "Sales pace chart", rivals: "Side-by-side shop charts", table: "Full data table",
  };
  var TYPES = {
    niche: { actor: "search", title: "Niche price snapshot", icon: "💲",
      blurb: "What page 1 of Etsy costs for your keyword: price range, sweet spot, badges, who ranks.",
      blocks: ["kpis", "takeaways", "prices", "badges", "shops", "table"],
      cols: ["position", "title", "price", "shop_name", "review_count", "rating_value", "bestseller", "free_shipping"] },
    compare: { actor: "search", title: "Compare keywords", icon: "⚖️",
      blurb: "Put 2 to 5 keywords side by side: prices, competition, bestseller share.",
      blocks: ["kpis", "takeaways", "compare", "prices", "table"],
      cols: ["query", "position", "title", "price", "shop_name", "review_count", "bestseller"] },
    bestsellers: { actor: "search", title: "What wins: badge check", icon: "🏅",
      blurb: "Which listings carry Bestseller, Popular Now and Star Seller badges, and what they charge.",
      blocks: ["kpis", "takeaways", "badges", "bestprice", "table"],
      cols: ["position", "title", "price", "shop_name", "bestseller", "popular_now", "star_seller", "etsys_pick", "review_count"] },
    competitors: { actor: "search", title: "Top shops in a niche", icon: "🏪",
      blurb: "Which shops own page 1 for your keyword: spots held, best rank, prices, reviews.",
      blocks: ["kpis", "takeaways", "shops", "shoptable", "table"],
      cols: ["position", "shop_name", "title", "price", "review_count", "bestseller"] },
    velocity: { actor: "tracker", title: "Shop sales tracker", icon: "📈",
      blurb: "Lifetime sales, sales per day and 7-day change for any Etsy shops you name.",
      blocks: ["kpis", "takeaways", "velocity", "table"],
      cols: ["shop", "sales_count", "sales_per_day", "delta_7d", "units_day", "reviews_count", "rating", "as_of"] },
    rivals: { actor: "tracker", title: "Competitor comparison", icon: "🥊",
      blurb: "Line up 2 to 10 shops: sales pace, lifetime sales, reviews, followers, listings.",
      blocks: ["kpis", "takeaways", "velocity", "rivals", "table"],
      cols: ["shop", "sales_per_day", "delta_7d", "sales_count", "reviews_count", "admirers", "listings_active", "rating"] },
    category: { actor: "tracker", title: "Category leaders", icon: "🏆",
      blurb: "The fastest-selling shops in an Etsy category, from our daily shop panel.",
      blocks: ["kpis", "takeaways", "velocity", "table"],
      cols: ["shop", "category", "sales_per_day", "delta_7d", "sales_count", "reviews_count", "as_of"] },
    breakouts: { actor: "tracker", title: "Breakout shops", icon: "🚀",
      blurb: "Shops whose last 7 days are far above their own usual pace.",
      blocks: ["kpis", "takeaways", "velocity", "table"],
      cols: ["shop", "category", "delta_7d", "lift_7d", "sales_per_day", "sales_count", "breakout_p"] },
  };
  var LABELS = {
    position: "Rank", title: "Listing", price: "Price", currency: "Currency", shop_name: "Shop", rating_value: "Rating",
    review_count: "Reviews", review_count_approx: "Reviews rounded", bestseller: "Bestseller", star_seller: "Star Seller",
    popular_now: "Popular now", etsys_pick: "Etsy's Pick", free_shipping: "Free shipping", is_ad: "Ad", query: "Keyword",
    page: "Page", total_results: "Etsy results", listing_id: "Listing ID", url: "Listing link", shop_url: "Shop link",
    shop_id: "Shop ID", surface: "Card type", source: "Source",
    shop: "Shop", headline: "Headline", category: "Category", sales_count: "Lifetime sales", sales_precision: "Sales precision",
    as_of: "Read on", read_interval_days: "Days between reads", delta_last: "Sales since last read",
    sales_per_day: "Sales per day", delta_7d: "Sales, last 7 days", delta_28d: "Sales, last 28 days",
    units_day: "Est. sales/day", units_lo: "Est. low", units_hi: "Est. high", lift_7d: "7-day lift", breakout: "Breakout",
    breakout_p: "Breakout odds", reviews_count: "Reviews", rating: "Rating", admirers: "Followers", listings_active: "Active listings",
    first_seen: "First seen", last_changed: "Last change", history_days: "Days of history", vintage_event: "Counter reset",
    snapshot_date: "Snapshot", snapshot_stale: "Snapshot stale", velocity_null_reason: "Why no pace",
    sales_precision_prev: "Prev precision", sales_precision_last: "Last precision",
  };
  var MONEY_COLS = { price: 1 }, BOOL_HINT = /^(bestseller|star_seller|popular_now|etsys_pick|free_shipping|is_ad|breakout|vintage_event|snapshot_stale|review_count_approx)$/;
  var CATS = [];
  var state = { type: "niche", blocks: null, cols: null, result: null, sort: null, user: null, refine: { by: "", dir: "top", n: "", filters: [] } };
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var unesc = function (s) { var t = document.createElement("textarea"); t.innerHTML = s == null ? "" : String(s); return t.value; };
  var ss = { get: function (k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (e) { return null; } },
    set: function (k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }, del: function (k) { try { sessionStorage.removeItem(k); } catch (e) {} } };

  function beacon(name, extra) {
    try {
      var u = CFG.worker + "/e/" + name + "?t=" + encodeURIComponent(state.type || "") + (extra ? "&" + extra : "");
      if (navigator.sendBeacon) navigator.sendBeacon(u); else fetch(u, { method: "POST", mode: "no-cors", keepalive: true });
    } catch (e) {}
  }
  function redirectUri() {
    var p = location.pathname.replace(/\/run(\.html)?$/, "/run.html");
    if (!/run\.html$/.test(p)) p = p.replace(/\/?$/, "/run.html");
    return location.origin + p;
  }
  function b64url(buf) { return btoa(String.fromCharCode.apply(null, new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
  function rand(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return b64url(a); }

  /* ------------------------------------------------------------------ numbers */
  function median(a) { a = a.filter(isFinite).sort(function (x, y) { return x - y; }); if (!a.length) return null; var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; }
  function quant(a, q) { a = a.filter(isFinite).sort(function (x, y) { return x - y; }); if (!a.length) return null; var i = (a.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i); return a[lo] + (a[hi] - a[lo]) * (i - lo); }
  function num(x, d) { if (x == null || x === "" || !isFinite(x)) return "–"; return Number(x).toLocaleString("en-US", { maximumFractionDigits: d == null ? 0 : d }); }
  function cur(rows) { var c = (rows.find(function (r) { return r.currency; }) || {}).currency || "$"; return c.length > 3 ? c + " " : c; }
  function money(x, c) { if (x == null || !isFinite(x)) return "–"; return (c || "$") + Number(x).toLocaleString("en-US", { minimumFractionDigits: x < 100 ? 2 : 0, maximumFractionDigits: x < 100 ? 2 : 0 }); }
  function pct(x, d) { return x == null || !isFinite(x) ? "–" : (100 * x).toFixed(d || 0) + "%"; }
  function usd(x) { return "$" + (x < 1 ? x.toFixed(3).replace(/0$/, "") : x.toFixed(2)); }
  function share(rows, f) { return rows.length ? rows.filter(function (r) { return r[f] === true; }).length / rows.length : null; }

  /* ------------------------------------------------------------------ inputs → Actor input JSON */
  function lines(v) { return String(v || "").split(/[\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean); }
  function shopName(s) {
    s = s.trim().replace(/^@/, "");
    var m = s.match(/etsy\.com\/(?:[a-z-]+\/)?shop\/([A-Za-z0-9_-]+)/i); if (m) return m[1];
    m = s.match(/^https?:\/\/([A-Za-z0-9-]+)\.etsy\.com/i); if (m && m[1].toLowerCase() !== "www") return m[1];
    return s.replace(/[^A-Za-z0-9_-]/g, "");
  }
  function val(id) { var el = document.getElementById(id); if (!el) return ""; return el.type === "checkbox" ? el.checked : el.value.trim(); }
  function int(id) { var v = val(id); return v === "" ? null : Math.max(0, parseInt(v, 10) || 0); }
  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
  var LIMITS = { perKwMax: 1200, perKwMaxFast: 240, pages: 20, perPage: 48, perPageFast: 12, inputsMax: 100, shopsMax: 20000, confirmUsd: 5 };
  // Cap passed to Apify (maxTotalChargeUsd) = this run's maximum possible event charges + 10% + $0.02, rounded up to the cent.
  // maxItems / maxShops bound the row events exactly, so the cap can never cut a report short.
  function capFor(maxEvents) { return Math.ceil((maxEvents * 1.1 + 0.02) * 100) / 100; }

  /* Returns {actor, jobs:[{label,input,cap,memory,timeout}], combined, est, max, rows, errors[], warns[]} */
  function buildPlan() {
    var t = TYPES[state.type], errors = [], warns = [], plan = { actor: t.actor, jobs: [], errors: errors, warns: warns };
    var mem = parseInt(val("f-memory"), 10) || (t.actor === "search" ? 2048 : 1024);
    var tmin = int("f-timeout");
    if (t.actor === "search") {
      var kws = lines(val("f-queries")), mps = lines(val("f-market")), cats = lines(val("f-caturls"));
      var fill = val("f-fill") !== false && document.getElementById("f-fill") ? val("f-fill") : true;
      var maxN = fill ? LIMITS.perKwMax : LIMITS.perKwMaxFast;
      var n = int("f-perkw"); if (n == null || n < 1) { n = 20; if (val("f-perkw") !== "") errors.push("Listings per keyword must be at least 1."); }
      if (n > maxN) { warns.push("Etsy shows at most 20 pages per search, so " + num(maxN) + " is the most one keyword can return" + (fill ? "" : " in fast mode") + ". Using " + num(maxN) + "."); n = maxN; }
      var pages = int("f-pages"); var autoPages = clamp(Math.ceil(n / (fill ? LIMITS.perPage : LIMITS.perPageFast)), 1, LIMITS.pages);
      pages = pages ? clamp(pages, 1, LIMITS.pages) : autoPages;
      var base = { sort: val("f-sort") || "relevance", maxPages: pages, fillLazyCards: !!fill, source: val("f-source") || "etsypulse-site-builder" };
      var purls = lines(val("f-proxyurls"));
      base.proxyConfiguration = val("f-proxymode") === "own" && purls.length ? { useApifyProxy: false, proxyUrls: purls }
        : { useApifyProxy: true, apifyProxyGroups: ["RESIDENTIAL"], apifyProxyCountry: val("f-region") || "US" };
      if (val("f-proxymode") === "own" && !purls.length) errors.push("Add at least one proxy URL, or switch back to Apify's proxy.");
      var mn = int("f-minprice"), mx = int("f-maxprice"), days = int("f-days");
      if (mn != null) base.minPrice = mn; if (mx != null) base.maxPrice = mx; if (days != null && days > 0) base.max_processing_days = days;
      if (val("f-shipto")) base.ship_to = val("f-shipto");
      ["is_best_seller", "is_star_seller", "free_shipping", "is_discounted", "instant_download", "is_handmade_only", "is_personalizable"].forEach(function (k) { if (val("f-" + k)) base[k] = true; });
      if (mn != null && mx != null && mx > 0 && mx < mn) errors.push("The highest price is below the lowest price.");
      cats = cats.filter(function (u) { if (!/^https?:\/\/(www\.)?etsy\.com\/c\//i.test(u)) { errors.push("Category links must look like https://www.etsy.com/c/jewelry/necklaces"); return false; } return true; })
        .map(function (u) { return u.split("?")[0]; });
      var timeout = tmin ? clamp(tmin, 1, 1440) * 60 : clamp(600 + pages * 90, 900, 3600);
      var cap = capFor(ACTORS.search.start + n * ACTORS.search.unit);
      var mk = function (label, extra) { plan.jobs.push({ label: label, input: Object.assign({}, base, extra, { maxItems: n }), cap: cap, memory: mem, timeout: timeout }); };
      kws.forEach(function (k) { mk(k, { queries: [k] }); });
      mps.forEach(function (k) { mk(k + " (market page)", { marketPhrases: [k] }); });
      cats.forEach(function (u) { mk(u.replace(/^https?:\/\/(www\.)?etsy\.com\/c\//, "category: "), { categoryUrls: [u] }); });
      if (!plan.jobs.length) errors.push("Type at least one keyword.");
      if (plan.jobs.length > LIMITS.inputsMax) errors.push("Up to " + LIMITS.inputsMax + " keywords per report (you have " + plan.jobs.length + "). Split it into two reports.");
      if (state.type === "compare" && plan.jobs.length < 2) errors.push("Comparing needs at least 2 keywords, one per line.");
      plan.combined = Object.assign({}, base, { maxItems: n * Math.max(1, plan.jobs.length) });
      if (kws.length) plan.combined.queries = kws; if (mps.length) plan.combined.marketPhrases = mps; if (cats.length) plan.combined.categoryUrls = cats;
      plan.perKw = n; plan.rows = n * plan.jobs.length;
      plan.est = plan.jobs.length * ACTORS.search.start + plan.rows * ACTORS.search.unit;
      plan.max = plan.jobs.reduce(function (s, j) { return s + j.cap; }, 0);
      plan.platform = 0;
      if (plan.jobs.length > 1) warns.push(plan.jobs.length + " keywords run as " + plan.jobs.length + " separate Apify runs (each gets exactly " + num(n) + " listings and its own $0.005 start fee).");
    } else {
      var named = state.type === "velocity" || state.type === "rivals";
      var shops = lines(val(named ? "f-shops" : "f-shops2")).map(shopName).filter(Boolean), inp = {};
      var maxShops = int("f-maxshops"); if (!maxShops) maxShops = shops.length || 20;
      if (maxShops > LIMITS.shopsMax) { warns.push("The tracker returns at most " + num(LIMITS.shopsMax) + " shops per run. Using " + num(LIMITS.shopsMax) + "."); maxShops = LIMITS.shopsMax; }
      if (shops.length) { inp.shops = shops; maxShops = Math.min(maxShops, shops.length); }
      var kw = lines(val("f-shopkw")); if (kw.length) inp.keywords = kw;
      var catv = val(named ? "f-category2" : "f-category"); if (catv) inp.category = catv;
      var ms = int("f-minsales"), mr = int("f-minrate"); if (ms) inp.minSales = ms; if (mr) inp.minRate = mr;
      if (val("f-since")) inp.since = val("f-since");
      if (state.type === "breakouts" || val("f-breakout")) inp.breakoutOnly = true;
      inp.maxShops = maxShops;
      if (named && !shops.length) errors.push("Add at least one shop name or link.");
      if (state.type === "rivals" && shops.length === 1) errors.push("Comparing needs at least 2 shops.");
      if (shops.length > LIMITS.shopsMax) errors.push("Up to " + num(LIMITS.shopsMax) + " shops per report.");
      if (state.type === "category" && !inp.category && !kw.length && !shops.length) errors.push("Pick a category (or add shop-name words under Advanced options).");
      var trows = maxShops, tcap = capFor(ACTORS.tracker.start + trows * ACTORS.tracker.unit);
      plan.jobs.push({ label: shops.length ? shops.length + " shops" : (inp.category ? unesc(inp.category) : "panel"), input: inp, cap: tcap, memory: mem, timeout: tmin ? clamp(tmin, 1, 1440) * 60 : 900 });
      plan.combined = inp; plan.rows = trows;
      plan.est = ACTORS.tracker.start + trows * ACTORS.tracker.unit;
      plan.max = tcap; plan.platform = ACTORS.tracker.platform;
    }
    plan.bigConfirm = plan.max + plan.platform > LIMITS.confirmUsd;
    return plan;
  }

  /* ------------------------------------------------------------------ form UI */
  function opt(v, l, sel) { return '<option value="' + esc(v) + '"' + (sel ? " selected" : "") + ">" + esc(l) + "</option>"; }
  function field(id, label, html, hint) { return '<label class="fld" for="' + id + '"><span>' + label + "</span>" + html + (hint ? "<small>" + hint + "</small>" : "") + "</label>"; }
  function check(id, label, on) { return '<label class="chk"><input type="checkbox" id="' + id + '"' + (on ? " checked" : "") + "> <span>" + label + "</span></label>"; }
  function sub(t) { return '<h3 class="asub">' + t + "</h3>"; }

  function renderForm(q) {
    var app = $("#builder");
    var groups = [["search", "About a keyword or niche", "Live Etsy search, via our Etsy Search Scraper"],
      ["tracker", "About specific shops", "Daily public sales counters, via our Etsy Shop Sales Tracker"]];
    var cards = groups.map(function (g) {
      return '<div class="tgroup"><div class="tgh"><b>' + g[1] + "</b><small>" + g[2] + '</small></div><div class="tcards">' +
        Object.keys(TYPES).filter(function (k) { return TYPES[k].actor === g[0]; }).map(function (k) {
          var t = TYPES[k];
          return '<button type="button" class="tcard" data-type="' + k + '" aria-pressed="false"><span class="ti">' + t.icon + '</span><span class="tt">' + t.title + '</span><span class="tb">' + t.blurb + "</span></button>";
        }).join("") + "</div></div>";
    }).join("");
    var catOpts = opt("", "Any category") + CATS.map(function (c) { return opt(c.v, c.l); }).join("");
    var countries = [["US", "United States"], ["GB", "United Kingdom"], ["CA", "Canada"], ["AU", "Australia"], ["DE", "Germany"], ["FR", "France"], ["NL", "Netherlands"], ["IT", "Italy"], ["ES", "Spain"], ["IE", "Ireland"], ["NZ", "New Zealand"], ["SE", "Sweden"], ["DK", "Denmark"], ["NO", "Norway"], ["CH", "Switzerland"], ["AT", "Austria"], ["BE", "Belgium"], ["PL", "Poland"], ["JP", "Japan"], ["IN", "India"]];
    app.innerHTML =
      '<div class="bstep"><div class="bh"><i>1</i><h2>Pick a report</h2></div>' + cards + "</div>" +
      '<div class="bstep" id="step2"><div class="bh"><i>2</i><h2>Tell it what to look at</h2></div>' +
      '<div data-for="search">' +
        field("f-queries", "Keywords <em>(one per line)</em>", '<textarea id="f-queries" rows="2" placeholder="ceramic mug&#10;personalized dog collar"></textarea>') +
        '<div class="frow">' +
        field("f-perkw", "Listings per keyword", '<input id="f-perkw" type="number" min="1" max="1200" step="1" inputmode="numeric" value="20">' +
          '<span class="quick" data-target="f-perkw"><button type="button" data-v="20">20</button><button type="button" data-v="60">60</button><button type="button" data-v="200">200</button><button type="button" data-v="500">500</button><button type="button" data-v="1200">max</button></span>', "Any number from 1 to 1,200 (Etsy shows at most 20 pages per search).") +
        field("f-sort", "Which listings Etsy returns", "<select id=f-sort>" + opt("relevance", "Etsy's best match (default)") + opt("top_reviews", "Most reviewed") + opt("newest", "Newest") + opt("price_asc", "Cheapest first") + opt("price_desc", "Most expensive first") + "</select>") +
        "</div></div>" +
      '<div data-for="tracker">' +
        '<div data-show="velocity rivals">' + field("f-shops", "Shop names or links <em>(one per line)</em>", '<textarea id="f-shops" rows="3" placeholder="CaitlynMinimalist&#10;https://www.etsy.com/shop/OrelCeramics"></textarea>', "A shop that isn't in our panel yet is added today and shows up from the next daily read.") + "</div>" +
        '<div class="frow">' +
        '<div data-show="category breakouts">' + field("f-category", "Category", "<select id=f-category>" + catOpts + "</select>") + "</div>" +
        '<div data-show="category breakouts">' + field("f-maxshops", "How many shops (at most)", '<input id="f-maxshops" type="number" min="1" max="20000" inputmode="numeric" value="20">' +
          '<span class="quick" data-target="f-maxshops"><button type="button" data-v="20">20</button><button type="button" data-v="100">100</button><button type="button" data-v="500">500</button><button type="button" data-v="2000">2,000</button></span>', "Any number up to 20,000. You only pay for shops returned.") + "</div>" +
        "</div></div></div>" +
      '<details class="adv bstep" id="adv"><summary>Advanced options <small>filters, ranking, columns, every Actor setting</small></summary><div class="advin">' +
        '<div data-for="search">' +
          sub("Search filters (applied by Etsy)") +
          '<div class="frow">' + field("f-minprice", "Lowest price", '<input id="f-minprice" type="number" min="0" inputmode="numeric" placeholder="any">', "Whole units of the shopper's currency.") +
          field("f-maxprice", "Highest price", '<input id="f-maxprice" type="number" min="0" inputmode="numeric" placeholder="any">') +
          field("f-days", "Ready to ship within (days)", '<input id="f-days" type="number" min="1" max="60" inputmode="numeric" placeholder="any">') + "</div>" +
          '<div class="chks">' + check("f-is_best_seller", "Bestsellers only") + check("f-is_star_seller", "Star Seller shops only") + check("f-free_shipping", "Free shipping only") +
          check("f-is_discounted", "On sale only") + check("f-instant_download", "Digital downloads only") + check("f-is_handmade_only", "Handmade only") + check("f-is_personalizable", "Personalizable only") + "</div>" +
          sub("What to search besides keywords") +
          field("f-market", "Etsy market pages <em>(one phrase per line)</em>", '<textarea id="f-market" rows="2" placeholder="personalized dog collar"></textarea>', "Etsy's /market/ page for a phrase. Each line is one more run.") +
          field("f-caturls", "Etsy category links <em>(one per line)</em>", '<textarea id="f-caturls" rows="2" placeholder="https://www.etsy.com/c/jewelry/necklaces"></textarea>', "Read in Etsy's default order. Each line is one more run.") +
          sub("Where and how Etsy is read") +
          '<div class="frow">' + field("f-shipto", "Only listings that ship to", "<select id=f-shipto>" + opt("", "Anywhere") + countries.map(function (c) { return opt(c[0], c[1]); }).join("") + "</select>") +
          field("f-region", "See prices as a shopper in", "<select id=f-region>" + countries.map(function (c) { return opt(c[0], c[1], c[0] === "US"); }).join("") + "</select>", "Sets the proxy country; Etsy shows that country's currency.") +
          field("f-pages", "Pages per keyword", '<input id="f-pages" type="number" min="1" max="20" inputmode="numeric" placeholder="auto">', "Leave empty: worked out from the listing count.") + "</div>" +
          check("f-fill", "Return every listing on each page (recommended; off = 12 per page, faster)", true) +
          '<div class="frow">' + field("f-proxymode", "Proxy", "<select id=f-proxymode>" + opt("apify", "Apify residential (recommended)") + opt("own", "My own proxy URLs") + "</select>", "Etsy blocks datacenter IPs. Apify's proxy cost is included in the price.") +
          field("f-source", "Label for this run", '<input id="f-source" placeholder="etsypulse-site-builder">', "Copied onto every row; handy for filtering later.") + "</div>" +
          '<div data-show-proxy>' + field("f-proxyurls", "Proxy URLs <em>(one per line)</em>", '<textarea id="f-proxyurls" rows="2" placeholder="http://user:pass@host:port"></textarea>') + "</div>" +
        "</div>" +
        '<div data-for="tracker">' +
          sub("Which shops") +
          '<div data-show="category breakouts">' + field("f-shops2", "Only these shops <em>(optional, one per line)</em>", '<textarea id="f-shops2" rows="2" placeholder="leave empty for the whole category"></textarea>') + "</div>" +
          '<div data-show="velocity rivals">' + field("f-category2", "Only shops in this category <em>(optional)</em>", "<select id=f-category2>" + catOpts + "</select>") + "</div>" +
          field("f-shopkw", "Words in the shop name or headline <em>(optional)</em>", '<input id="f-shopkw" placeholder="e.g. ceramics, wedding">', "Any of the words matches.") +
          '<div class="frow">' + field("f-minsales", "At least this many lifetime sales", '<input id="f-minsales" type="number" min="0" inputmode="numeric" placeholder="0">') +
          field("f-minrate", "At least this many sales a day (estimated)", '<input id="f-minrate" type="number" min="0" inputmode="numeric" placeholder="0">') +
          field("f-since", "Numbers changed on or after", '<input id="f-since" type="date">') + "</div>" +
          '<div data-show="velocity rivals category">' + check("f-breakout", "Breakout shops only (last 7 days far above their usual pace)") + "</div>" +
          '<div data-show="velocity rivals">' + field("f-maxshops2", "How many shops (at most)", '<input id="f-maxshops2" type="number" min="1" max="20000" inputmode="numeric" placeholder="all you listed">') + "</div>" +
        "</div>" +
        sub("After the run: rank and filter the results") +
        '<p class="hint">Applied to what comes back, so you can keep e.g. the 10 cheapest, the 25 with the most reviews, or only shops gaining 50+ sales a week. You can change this on the report too.</p>' +
        '<div id="refine-b"></div>' +
        sub("Report sections") + '<div class="blocks" id="blockpick"></div>' +
        sub("Columns in the table and spreadsheet") + '<div class="chks" id="colpick"></div>' +
        sub("Run settings") +
        '<div class="frow">' + field("f-memory", "Memory per run", "<select id=f-memory>" + opt("", "Auto") + opt("1024", "1 GB") + opt("2048", "2 GB") + opt("4096", "4 GB") + "</select>", "Auto is fine. More memory doesn't change the Actor price.") +
        field("f-timeout", "Stop a run after (minutes)", '<input id="f-timeout" type="number" min="1" max="1440" inputmode="numeric" placeholder="auto">', "Auto: 15–60 min depending on size. Rows read before a stop are kept.") +
        field("f-parallel", "Keywords running at once", "<select id=f-parallel>" + opt("1", "1") + opt("2", "2") + opt("3", "3", true) + opt("4", "4") + opt("5", "5") + "</select>", "Apify's free plan allows 5 runs at a time.") + "</div>" +
      "</div></details>" +
      '<div class="brun" id="brun"></div>';
    $$(".tcard", app).forEach(function (b) { b.onclick = function () { setType(b.dataset.type); }; });
    $$(".quick button", app).forEach(function (b) { b.onclick = function () { var el = document.getElementById(b.parentNode.dataset.target); el.value = b.dataset.v; refresh(); }; });
    var m2 = $("#f-maxshops2"); m2.oninput = function () { $("#f-maxshops").value = m2.value; };
    app.addEventListener("input", function (e) { if (!e.target.closest("#refine-b")) refresh(); });
    app.addEventListener("change", function (e) { if (!e.target.closest("#refine-b")) refresh(); });
    if (q) { $("#f-queries").value = q; }
  }

  function setType(k, keepPicks) {
    var prev = state.type; state.type = k; var t = TYPES[k];
    $$(".tcard").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.type === k ? "true" : "false"); });
    $$("[data-for]").forEach(function (el) { el.hidden = el.dataset.for !== t.actor; });
    $$("[data-show]").forEach(function (el) { el.hidden = el.dataset.show.split(" ").indexOf(k) < 0; });
    if (!keepPicks) { state.blocks = t.blocks.slice(); state.cols = t.cols.slice(); if (TYPES[prev] && TYPES[prev].actor !== t.actor) state.refine = { by: "", dir: "top", n: "", filters: [] }; }
    if (prev === "breakouts" && k !== "breakouts") $("#f-breakout").checked = false;
    // named-shop reports: default "how many" = number of shops listed
    if ((k === "velocity" || k === "rivals") && (prev === "category" || prev === "breakouts")) $("#f-maxshops").value = $("#f-maxshops2").value || "";
    if ((k === "category" || k === "breakouts") && !$("#f-maxshops").value) $("#f-maxshops").value = 20;
    $("#f-queries").placeholder = k === "compare" ? "ceramic mug\nstoneware mug\nhandmade mug" : "ceramic mug\npersonalized dog collar";
    renderPicks(); renderRefine(); refresh();
  }

  function knownCols(actor) {
    return actor === "search"
      ? ["position", "title", "price", "currency", "shop_name", "rating_value", "review_count", "review_count_approx", "bestseller", "popular_now", "star_seller", "etsys_pick", "free_shipping", "is_ad", "query", "page", "total_results", "url", "shop_url", "listing_id", "shop_id", "surface", "source"]
      : ["shop", "title", "headline", "category", "sales_count", "sales_precision", "sales_per_day", "delta_last", "delta_7d", "delta_28d", "units_day", "units_lo", "units_hi", "lift_7d", "breakout", "breakout_p", "reviews_count", "rating", "admirers", "listings_active", "as_of", "read_interval_days", "first_seen", "last_changed", "history_days", "vintage_event", "snapshot_date", "snapshot_stale", "shop_url"];
  }
  function blocksFor(actor) {
    var s = { prices: 1, badges: 1, bestprice: 1, shops: 1, shoptable: 1, compare: 1 }, tr = { velocity: 1, rivals: 1 };
    return Object.keys(BLOCKS).filter(function (b) { return actor === "search" ? !tr[b] : !s[b]; });
  }
  function renderPicks() {
    var t = TYPES[state.type];
    $("#blockpick").innerHTML = blocksFor(t.actor).map(function (b) {
      return '<label class="pill"><input type="checkbox" value="' + b + '"' + (state.blocks.indexOf(b) >= 0 ? " checked" : "") + "><span>" + BLOCKS[b] + "</span></label>";
    }).join("");
    $$("#blockpick input").forEach(function (i) { i.onchange = function () { state.blocks = $$("#blockpick input:checked").map(function (x) { return x.value; }); if (state.result) renderReport(); }; });
    $("#colpick").innerHTML = knownCols(t.actor).map(function (c) {
      return '<label class="chk"><input type="checkbox" value="' + c + '"' + (state.cols.indexOf(c) >= 0 ? " checked" : "") + "> <span>" + esc(LABELS[c] || c) + "</span></label>";
    }).join("");
    $$("#colpick input").forEach(function (i) { i.onchange = function () { state.cols = $$("#colpick input:checked").map(function (x) { return x.value; }); if (state.result) renderReport(); }; });
  }

  /* ------------------------------------------------------------------ rank & filter (client-side, after the run) */
  var NUMERIC = { position: 1, price: 1, rating_value: 1, review_count: 1, page: 1, total_results: 1, sales_count: 1, sales_per_day: 1, delta_last: 1, delta_7d: 1, delta_28d: 1,
    units_day: 1, units_lo: 1, units_hi: 1, lift_7d: 1, breakout_p: 1, reviews_count: 1, rating: 1, admirers: 1, listings_active: 1, history_days: 1, read_interval_days: 1 };
  var RANKABLE = {
    search: ["price", "review_count", "rating_value", "position", "total_results"],
    tracker: ["sales_per_day", "delta_7d", "delta_28d", "sales_count", "units_day", "lift_7d", "reviews_count", "admirers", "listings_active", "rating", "delta_last"] };
  var RANK_WORD = { price: "Price", review_count: "Reviews", rating_value: "Rating", position: "Etsy rank (1 = top)", total_results: "Etsy results for the search",
    sales_per_day: "Sales per day", delta_7d: "Sales gained, last 7 days", delta_28d: "Sales gained, last 28 days", sales_count: "Lifetime sales", units_day: "Estimated sales per day",
    lift_7d: "7-day lift vs usual", reviews_count: "Reviews", admirers: "Followers (favorites)", listings_active: "Active listings", rating: "Rating", delta_last: "Sales since last read" };
  function ftype(f) { return NUMERIC[f] ? "num" : BOOL_HINT.test(f) ? "bool" : "text"; }
  function renderRefine() {
    if (state.inRefine) return; state.inRefine = true;
    try { renderRefine2(); } finally { state.inRefine = false; }
  }
  function renderRefine2() {
    var actor = TYPES[state.type].actor, R = state.refine;
    var fields = knownCols(actor).filter(function (f) { return !/url$|_id$|^surface$|^source$/.test(f); });
    var html = '<div class="refine"><div class="frow rank">' +
      field("rf-by", "Rank by", "<select id=\"rf-by\">" + opt("", "Don't rank (keep Etsy's order)") + RANKABLE[actor].map(function (f) { return opt(f, RANK_WORD[f] || LABELS[f], R.by === f); }).join("") + "</select>") +
      field("rf-dir", "Keep", "<select id=\"rf-dir\">" + opt("top", "Top (highest first)", R.dir === "top") + opt("bottom", "Bottom (lowest first)", R.dir === "bottom") + "</select>") +
      field("rf-n", "How many", '<input id="rf-n" type="number" min="1" inputmode="numeric" placeholder="all" value="' + esc(R.n) + '">') + "</div>" +
      '<div class="flist">' + R.filters.map(function (fl, i) {
        var ty = ftype(fl.f), ops = ty === "num" ? [[">=", "at least"], ["<=", "at most"], [">", "more than"], ["<", "less than"], ["=", "exactly"], ["!=", "not"]]
          : ty === "bool" ? [["yes", "is yes"], ["no", "is no"]] : [["has", "contains"], ["not", "doesn't contain"], ["is", "is exactly"]];
        return '<div class="fl" data-i="' + i + '"><select class="rf-f" aria-label="Field">' + fields.map(function (f) { return opt(f, LABELS[f] || f, fl.f === f); }).join("") + "</select>" +
          '<select class="rf-op" aria-label="Condition">' + ops.map(function (o) { return opt(o[0], o[1], fl.op === o[0]); }).join("") + "</select>" +
          (ty === "bool" ? "" : '<input class="rf-v" aria-label="Value" ' + (ty === "num" ? 'type="number" inputmode="decimal"' : "") + ' value="' + esc(fl.v) + '">') +
          '<button type="button" class="rf-x" aria-label="Remove filter">✕</button></div>';
      }).join("") + '</div><button type="button" class="btn2" id="rf-add">+ Add a filter</button></div>';
    ["#refine-b", "#refine-r"].forEach(function (sel) { var box = $(sel); if (box) box.innerHTML = html.replace(/id="rf-/g, 'id="' + sel.slice(1) + "-rf-").replace(/for="rf-/g, 'for="' + sel.slice(1) + "-rf-"); });
    $$(".refine").forEach(function (box) {
      var pre = box.parentNode.id + "-rf-";
      var upd = function () {
        state.refine.by = $("#" + pre + "by", box).value; state.refine.dir = $("#" + pre + "dir", box).value; state.refine.n = $("#" + pre + "n", box).value;
        state.refine.filters = $$(".fl", box).map(function (d) { var v = $(".rf-v", d); return { f: $(".rf-f", d).value, op: $(".rf-op", d).value, v: v ? v.value : "" }; });
      };
      box.addEventListener("change", function (e) {
        upd(); if (e.target.classList.contains("rf-f")) { var fl = state.refine.filters[+e.target.closest(".fl").dataset.i]; fl.op = ftype(fl.f) === "num" ? ">=" : ftype(fl.f) === "bool" ? "yes" : "has"; fl.v = ""; }
        setTimeout(function () { renderRefine(); if (state.result) renderReport(true); }, 0);
      });
      box.addEventListener("input", function (e) { if (e.target.matches("input")) { upd(); if (state.result) { clearTimeout(state.rt); state.rt = setTimeout(function () { renderReport(true); }, 350); } } });
      $("#rf-add", box) || null;
      $$("button", box).forEach(function (b) {
        if (b.id === "rf-add" || b.textContent.indexOf("Add a filter") >= 0) b.onclick = function () { upd(); var f0 = RANKABLE[actor][0]; state.refine.filters.push({ f: f0, op: ">=", v: "" }); renderRefine(); };
        if (b.classList.contains("rf-x")) b.onclick = function () { upd(); state.refine.filters.splice(+b.closest(".fl").dataset.i, 1); renderRefine(); if (state.result) renderReport(); };
      });
    });
  }
  function applyRefine(rows) {
    var R = state.refine || {}, out = rows.slice();
    (R.filters || []).forEach(function (fl) {
      var ty = ftype(fl.f), v = fl.v;
      if (ty !== "bool" && (v === "" || v == null)) return;
      out = out.filter(function (r) {
        var x = r[fl.f];
        if (ty === "bool") return fl.op === "yes" ? x === true : x !== true;
        if (ty === "num") { if (x == null || !isFinite(x)) return false; var y = parseFloat(v); return { ">=": x >= y, "<=": x <= y, ">": x > y, "<": x < y, "=": x === y, "!=": x !== y }[fl.op]; }
        var s = String(fl.f === "category" ? unesc(x) : x == null ? "" : x).toLowerCase(), w = String(v).toLowerCase();
        return fl.op === "has" ? s.indexOf(w) >= 0 : fl.op === "not" ? s.indexOf(w) < 0 : s === w;
      });
    });
    if (R.by) {
      var d = R.dir === "bottom" ? 1 : -1;
      out.sort(function (a, b) { var x = a[R.by], y = b[R.by]; if (x == null) return 1; if (y == null) return -1; return (x - y) * d; });
    }
    var n = parseInt(R.n, 10); if (n > 0) out = out.slice(0, n);
    return out;
  }
  function refineWords() {
    var R = state.refine || {}, w = [];
    if (R.by) w.push((R.dir === "bottom" ? "lowest" : "highest") + " " + (RANK_WORD[R.by] || LABELS[R.by]).toLowerCase() + " first" + (parseInt(R.n, 10) > 0 ? ", " + R.dir + " " + R.n : ""));
    else if (parseInt(R.n, 10) > 0) w.push("first " + R.n);
    (R.filters || []).forEach(function (f) { if (ftype(f.f) === "bool" || f.v !== "") w.push((LABELS[f.f] || f.f) + " " + ({ ">=": "≥", "<=": "≤", ">": ">", "<": "<", "=": "=", "!=": "≠", yes: "= yes", no: "= no", has: "contains", not: "doesn't contain", is: "is" }[f.op]) + (ftype(f.f) === "bool" ? "" : " " + f.v)); });
    return w.join(" · ");
  }

  function refresh() {
    var plan = buildPlan(), t = TYPES[state.type], a = ACTORS[t.actor], tok = ss.get("ep_tok");
    var mx = $("#f-proxymode"); $$("[data-show-proxy]").forEach(function (el) { el.hidden = !mx || mx.value !== "own"; });
    var empty = !plan.jobs.length || !plan.rows;
    var nUnits = t.actor === "search" ? num(plan.rows) + " listings" : "up to " + num(plan.rows) + " shops";
    var errs = plan.errors.length && state.tried ? '<div class="berr">' + plan.errors.map(esc).join("<br>") + "</div>" : "";
    var warns = plan.warns.length ? '<div class="bwarn">' + plan.warns.map(esc).join("<br>") + "</div>" : "";
    var who = state.user ? '<div class="who">Signed in to Apify as <b>' + esc(state.user.username) + '</b> · <a href="#" id="signout">sign out</a></div>' : "";
    var fallbackHref = CFG.worker + "/r/site-run?a=" + t.actor + "&t=" + state.type + (t.actor === "search" && plan.combined.queries ? "&q=" + encodeURIComponent(plan.combined.queries.slice(0, 5).join(", ")) : "") + utmPass();
    var plat = plan.platform ? " + Apify platform usage, usually under " + usd(plan.platform) + " per run (billed separately for this tool)" : " (Apify platform usage included)";
    var conf = plan.bigConfirm ? '<label class="bigconf"><input type="checkbox" id="bigok"' + (state.bigok === plan.max ? " checked" : "") + "> Yes, run it: this report can cost up to <b>" + usd(plan.max + plan.platform) + "</b> on my Apify account.</label>" : "";
    $("#brun").innerHTML = errs + warns +
      (empty ? '<div class="cost"><b>' + (t.actor === "search" ? "Add a keyword above to see the price" : "Add a shop above to see the price") + '</b><span>' + usd(a.unit) + " per " + (t.actor === "search" ? "listing" : "shop") + " + " + usd(a.start) + " per run" + plat + ".</span></div>" :
      '<div class="cost"><b>About ' + usd(plan.est) + ", at most " + usd(plan.max) + '</b><span>' + nUnits + " × " + usd(a.unit) + " + " + usd(a.start) + " start fee" + (plan.jobs.length > 1 ? " × " + plan.jobs.length + " runs" : "") + plat +
      ". You pay only for rows delivered; Apify stops the run at the maximum. Apify's free plan includes $5 of usage every month, no card needed.</span></div>") + conf +
      '<button type="button" class="runbtn" id="runbtn">' + (tok ? "Run my report →" : "Sign in with Apify &amp; run →") + "</button>" + who +
      (tok ? "" : '<p class="perm">Apify will ask you to approve <b>Etsy Pulse by publicrecords</b>. Apify only offers one permission level (full account access), so here is exactly what we do with it: start this report on your account and read its results, from this page. The key stays in this browser tab, is deleted when you close it, and never touches our servers. You can remove the approval any time in Apify Console → Settings → API &amp; Integrations.</p>') +
      '<p class="alt"><a href="#" id="demo">See an example report first</a> · <a href="#" id="showfb">Rather run it inside Apify?</a></p>' +
      '<div id="fb" class="fb"' + (state.fbOpen ? "" : " hidden") + '><ol><li><a class="btn2" href="' + esc(fallbackHref) + '" target="_blank" rel="noopener">Open the ' + a.name + " on Apify</a> (free sign-up if you're new).</li>" +
      "<li>Above the form, switch the input view from <b>Manual</b> to <b>JSON</b>, then paste these settings:<pre id=fbjson>" + esc(JSON.stringify(plan.combined, null, 2)) + '</pre><button type="button" class="btn2" id="copyjson">Copy settings</button></li>' +
      "<li>Press <b>Start</b>. When it finishes, open <b>Export</b> to download a spreadsheet (CSV or Excel).</li></ol></div>";
    $("#runbtn").onclick = function () { go(buildPlan()); };
    var bk = $("#bigok"); if (bk) bk.onchange = function () { state.bigok = bk.checked ? plan.max : null; };
    var sb = $("#stickyrun"); if (sb) sb.innerHTML = "<span>" + esc(t.title) + (empty ? "" : " · about " + usd(plan.est)) + "</span><button type=\"button\">Run ↓</button>";
    $("#demo").onclick = function (e) { e.preventDefault(); demo(); };
    $("#showfb").onclick = function (e) { e.preventDefault(); state.fbOpen = !state.fbOpen; $("#fb").hidden = !state.fbOpen; if (state.fbOpen) beacon("fallback-open"); };
    $("#copyjson").onclick = function () { navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(plan.combined, null, 2)); this.textContent = "Copied ✓"; beacon("fallback-copy"); };
    var so = $("#signout"); if (so) so.onclick = function (e) { e.preventDefault(); ss.del("ep_tok"); state.user = null; refresh(); };
  }
  function utmPass() { var p = new URLSearchParams(location.search), o = ""; p.forEach(function (v, k) { if (/^utm_/.test(k)) o += "&" + k + "=" + encodeURIComponent(v); }); return o; }

  /* ------------------------------------------------------------------ OAuth */
  function snapshotForm() { var o = {}; $$("#builder input, #builder select, #builder textarea").forEach(function (el) { if (el.id) o[el.id] = el.type === "checkbox" ? el.checked : el.value; }); return o; }
  function restoreForm(o) { Object.keys(o || {}).forEach(function (id) { var el = document.getElementById(id); if (!el) return; if (el.type === "checkbox") el.checked = o[id]; else el.value = o[id]; }); }

  async function signIn(autorun) {
    var verifier = rand(48), st = rand(16);
    var challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
    ss.set("ep_pending", { verifier: verifier, state: st, type: state.type, blocks: state.blocks, cols: state.cols, refine: state.refine, bigok: state.bigok, form: snapshotForm(), autorun: !!autorun, at: Date.now() });
    beacon("signin-start");
    location.href = CFG.authUrl + "?" + new URLSearchParams({ response_type: "code", client_id: CFG.clientId, redirect_uri: redirectUri(),
      scope: "full_api_access", state: st, code_challenge: challenge, code_challenge_method: "S256" }).toString();
  }

  async function finishSignIn(params) {
    var p = ss.get("ep_pending"); ss.del("ep_pending");
    history.replaceState(null, "", location.pathname);
    if (!p || p.state !== params.get("state")) { return { error: "That sign-in link expired or came from another tab. Please press the button again." }; }
    if (params.get("error")) { beacon("signin-denied"); return { pending: p, error: params.get("error") === "access_denied" ? "No problem: you didn't approve, so nothing ran." : "Apify sign-in didn't finish (" + params.get("error") + ")." }; }
    try {
      var r = await fetch(CFG.tokenUrl, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ grant_type: "authorization_code", code: params.get("code"), redirect_uri: redirectUri(), client_id: CFG.clientId, code_verifier: p.verifier }).toString() });
      var j = await r.json();
      if (!r.ok || !j.access_token) throw new Error(j.error_description || j.error || "token exchange failed");
      ss.set("ep_tok", j.access_token);
      beacon("signin-ok");
      return { pending: p };
    } catch (e) { return { pending: p, error: "Apify sign-in didn't finish: " + e.message }; }
  }

  async function api(path, opts) {
    opts = opts || {}; var tok = ss.get("ep_tok");
    var r = await fetch(CFG.api + path, { method: opts.method || "GET", headers: Object.assign({ Authorization: "Bearer " + tok }, opts.body ? { "content-type": "application/json" } : {}), body: opts.body ? JSON.stringify(opts.body) : undefined });
    var j = null; try { j = await r.json(); } catch (e) {}
    if (r.status === 401) { ss.del("ep_tok"); state.user = null; throw Object.assign(new Error("Your Apify sign-in expired. Press the button to sign in again."), { code: 401 }); }
    if (!r.ok) { var m = (j && j.error && (j.error.message || j.error.type)) || ("HTTP " + r.status); throw Object.assign(new Error(friendly(m, j)), { code: r.status }); }
    return j && j.data !== undefined ? j.data : j;
  }
  function friendly(m, j) {
    var t = (j && j.error && j.error.type) || "";
    if (/usage|limit|credit|payment|insufficient|exceed/i.test(m + t)) return "Apify says your account is out of usage for this month (" + m + "). The free plan resets monthly; a paid plan lifts the limit.";
    if (/memory/i.test(m + t)) return "Apify says your account is already running other jobs (" + m + "). Wait for them to finish and try again.";
    return m;
  }
  async function loadUser() { try { state.user = await api("/users/me"); } catch (e) { if (e.code === 401) state.user = null; } }

  /* ------------------------------------------------------------------ runs */
  function go(plan) {
    if (plan.errors.length) { state.tried = true; refresh(); var f = $("#step2"); if (f) f.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    if (plan.bigConfirm && state.bigok !== plan.max) { state.tried = true; refresh(); var c = $(".bigconf"); if (c) { c.classList.add("shake"); c.scrollIntoView({ behavior: "smooth", block: "center" }); } return; }
    if (!ss.get("ep_tok")) { signIn(true); return; }
    runPlan(plan);
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  async function allItems(dsId, onPage) {
    var out = [], off = 0, lim = 1000;
    for (;;) {
      var page = await api("/datasets/" + dsId + "/items?clean=1&format=json&offset=" + off + "&limit=" + lim);
      if (!page || !page.length) break; out = out.concat(page); off += page.length; if (onPage) onPage(out.length);
      if (page.length < lim) break;
    }
    return out;
  }
  async function runPlan(plan) {
    var t = TYPES[state.type], a = ACTORS[t.actor];
    var prog = $("#progress"), rep = $("#report");
    rep.hidden = true; prog.hidden = false; prog.scrollIntoView({ behavior: "smooth", block: "start" });
    var jobs = plan.jobs.map(function (j) { return Object.assign({ status: "waiting", rows: 0 }, j); });
    var par = clamp(parseInt(val("f-parallel"), 10) || 3, 1, 5), t0 = Date.now();
    var draw = function (msg) {
      var done = jobs.filter(function (j) { return /SUCCEEDED|FAILED|ABORTED|TIMED|error/.test(j.status); }).length, rows = jobs.reduce(function (s, j) { return s + (j.rows || 0); }, 0);
      var list = jobs.length > 12 ? jobs.filter(function (j) { return !/waiting|SUCCEEDED/.test(j.status); }).slice(0, 12) : jobs;
      prog.innerHTML = '<div class="pcard"><h2>Running your report…</h2><p class="sub">' + (msg || (jobs.length > 1 ? done + " of " + jobs.length + " runs finished · " + num(rows) + " rows so far. " : "") + "Keep this tab open. Small reports take 1–3 minutes; big ones longer.") + "</p>" +
        list.map(function (j) {
          var ok = j.status === "SUCCEEDED", bad = /FAILED|ABORTED|TIMED|error/i.test(j.status);
          return '<div class="pj' + (ok ? " ok" : bad ? " bad" : j.status === "waiting" ? " wait" : "") + '"><span class="dot"></span><b>' + esc(j.label) + "</b><span>" + esc(statusWord(j)) + "</span></div>";
        }).join("") + (jobs.length > 12 ? '<p class="note">Showing runs in progress; ' + jobs.filter(function (j) { return j.status === "waiting"; }).length + " waiting.</p>" : "") + "</div>";
    };
    draw(); beacon("run-start", "n=" + jobs.length + "&rows=" + plan.rows);
    async function startJob(j) {
      for (var attempt = 0; attempt < 30; attempt++) {
        try {
          j.run = await api("/acts/" + a.id + "/runs?memory=" + j.memory + "&timeout=" + j.timeout + "&maxTotalChargeUsd=" + j.cap, { method: "POST", body: j.input });
          j.status = j.run.status; return;
        } catch (e) {
          if (/already running other jobs|memory|concurren/i.test(e.message) && attempt < 29) { j.status = "waiting"; j.wait = "waiting for a free slot on your Apify account"; draw(); await sleep(15000); continue; }
          j.status = "error"; j.err = e.message; return;
        }
      }
    }
    async function watch(j) {
      while (j.run && /READY|RUNNING/.test(j.status)) {
        await sleep(4000);
        try { var r = await api("/actor-runs/" + j.run.id); j.run = r; j.status = r.status; var ds = await api("/datasets/" + r.defaultDatasetId); j.rows = ds.itemCount || 0; } catch (e) {}
        draw(Date.now() - t0 > 300000 && jobs.length === 1 ? "Still reading Etsy. Big reports and Etsy slow-downs take longer; it will finish or stop at your time limit, and you keep every row read." : null);
      }
    }
    var queue = jobs.slice();
    async function worker() { while (queue.length) { var j = queue.shift(); j.status = "starting"; draw(); await startJob(j); draw(); await watch(j); draw(); } }
    var workers = []; for (var w = 0; w < Math.min(par, jobs.length); w++) { workers.push(worker()); await sleep(300); }
    await Promise.all(workers);
    if (jobs.every(function (j) { return j.status === "error"; })) {
      prog.innerHTML = '<div class="pcard bad"><h2>That didn\'t start</h2><p>' + esc(jobs[0].err) + '</p><p><button type="button" class="btn2" id="retry">Try again</button></p></div>';
      $("#retry").onclick = function () { runPlan(buildPlan()); }; beacon("run-fail-start"); refresh(); return;
    }
    var rows = [], runs = [];
    for (var i = 0; i < jobs.length; i++) {
      var j = jobs[i]; if (!j.run) continue;
      runs.push({ id: j.run.id, label: j.label, status: j.status });
      try {
        draw("Collecting results… " + num(rows.length) + " rows");
        var items = await allItems(j.run.defaultDatasetId);
        items.forEach(function (r) { if (t.actor === "search" && !r.query) r.query = j.label; rows.push(r); });
      } catch (e) {}
    }
    var bad = jobs.filter(function (j) { return j.status !== "SUCCEEDED"; });
    state.result = { type: state.type, actor: t.actor, rows: rows, runs: runs, at: new Date().toISOString(), live: true,
      warn: bad.length ? bad.slice(0, 5).map(function (j) { return j.label + ": " + statusWord(j); }).join("; ") + (bad.length > 5 ? " (+" + (bad.length - 5) + " more)" : "") : "" };
    try { if (rows.length <= 3000) ss.set("ep_last", state.result); else ss.del("ep_last"); } catch (e) {}
    beacon(rows.length ? "run-ok" : "run-empty", "rows=" + rows.length);
    prog.hidden = true; state.page = 1; rep.dataset.shown = ""; renderReport(); refresh();
  }
  function statusWord(j) {
    return { waiting: j.wait || "waiting its turn", starting: "starting…", READY: "queued at Apify…", RUNNING: "reading Etsy… " + (j.rows ? num(j.rows) + " rows so far" : ""), SUCCEEDED: "done · " + num(j.rows) + " rows",
      FAILED: "failed. You are only charged for rows delivered; please try again in a few minutes", "TIMED-OUT": "hit the time limit · " + num(j.rows) + " rows kept", ABORTED: "stopped · " + num(j.rows) + " rows kept", error: "didn't start: " + (j.err || "") }[j.status] || j.status;
  }

  async function demo() {
    var t = TYPES[state.type], f = t.actor === "search" ? "assets/sample-search.json" : "assets/sample-tracker.json";
    var j = await (await fetch(f)).json(), rows = j.rows;
    if (t.actor === "search" && state.type !== "compare") rows = rows.filter(function (r) { return r.query === "aprons"; });
    state.result = { type: state.type, actor: t.actor, rows: rows, runs: [], at: j.captured, live: false,
      demo: t.actor === "search" ? "Example: a real run of our Etsy Search Scraper captured " + j.captured + " (Apify run " + j.run + ")." : "Example: real rows from our Etsy Shop Sales Tracker, snapshot " + j.captured + ". Today's numbers will differ." };
    $("#report").dataset.shown = ""; state.page = 1; beacon("demo"); renderReport();
  }

  /* ------------------------------------------------------------------ report */
  function bars(items, fmt, opts) {
    opts = opts || {}; var mx = Math.max.apply(null, items.map(function (x) { return x[1] || 0; })) || 1;
    return '<div class="bars">' + items.map(function (x) {
      return '<div class="br"><span class="bl" title="' + esc(x[0]) + '">' + esc(x[0]) + '</span><span class="bt"><i style="width:' + Math.max(1.5, 100 * (x[1] || 0) / mx).toFixed(1) + '%"></i></span><b>' + fmt(x[1], x) + "</b></div>";
    }).join("") + "</div>";
  }
  function card(title, inner, sub) { return '<div class="rblock"><h3>' + title + "</h3>" + (sub ? '<p class="sub">' + sub + "</p>" : "") + inner + "</div>"; }
  function kpis(list) { return '<div class="kpis">' + list.map(function (k) { return '<div class="kpi"><div class="v">' + k[0] + '</div><div class="l">' + k[1] + "</div></div>"; }).join("") + "</div>"; }
  function groupBy(rows, f) { var m = {}; rows.forEach(function (r) { var k = r[f] == null ? "–" : r[f]; (m[k] = m[k] || []).push(r); }); return m; }
  function priceBands(prices) {
    var p25 = quant(prices, .25), p75 = quant(prices, .75); if (p25 == null) return [];
    var cuts = [0, Math.round(p25), Math.round(median(prices)), Math.round(p75)].filter(function (x, i, a) { return i === 0 || (x > 0 && x > a[i - 1]); });
    cuts = cuts.filter(function (x, i) { return cuts.indexOf(x) === i; }).concat([Infinity]);
    var c = cur(state.result.rows);
    return cuts.slice(0, -1).map(function (lo, i) {
      var hi = cuts[i + 1], n = prices.filter(function (p) { return p >= lo && p < hi; }).length;
      return [hi === Infinity ? c + lo + "+" : lo === 0 ? "under " + c + hi : c + lo + "–" + c + hi, n];
    });
  }

  function searchReport(rows, B) {
    var c = cur(rows), prices = rows.map(function (r) { return r.price; }).filter(function (x) { return typeof x === "number"; });
    var byQ = groupBy(rows, "query"), qs = Object.keys(byQ), out = [], tk = [];
    var med = median(prices), p25 = quant(prices, .25), p75 = quant(prices, .75), bs = share(rows, "bestseller"), fs = share(rows, "free_shipping");
    var shops = groupBy(rows, "shop_name"), shopList = Object.keys(shops).map(function (s) {
      var a = shops[s]; return { shop: s, n: a.length, best: Math.min.apply(null, a.map(function (r) { return r.position || 999; })), med: median(a.map(function (r) { return r.price; })),
        rev: Math.max.apply(null, a.map(function (r) { return r.review_count || 0; })), bs: a.filter(function (r) { return r.bestseller; }).length, url: a[0].shop_url };
    }).sort(function (a, b) { return b.n - a.n || a.best - b.best; });
    var totalRes = qs.map(function (q) { return (byQ[q][0] || {}).total_results; }).filter(Boolean);
    if (B.kpis) out.push(kpis([[num(rows.length), "listings read" + (qs.length > 1 ? " across " + qs.length + " keywords" : "")], [money(med, c), "median price"],
      [money(p25, c) + "–" + money(p75, c), "middle half of prices"], [pct(bs), "carry a Bestseller badge"]].concat(totalRes.length === 1 ? [[num(totalRes[0]), "results Etsy shows for this search"]] : [[pct(fs), "offer free shipping"]])));
    if (med != null) tk.push("Half of these listings are priced between <b>" + money(p25, c) + "</b> and <b>" + money(p75, c) + "</b>; the middle price is <b>" + money(med, c) + "</b>. Pricing inside that band puts you where page 1 already is.");
    var bsr = rows.filter(function (r) { return r.bestseller; }), rest = rows.filter(function (r) { return !r.bestseller; });
    var mb = median(bsr.map(function (r) { return r.price; })), mr = median(rest.map(function (r) { return r.price; }));
    if (bsr.length >= 3 && rest.length >= 3) tk.push("<b>" + pct(bs) + "</b> carry a Bestseller badge. Their middle price is <b>" + money(mb, c) + "</b> vs <b>" + money(mr, c) + "</b> for the rest" + (mb > mr * 1.1 ? ": buyers here pay up for proven listings." : mb < mr * .9 ? ": the badge goes to the cheaper end." : ": about the same, so the badge isn't about price here."));
    if (shopList.length && shopList[0].n > 1) tk.push("<b>" + esc(shopList[0].shop) + "</b> holds " + shopList[0].n + " of the " + rows.length + " spots" + (shopList[1] && shopList[1].n > 1 ? ", then " + esc(shopList[1].shop) + " (" + shopList[1].n + ")" : "") + "; " + (shopList.filter(function (s) { return s.n === 1; }).length) + " other shops have one listing each.");
    else if (shopList.length) tk.push("Every listing here comes from a different shop (" + shopList.length + " shops): nobody dominates this search.");
    var revs = rows.map(function (r) { return r.review_count; }).filter(isFinite);
    if (revs.length) tk.push("The middle listing shows <b>" + num(median(revs)) + "</b> reviews on its card" + (median(revs) < 300 ? ", a low bar: newer shops can compete here." : median(revs) > 2000 ? ", a high bar: established shops own this search." : "."));
    if (fs != null) tk.push("<b>" + pct(fs) + "</b> offer free shipping" + (fs >= .5 ? ", so buyers here expect it." : "."));
    if (qs.length > 1) {
      var stats = qs.map(function (q) { var a = byQ[q]; return { q: q, med: median(a.map(function (r) { return r.price; })), bs: share(a, "bestseller"), tr: (a[0] || {}).total_results }; });
      var hi = stats.slice().sort(function (a, b) { return b.med - a.med; })[0], lo = stats.slice().sort(function (a, b) { return a.med - b.med; })[0];
      tk.unshift("<b>“" + esc(hi.q) + "”</b> has the highest middle price (" + money(hi.med, c) + "), <b>“" + esc(lo.q) + "”</b> the lowest (" + money(lo.med, c) + ").");
      var trs = stats.filter(function (s) { return s.tr; }); if (trs.length > 1) { var least = trs.sort(function (a, b) { return a.tr - b.tr; })[0]; tk.push("Least crowded: <b>“" + esc(least.q) + "”</b> with " + num(least.tr) + " Etsy results."); }
    }
    if (B.takeaways && tk.length) out.push('<div class="insights"><h3>What this means for you</h3><ul>' + tk.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div>");
    if (B.compare && qs.length > 1) {
      var rowsC = qs.map(function (q) { var a = byQ[q], pr = a.map(function (r) { return r.price; }); return { q: q, n: a.length, med: median(pr), p25: quant(pr, .25), p75: quant(pr, .75), bs: share(a, "bestseller"), fs: share(a, "free_shipping"), rv: median(a.map(function (r) { return r.review_count; })), tr: (a[0] || {}).total_results }; });
      out.push(card("Keyword comparison", bars(rowsC.map(function (r) { return [r.q, r.med]; }), function (v) { return money(v, c); }) +
        '<div class="tscroll"><table class="dt"><thead><tr><th>Keyword</th><th>Listings</th><th>Median price</th><th>Middle half</th><th>Bestseller</th><th>Free ship</th><th>Median reviews</th><th>Etsy results</th></tr></thead><tbody>' +
        rowsC.map(function (r) { return "<tr><td>" + esc(r.q) + "</td><td>" + r.n + "</td><td>" + money(r.med, c) + "</td><td>" + money(r.p25, c) + "–" + money(r.p75, c) + "</td><td>" + pct(r.bs) + "</td><td>" + pct(r.fs) + "</td><td>" + num(r.rv) + "</td><td>" + num(r.tr) + "</td></tr>"; }).join("") + "</tbody></table></div>", "Median page-1 price per keyword."));
    }
    if (B.prices && prices.length) {
      if (qs.length > 1) out.push(card("Price bands", qs.map(function (q) { var pr = byQ[q].map(function (r) { return r.price; }).filter(isFinite); return "<h4>“" + esc(q) + "”</h4>" + bars(priceBands(pr), function (v) { return v + " listings"; }); }).join(""), "Bands split at each keyword's quarter points."));
      else out.push(card("Price bands", bars(priceBands(prices), function (v) { return v + " listings"; }), "Listings per price band (bands split at the quarter points)."));
    }
    if (B.badges) out.push(card("Badges on page 1", bars([["Bestseller", share(rows, "bestseller")], ["Popular now", share(rows, "popular_now")], ["Star Seller", share(rows, "star_seller")], ["Etsy's Pick", share(rows, "etsys_pick")], ["Free shipping", share(rows, "free_shipping")]], function (v) { return pct(v); }), "Share of listings carrying each badge."));
    if (B.bestprice && bsr.length && rest.length) out.push(card("Bestsellers vs the rest", '<div class="kpis two">' +
      '<div class="kpi"><div class="v">' + money(mb, c) + '</div><div class="l">median price, ' + bsr.length + " Bestseller listings</div></div>" +
      '<div class="kpi"><div class="v">' + money(mr, c) + '</div><div class="l">median price, ' + rest.length + " other listings</div></div>" +
      '<div class="kpi"><div class="v">' + num(median(bsr.map(function (r) { return r.review_count; }))) + '</div><div class="l">median reviews, Bestsellers</div></div>' +
      '<div class="kpi"><div class="v">' + num(median(rest.map(function (r) { return r.review_count; }))) + '</div><div class="l">median reviews, others</div></div></div>'));
    if (B.shops && shopList.length) out.push(card("Shops with the most spots", bars(shopList.slice(0, 10).map(function (s) { return [s.shop, s.n]; }), function (v) { return v + (v === 1 ? " spot" : " spots"); }), "Listings each shop has in these results (top 10)."));
    if (B.shoptable && shopList.length) out.push(card("Shop leaderboard", '<div class="tscroll"><table class="dt"><thead><tr><th>Shop</th><th>Spots</th><th>Best rank</th><th>Median price</th><th>Most reviews</th><th>Bestsellers</th></tr></thead><tbody>' +
      shopList.slice(0, 25).map(function (s) { return '<tr><td><a href="' + esc(s.url) + '" rel="nofollow noopener" target="_blank">' + esc(s.shop) + "</a></td><td>" + s.n + "</td><td>#" + s.best + "</td><td>" + money(s.med, c) + "</td><td>" + num(s.rev) + "</td><td>" + s.bs + "</td></tr>"; }).join("") + "</tbody></table></div>"));
    return out;
  }

  function trackerReport(rows, B) {
    rows.forEach(function (r) { if (r.category) r.category = unesc(r.category); });
    var out = [], tk = [], pace = function (r) { return r.sales_per_day != null ? r.sales_per_day : r.units_day; };
    var byPace = rows.slice().sort(function (a, b) { return (pace(b) || -1) - (pace(a) || -1); });
    var sum = rows.reduce(function (s, r) { return s + (pace(r) || 0); }, 0), br = rows.filter(function (r) { return r.breakout; });
    var has7 = rows.filter(function (r) { return r.delta_7d != null; });
    if (B.kpis) out.push(kpis([[num(rows.length), "shops in this report"], [num(sum, 0), "sales a day, all of them together"],
      [byPace[0] ? esc(byPace[0].shop) : "–", "fastest: " + (byPace[0] ? num(pace(byPace[0]), 1) + " sales/day" : "")], [num(br.length), "breakout shops"]]));
    if (byPace[0]) tk.push("<b>" + esc(byPace[0].shop) + "</b> is selling about <b>" + num(pace(byPace[0]), 1) + "</b> a day" + (byPace[1] ? ", ahead of " + esc(byPace[1].shop) + " (" + num(pace(byPace[1]), 1) + ")." : "."));
    if (has7.length) { var t7 = has7.slice().sort(function (a, b) { return b.delta_7d - a.delta_7d; })[0]; tk.push("Biggest last-7-days total: <b>" + esc(t7.shop) + "</b> with <b>" + num(t7.delta_7d) + "</b> sales."); }
    else tk.push("7-day totals appear once a shop has 7 days of reads; until then we show the measured pace between reads.");
    if (br.length) tk.push("<b>" + br.length + "</b> shop" + (br.length > 1 ? "s are" : " is") + " breaking out: last 7 days far above their own prior 4 weeks (" + br.slice(0, 3).map(function (r) { return esc(r.shop); }).join(", ") + ").");
    var young = rows.filter(function (r) { return r.sales_count != null && r.sales_count < 1000 && (pace(r) || 0) >= 3; });
    if (young.length) tk.push("Small but quick: " + young.slice(0, 3).map(function (r) { return "<b>" + esc(r.shop) + "</b> (" + num(r.sales_count) + " lifetime, " + num(pace(r), 1) + "/day)"; }).join(", ") + ".");
    var rounded = rows.filter(function (r) { return r.sales_precision === "rounded"; }).length;
    if (rounded) tk.push(rounded + " shop" + (rounded > 1 ? "s show" : " shows") + " a rounded sales counter on Etsy (e.g. 12.3k), so small daily changes can hide until the counter ticks over.");
    var stale = rows.filter(function (r) { return r.snapshot_stale; }).length; if (stale) tk.push("Heads-up: " + stale + " rows come from a snapshot older than 48 hours.");
    if (!rows.length) tk.push("No shops matched. If you named shops that aren't in our panel yet, they're added now and appear from the next daily read.");
    if (B.takeaways) out.push('<div class="insights"><h3>What this means for you</h3><ul>' + tk.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div>");
    if (B.velocity && rows.length) out.push(card("Sales pace", bars(byPace.slice(0, 20).map(function (r) { return [r.shop, pace(r)]; }), function (v, x) { return v == null ? "–" : num(v, 1) + "/day"; }), "Measured sales per day between the last two reads (model estimate where no measured pace yet)."));
    if (B.rivals && rows.length > 1) {
      var m = [["sales_count", "Lifetime sales"], ["delta_7d", "Sales, last 7 days"], ["reviews_count", "Reviews"], ["admirers", "Followers"], ["listings_active", "Active listings"]];
      out.push(card("Side by side", '<div class="grid2">' + m.filter(function (k) { return rows.some(function (r) { return r[k[0]] != null; }); }).map(function (k) {
        return "<div><h4>" + k[1] + "</h4>" + bars(rows.slice().sort(function (a, b) { return (b[k[0]] || 0) - (a[k[0]] || 0); }).map(function (r) { return [r.shop, r[k[0]]]; }), function (v) { return num(v); }) + "</div>";
      }).join("") + "</div>"));
    }
    return out;
  }

  function fmtCell(c, v, r) {
    if (v == null || v === "") return '<td class="nil">–</td>';
    if (typeof v === "boolean" || BOOL_HINT.test(c)) return "<td>" + (v === true ? "✓" : v === false ? "" : esc(v)) + "</td>";
    if (c === "title" && r.url) return '<td class="wide"><a href="' + esc(r.url) + '" target="_blank" rel="nofollow noopener">' + esc(v) + "</a></td>";
    if ((c === "shop_name" || c === "shop") && r.shop_url) return '<td><a href="' + esc(r.shop_url) + '" target="_blank" rel="nofollow noopener">' + esc(v) + "</a></td>";
    if (/url$/.test(c)) return '<td><a href="' + esc(v) + '" target="_blank" rel="nofollow noopener">open</a></td>';
    if (MONEY_COLS[c]) return '<td class="n">' + money(v, r.currency && r.currency.length <= 3 ? r.currency : "") + "</td>";
    if (typeof v === "number") return '<td class="n">' + num(v, Math.abs(v) < 10 && v % 1 ? 2 : Math.abs(v) < 100 && v % 1 ? 1 : 0) + "</td>";
    return "<td>" + esc(c === "category" ? unesc(v) : v) + "</td>";
  }
  function cols(rows) {
    var have = {}; rows.forEach(function (r) { Object.keys(r).forEach(function (k) { have[k] = 1; }); });
    var c = state.cols.filter(function (k) { return have[k]; }); return c.length ? c : Object.keys(have).slice(0, 8);
  }
  function tableHtml(rows) {
    var cs = cols(rows), s = state.sort, per = 200, shown = (state.page || 1) * per;
    if (s) rows = rows.slice().sort(function (a, b) { var x = a[s.c], y = b[s.c]; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * s.d; });
    var head = '<div class="tscroll"><table class="dt sortable"><thead><tr>' + cs.map(function (c) {
      return '<th data-c="' + c + '" aria-sort="' + (s && s.c === c ? (s.d > 0 ? "ascending" : "descending") : "none") + '">' + esc(LABELS[c] || c) + (s && s.c === c ? (s.d > 0 ? " ▲" : " ▼") : "") + "</th>";
    }).join("") + "</tr></thead><tbody>";
    return head + rows.slice(0, shown).map(function (r) { return "<tr>" + cs.map(function (c) { return fmtCell(c, r[c], r); }).join("") + "</tr>"; }).join("") + "</tbody></table></div>" +
      (rows.length > shown ? '<p class="more"><button type="button" class="btn2" id="more">Show ' + num(Math.min(per, rows.length - shown)) + " more (" + num(rows.length - shown) + ' left)</button> <span class="note">The spreadsheet always has every row.</span></p>' : "");
  }
  function csv(rows, all) {
    var cs = all ? Object.keys(rows.reduce(function (o, r) { Object.keys(r).forEach(function (k) { o[k] = 1; }); return o; }, {})) : cols(rows);
    var q = function (v) { if (v == null) return ""; v = typeof v === "object" ? JSON.stringify(v) : String(v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    return "\ufeff" + [cs.map(function (c) { return q(all ? c : LABELS[c] || c); }).join(",")].concat(rows.map(function (r) { return cs.map(function (c) { return q(c === "category" ? unesc(r[c]) : r[c]); }).join(","); })).join("\r\n");
  }
  function download(name, text) {
    var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" })); a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }

  function renderReport(quiet) {
    var R = state.result, rep = $("#report"); if (!R) return;
    var t = TYPES[R.type], B = {}; state.blocks.forEach(function (b) { B[b] = 1; });
    var all = R.rows || [], rows = applyRefine(all), rw = refineWords();
    if (!quiet || !$("#rbody")) {
      var when = R.live ? new Date(R.at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : R.at;
      var colsAvail = Object.keys(all.reduce(function (o, r) { Object.keys(r).forEach(function (k) { o[k] = 1; }); return o; }, {}));
      rep.innerHTML = '<div class="rhead"><div class="eyebrow">Etsy Pulse · Custom report</div><h2 id="rtitle"></h2><p class="sub" id="rsub"></p>' +
        (R.demo ? '<div class="demo">' + esc(R.demo) + ' <a href="#builder">Run it on your own ' + (R.actor === "search" ? "keyword" : "shops") + " →</a></div>" : "") +
        (R.warn ? '<div class="berr">Some parts didn\'t finish: ' + esc(R.warn) + ". You were only charged for rows delivered.</div>" : "") +
        '<div class="ract"><button type="button" class="btn2 pri" id="dlcsv">⬇ Spreadsheet (CSV)</button><button type="button" class="btn2" id="dlall">⬇ All fields</button><button type="button" class="btn2" id="print">🖨 Print / save PDF</button>' +
        (R.runs && R.runs.length ? '<a class="btn2" target="_blank" rel="noopener" href="https://console.apify.com/view/runs/' + esc(R.runs[0].id) + '">Open run in Apify</a>' : "") +
        '<a class="btn2" href="#builder">New report</a></div>' +
        '<details class="adv noprint" id="rctl"' + (state.rctlOpen ? " open" : "") + '><summary>Rank, filter and choose what\'s shown</summary><div class="advin">' +
        sub("Rank and filter") + '<div id="refine-r"></div>' +
        sub("Sections") + '<div class="blocks" id="rblocks">' + blocksFor(R.actor).map(function (b) {
          return '<label class="pill"><input type="checkbox" value="' + b + '"' + (B[b] ? " checked" : "") + "><span>" + BLOCKS[b] + "</span></label>"; }).join("") + "</div>" +
        sub("Columns") + '<div class="chks" id="rcols">' +
        colsAvail.map(function (c) { return '<label class="chk"><input type="checkbox" value="' + c + '"' + (state.cols.indexOf(c) >= 0 ? " checked" : "") + "> <span>" + esc(LABELS[c] || c) + "</span></label>"; }).join("") + "</div></div></details></div>" +
        '<div id="rbody"></div>';
      rep.hidden = false;
      $("#rctl").ontoggle = function () { state.rctlOpen = $("#rctl").open; };
      $("#dlcsv").onclick = function () { download("etsy-pulse-" + R.type + "-" + String(R.at).slice(0, 10) + ".csv", csv(applyRefine(R.rows))); beacon("csv"); };
      $("#dlall").onclick = function () { download("etsy-pulse-" + R.type + "-" + String(R.at).slice(0, 10) + "-all-fields.csv", csv(applyRefine(R.rows), true)); beacon("csv"); };
      $("#print").onclick = function () { beacon("print"); window.print(); };
      $$("#rblocks input").forEach(function (i) { i.onchange = function () { state.blocks = $$("#rblocks input:checked").map(function (x) { return x.value; }); renderPicks(); renderReport(true); }; });
      $$("#rcols input").forEach(function (i) { i.onchange = function () { state.cols = $$("#rcols input:checked").map(function (x) { return x.value; }); renderPicks(); renderReport(true); }; });
      renderRefine();
    }
    var parts = R.actor === "search" ? searchReport(rows, B) : trackerReport(rows, B);
    var subj = R.actor === "search" ? Object.keys(groupBy(all, "query")).slice(0, 6).map(function (q) { return "“" + q + "”"; }).join(", ") + (Object.keys(groupBy(all, "query")).length > 6 ? "…" : "") : all.length + " shops";
    $("#rtitle").textContent = t.title + ": " + subj;
    var when2 = R.live ? new Date(R.at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : R.at;
    $("#rsub").innerHTML = esc(when2) + " · " + (rows.length !== all.length ? "<b>" + num(rows.length) + " of " + num(all.length) + " rows</b>" : num(all.length) + " rows") + " · " + esc(ACTORS[R.actor].name) + " by publicrecords on Apify" + (rw ? '<br><span class="rw">Showing: ' + esc(rw) + "</span>" : "");
    $("#rbody").innerHTML = (rows.length ? parts.join("") : '<div class="insights"><h3>No rows to show</h3><ul><li>' + (all.length ? "Your filters remove every row. Loosen them under “Rank, filter and choose what's shown”." : R.actor === "search" ? "Etsy returned no listings for this search with these filters, or blocked our reads this time (blocked pages are never charged). Try fewer filters or run again." : "No shops matched these settings. Shops you named that aren't in our panel yet are added now and appear from the next daily read.") + "</li></ul></div>") +
      (B.table && rows.length ? card("All rows", tableHtml(rows), "Tap a column name to sort. Pick columns under “Rank, filter and choose what's shown”.") : "") +
      '<p class="note">Data: public Etsy pages read by our ' + esc(ACTORS[R.actor].name) + " (publicrecords). Not affiliated with Etsy, Inc." + (R.actor === "search" ? " Prices are what Etsy shows a shopper in the chosen country." : " Sales come from each shop's public sales counter; pace is measured between our reads.") + "</p>";
    $$("th[data-c]", rep).forEach(function (th) { th.onclick = function () { var c = th.dataset.c; state.sort = state.sort && state.sort.c === c ? { c: c, d: -state.sort.d } : { c: c, d: /^(position|rank|title|shop|shop_name|query)$/.test(c) ? 1 : -1 }; renderReport(true); var tb = $(".sortable", rep); if (tb) tb.scrollIntoView({ block: "nearest" }); }; });
    var mb = $("#more"); if (mb) mb.onclick = function () { state.page = (state.page || 1) + 1; renderReport(true); };
    if (!rep.dataset.shown) { rep.dataset.shown = 1; rep.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

  function stickyBar() {
    var bar = document.createElement("div"); bar.id = "stickyrun"; bar.className = "stickyrun"; document.body.appendChild(bar);
    bar.onclick = function () { $("#brun").scrollIntoView({ behavior: "smooth", block: "center" }); };
    if (!("IntersectionObserver" in window)) return;
    var vis = {}, upd = function () { bar.classList.toggle("on", !vis.brun && !vis.report && !!vis.builder); };
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { vis[e.target.id] = e.isIntersecting; }); upd(); });
    ["builder", "brun", "report"].forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
  }

  /* ------------------------------------------------------------------ boot */
  async function boot() {
    var params = new URLSearchParams(location.search);
    try { CATS = await (await fetch("assets/tracker-categories.json")).json(); } catch (e) { CATS = []; }
    renderForm(params.get("q") || ""); stickyBar();
    var type = TYPES[params.get("type")] ? params.get("type") : "niche";
    setType(type);
    if (params.get("shops")) { $("#f-shops").value = params.get("shops").split(",").join("\n"); refresh(); }
    if (params.get("category")) { $("#f-category").value = params.get("category"); refresh(); }
    beacon("builder-view", "from=" + encodeURIComponent(params.get("from") || document.referrer.replace(/^https?:\/\/[^/]+/, "").slice(0, 40)));
    var pending = null;
    if (params.get("code") || params.get("error")) {
      var fin = await finishSignIn(params); pending = fin.pending;
      if (pending) { restoreForm(pending.form); state.blocks = pending.blocks; state.cols = pending.cols; state.refine = pending.refine || state.refine; state.bigok = pending.bigok; setType(pending.type, true); restoreForm(pending.form); renderRefine(); refresh(); }
      if (fin.error) { var e = document.createElement("div"); e.className = "berr"; e.textContent = fin.error; $("#brun").prepend(e); pending = null; }
    }
    if (ss.get("ep_tok")) { await loadUser(); refresh(); }
    if (pending && pending.autorun && ss.get("ep_tok")) { runPlan(buildPlan()); return; }
    var last = ss.get("ep_last"); if (last && !params.get("type")) { state.result = last; state.blocks = TYPES[last.type].blocks.slice(); state.cols = TYPES[last.type].cols.slice(); renderReport(); $("#report").dataset.shown = 1; }
    if (params.get("demo")) demo();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
