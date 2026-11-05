#!/usr/bin/env python3
"""FB-PACK (Mark t628u, 2026-10-08): daily ready-to-paste Facebook group pack. Nothing is posted; Meta has no Groups API,
so Mark copies and pastes by hand.

  python3 make_fb_pack.py [--repo /workspace/publicrecords-data] [--day YYYY-MM-DD] [--out-root .../facebook/packs]

Reads ONLY the exact Daily Movers export data/daily-movers/<day>/ (movers, pct, niches, rising + meta.json); every sales
figure goes through guerrilla/exact_numbers (load/check/guard semantics) and the real window is always stated.
Writes <out-root>/<day>/: pack.md (group-by-group posts + link variants + comment bank + rules), posts.txt (plain text to
copy), cards (EN + TR PNGs: niches, shops, jumps, rising), manifest.json; and points <out-root>/latest at it.
Its own guard (exact numbers, banned words, coverage counts, links = www.etsypulse.ca + from=fb-<slug> only, $ framing,
not-affiliated line) runs on every text and card; any failure exits non-zero and leaves the previous pack in place.
Hooked into scripts/box_refresh.py (fb_pack(), right after the movers card) so a fresh pack lands with each complete snapshot.
"""
from __future__ import annotations

import argparse, csv, datetime as dt, glob, json, os, re, shutil, sys, tempfile

# This repo-owned copy keeps CI and the publish loop on the same guarded pack code.
# The existing box-only exact-number and card helpers remain external dependencies.
BOX = os.environ.get("ETSY_PULSE_BOX", "/workspace")
HERE = os.path.join(BOX, "x-etsypulse", "facebook")
XDIR = os.path.join(BOX, "x-etsypulse")
sys.path.insert(0, XDIR)
sys.path.insert(0, os.path.join(XDIR, "guerrilla"))
import exact_numbers as XN  # noqa: E402
from make_posts import (F, ORANGE, INK, MUT, CARD, LINE, BAR_BG, W, H, frame, tw, fit,  # noqa: E402
                        BANNED, COVERAGE_RE, APIFY_RE, STALE_RE, price_violation)
from PIL import Image  # noqa: E402

SITE = "https://www.etsypulse.ca"
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon-192.png")
NOT_AFF = {"en": "Not affiliated with Etsy.", "tr": "Etsy ile bağlantılı değildir. (Not affiliated with Etsy.)"}
ROWS = 8  # table rows in posts and cards (5-10)
GIFT_DEPTS = ("kids & baby", "toys & games", "home & living", "jewellery", "jewelry", "art & collectibles", "pet supplies")

# Group rules come from facebook/2026-10-08-fb-plan.md (§1 table + §4). links: yes / no / unknown.
# default: which variant Mark should use. lic = "link in comments if anyone wants it" allowed (plan: only where links are OK).
GROUPS = [
    dict(slug="etsyseo", name="Etsy Sellers and Buyers | Etsy SEO | Etsy Promotion", url="https://www.facebook.com/groups/etsyseo",
         lang="en", table="niches", links="yes (looks allowed)", default="link", lic=True, brand=True,
         alt_table="shops", alt_hook="Which Etsy shops added the most sales {span}? Here's today's table, read from public Etsy sales counters ({frm} → {to}):",
         rule="'Promotion' is in the group name and members already recommend tools in comments (plan §1 row 1). Pinned rules not verified: read them first.",
         hook="Which Etsy niches added the most sales {span}? Here's today's table, read from public Etsy sales counters ({frm} → {to}):"),
    dict(slug="tedooo", name="Etsy and Tedooo app Sellers Support Community", url="https://www.facebook.com/groups/1919359608205619",
         lang="en", table="jumps", links="no", default="comments", lic=False, brand=False,
         rule="Co-branded with the Tedooo app (a vendor); promo posts 'sometimes get denied'. Plan: comment only, no links. The no-link post is optional, only if the pinned rules allow data posts.",
         hook="For anyone feeling too small to compete: these shops grew their total sales the most {span} ({frm} → {to}), all with {base}+ sales before. Read from public Etsy sales counters:"),
    dict(slug="nancybadillo", name="Etsy Sellers Support Group (Nancy Badillo)", url="https://www.facebook.com/groups/EtsySellersSupportGroup",
         lang="en", table="rising", links="no (rules verified)", default="nolink", lic=False, brand=False,
         rule="Rules (verified, plan §1 row 3): zero spam or selling, no links at all, only the admin posts product links. Value-only post with no link and no brand. The only route for the tool is an admin partnership (plan §4.5).",
         hook="A bit of encouragement from the numbers: small shops (under {under} lifetime sales) that added the most sales {span}, from public Etsy sales counters ({frm} → {to}):"),
    dict(slug="mompreneurs", name="The Mompreneurs", url="https://www.facebook.com/groups/180837768789806",
         lang="en", table="niches", links="unknown (not Etsy-only)", default="comments", lic=False, brand=False,
         alt_table="jumps", alt_hook="For the Etsy sellers here: shops that grew their total sales the most {span} ({frm} → {to}), all with {base}+ sales before, from public Etsy sales counters:",
         rule="General mom-business group, not Etsy-only. Plan: answer Etsy questions only (comment bank). No-link post only if Mark sees data posts are welcome.",
         hook="For the Etsy sellers here: the niches that added the most sales {span}, from public Etsy sales counters ({frm} → {to}):"),
    dict(slug="dylanjahraus", name="Dylan Jahraus Etsy Success Secrets", url="https://www.facebook.com/groups/dylanjahraus",
         lang="en", table="shops", links="no (almost certainly)", default="comments", lic=False, brand=False,
         rule="Coach sells her own course, so outside tools are almost certainly banned. Comments only, no link, no brand; the tool only via an admin/sponsor route (plan §4.5).",
         hook="Proof buyers are out there: the Etsy shops that added the most sales {span}, from public Etsy sales counters ({frm} → {to}):"),
    dict(slug="etsypod", name="ETSY Print On Demand | Digital Product & Printable Art", url="https://www.facebook.com/groups/461900375110734",
         lang="en", table="rising", links="unknown", default="nolink", lic=False, brand=True,
         rule="Rules not verified (plan §1 row 14). Use the no-link post; switch to the link version only if the pinned rules allow links.",
         hook="Small shops still break through. Shops under {under} lifetime sales that added the most sales {span}, from public Etsy sales counters ({frm} → {to}):"),
    dict(slug="etsytr", name="Etsy Türkiye Yardımlaşma Platformu", url="https://www.facebook.com/groups/etsytr",
         lang="tr", table="niches", links="unknown", default="nolink", lic=False, brand=True,
         alt_table="jumps", alt_hook="Son {span} toplam satışını en çok artıran Etsy mağazaları (öncesinde {base}+ satışı olanlar), herkese açık Etsy satış sayaçlarından ({frm} → {to}):",
         rule="Rules not verified (login wall, plan §1 row 18). Use the Turkish no-link post; the link version only if the pinned rules allow links.",
         hook="Son {span} en çok satış eklenen Etsy nişleri hangileri? Herkese açık Etsy satış sayaçlarından bugünkü tablo ({frm} → {to}):"),
    dict(slug="etsyturkiye", name="Etsy Türkiye – Mikro İhracat", url="https://www.facebook.com/groups/etsyturkiye",
         lang="tr", table="shops", links="unknown", default="nolink", lic=False, brand=True,
         rule="Rules not verified (plan §1 row 19). Use the Turkish no-link post; the link version only if the pinned rules allow links.",
         hook="Son {span} en çok satış ekleyen Etsy mağazaları, herkese açık Etsy satış sayaçlarından ({frm} → {to}):"),
]
ANCHOR = {"niches": "#niches", "shops": "", "jumps": "", "rising": ""}

