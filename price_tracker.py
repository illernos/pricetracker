#!/usr/bin/env python3
"""
Enkel prisbevakare för svenska nätbutiker.

Läser produkter/butiker från config.json, hämtar sidorna, försöker läsa ut
priset (först via schema.org JSON-LD, annars via regex på svenska
prisformat som "5 990:-" eller "5 990 kr"), och lägger till en rad per
körning i data/price_history.csv.

Körs tänkt som ett dagligt GitHub Actions-jobb, men går lika bra att köra
lokalt: `python price_tracker.py`

VIKTIGT om underhåll:
Butiker byter då och då sin sidstruktur. Går JSON-LD-tolkningen och
regex-fallbacken fel för en viss butik behöver du/jag lägga till en
site-specifik regel i SITE_OVERRIDES nedan. Det är den återkommande
kostnaden med den här typen av lösning - se den som en förutsättning,
inte ett tecken på att något är trasigt.
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
HISTORY_PATH = DATA_DIR / "price_history.csv"

CSV_HEADER = ["timestamp_utc", "product", "retailer", "price_sek", "currency", "url", "status"]

# Svenska prisformat: "5 990:-", "5990:-", "5 990 kr", "3989 kr"
# Mellanslag kan vara vanligt mellanslag eller icke-brytande mellanslag (\xa0/ ).
PRICE_RE = re.compile(
    r"(\d{1,3}(?:[\s  ]?\d{3})*)(?:\s?:-|\s?kr\b)",
    re.IGNORECASE,
)

# Lägg till site-specifika CSS-selektorer här om den generella tolkningen
# missar priset för en viss butik. Exempel:
# "hifiklubben.se": {"selector": "span.product-price", "attr": None}
SITE_OVERRIDES = {}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize_whitespace(text):
    return text.replace("\xa0", " ").replace(" ", " ")


def parse_price_from_jsonld(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            offers = entry.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict) and "price" in offers:
                try:
                    price = float(str(offers["price"]).replace(",", "."))
                    currency = offers.get("priceCurrency", "SEK")
                    return round(price), currency
                except ValueError:
                    continue
    return None, None


def parse_price_from_meta(soup):
    for prop in ["product:price:amount", "og:price:amount"]:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            try:
                return round(float(tag["content"])), "SEK"
            except ValueError:
                continue
    return None, None


def parse_price_from_text(soup, hostname):
    # Medvetet ingen blind "ta första kr-mönstret på sidan"-fallback här.
    # Testat mot verklig HiFi Klubben-sida: första prismönstret på sidan är
    # ofta ett outlet-/från-pris ("från 5 691:-"), inte huvudpriset
    # ("5 990:-"). Att gissa fel skulle tysta förstöra prishistoriken, så
    # om JSON-LD/meta-tolkningen misslyckas kräver vi en explicit,
    # verifierad CSS-selektor per butik i SITE_OVERRIDES istället för att
    # chansa.
    override = SITE_OVERRIDES.get(hostname)
    if override:
        el = soup.select_one(override["selector"])
        if el:
            text = el.get(override["attr"]) if override.get("attr") else el.get_text()
            match = PRICE_RE.search(normalize_whitespace(text))
            if match:
                return int(match.group(1).replace(" ", "")), "SEK"
    return None, None


def fetch_price(url, settings):
    headers = {"User-Agent": settings.get("user_agent", "Mozilla/5.0")}
    timeout = settings.get("timeout_seconds", 15)
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    hostname = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]

    price, currency = parse_price_from_jsonld(soup)
    if price is None:
        price, currency = parse_price_from_meta(soup)
    if price is None:
        price, currency = parse_price_from_text(soup, hostname)
    return price, currency


def ensure_history_file():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_PATH.exists():
        with open(HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)


def last_price(product, retailer):
    if not HISTORY_PATH.exists():
        return None
    last = None
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["product"] == product and row["retailer"] == retailer and row["price_sek"]:
                last = int(row["price_sek"])
    return last


def append_row(row):
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def main():
    config = load_config()
    settings = config.get("settings", {})
    ensure_history_file()

    any_success = False
    for product in config["products"]:
        name = product["name"]
        for source in product["sources"]:
            retailer = source["retailer"]
            url = source["url"]
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                price, currency = fetch_price(url, settings)
                if price is None:
                    print(f"[VARNING] Kunde inte tolka pris för {name} @ {retailer} ({url})")
                    append_row([timestamp, name, retailer, "", "", url, "parse_failed"])
                else:
                    previous = last_price(name, retailer)
                    trend = ""
                    if previous is not None and price != previous:
                        diff = price - previous
                        trend = f" ({'+' if diff > 0 else ''}{diff} kr vs föregående körning)"
                    print(f"[OK] {name} @ {retailer}: {price} {currency}{trend}")
                    append_row([timestamp, name, retailer, price, currency, url, "ok"])
                    any_success = True
            except requests.RequestException as exc:
                print(f"[FEL] Kunde inte hämta {name} @ {retailer} ({url}): {exc}")
                append_row([timestamp, name, retailer, "", "", url, "fetch_failed"])

            time.sleep(settings.get("request_delay_seconds", 3))

    if not any_success:
        print("Ingen enda källa gick att läsa av denna körning.")
        sys.exit(1)


if __name__ == "__main__":
    main()
