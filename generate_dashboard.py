#!/usr/bin/env python3
"""
Bygger docs/index.html - en fristående sida med prishistorik per produkt/butik.
Läser data/price_history.csv och skriver en självbärande HTML-fil (Chart.js
laddas från CDN, all data är inbäddad direkt i sidan).

Tänkt att köras efter price_tracker.py, och docs/-mappen är tänkt att
publiceras med GitHub Pages.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HISTORY_PATH = BASE_DIR / "data" / "price_history.csv"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_PATH = DOCS_DIR / "index.html"


def sek(n):
    """Svenskt talformat: 5990 -> '5 990 kr'"""
    return f"{n:,.0f}".replace(",", " ") + " kr"


def load_history():
    series = defaultdict(list)  # (product, retailer) -> [(timestamp, price)]
    if not HISTORY_PATH.exists():
        return series
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok" and row.get("price_sek"):
                key = (row["product"], row["retailer"])
                series[key].append((row["timestamp_utc"], int(row["price_sek"])))
    for key in series:
        series[key].sort(key=lambda pair: pair[0])
    return series


def build_html(series):
    products = sorted({product for product, _ in series})
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards = []
    chart_datasets = {}
    for product in products:
        retailer_rows = []
        chart_datasets[product] = []
        for (p, retailer), points in series.items():
            if p != product:
                continue
            latest_ts, latest_price = points[-1]
            lowest_price = min(price for _, price in points)
            first_price = points[0][1]
            diff = latest_price - first_price
            trend = "→"
            if diff < 0:
                trend = "↓"
            elif diff > 0:
                trend = "↑"
            retailer_rows.append(
                f"<tr><td>{retailer}</td><td>{sek(latest_price)}</td>"
                f"<td>{sek(lowest_price)}</td><td>{trend} {sek(abs(diff))}</td>"
                f"<td>{latest_ts[:16].replace('T', ' ')}</td></tr>"
            )
            chart_datasets[product].append(
                {
                    "label": retailer,
                    "data": [{"x": ts, "y": price} for ts, price in points],
                }
            )

        cards.append(
            f"""
            <section class="card">
              <h2>{product}</h2>
              <table>
                <thead>
                  <tr><th>Butik</th><th>Senaste pris</th><th>Lägsta pris</th>
                  <th>Trend</th><th>Senast uppdaterad</th></tr>
                </thead>
                <tbody>{''.join(retailer_rows)}</tbody>
              </table>
              <canvas id="chart-{products.index(product)}" height="120"></canvas>
            </section>
            """
        )

    chart_js_blocks = []
    for i, product in enumerate(products):
        datasets_json = json.dumps(chart_datasets[product])
        chart_js_blocks.append(
            f"""
            new Chart(document.getElementById('chart-{i}'), {{
              type: 'line',
              data: {{ datasets: {datasets_json}.map((d, idx) => ({{
                ...d,
                borderColor: ['#0a5','#06c','#c60','#c06','#666'][idx % 5],
                fill: false,
                tension: 0.15,
              }})) }},
              options: {{
                parsing: false,
                scales: {{ x: {{ type: 'time', time: {{ unit: 'day' }} }},
                           y: {{ ticks: {{ callback: (v) => v.toLocaleString('sv-SE') + ' kr' }} }} }},
                plugins: {{ legend: {{ position: 'bottom' }} }}
              }}
            }});
            """
        )

    return f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prisbevakning</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-adapter-date-fns/3.0.0/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#f7f7f8; margin:0; padding:2rem; color:#1a1a1a; }}
  h1 {{ font-size:1.4rem; }}
  .meta {{ color:#666; font-size:0.85rem; margin-bottom:2rem; }}
  .card {{ background:#fff; border-radius:12px; padding:1.25rem 1.5rem; margin-bottom:1.5rem;
           box-shadow:0 1px 3px rgba(0,0,0,0.08); }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:1rem; font-size:0.9rem; }}
  th, td {{ text-align:left; padding:0.4rem 0.6rem; border-bottom:1px solid #eee; }}
  th {{ color:#666; font-weight:600; }}
</style>
</head>
<body>
<h1>Prisbevakning</h1>
<div class="meta">Senast uppdaterad: {generated_at} · genererad automatiskt, redigera inte manuellt</div>
{''.join(cards) if cards else '<p>Ingen prisdata ännu — vänta på första körningen.</p>'}
<script>
{''.join(chart_js_blocks)}
</script>
</body>
</html>
"""


def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    series = load_history()
    html = build_html(series)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Skrev {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