TRM = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def sd(iso, lang):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {TRM[d.month - 1]}" if lang == "tr" else d.strftime("%b %-d")


def num(n, lang):
    return XN.fmt(int(n), lang)


def pct(x, lang):
    s = f"{float(x):.1f}"
    return f"+%{s.replace('.', ',')}" if lang == "tr" else f"+{s}%"


def under(D):
    return num(int(D["meta"].get("rising_max_total_sales") or 999) + 1, "en")


def under_tr(D):
    return num(int(D["meta"].get("rising_max_total_sales") or 999) + 1, "tr")


def link(slug, lang, table):
    base = f"{SITE}/tr/movers/" if lang == "tr" else f"{SITE}/movers/"
    return f"{base}?from=fb-{slug}{ANCHOR[table]}"


def day_groups(D):
    """GROUPS for this day: niche-table groups switch to their alt table/hook when the day has no niche list."""
    if D["niches"]:
        return GROUPS
    return [{**g, "table": g["alt_table"], "hook": g["alt_hook"]} if g["table"] == "niches" else g for g in GROUPS]


# ---------------------------------------------------------------- data
def load(repo, day):
    dd = os.path.join(repo, "data", "daily-movers", day)
    meta = json.load(open(os.path.join(dd, "meta.json")))
    rd = lambda f: list(csv.DictReader(open(os.path.join(dd, f), encoding="utf-8"))) if os.path.exists(os.path.join(dd, f)) else []
    D = {"meta": meta, "shops": rd("movers.csv"), "jumps": rd("pct.csv"), "niches": rd("niches.csv"), "rising": rd("rising.csv")}
    if meta.get("snapshot_date") != day:
        raise SystemExit(f"{day}: meta snapshot_date {meta.get('snapshot_date')} != folder day: mismatched export, no pack")
    for k in ("shops", "jumps", "rising"):
        if len(D[k]) < 5:
            raise SystemExit(f"{day}: {k} has {len(D[k])} rows (<5): incomplete export, no pack")
    if len(D["niches"]) < 5:   # niche list is optional: some days no categorized shop has an exact pair in the window
        D["niches"] = []
    for k in ("shops", "jumps", "niches", "rising"):   # never mix days or windows within a table
        # Niches deliberately fall back to a longer exact window when too few categorized shops have a 1-day pair.
        # Their declared niche_window_days/niche_from_date is authoritative; the main meta window belongs to shops/pct/rising.
        prefix = "niche_" if k == "niches" else ""
        frm = meta[prefix + "from_date"] if k == "niches" else meta["from_date"]
        w = int(meta[prefix + "window_days"] if k == "niches" else meta["window_days"])
        for r in D[k]:
            if r["to_date"] != day or r["from_date"] != frm or int(r["window_days"]) != w:
                raise SystemExit(f"{day}: {k} row {r.get('rank')} window {r['from_date']}->{r['to_date']} != declared {frm}->{day} ({w}d): no pack")
    tr = json.load(open(os.path.join(repo, "config", "i18n", "tr.json"), encoding="utf-8")).get("movers", {})
    D["trn"] = tr.get("niche_names", {})
    D["tagline"] = json.load(open(os.path.join(repo, "config", "movers.json"), encoding="utf-8"))["tagline"]
    return D


def niche_name(r, lang, D):
    return D["trn"].get(r["category"].split(" > ")[-1].strip(), r["niche"]) if lang == "tr" else r["niche"]


def table_lines(kind, lang, D):
    rows, out = D[kind][:ROWS], []
    sales = "satış" if lang == "tr" else "sales"
    for i, r in enumerate(rows):
        if kind == "niches":
            out.append(f"{r['rank']}. {niche_name(r, lang, D)}: +{num(r['sales_added'], lang)}" + (f" {sales}" if i == 0 else ""))
        elif kind == "shops":
            out.append(f"{r['rank']}. {r['shop_name']}: +{num(r['sales_added'], lang)}" + (f" {sales}" if i == 0 else ""))
        elif kind == "jumps":
            out.append(f"{r['rank']}. {r['shop_name']}: {pct(r['pct_added'], lang)} (+{num(r['sales_added'], lang)} {sales})")
        else:  # rising
            tot = "toplam" if lang == "tr" else "lifetime"
            out.append(f"{r['rank']}. {r['shop_name']}: +{num(r['sales_added'], lang)} {sales} ({num(r['sales_total'], lang)} {tot})")
    return out


