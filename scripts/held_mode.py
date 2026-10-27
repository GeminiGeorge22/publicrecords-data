"""SITE-HELD-1 (Claude t781u): when the newest published shop-sales data (data/daily-movers/<day>/) is 1 or more days older
than the newest snapshot (data/panel/<cut>/meta.json snapshot_date), the newer snapshot(s) failed the balance check and the
sales lists are HELD. Then /, /movers/ and /rising.html in en/fr/tr must say so in plain words next to every held date, drop the
'today' / 'daily' / 'every day' claims, and the footer must name the held data date instead of the newest snapshot.

apply(out_dir, held_day, newest, short_date_fn) rewrites those 9 built pages in place. The rewrite tables below are the ONE place
for held-mode wording. scripts/held_check.py is the check (also run by the box keepalive against the live site)."""
import os
import re

PAGES = ["index.html", "movers/index.html", "rising.html"]
LANGS = {"en": "", "fr": "fr/", "tr": "tr/"}
AP = r"(?:'|&#x27;|’)"
BANNER = {
    "en": "Held since {d}: no balanced snapshot since then. Updates resume when one lands.",
    "fr": "Retenu depuis le {d} : aucun instantané équilibré depuis. Les mises à jour reprendront dès qu{ap}il y en aura un.",
    "tr": "{d} tarihinden beri bekletiliyor: o tarihten beri dengeli anlık görüntü yok. Yeni bir tane gelince güncellemeler sürecek.",
}
TAG = {"en": "Held since {d}", "fr": "Retenu depuis le {d}", "tr": "{d} tarihinden beri bekletiliyor"}
FOOT = {
    "en": "Sales data held since {iso} (counters read through {iso}); newer snapshots up to {new} have not passed the balance check.",
    "fr": "Données de ventes retenues depuis le {d} (compteurs lus jusqu{ap}au {d}); les instantanés plus récents, jusqu{ap}au {nd}, n{ap}ont pas passé le contrôle d{ap}équilibre.",
    "tr": "Satış verileri {d} tarihinden beri bekletiliyor (sayaçlar {d} itibarıyla); {nd} tarihine kadarki yeni anlık görüntüler denge kontrolünü geçmedi.",
}
FOOT_RX = {"en": r"Movers cut [^<]*?\(counters read through [^)]*\)\.",
           "fr": r"Données du [^<]*?\(compteurs lus jusqu" + AP + r"au [^)]*\)\.",
           "tr": r"Kesit [^<]*?\(sayaçlar [^)]*itibarıyla\)\."}
# (regex, replacement) applied to the page HTML; {tag} = TAG, {banner} = BANNER
SUBS = {
    "en": [
        (r"Updated daily · Counters read through", "{tag} · Counters read through"),
        (r"Etsy Pulse · Daily movers", "Etsy Pulse · Movers · {tag}"),
        (r"New list every day\.", "{tag}."),
        (r"Today" + AP + r"s top (\d+)", r"Top \1"),
        (r"by today" + AP + r"s top", "by the top"),
        (r"Today" + AP + r"s takeaways", "Takeaways ({tag})"),
        (r"Our dataset grows every day as we read more Etsy shops\.", "{tag}."),
        (r"Free reports refresh daily when new sales counters land\.", "Free reports update when a balanced snapshot lands."),
        (r"Free reports refresh daily\.", "Free reports update when a balanced snapshot lands."),
        (r" · refreshed daily", " · {tag}"),
        (r"Full daily list →", "Full list →"),
        (r"(>|\s)Daily Movers(?=[,<\s])", r"\1Movers"),
        (r"See today" + AP + r"s movers →", "See the latest movers →"),
    ],
    "fr": [
        (r"Mis à jour chaque jour · Compteurs lus", "{tag} · Compteurs lus"),
        (r"Etsy Pulse · Palmarès du jour", "Etsy Pulse · Palmarès · {tag}"),
        (r"Nouvelle liste chaque jour\.", "{tag}."),
        (r"À retenir aujourd" + AP + r"hui", "À retenir ({tag})"),
        (r"Notre jeu de données grandit chaque jour : nous lisons de plus en plus de boutiques Etsy\.", "{tag}."),
        (r"Les rapports gratuits sont mis à jour chaque jour, dès que de nouveaux compteurs de ventes arrivent\.",
         "Les rapports gratuits sont mis à jour dès qu&#x27;un instantané équilibré arrive."),
        (r" · mis à jour chaque jour", " · {tag}"),
        (r"(\b[Ll]e |\b[Ll]es )?[Tt]op (\d+) du jour", r"\1top \2"),
        (r"Voir le palmarès d" + AP + r"aujourd" + AP + r"hui →", "Voir le dernier palmarès →"),
        (r"du jour\b", ""),
    ],
    "tr": [
        (r"Her gün güncellenir · Sayaçlar", "{tag} · Sayaçlar"),
        (r"Etsy Pulse · Günlük yükselenler", "Etsy Pulse · Yükselenler · {tag}"),
        (r"Her gün yeni liste\.", "{tag}."),
        (r"Bugünün ilk (\d+)" + AP + r"?(\w*)", r"İlk \1'\2"),
        (r"Bugünün ", ""),
        (r"Veri setimiz her gün büyüyor: her gün daha fazla Etsy mağazası okuyoruz\.", "{tag}."),
        (r"Ücretsiz raporlar her gün, yeni satış sayaçları geldiğinde yenilenir\.", "Ücretsiz raporlar dengeli bir anlık görüntü gelince yenilenir."),
        (r" · her gün yenilenir", " · {tag}"),
        (r"Günün hareketlileri", "Hareketliler"),
    ],
}


