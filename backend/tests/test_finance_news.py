"""Tests für Währungsumrechnung, RSS-Parser und Finanz-Endpunkte."""

from datetime import date

from app.services.news import clean_html, parse_feed
from app.services.stocks import fx_symbol, to_eur

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>BGH: Neues Urteil &amp; Folgen</title><link>https://example.org/a</link>
<description>&lt;p&gt;Der &lt;b&gt;BGH&lt;/b&gt; hat entschieden.&lt;/p&gt;</description>
<pubDate>Tue, 22 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>Ohne Link</title></item>
</channel></rss>"""


def test_parse_feed():
    items = parse_feed(RSS)
    assert len(items) == 1
    assert items[0]["title"] == "BGH: Neues Urteil & Folgen"
    assert items[0]["summary"] == "Der BGH hat entschieden."
    assert items[0]["published"].year == 2026


def test_clean_html_limits_length():
    assert clean_html("<p>a   b</p>") == "a b"
    assert clean_html("x" * 700, 600).endswith("…")


def test_currency_conversion():
    rates = {"USD": 1.10, "GBP": 0.85}
    assert round(to_eur(110, "USD", rates), 6) == 100
    assert to_eur(50, "EUR", rates) == 50
    assert round(to_eur(8500, "GBp", rates), 2) == 100  # Pence
    assert to_eur(10, "CHF", rates) is None  # kein Kurs bekannt
    assert fx_symbol("USD") == "EURUSD=X"
    assert fx_symbol("EUR") is None


def test_finance_month_summary(client):
    today = date.today().isoformat()
    client.post("/api/finance/transactions", json={"date": today, "amount": 800, "kind": "einnahme", "category": "Werkstudentenjob"})
    client.post("/api/finance/transactions", json={"date": today, "amount": 120.5, "kind": "ausgabe", "category": "Lebensmittel"})
    client.post("/api/finance/transactions", json={"date": today, "amount": 400, "kind": "ausgabe", "category": "Lebensmittel"})
    data = client.get("/api/finance").json()
    assert data["summary"] == {"income": 800.0, "expense": 520.5, "saldo": 279.5, "count": 3}
    food = next(c for c in data["categories"] if c["category"] == "Lebensmittel")
    assert food["over"] is True  # Budget 280 €
    assert client.post("/api/finance/transactions", json={"date": today, "amount": -5, "kind": "ausgabe"}).status_code == 422