def tip(kind, lang, D):
    span = XN.window(int(D["meta"]["niche_window_days"] if kind == "niches" else D["meta"]["window_days"]), lang)
    if kind == "niches":
        top5 = D["niches"][:5]
        r = min(top5, key=lambda x: float(x["top_shop_share"]))
        share = round(float(r["top_shop_share"]) * 100)
        if lang == "tr":
            return (f"Senin için anlamı: talep dağınık. {niche_name(r, lang, D)} nişindeki +{num(r['sales_added'], lang)} satışta en büyük mağazanın payı "
                    f"sadece %{share}; siparişler pek çok mağazaya gidiyor. Bu nişlere yakın bir şey satıyorsan başlığını ve ilk fotoğrafını şimdi tazele.")
        return (f"What this means for you: demand for {r['niche'].lower()} is spread out. The biggest shop made only {share}% of its "
                f"+{num(r['sales_added'], lang)} sales, so plenty of shops are getting those orders. If you sell anything close to these niches, "
                f"refresh your title and first photo now.")
    if kind == "shops":
        if lang == "tr":
            return ("Senin için anlamı: alıcılar şu an sipariş veriyor. Kendi kategorindeki en iyi mağazayı aç ve ilk sıradaki ürünlerine bak: "
                    "şu an satan bunlar. Fotoğraf, başlık ve fiyat aralığını kendi ürünlerinle karşılaştır.")
        return ("What this means for you: buyers are ordering right now. Open the top shop in your own category and look at its first row of "
                "listings, because that's what is selling. Compare their photos, titles and price range with yours.")
    if kind == "jumps":
        if lang == "tr":
            return ("Senin için anlamı: küçük ve orta boy mağazalar sandığından hızlı büyüyebiliyor. Eski ürünleri sonsuza kadar düzeltmek yerine "
                    "yeni ürünler eklemeye ve denemeye devam et.")
        return ("What this means for you: small and mid-size shops can grow faster than you'd think. Keep adding and testing new listings "
                "instead of tweaking old ones forever.")
    r = D["rising"][0]
    if lang == "tr":
        return (f"Senin için anlamı: bulunmak sadece dev mağazalara özgü değil. {r['shop_name']} {under_tr(D)} satışın altında ve yine de "
                f"{span} +{num(r['sales_added'], lang)} satış ekledi.")
    return (f"What this means for you: getting found isn't only for giant shops. {r['shop_name']} is still under {under(D)} lifetime sales "
            f"and added +{num(r['sales_added'], lang)} sales {span}.")


def post(g, D, variant):
    """variant: link | nolink | nolink_lic"""
    lang, kind, m = g["lang"], g["table"], D["meta"]
    niche = kind == "niches"
    w = int(m["niche_window_days"] if niche else m["window_days"])
    frm = m["niche_from_date"] if niche else m["from_date"]
    span = XN.window(w, lang)
    hook = g["hook"].format(span=span, frm=sd(frm, lang), to=sd(m["to_date"], lang), under=under(D) if lang == "en" else under_tr(D),
                            base=num(m.get("pct_min_base_sales") or 1000, lang))
    parts = [hook, "\n".join(table_lines(kind, lang, D)), tip(kind, lang, D)]
    if variant == "link":
        u = link(g["slug"], lang, kind)
        if lang == "tr":
            parts.append(f"Bunu takip etmek için ücretsiz bir araç yaptım (Etsy Pulse). Mağazalar{', nişler' if D['niches'] else ''} ve küçük mağazaların sıçramalarında "
                         f"tam ilk 10, her gün güncellenir: {u}\n{D['tagline']['tr']}")
        else:
            parts.append(f"Free daily top 10s for shops{', niches' if D['niches'] else ''} and small-shop jumps (Etsy Pulse): "
                         f"{u}\n{D['tagline']['en']}")
    elif variant == "nolink_lic":
        parts.append("Kullanmak isteyen olursa link yorumlarda." if lang == "tr" else "Link in comments if anyone wants it.")
    parts.append(NOT_AFF[lang])
    return "\n\n".join(parts)


def first_comment(g, D):
    u = link(g["slug"], g["lang"], g["table"])
    if g["lang"] == "tr":
        return f"İşte link: {u} (Etsy Pulse, ücretsiz, her gün güncellenir. Ben yaptım.) {NOT_AFF['tr']}"
    return f"Here it is: {u} (Etsy Pulse, free, updated daily. I built it.) {NOT_AFF['en']}"


# ---------------------------------------------------------------- comment bank (no links, one exact number each)
def niche_comments(N, add, nn, sp_en, sp_tr):
    nS = min(N[:5], key=lambda x: float(x["top_shop_share"]))
    nG = next((r for r in N if r["department"] in GIFT_DEPTS), N[min(2, len(N) - 1)])
    add("what-to-sell", "What should I sell?", "Ne satmalıyım?",
        f"If you're stuck, start from what's already moving. On public Etsy sales counters, {N[0]['niche'].lower()} added "
        f"+{num(N[0]['sales_added'], 'en')} sales {sp_en}, with {N[1]['niche'].lower()} right behind. Pick one you can make really well, then niche down inside it.",
        f"Takıldıysan, zaten satan yerden başla. Herkese açık Etsy satış sayaçlarına göre {nn(N[0], 'tr').lower()} {sp_tr} "
        f"+{num(N[0]['sales_added'], 'tr')} satış ekledi, {nn(N[1], 'tr').lower()} hemen arkasında. İyi yapabileceğin birini seç, sonra onun içinde daha dar bir niş bul.",
        f"niche:{N[0]['niche']}")
    add("saturated", "Is this niche too saturated?", "Bu niş çok mu doymuş?",
        f"Busy isn't the same as saturated. {nS['niche']} added +{num(nS['sales_added'], 'en')} sales {sp_en} and no single shop took most of it, "
        f"so lots of sellers are getting orders. Before you rule a niche out, check whether its sales are spread out or owned by one giant.",
        f"Kalabalık, doymuş demek değil. {nn(nS, 'tr')} {sp_tr} +{num(nS['sales_added'], 'tr')} satış ekledi ve bunun çoğunu tek bir mağaza almadı; "
        f"yani pek çok satıcı sipariş alıyor. Bir nişi elemeden önce satışların dağınık mı, yoksa tek bir devde mi olduğuna bak.",
        f"niche:{nS['niche']}")
    add("q4-hot", "What's hot for Q4 / the holidays?", "Yılbaşı / Q4 için ne satıyor?",
        f"Gift niches are already moving. {nG['niche']} added +{num(nG['sales_added'], 'en')} sales {sp_en} on public Etsy sales counters. "
        f"If you can make something giftable in that space, list it now so it has time to get picked up before the holiday rush.",
        f"Hediye nişleri şimdiden hareketli. Herkese açık Etsy satış sayaçlarına göre {nn(nG, 'tr').lower()} {sp_tr} +{num(nG['sales_added'], 'tr')} satış ekledi. "
        f"Bu alanda hediyelik bir şey yapabiliyorsan şimdi listele, yılbaşı yoğunluğundan önce bulunmaya zamanı olsun.",
        f"niche:{nG['niche']}")


