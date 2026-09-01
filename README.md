# Prisbevakare

Egen, gratis prisbevakning för valfria produkter hos svenska nätbutiker.
Byggd som ersättning för Prisjakt i mindre skala: du bestämmer exakt vilka
produkter och butiker som bevakas, ingen mellanhand, ingen kostnad.

## Hur det fungerar

1. `price_tracker.py` läser `config.json`, hämtar varje produktsida och
   försöker läsa ut priset (först via schema.org JSON-LD i sidan, sedan via
   regex på svenska prisformat som "5 990:-" eller "5 990 kr").
2. Varje körning lägger till en rad i `data/price_history.csv` — full
   historik, aldrig skrivs över.
3. `generate_dashboard.py` bygger `docs/index.html`: tabell + graf per
   produkt, med senaste pris, lägsta pris och trend.
4. GitHub Actions (`.github/workflows/price-check.yml`) kör steg 1–3
   automatiskt en gång per dag, och committar resultatet tillbaka till
   repot.
5. GitHub Pages serverar `docs/index.html` som en vanlig webbsida du kan
   bokmärka.

## Kom igång (en gång)

1. Skapa ett nytt repo på GitHub (kan vara privat).
2. Lägg in alla filer i den här mappen i repot, pusha.
3. Gå till **Settings → Actions → General → Workflow permissions** och
   välj "Read and write permissions" (annars kan workflowet inte committa
   tillbaka datan).
4. Gå till **Settings → Pages**, välj Source: "Deploy from a branch",
   branch: `main`, mapp: `/docs`. Efter någon minut får du en URL typ
   `https://<ditt-användarnamn>.github.io/<repo-namn>/`.
5. Kör workflowet manuellt en första gång: fliken **Actions → Prisbevakning
   → Run workflow**, så du slipper vänta till nästa schemalagda körning.

Efter det sköter GitHub resten. Du betalar ingenting så länge repot är
inom GitHubs gratiskvot för Actions (privata repon: 2 000 minuter/månad —
den här jobben tar någon sekund per körning, alltså inget att oroa sig
för).

## Lägga till fler produkter/butiker

Redigera `config.json`:

```json
{
  "products": [
    {
      "name": "Sennheiser HDB 630",
      "sources": [
        {"retailer": "HiFi Klubben", "url": "https://www.hifiklubben.se/..."},
        {"retailer": "Power", "url": "https://www.power.se/..."}
      ]
    }
  ]
}
```

Lägg till hur många produkter och butiker som helst. Varje källa hämtas
separat och sparas separat i historiken.

## Kända begränsningar (läs innan du är besviken)

- **Sidor som renderas med JavaScript kan inte läsas av det här scriptet**
  utan vidare — `requests` hämtar bara den råa HTML:en, ingen webbläsare
  körs. De flesta svenska e-handelssidor (inklusive HiFi Klubben, som är
  testad) renderar priset på servern så det fungerar, men stöter du på en
  butik där priset saknas i utdata behöver scriptet byggas om med
  Playwright för just den butiken — mer komplext, inte "hyfsat enkelt".
- **Prisavläsningen är heuristisk.** Fungerar den generella regeln inte
  för en specifik butik, lägg till en sajt-specifik CSS-selektor i
  `SITE_OVERRIDES` i `price_tracker.py`. Detta är den återkommande
  underhållskostnaden — räkna med att någon butik då och då kräver en
  liten justering efter en sajtomdesign.
- **Botskydd (Cloudflare m.fl.)** kan blockera automatiserade anrop även
  om sidan i övrigt är enkel att läsa. Märker du 403-fel i Actions-loggen
  är det troligen detta — det finns ingen garanterad lösning som inte
  bryter mot butikens användarvillkor.
- **Robots.txt och användarvillkor:** kontrollerat att hifiklubben.se och
  power.se tillåter allmän crawling i sina robots.txt (september 2026),
  men det säger inget om butikens användarvillkor. Håll anropsfrekvensen
  låg (en gång/dag, `request_delay_seconds` mellan varje sida) och
  använd inte datan kommersiellt.

## Lägga till avisering vid prisfall (nästa steg, inte byggt än)

Om du vill ha en Slack- eller mejlnotis när priset går ner: enklast är
att lägga till ett `slack_webhook` eller SMTP-steg i GitHub Actions som
läser sista raden i `price_history.csv` och jämför med föregående, och
skickar bara om priset sjunkit. Säg till så bygger jag det när du vet
vilken kanal du vill använda.
