#!/usr/bin/env python3
"""SITE-HELD-1 (Claude t781u): buyer-visible stale-data check for /, /movers/, /rising.html in en/fr/tr.

  python scripts/held_check.py --base https://www.etsypulse.ca/ [--snapshot YYYY-MM-DD] [--dir LOCAL_SITE]

newest = --snapshot, else the newest data/panel/<cut>/meta.json snapshot_date (what the box keepalive publishes).
Rules, per page, on visible text outside <header>/<nav> and outside archive links (class "arch"):
  R1 any data date older than newest - 1 day must have the held word (Held / Retenu / Bekletiliyor) within HELD_BEFORE chars
     before it or HELD_AFTER chars after it;
  R2 'today' / 'daily' / 'every day' (fr: aujourd'hui, quotidien, chaque jour; tr: bugün, günlük, her gün) within FRESH_NEAR chars
     of a held date fails;
  R3 the footer's dates must equal the newest data date shown in the body (or the footer says Held);
  R4 no '0 niches' line (fr '0 niches', tr '0 niş').
Exit 1 on any failure; prints one line per finding."""
import argparse, datetime as dt, glob, html, json, os, re, sys, urllib.request
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PAGES = ["", "movers/", "rising.html"]
LANGS = {"en": "", "fr": "fr/", "tr": "tr/"}
HELD = {"en": r"\bHeld\b", "fr": r"\bRetenue?s?\b", "tr": r"\bBekletiliyor\b|\bBekletilen\b"}
FRESH = {"en": r"\btoday(?:'s)?\b|\bdaily\b|\bevery day\b",
         "fr": r"aujourd['’]hui|\bquotidien\w*|\bchaque jour\b",
         "tr": r"\bbugün\w*|\bgünlük\b|\bher gün\b|\bgünün\b"}
ZERO_N = {"en": r"\b0 niches\b", "fr": r"\b0 niches?\b", "tr": r"\b0 niş\b"}
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
       "janv": 1, "févr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "août": 8, "sept": 9, "déc": 12,
       "octobre": 10, "septembre": 9, "novembre": 11, "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
       "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12, "october": 10, "september": 9, "november": 11}
DATE_RX = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b|\b([A-Z][a-z]{2,8})\.? (\d{1,2})\b|\b(\d{1,2}) ([a-zéûçşığüö]{3,9}|[A-ZÇŞĞÜÖİ][a-zçşığüö]{2,8})\.?")
HELD_BEFORE, HELD_AFTER, FRESH_NEAR = 320, 160, 120


def vis(raw):
    raw = re.sub(r"<(script|style|header|nav)\b[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r'<(\w+)[^>]*class="[^"]*\barch\b[^"]*"[^>]*>.*?</\1>', " ", raw, flags=re.S)
    foot = re.search(r"<footer\b.*?</footer>", raw, re.S)
    ft = foot.group(0) if foot else ""
    body = raw.replace(ft, " ") if ft else raw
    clean = lambda h: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    return clean(body), clean(ft)


def dates(t, year=2026):
    out = []
    for m in DATE_RX.finditer(t):
        try:
            if m.group(1):
                d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif m.group(4):
                mo = MON.get(m.group(4).lower()[:3] if m.group(4).lower()[:3] in MON and len(m.group(4)) <= 4 else m.group(4).lower())
                mo = mo or MON.get(m.group(4).lower()[:3])
                if not mo:
                    continue
                d = dt.date(year, mo, int(m.group(5)))
            else:
                k = m.group(7).lower().rstrip(".")
                mo = MON.get(k) or MON.get(k[:4]) or MON.get(k[:3])
                if not mo:
                    continue
                d = dt.date(year, mo, int(m.group(6)))
        except ValueError:
            continue
        out.append((m.start(), m.end(), d, m.group(0)))
    return out


def newest_snapshot():
    ms = sorted(glob.glob(os.path.join(ROOT, "data", "panel", "*", "meta.json")))
    return dt.date.fromisoformat(json.load(open(ms[-1]))["snapshot_date"])


def check_page(url, raw, lg, newest):
    bad = []
    body, foot = vis(raw)
    ds = dates(body)
    held = [x for x in ds if (newest - x[2]).days > 1]
    for s, e, d, txt in held:
        win = body[max(0, s - HELD_BEFORE): e + HELD_AFTER]
        if not re.search(HELD[lg], win, re.I):
            bad.append(f"R1 {url}: held date '{txt}' ({d}) has no held word nearby: …{body[max(0, s - 70): e + 40]}…")
        near = body[max(0, s - FRESH_NEAR): e + FRESH_NEAR]
        for m in re.finditer(FRESH[lg], near, re.I):
            bad.append(f"R2 {url}: '{m.group(0)}' next to held date '{txt}': …{near[max(0, m.start() - 50): m.end() + 50]}…")
    data_max = max((x[2] for x in ds), default=None)
    if data_max and not re.search(HELD[lg], foot, re.I):
        for s, e, d, txt in dates(foot):
            if d != data_max:
                bad.append(f"R3 {url}: footer date '{txt}' ({d}) != newest data date shown ({data_max}): {foot.strip()[-160:]}")
    for m in re.finditer(ZERO_N[lg], body, re.I):
        bad.append(f"R4 {url}: zero-niches line: …{body[max(0, m.start() - 60): m.end() + 30]}…")
    return sorted(set(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://www.etsypulse.ca/")
    ap.add_argument("--dir", help="check a local build instead of URLs")
    ap.add_argument("--snapshot")
    a = ap.parse_args()
    newest = dt.date.fromisoformat(a.snapshot) if a.snapshot else newest_snapshot()
    print(f"held_check newest_snapshot={newest} held_if_older_than={newest - dt.timedelta(days=1)} source={a.dir or a.base}")
    allbad, n = [], 0
    for lg, lp in LANGS.items():
        for p in PAGES:
            rel = lp + p
            if a.dir:
                f = os.path.join(a.dir, rel + ("index.html" if rel.endswith("/") or rel == "" else ""))
                raw, url = open(f, encoding="utf-8").read(), rel or "/"
            else:
                url = a.base + rel
                req = urllib.request.Request(url + ("&" if "?" in url else "?") + "hc=" + dt.datetime.now().strftime("%H%M%S"),
                                             headers={"User-Agent": "etsypulse-held-check/1", "Cache-Control": "no-cache"})
                raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
            n += 1
            b = check_page(url, raw, lg, newest)
            print(f"{'FAIL' if b else 'PASS'} {url} ({len(b)} findings)")
            allbad += b
    for b in allbad:
        print("  " + b)
    print(f"held_check {'FAIL' if allbad else 'PASS'}: {n} pages, {len(allbad)} findings")
    sys.exit(1 if allbad else 0)


if __name__ == "__main__":
    main()