def comments(D):
    m = D["meta"]
    w = int(m["niche_window_days"] if D["niches"] else m["window_days"])
    N, S, J, R = D["niches"], D["shops"], D["jumps"], D["rising"]
    rs = next((r for r in S if r["category"]), S[0])
    out = []

    def add(key, q_en, q_tr, en, tr, fig):
        out.append(dict(key=key, q_en=q_en, q_tr=q_tr, en=en, tr=tr, figure=fig, table="niches" if fig.startswith("niche:") else "shops"))

    def nn(r, lang):
        return niche_name(r, lang, D)
    sp_en, sp_tr = XN.window(w, "en"), XN.window(w, "tr")
    main_w = int(m["window_days"])
    main_sp_en, main_sp_tr = XN.window(main_w, "en"), XN.window(main_w, "tr")
    if N:
        niche_comments(N, add, nn, sp_en, sp_tr)
    else:
        add("too-late", "Is it too late to start on Etsy?", "Etsy'de başlamak için geç mi?",
            f"Not from what the public sales counters show. {J[1]['shop_name']} grew its total sales {pct(J[1]['pct_added'], 'en')} {main_sp_en}. "
            f"Shops that keep adding listings still grow fast.",
            f"Herkese açık satış sayaçlarına bakılırsa hayır. {J[1]['shop_name']} toplam satışını {main_sp_tr} {pct(J[1]['pct_added'], 'tr')} artırdı. "
            f"Ürün eklemeye devam eden mağazalar hâlâ hızlı büyüyor.",
            f"pct:{J[1]['shop_name']}")
    add("why-no-sales", "Why am I getting no sales?", "Neden hiç satış yapamıyorum?",
        f"Don't give up yet, small shops do break through. {R[0]['shop_name']}, still under a thousand lifetime sales, added "
        f"+{num(R[0]['sales_added'], 'en')} sales {main_sp_en}. When views come but sales don't, I'd check the first photo, then the title, then price against the top sellers in that niche.",
        f"Hemen pes etme, küçük mağazalar da öne çıkabiliyor. {R[0]['shop_name']} henüz bin satışın altında ve {main_sp_tr} "
        f"+{num(R[0]['sales_added'], 'tr')} satış ekledi. Görüntülenme var ama satış yoksa önce ilk fotoğrafa, sonra başlığa, sonra o nişteki en iyi satıcılara göre fiyata bak.",
        f"shop:{R[0]['shop_name']}")
    add("how-to-research", "How do you research products / competitors?", "Ürün ve rakip araştırmasını nasıl yapıyorsun?",
        f"Free trick: every Etsy shop shows its total sales. Note a competitor's count, check it again a couple of days later, and you have "
        f"their real pace. For example, {rs['shop_name']} added +{num(rs['sales_added'], 'en')} sales {main_sp_en} that way.",
        f"Ücretsiz bir yöntem: her Etsy mağazası toplam satış sayısını gösterir. Bir rakibin sayısını not al, birkaç gün sonra tekrar bak; "
        f"gerçek hızını görürsün. Örneğin {rs['shop_name']} bu şekilde bakınca {main_sp_tr} +{num(rs['sales_added'], 'tr')} satış eklemiş.",
        f"shop:{rs['shop_name']}")
    add("small-shop", "Can a small shop still compete?", "Küçük bir mağaza hâlâ rekabet edebilir mi?",
        f"Yes. {J[0]['shop_name']} added {pct(J[0]['pct_added'], 'en')} to its total sales {main_sp_en}. Smaller shops can move a lot faster than you'd think.",
        f"Evet. {J[0]['shop_name']} toplam satışını {main_sp_tr} {pct(J[0]['pct_added'], 'tr')} artırdı. Küçük mağazalar sandığından çok daha hızlı büyüyebiliyor.",
        f"pct:{J[0]['shop_name']}")
    add("etsy-dead", "Is Etsy dead?", "Etsy bitti mi?",
        f"Not from what the public sales counters show. {S[0]['shop_name']} alone added +{num(S[0]['sales_added'], 'en')} sales {main_sp_en}. "
        f"Buyers are there; the hard part is getting found.",
        f"Herkese açık satış sayaçlarına bakılırsa hayır. Sadece {S[0]['shop_name']} {main_sp_tr} +{num(S[0]['sales_added'], 'tr')} satış ekledi. "
        f"Alıcılar orada; zor olan bulunmak.",
        f"shop:{S[0]['shop_name']}")
    return out


