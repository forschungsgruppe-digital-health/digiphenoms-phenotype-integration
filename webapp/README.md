# DigiPhenoMS Demonstrator (Webapp)

Vue-3-Demonstrator zur Visualisierung der DigiPhenoMS-FHIR-Daten —
**ausschließlich mit synthetischen Daten**. Die App wird über GitHub Pages
veröffentlicht und kann alternativ an einen lokalen HAPI FHIR Server
angebunden werden. Der ML-Server ist **gemockt** (Dummy-Antworten, kein
Netzzugriff).

## Datenquellen

| Quelle                    | Inhalt                                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Demo-Daten** (Standard) | Gebündelte synthetische FHIR-Ressourcen (`public/demo-data/demo-bundle.json`), erzeugt aus den Pipeline-Fixtures |
| **HAPI FHIR Server**      | REST-Anbindung an einen laufenden HAPI-Server (z. B. `docker compose up fhir-server`), nur synthetische Daten    |

Der Mock des ML-Servers simuliert die dokumentierte Job-API
(`docs/ml_server_api.md`): Jobs durchlaufen *wartend → läuft →
abgeschlossen*; die drei dokumentierten Job-IDs sind vorbelegt.

## Entwicklung

```bash
cd webapp
npm install
npm run dev        # http://localhost:5173
npm run build      # Produktions-Build nach dist/
npm run preview    # Build lokal serven
```

### Demo-Daten neu erzeugen

Erzeugt `public/demo-data/demo-bundle.json` aus den synthetischen
Pipeline-Fixtures (benötigt die installierte Pipeline, z. B.
`pip install -e ../pipeline`):

```bash
npm run demo-data
```

### Deep-Links

| Parameter        | Wirkung                                        |
| ----------------- | ----------------------------------------------- |
| `?patient=<id>`  | Öffnet direkt die Detailansicht                |
| `?tab=ml`        | Öffnet den ML-Mock-Bereich                     |
| `?fhir=<url>`    | Verbindet beim Laden mit einem HAPI-Endpunkt   |

Beispiel lokal: `http://localhost:5173/?fhir=http://localhost:8080/fhir`

## Deployment (GitHub Pages)

Der Workflow `.github/workflows/pages.yml` baut die App bei Pushes auf
`main` (Pfad `webapp/**`) und veröffentlicht sie über GitHub Pages
(`BASE_PATH=/<repo>/`). Voraussetzung: GitHub Pages ist für das Repository
verfügbar (öffentliches Repository oder entsprechender Org-Plan).

Da die App ausschließlich synthetische, gebündelte Daten enthält, ist die
Veröffentlichung unbedenklich; eine Verbindung zu einem FHIR-Server wird
nur auf explizite Nutzeraktion aufgebaut (Browser → Server, z. B.
`http://localhost:8080/fhir` über die localhost-Ausnahme für Mixed
Content).