NAV_HELD = {"en": ("⚡ Daily Movers", "⚡ Movers"), "fr": ("⚡ Palmarès du jour", "⚡ Palmarès"), "tr": ("⚡ Günün yükselenleri", "⚡ Yükselenler")}


def apply(out_dir, held_day, newest, short_date_fn, date_loc_fn):
    changed = []
    # SITE-HELD-1b: while held, the Movers tab drops "daily"/"du jour"/"Günün" on EVERY page (the tab sits next to held dates)
    for root, _, fs in os.walk(out_dir):
        for fn in fs:
            if fn.endswith(".html"):
                f = os.path.join(root, fn)
                raw = open(f, encoding="utf-8").read()
                out = raw
                for old, new in NAV_HELD.values():
                    out = out.replace(f">{old}</a>", f">{new}</a>")
                if out != raw:
                    open(f, "w", encoding="utf-8").write(out)
    for lg, lp in LANGS.items():
        d = short_date_fn(held_day, lg)
        tag = TAG[lg].format(d=d)
        banner = BANNER[lg].format(d=d, ap="&#x27;")
        for p in PAGES:
            f = os.path.join(out_dir, lp + p)
            if not os.path.exists(f):
                continue
            raw = open(f, encoding="utf-8").read()
            head, sep, rest = raw.partition("</nav>")   # never touch <head>/<header>/<nav> (tab names stay)
            if not sep:
                head, rest = "", raw
            for rx, rep in SUBS[lg]:
                rest = re.sub(rx, rep.replace("{tag}", tag), rest)
            # every ISO held date in visible text (method lines, CSV labels) gets the word too; hrefs/filenames untouched
            hw = {"en": "held", "fr": "retenu", "tr": "bekletiliyor"}[lg]
            rest = re.sub(r">([^<]*)<", lambda m: ">" + re.sub(r"\b" + held_day + r"\b(?! \()", f"{held_day} ({hw})", m.group(1)) + "<", rest)
            # a held tag in front of every dated window line and snapshot chip, and one banner at the top of <main>
            rest = rest.replace('<div class="dmwin">', f'<div class="dmwin"><b>{tag} ·</b> ')
            rest = rest.replace('<main class="wrap">', f'<main class="wrap">\n<p class="heldbar" role="status"><b>{banner}</b></p>', 1)
            foot = FOOT[lg].format(iso=held_day, new=newest, d=date_loc_fn(held_day, lg), nd=date_loc_fn(newest, lg), ap="&#x27;")
            rest = re.sub(FOOT_RX[lg], foot, rest)
            # title: the held date in the browser tab / search result carries the word too
            head = re.sub(r"(<title>[^<]*?)(\s*\|\s*Etsy Pulse)?</title>", lambda m: m.group(1) + f" · {tag}" + (m.group(2) or "") + "</title>", head, 1)
            out = head + sep + rest
            if out != raw:
                open(f, "w", encoding="utf-8").write(out)
                changed.append(lp + p)
    return changed