# ---------------------------------------------------------------- cards
CARD_TXT = {
    "en": {"niches": ("Daily niches · public Etsy sales counters", "Fastest-growing niches, {to}"),
           "shops": ("Daily movers · public Etsy sales counters", "Shops that added the most sales, {to}"),
           "jumps": ("Daily jumps · public Etsy sales counters", "Biggest jumps for their size, {to}"),
           "rising": ("Rising shops · public Etsy sales counters", "Small shops on the rise, {to}"),
           "sub": "Sales added {span}, {frm} → {to}", "url": "etsypulse.ca/movers"},
    "tr": {"niches": ("Günlük nişler · herkese açık Etsy satış sayaçları", "En hızlı büyüyen nişler, {to}"),
           "shops": ("Günlük yükselenler · herkese açık Etsy satış sayaçları", "En çok satış ekleyen mağazalar, {to}"),
           "jumps": ("Günlük sıçramalar · herkese açık Etsy satış sayaçları", "Büyüklüğüne göre en büyük sıçramalar, {to}"),
           "rising": ("Yükselen mağazalar · herkese açık Etsy satış sayaçları", "Yükselen küçük mağazalar, {to}"),
           "sub": "{span} eklenen satış, {frm} → {to}", "url": "etsypulse.ca/tr/movers"},
}


def card_rows(kind, lang, D):
    rows = []
    for r in D[kind][:ROWS]:
        if kind == "niches":
            rows.append((int(r["rank"]), niche_name(r, lang, D), f"+{num(r['sales_added'], lang)}", "", float(r["sales_added"])))
        elif kind == "shops":
            rows.append((int(r["rank"]), r["shop_name"], f"+{num(r['sales_added'], lang)}", "", float(r["sales_added"])))
        elif kind == "jumps":
            note = (f"önce {num(r['sales_before'], lang)}" if lang == "tr" else f"from {num(r['sales_before'], lang)}")
            rows.append((int(r["rank"]), r["shop_name"], pct(r["pct_added"], lang), note, float(r["pct_added"])))
        else:
            note = (f"toplam {num(r['sales_total'], lang)}" if lang == "tr" else f"{num(r['sales_total'], lang)} total")
            rows.append((int(r["rank"]), r["shop_name"], f"+{num(r['sales_added'], lang)}", note, float(r["sales_added"])))
    return rows


