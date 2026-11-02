"""SITE-HELD-1e: R1 read the movers shop handle '4 MarysYarnsEtc' (rank/% cell, then the shop name) as a held date
2026-03-04 on tr/movers/ and fr/movers/ and blocked the 2026-11-02 06:04 ET publish. A number followed by a word that only
STARTS with month letters (shop handle) is not a date; real dates in en/fr/tr must still be caught."""
import datetime as dt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import held_check as hc

NEWEST = dt.date(2026, 11, 1)
# exact visible copy from the 2026-11-02 publish skip line (fr + tr movers rows)
FR_SHOP = ("<main><table><tr><td>Boutique 1 182 ventes au total</td><td>+39 ventes ajoutées</td><td>+3,4 %</td>"
           "<td>4 MarysYarnsEtc</td><td>Suivre les ventes de cette boutique</td></tr></table></main>")
TR_SHOP = ("<main><table><tr><td>PaperCo Bu mağazanın satışlarını izle</td><td>1.182 toplam satış</td><td>+39 satış</td>"
           "<td>%3,4</td><td>4 MarysYarnsEtc</td><td>Bu mağazanın satışlarını izle</td></tr></table></main>")


def r1(raw, lg, newest=NEWEST):
    return [b for b in hc.check_page("/", raw, lg, newest) if b.startswith("R1")]


def test_fr_shop_handle_is_not_a_date():
    assert r1(FR_SHOP, "fr") == []


def test_tr_shop_handle_is_not_a_date():
    assert r1(TR_SHOP, "tr") == []


def test_en_shop_handle_is_not_a_date():
    assert r1(FR_SHOP.replace("ventes", "sales"), "en") == []


def test_glued_month_prefix_handle_is_not_a_date():
    # even a handle whose first letters ARE a full month name is not a date when letters follow
    assert r1("<main><p>4 MarchYarnsEtc 7 MartiniGlassCo 2 MaiStudio</p></main>", "tr") == []
    assert hc.dates("4 MarysYarnsEtc") == []


def test_real_french_date_still_caught():
    assert len(r1("<main><p>Lu le 4 mars 2026, boutique suivie.</p></main>", "fr")) == 1


def test_real_turkish_date_still_caught():
    assert len(r1("<main><p>4 Mart 2026 tarihinde okundu.</p></main>", "tr")) == 1


def test_real_english_dates_still_caught():
    assert len(r1("<main><p>Shop counters read March 4, 2026.</p></main>", "en")) == 1
    assert len(r1("<main><p>Shop counters read Mar 4, 2026.</p></main>", "en")) == 1
    assert len(r1("<main><p>Shop counters read 4 March 2026.</p></main>", "en")) == 1


def test_site_month_formats_still_parse():
    # every month form build_site emits (config/i18n months + months_short, %b) plus common variants
    for txt, mo in [("4 janv. 2026", 1), ("4 févr. 2026", 2), ("4 juill. 2026", 7), ("4 juillet 2026", 7),
                    ("4 août 2026", 8), ("4 sept. 2026", 9), ("4 déc. 2026", 12), ("4 décembre 2026", 12),
                    ("4 Ocak 2026", 1), ("4 Şubat 2026", 2), ("4 Mayıs 2026", 5), ("4 Ağustos 2026", 8),
                    ("4 Eylül 2026", 9), ("4 Kasım 2026", 11), ("4 Aralık 2026", 12), ("4 Ekimde", 10),
                    ("4 Mart'ta", 3), ("Sep 4", 9), ("Sept 4", 9), ("June 4", 6), ("Oct 19", 10)]:
        got = [d.month for _, _, d, _ in hc.dates(txt)]
        assert got == [mo], (txt, got)


def test_shop_handle_does_not_mask_a_real_held_date_beside_it():
    raw = FR_SHOP.replace("</table>", "</table><p>Lu le 4 mars 2026.</p>")
    out = r1(raw, "fr")
    assert len(out) == 1 and "4 mars" in out[0]
    raw = TR_SHOP.replace("</table>", "</table><p>4 Mart 2026 tarihinde okundu.</p>")
    out = r1(raw, "tr")
    assert len(out) == 1 and "4 Mart" in out[0]


def test_held_word_still_excuses_real_date():
    assert r1("<main><p>Retenu : lu le 4 mars 2026.</p></main>", "fr") == []
    assert r1("<main><p>Bekletiliyor: 4 Mart 2026 tarihinde okundu.</p></main>", "tr") == []