def render_card(kind, lang, D, out):
    m, T = D["meta"], CARD_TXT[lang]
    niche = kind == "niches"
    span = XN.window(int(m["niche_window_days"] if niche else m["window_days"]), lang)
    sub = T["sub"].format(span=span, frm=sd(m["niche_from_date"] if niche else m["from_date"], lang), to=sd(m["to_date"], lang))
    sub = sub[0].upper() + sub[1:]
    label, head = T[kind][0], T[kind][1].format(to=sd(m["to_date"], lang))
    rows = card_rows(kind, lang, D)
    bits = [label, head, sub] + [f"{n} {v} {note}" for _, n, v, note, _ in rows]
    logo = Image.open(LOGO).convert("RGB") if os.path.exists(LOGO) else Image.new("RGB", (68, 68), ORANGE)
    im, d = frame(label.replace("i", "İ").upper() if lang == "tr" else label, head, sub, logo, foot="")
    ft = F(27, "ExtraBold")
    tag = D["tagline"][lang]
    d.text((56, H - 54), tag, font=ft, fill=INK)
    d.text((56 + tw(d, tag + "  ", ft), H - 54), T["url"], font=ft, fill=ORANGE)
    x0, x1, top = 56, W - 56, 318
    d.rounded_rectangle([x0, top, x1, H - 76], 22, fill=CARD, outline=LINE, width=2)
    half = (len(rows) + 1) // 2
    colw = (x1 - x0) // 2
    rh = (H - 76 - top - 24) / half
    maxv = max(r[4] for r in rows) or 1
    fn, fs, fv = F(32, "Bold"), F(22, "SemiBold"), F(40, "ExtraBold")
    for i, (rank, name, val, note, v) in enumerate(rows):
        cx = x0 + (0 if i < half else colw)
        cy = top + 12 + rh * (i % half) + rh / 2
        if i % half:
            d.line([(cx + 20, cy - rh / 2), (cx + colw - 20, cy - rh / 2)], fill=LINE, width=2)
        d.text((cx + 26, cy - 20), str(rank), font=F(34, "ExtraBold"), fill=ORANGE if rank <= 3 else MUT)
        d.text((cx + 84, cy - 26), fit(d, name, fn, colw - 330), font=fn, fill=INK)
        if note:
            d.text((cx + colw - 28 - tw(d, note, fs), cy + 13), note, font=fs, fill=MUT)
        bx0, bx1 = cx + 84, cx + colw - 210
        d.rounded_rectangle([bx0, cy + 18, bx1, cy + 28], 5, fill=BAR_BG)
        d.rounded_rectangle([bx0, cy + 18, bx0 + max(12, (bx1 - bx0) * v / maxv), cy + 28], 5, fill=ORANGE)
        d.text((cx + colw - 28 - tw(d, val, fv), cy - (36 if note else 24)), val, font=fv, fill=ORANGE)
    d.line([((x0 + x1) // 2, top + 20), ((x0 + x1) // 2, H - 96)], fill=LINE, width=2)
    im.save(out, optimize=True)
    return "\n".join(bits + [tag])


# ---------------------------------------------------------------- guard
EXTRA_BANNED = [
    r"\bmedian\b", r"\bmedyan\b", r"page[ -]?1\b", r"sayfa 1\b", r"middle half", r"automat", r"otomatik", "🤖", r"real[- ]?time", r"gerçek zamanlı",
    r"20 per keyword", r"need a second", r"shops? (?:tracked|we track|in our panel)", r"\bpanel\b", r"your etsy data", r"etsy verilerin",
    r"blocked pages", r"scrap(?:e|er|ing)", r"kazı(?:ma|yıcı)", r"\bclaude\b", r"chatgpt", r"\bcursor\b", r"gemini", r"copilot",
    r"this week", r"bu hafta", r"\bweekly\b", r"haftalık", r"\b7[- ]day", r"7 gün",
    r"\b\d[\d.,]*\s+(?:shops|mağaza)\b",  # no shop counts at all (coverage-count rule)
]


def guard(key, text, D, S, kind="post", slug=None, lang="en", card=False, table=None):
    low = text.lower()
    for w_ in BANNED:
        if w_ in low:
            raise ValueError(f"{key}: banned word {w_!r}")
    for rx in EXTRA_BANNED:
        m_ = re.search(rx, text, re.I)
        if m_:
            raise ValueError(f"{key}: banned wording {m_.group(0)!r}")
    for rx in COVERAGE_RE:
        m_ = rx.search(text)
        if m_:
            raise ValueError(f"{key}: coverage count {m_.group(0)!r}")
    if APIFY_RE.search(text) or price_violation(text):
        raise ValueError(f"{key}: apify link or stale price line")
    for rx in STALE_RE:
        m_ = rx.search(text)
        if m_:
            raise ValueError(f"{key}: stale copy {m_.group(0)!r}")
    for m_ in re.finditer(r"[$€£₺]|\bUSD\b|\bTL\b", text):
        ctx = text[max(0, m_.start() - 80): m_.end() + 80].lower()
        if not re.search(r"sellers? charge|satıcıların? .{0,20}(fiyat|ücret)", ctx):
            raise ValueError(f"{key}: money figure not framed as what sellers charge")
    # exact numbers: week wording, scaled figures (unless also exact today), window stated
    wk = XN.GUARD_WEEK.search(text)
    if wk:
        raise ValueError(f"{key}: week/scaled wording {wk.group(0)!r}")
    exact = {v["added"] for v in S.values()}
    for m_ in XN.GUARD_NUM.finditer(text):
        v = int(re.sub(r"[.,]", "", m_.group(1) or m_.group(2)))
        if v in XN.scaled_figures() and v not in exact:
            raise ValueError(f"{key}: {m_.group(0)} is a scaled 7-day panel figure")
    no_pct = re.sub(r"\+%\d[\d.,]*|\+\d[\d.,]*%", " ", text)
    XN.check(no_pct, S=S, lang=lang)          # every +N is an exact figure, window stated and right
    if re.search(r"\+\s?\d", no_pct) or re.search(r"[+%]\d", text):
        if not XN.GUARD_WIN.search(text) and not card:
            raise ValueError(f"{key}: sales figure without its window")
        if card and not re.search(r"sales added|eklenen satış", text, re.I):
            raise ValueError(f"{key}: card without its window")
    w = int(D["meta"]["niche_window_days"] if table == "niches" else D["meta"]["window_days"])
    for m_ in re.finditer(r"in (\d+) days?|(\d+) günde", text):
        if int(m_.group(1) or m_.group(2)) != w:
            raise ValueError(f"{key}: stated window {m_.group(0)!r} != exact {w}d")
    # every +N must be one of TODAY's exact figures; every % must match pct.csv
    allowed = {int(r["sales_added"]) for k in ("shops", "jumps", "niches", "rising") for r in D[k]} | {int(r["top_shop_added"]) for r in D["niches"]}
    for m_ in re.finditer(r"\+(\d[\d.,]*)(?!\d)(?![.,]\d)(?!%)", text):
        if m_.group(1).endswith(("%",)):
            continue
        v = int(re.sub(r"[^\d]", "", m_.group(1)))
        if v not in allowed:
            raise ValueError(f"{key}: +{m_.group(1)} not an exact figure in today's export")
    okp = {pct(r["pct_added"], l) for r in D["jumps"] for l in ("en", "tr")}
    for m_ in re.finditer(r"\+%\d+,\d|\+\d+\.\d%", text):
        if m_.group(0) not in okp:
            raise ValueError(f"{key}: {m_.group(0)} not in pct.csv")
    # links
    links = re.findall(r"https?://\S+", text)
    if kind == "comment" or card:
        if links:
            raise ValueError(f"{key}: comments/cards carry no link")
    for u in links:
        if not u.startswith(SITE + "/") or f"from=fb-{slug}" not in u or re.search(r"[?&]from=fb-(?!" + re.escape(slug) + r"\b)", u):
            raise ValueError(f"{key}: link {u!r} must be {SITE}/... with from=fb-{slug}")
    if kind == "post" and not text.rstrip().endswith(NOT_AFF[lang]):
        raise ValueError(f"{key}: post must end with the not-affiliated line")
    return True


# ---------------------------------------------------------------- pack
def build(repo, day, out_root):
    D = load(repo, day)
    S = XN.load(day)
    m = D["meta"]
    tmp = tempfile.mkdtemp(prefix=f"fbpack-{day}-", dir=out_root)
    checks = 0
    cards = {}
    for kind in [k for k in ("niches", "shops", "jumps", "rising") if D[k]]:
        for lang in ("en", "tr"):
            fn = f"card-{kind}-{lang}.png"
            bits = render_card(kind, lang, D, os.path.join(tmp, fn))
            guard(f"card-{kind}-{lang}", bits, D, S, kind="card", lang=lang, card=True, table=kind)
            checks += 1
            cards[(kind, lang)] = fn
    G = []
    for g in day_groups(D):
        lang = g["lang"]
        v = {"nolink": post(g, D, "nolink")}
        if g["links"].startswith(("yes", "unknown")):
            v["link"] = post(g, D, "link")
        if g["lic"]:
            v["nolink_lic"] = post(g, D, "nolink_lic")
            v["first_comment"] = first_comment(g, D)
        for vk, t in v.items():
            guard(f"{g['slug']}:{vk}", t, D, S, kind="comment-link" if vk == "first_comment" else "post", slug=g["slug"], lang=lang, table=g["table"])
            checks += 1
            if vk == "first_comment" and len(re.findall(r"https?://\S+", t)) != 1:
                raise ValueError("first comment must carry exactly one link")
            if vk != "first_comment" and vk.startswith("nolink") and re.search(r"https?://", t):
                raise ValueError(f"{g['slug']}:{vk} no-link variant has a link")
            if not g["brand"] and vk == "nolink" and "Etsy Pulse" in t:
                raise ValueError(f"{g['slug']}: no-brand group mentions Etsy Pulse")
        G.append({**g, "variants": v, "card": cards[(g["table"], lang)]})
    C = comments(D)
    for c in C:
        for lang in ("en", "tr"):
            guard(f"comment:{c['key']}:{lang}", c[lang], D, S, kind="comment", lang=lang, table=c.get("table", "shops"))
            n_figs = len(re.findall(r"\+\s?%?\d", c[lang]))
            if n_figs != 1:
                raise ValueError(f"comment:{c['key']}:{lang} must carry exactly one exact figure (has {n_figs})")
            checks += 1
    # duplicate text across groups is a ban risk (plan §5b): no two default posts identical
    defaults = [g["variants"].get(g["default"], g["variants"]["nolink"]) for g in G]
    if len(set(defaults)) != len(defaults):
        raise ValueError("two groups would get identical text")
    write(tmp, D, G, C, cards, checks, day)
    final = os.path.join(out_root, day)
    if os.path.isdir(final):
        shutil.rmtree(final)
    os.rename(tmp, final)
    os.chmod(final, 0o755)
    lk = os.path.join(out_root, "latest")
    if os.path.islink(lk) or os.path.exists(lk):
        os.remove(lk)
    os.symlink(day, lk)
    log = os.path.join(HERE, "engagement-log.csv")
    if not os.path.exists(log):
        open(log, "w").write("posted_at_et,group_slug,kind,thread_url,variant_or_comment_key,figure_used,pack_day,notes\n")
    return final, checks


DEFAULT_LABEL = {"link": "post WITH link", "nolink": "post, NO link", "comments": "comments only (no post)"}


def write(out, D, G, C, cards, checks, day):
    m = D["meta"]
    w = int(m["window_days"])
    nw = int(m.get("niche_window_days") or w)
    win = f"{m['from_date']} → {m['to_date']} ({w}-day exact counter pairs, no scaling)"
    nwin = f"{m.get('niche_from_date', m['from_date'])} → {m['to_date']} ({nw}-day exact counter pairs, no scaling)"
    md = [f"# Facebook group pack: {day}", "",
          f"Data: `data/daily-movers/{day}/` (snapshot {m['snapshot_date']}, main window {win}; niches window {nwin}). Built {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} ET by "
          f"`facebook/make_fb_pack.py`. **Nothing is posted.** Meta has no Groups API, so you paste these by hand from your own profile.", "",
          f"Guard: **PASS** ({checks} texts/cards checked: exact figures from today's export with the window stated, no scaled or week wording, "
          f"banned words, no shop counts, links only to www.etsypulse.ca with the group's `from=fb-<slug>` tag, every post ends with the not-affiliated line).", "",
          "## How to use (plan §4)", "",
          "1. Join 2–3 groups a day at most. Read the pinned rules, then post nothing for 3–5 days.",
          "2. Use each group's **default** below. Switch to a link version only where the rules allow links.",
          "3. About 3 comments per group per day, never the same text twice, no DMs, no cold tags. In no-promo groups: value only.",
          "4. If someone asks where the numbers come from: say it's your own tracker. Give the link only where links are allowed.",
          "5. Log every post or comment in `facebook/engagement-log.csv` (group, thread URL, figure used).", "",
          "## Groups at a glance", "",
          "| Group | Lang | Links allowed? | Default | Card | Tracking tag |", "|---|---|---|---|---|---|"]
    for g in G:
        md.append(f"| [{g['name'].replace('|', '·')}]({g['url']}) | {g['lang'].upper()} | {g['links']} | {DEFAULT_LABEL[g['default']]} | `{g['card']}` | "
                  f"`from=fb-{g['slug']}` |")
    md += ["", "Links point straight at www.etsypulse.ca with `?from=fb-<slug>`. The site's page-view beacon records that tag "
           "(it's in the `/activity` ledger as the view's `from`), so visits and later runs can be traced to the group.", ""]
    txt = [f"FACEBOOK GROUP PACK {day}  (window {m['from_date']} -> {m['to_date']}, exact). Nothing is posted. Copy below each line of dashes.", ""]
    names = {"link": "WITH LINK", "nolink": "NO LINK", "nolink_lic": "NO LINK, link in comments", "first_comment": "FIRST COMMENT (the link, only if someone asks / rules allow)"}
    for g in G:
        md += [f"## {g['name']} ({g['lang'].upper()})", "", f"- URL: {g['url']}", f"- Links: **{g['links']}**. {g['rule']}",
               f"- Default: **{DEFAULT_LABEL[g['default']]}**", f"- Attach: `{g['card']}`", ""]
        if g["default"] == "comments":
            md += ["Use the comment bank below. The post here is optional, only if you see the rules welcome data posts.", ""]
        order = ["link", "nolink_lic", "first_comment", "nolink"] if g["default"] == "link" else ["nolink", "link", "nolink_lic", "first_comment"]
        for vk in order:
            if vk not in g["variants"]:
                continue
            tag = " (default)" if vk == g["default"] else ""
            md += [f"**{names[vk]}{tag}**", "", "```text", g["variants"][vk], "```", ""]
            txt += ["=" * 70, f"[{g['slug']}] {g['name']} | {names[vk]}{tag} | attach {g['card']}", "-" * 70, g["variants"][vk], ""]
    md += ["## Comment bank (no links, one exact number each)", "",
           "Reply only where the question really fits, and reword a little each time. Never paste the same text twice in one group.", ""]
    txt += ["=" * 70, "COMMENT BANK (no links)", ""]
    for c in C:
        md += [f"### {c['q_en']} / {c['q_tr']}", "", "EN:", "```text", c["en"], "```", "TR:", "```text", c["tr"], "```",
               f"_Figure: `{c['figure']}`_", ""]
        txt += ["-" * 70, f"[{c['key']}] EN: {c['q_en']}", c["en"], "", f"[{c['key']}] TR: {c['q_tr']}", c["tr"], ""]
    md += ["## Cards", ""] + [f"- `{fn}` ({k} {l.upper()}): ![]({fn})" for (k, l), fn in cards.items()] + [""]
    md += ["## Today's tables (all four, for reference)", ""]
    if not D["niches"]:
        md += ["_No niche table today: no niche had enough exact counter pairs in this window. Niche groups use a shop table instead._", ""]
    for kind, title in (("niches", "Niches by sales added"), ("shops", "Shops by sales added"), ("jumps", "Biggest % jumps (1,000+ sales before)"),
                        ("rising", f"Rising small shops (under {under(D)} lifetime sales)")):
        if not D[kind]:
            continue
        md += [f"**{title}, {XN.window(nw if kind == 'niches' else w, 'en')}**", "", "```text", "\n".join(table_lines(kind, "en", D)), "```", ""]
    open(os.path.join(out, "pack.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    open(os.path.join(out, "posts.txt"), "w", encoding="utf-8").write("\n".join(txt) + "\n")
    json.dump({"day": day, "window_days": w, "from_date": m["from_date"], "to_date": m["to_date"], "snapshot_sha256": m.get("snapshot_sha256"),
               "guard": "pass", "checks": checks, "groups": [{k: g[k] for k in ("slug", "lang", "links", "default", "card")} |
                                                             {"links_out": sorted({u for t in g["variants"].values() for u in re.findall(r'https?://\S+', t)})} for g in G],
               "comments": [{k: c[k] for k in ("key", "figure")} for c in C],
               "built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")},
              open(os.path.join(out, "manifest.json"), "w"), indent=1)


def selftest(repo, day):
    """The guard must REJECT each of these (run on every build before anything is written)."""
    D, S = load(repo, day), XN.load(day)
    na = NOT_AFF["en"]
    top = D["niches"][0] if D["niches"] else D["shops"][0]
    self_window = int(D["meta"]["niche_window_days"] if D["niches"] else D["meta"]["window_days"])
    subj, v = top.get("niche") or top["shop_name"], int(top["sales_added"])
    exact = {x["added"] for x in S.values()}
    nx = next(x for x in range(v + 1, v + 1000) if x not in exact and x not in XN.scaled_figures())
    ok = f"Backpacks added +{num(v, 'en')} sales {XN.window(self_window, 'en')}.\n\n{na}"
    guard("selftest-ok", ok, D, S, slug="etsyseo", table="niches" if D["niches"] else "shops")
    bad = {
        "scaled week": "Backpacks added +7,021 sales this week.\n\n" + na,
        "7 days": ok.replace(XN.window(self_window, "en"), "in 7 days"),
        "not exact": f"Backpacks added +{num(nx, 'en')} sales {XN.window(self_window, 'en')}.\n\n" + na,
        "no window": f"Backpacks added +{num(v, 'en')} sales.\n\n" + na,
        "median": f"The median shop added +{num(v, 'en')} sales {XN.window(self_window, 'en')}.\n\n" + na,
        "scraper": ok.replace("Backpacks", "Our scraper says backpacks"),
        "claude": ok + " Ask Claude.",
        "coverage": ok.replace("Backpacks", "Across 23 shops, backpacks"),
        "panel": ok.replace("Backpacks", "In our panel, backpacks"),
        "etsy data": ok.replace("Backpacks", "Using your Etsy data, backpacks"),
        "page 1": ok.replace("Backpacks", "On page 1, backpacks"),
        "real-time": ok.replace("Backpacks", "Real-time: backpacks"),
        "money": ok.replace("Backpacks", "For $25 backpacks"),
        "other host": ok.replace("\n\n" + na, " https://tinyurl.com/etsypulse\n\n" + na),
        "no tag": ok.replace("\n\n" + na, " https://www.etsypulse.ca/movers/\n\n" + na),
        "wrong tag": ok.replace("\n\n" + na, " https://www.etsypulse.ca/movers/?from=fb-tedooo\n\n" + na),
        "no not-affiliated line": ok.replace("\n\n" + na, ""),
        "bad pct": "CrochetRustandi +99.9% in 2 days.\n\n" + na,
        "tr week": "Sırt çantaları bu hafta +2.389 satış.\n\nEtsy ile bağlantılı değildir. (Not affiliated with Etsy.)",
    }
    ok = ok.replace("Backpacks", subj)
    bad = {k: t.replace("Backpacks", subj) for k, t in bad.items()}
    guard("selftest-ok-subject", ok, D, S, slug="etsyseo", table="niches" if D["niches"] else "shops")
    for k, t in bad.items():
        try:
            guard(f"selftest-{k}", t, D, S, slug="etsyseo", lang="tr" if k.startswith("tr") else "en", table="niches" if D["niches"] else "shops")
        except (ValueError, AssertionError):
            continue
        raise SystemExit(f"guard selftest FAILED: '{k}' was not rejected")
    try:
        guard("selftest-comment-link", f"{subj} +{num(v, 'en')} sales {XN.window(self_window, 'en')} https://www.etsypulse.ca/movers/?from=fb-etsyseo", D, S, kind="comment", slug="etsyseo", table="niches" if D["niches"] else "shops")
    except ValueError:
        return len(bad) + 1
    raise SystemExit("guard selftest FAILED: link in a comment was not rejected")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/workspace/publicrecords-data")
    ap.add_argument("--day")
    ap.add_argument("--out-root", default=os.path.join(HERE, "packs"))
    a = ap.parse_args()
    days = sorted(os.path.basename(p) for p in glob.glob(os.path.join(a.repo, "data", "daily-movers", "20*"))
                  if all(os.path.exists(os.path.join(p, f)) for f in ("meta.json", "movers.csv", "pct.csv", "rising.csv")))
    if not days:
        raise SystemExit("no complete data/daily-movers/<day>/")
    day = a.day or days[-1]
    # Guard intent: never publish numbers from mismatched days. The pack is built from ONE day folder; the exact-figure set
    # (XN.load(day)) and every row's window are read from that same folder (load() checks to_date/from_date/window per row).
    # The newest day must also be what exact_numbers sees as newest, so X drafts and the FB pack never disagree.
    if not a.day and day != XN.latest_day():
        raise SystemExit(f"exact_numbers newest day {XN.latest_day()} != {day}")
    os.makedirs(a.out_root, exist_ok=True)
    neg = selftest(a.repo, day)
    try:
        final, checks = build(a.repo, day, a.out_root)
    except Exception:
        for p in glob.glob(os.path.join(a.out_root, f"fbpack-{day}-*")):
            shutil.rmtree(p, ignore_errors=True)
        raise
    print(json.dumps({"day": day, "pack": final, "guard": "pass", "checks": checks, "guard_selftest_rejected": neg}))


if __name__ == "__main__":
    main()
