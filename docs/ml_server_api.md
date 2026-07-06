# ML-Server API — Synthetische Daten

Der ML-Server der DigiPhenoMS-Arbeitsgruppe erzeugt **synthetische Assessmentdaten** auf Basis der realen Kohorte. Hinter dem Server steht ein **Job-Management**: Jedes Artefakt (Modell, synthetischer Datensatz, Evaluationsreport) ist einem Job und damit einer Job-ID zugeordnet. Diese Dokumentation beschreibt die API des Servers sowie ihre Integration in die DigiPhenoMS-Pipeline und den HAPI FHIR Server.

## Überblick für Einsteiger: Wozu der ML-Server da ist

Die echten DigiPhenoMS-Patientendaten sind schutzbedürftig und dürfen nicht frei weitergegeben werden — auch nicht an alle, die Software dafür entwickeln oder testen wollen. Der ML-Server löst genau dieses Problem: Er steht in einer geschützten Umgebung **bei den echten Daten**, lernt deren statistische Muster und erzeugt daraus **synthetische Daten** — künstliche Patient:innen, die sich statistisch wie die reale Kohorte verhalten, aber keiner echten Person entsprechen. Mit diesen Daten kann gefahrlos entwickelt, getestet und demonstriert werden.

### Das Job-Modell

Die Aufgaben des Servers dauern Minuten bis Stunden — Anfragen werden deshalb nicht sofort beantwortet, sondern als **Job** ausgeführt: Ein `POST /jobs` startet einen Job und liefert eine **Job-ID** zurück; die Arbeit läuft im Hintergrund. Über `GET /jobs/{id}` fragt man den Status ab, bis der Job abgeschlossen ist. Jedes Ergebnis (**Artefakt**) bleibt seinem Job zugeordnet — die Job-ID ist gewissermaßen der *Abholschein*, mit dem das Artefakt später heruntergeladen wird.

### Die drei Job-Typen

| Job-Typ        | `job_type`   | Eingabe                           | Aufgabe                                                                                       | Artefakt                         |
| -------------- | ------------ | --------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------- |
| **Training**   | `training`   | —                                 | Generatives Modell auf den echten Patiententabellen trainieren                                | Modell (**nicht** downloadbar)   |
| **Synthese**   | `synthesis`  | `training_job_id`, `scale_factor` | Mit dem trainierten Modell einen künstlichen Datensatz erzeugen                               | Datensatz (ZIP mit CSV-Tabellen) |
| **Evaluation** | `evaluation` | `synthesis_job_id`                | Qualität des synthetischen Datensatzes prüfen (statistische Treue, Nutzbarkeit, Privatsphäre) | Report (ZIP)                     |

Anschaulich: Das **Training** ist wie ein Autor, der alle echten Fallakten liest, bis er neue, fiktive, aber realistische Akten schreiben kann. Das Modell selbst verlässt den geschützten Server **nie** — man erhält nur seine Job-ID, um darauf aufzubauen. Die **Synthese** lässt diesen Autor dann tatsächlich schreiben: `scale_factor` bestimmt die Größe des Ergebnisses (`1.0` ≈ Umfang des Originals, `2.0` doppelt so groß, `0.5` halb). Die **Evaluation** ist die Qualitätskontrolle: Wie originalgetreu ist der Datensatz, taugt er für Analysen, und verrät er nichts über echte Personen?

Die Job-Typen bauen aufeinander auf — jede Stufe konsumiert die Job-ID der vorherigen:

```text
Training ──(training_job_id)──▶ Synthese ──(synthesis_job_id)──▶ Evaluation
  Modell                          Datensatz (ZIP)                  Report (ZIP)
```

Für alle drei Stufen liegt auf dem Server bereits je ein abgeschlossener Beispiel-Job (siehe [Abschnitt 5](#5-bekannte-jobs-und-artefakte)) — den Datensatz des Synthese-Jobs kann man also sofort herunterladen, ohne selbst zu trainieren. Wie Pipeline, CLI und FHIR-Operationen diese Jobs ansteuern, zeigt [Abschnitt 7](#7-integration-cli-pipeline-und-fhir-operationen).

## Inhalt

1. [Zugang: SSH Port Forwarding](#1-zugang-ssh-port-forwarding)
2. [Authentifizierung](#2-authentifizierung)
3. [Endpunkte und OpenAPI-Spezifikation](#3-endpunkte-und-openapi-spezifikation)
4. [Jobs anstoßen und überwachen (curl)](#4-jobs-anstoßen-und-überwachen-curl)
5. [Bekannte Jobs und Artefakte](#5-bekannte-jobs-und-artefakte)
6. [Beschreibung der synthetischen Daten](#6-beschreibung-der-synthetischen-daten)
7. [Integration: CLI, Pipeline und FHIR-Operationen](#7-integration-cli-pipeline-und-fhir-operationen)
8. [Fehlerbehebung](#8-fehlerbehebung)

---

## 1. Zugang: SSH Port Forwarding

Der Proxy auf dem ML-Server ist sehr restriktiv — direkte HTTP-Verbindungen sind nicht möglich. Als Workaround wird ein lokales SSH Port Forwarding eingerichtet, sodass alle HTTP-Anfragen an `localhost` gesendet und von dort an den ML-Server weitergeleitet werden.

Benötigte Zugangsdaten (bei der ML-Arbeitsgruppe erfragen — Host-Adresse und Zugangsdaten werden **nicht** im Repository hinterlegt):

- **Nutzername** → Umgebungsvariable `ML_SERVER_SSH_USER`
- **Passwort**
- **Host-Adresse des ML-Servers** → Umgebungsvariable `ML_SERVER_SSH_HOST`

In einem separaten Terminal (offen lassen):

```bash
export ML_SERVER_SSH_USER=<nutzername>
export ML_SERVER_SSH_HOST=<ml-server-host>

ssh -L 8000:localhost:8000 "$ML_SERVER_SSH_USER@$ML_SERVER_SSH_HOST" -N
```

Der erste Port bestimmt, unter welchem lokalen Port die API erreichbar ist. Ist Port 8000 belegt, kann ein anderer verwendet werden — dann muss der Port in allen API-Aufrufen (bzw. in `ML_SERVER_URL`) angepasst werden:

```bash
ssh -L 9000:localhost:8000 "$ML_SERVER_SSH_USER@$ML_SERVER_SSH_HOST" -N
# API-Aufrufe dann gegen http://localhost:9000/...
```

## 2. Authentifizierung

Jeder HTTP-Request benötigt einen **Bearer-Token** im `Authorization`-Header. Der Token wird von der ML-Arbeitsgruppe separat geteilt und in der Umgebungsvariable `API_AUTH_TOKEN` hinterlegt — **niemals im Repository committen**:

```bash
export API_AUTH_TOKEN=<token>
```

Für das Docker-Setup wird der Token in `docker/.env` eingetragen (die Datei ist gitignored, Vorlage: `docker/.env.example`).

## 3. Endpunkte und OpenAPI-Spezifikation

| Methode | Pfad                 | Beschreibung                                        |
| ------- | -------------------- | --------------------------------------------------- |
| `POST`  | `/jobs`              | Job starten (`training`, `synthesis`, `evaluation`) |
| `GET`   | `/jobs/{id}`         | Job-Status abfragen                                 |
| `GET`   | `/jobs/{id}/dataset` | Synthetischen Datensatz herunterladen (ZIP)         |
| `GET`   | `/jobs/{id}/report`  | Evaluationsreport herunterladen (ZIP)               |
| `GET`   | `/openapi.json`      | OpenAPI-Spezifikation (für Client-Generierung)      |

Die OpenAPI-Spezifikation kann als JSON gespeichert oder im Browser eingesehen werden:

```bash
curl -s http://localhost:8000/openapi.json | python3 -m json.tool > openapi.json
# oder mit dem mitgelieferten Client:
digiphenoms-ml openapi --output openapi.json
```

Dokumentation im Browser: `http://localhost:8000/docs`

## 4. Jobs anstoßen und überwachen (curl)

### Trainings-Job

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "training"
  }'
```

### Synthese-Job (basierend auf einem Trainings-Job)

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "synthesis",
    "scale_factor": 1.0,
    "training_job_id": "ee81f8cd-70d4-4db3-b2e1-02eb54b99a21"
  }'
```

### Evaluations-Job (basierend auf einem Synthese-Job)

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "evaluation",
    "synthesis_job_id": "f148e40c-ec8b-4f99-8de4-8177ac4bc8c8"
  }'
```

### Job-Status prüfen

```bash
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://localhost:8000/jobs/f148e40c-ec8b-4f99-8de4-8177ac4bc8c8
```

### Artefakte herunterladen

```bash
# Synthetischer Datensatz (Synthese-Job)
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -o datasets.zip \
  http://localhost:8000/jobs/f148e40c-ec8b-4f99-8de4-8177ac4bc8c8/dataset

# Evaluationsreport (Evaluations-Job)
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -o report.zip \
  http://localhost:8000/jobs/58e3fc43-e385-4c09-8bfd-103a177bdaae/report
```

## 5. Bekannte Jobs und Artefakte

Artefakte sind an Job-IDs gebunden — man benötigt also das Wissen, welche Job-IDs auf dem Server existieren und welches Artefakt ihnen zugeordnet ist. Aktuell hinterlegt:

| Job-ID                                 | Typ        | Artefakt                   |
| -------------------------------------- | ---------- | -------------------------- |
| `ee81f8cd-70d4-4db3-b2e1-02eb54b99a21` | Training   | Modell (nicht downloadbar) |
| `f148e40c-ec8b-4f99-8de4-8177ac4bc8c8` | Synthese   | Synthetischer Datensatz    |
| `58e3fc43-e385-4c09-8bfd-103a177bdaae` | Evaluation | Evaluationsreport          |

## 6. Beschreibung der synthetischen Daten

Die synthetischen Daten umfassen aktuell **vier Tabellen**:

- **Patienten** (→ Pipeline-Schritt `patient_profile`)
- **MRT** (→ `mrt`)
- **LCLAT** (→ `lclat_summary`)
- **WST** (→ `wst_summary`)

Die Pipeline überspringt Schritte ohne passende Eingabedateien automatisch (Warnung im Log) — ein Lauf mit nur diesen vier Tabellen ist also problemlos möglich.

### Bekannte Schwächen der Daten

- **Zeitpunkte, die chronologisch sein müssen, sind nicht garantiert chronologisch** (z. B. kann der Endzeitpunkt eines Assessments vor seinem Startzeitpunkt liegen).

  → Die Pipeline korrigiert invertierte `Period`-Zeiträume automatisch beim Ressourcen-Aufbau (FHIR-Invariante `per-1`, Tausch von `start`/`end` mit Warnung im Log). Konfigurierbar über `data_quality.fix_chronology` in `pipeline/config/pipeline.yaml` (Standard: aktiviert).

Weitere Unzulänglichkeiten der synthetischen Daten bitte an die ML-Arbeitsgruppe zurückmelden.

## 7. Integration: CLI, Pipeline und FHIR-Operationen

### 7.1 `digiphenoms-ml` — Job-Verwaltung per CLI

Installation: `pip install -e "pipeline[ml]"` (bzw. `[submit]` oder `[dev]`, enthalten jeweils `httpx`). Der Token kommt aus `$API_AUTH_TOKEN`, die Server-URL aus `$ML_SERVER_URL` (Standard: `http://localhost:8000`), das Request-Timeout aus `$ML_SERVER_TIMEOUT` (Standard: 60 s).

```bash
# Jobs starten
digiphenoms-ml train
digiphenoms-ml synthesize --training-job ee81f8cd-70d4-4db3-b2e1-02eb54b99a21 --scale-factor 1.0
digiphenoms-ml evaluate --synthesis-job f148e40c-ec8b-4f99-8de4-8177ac4bc8c8

# Status abfragen (--wait pollt bis zum Abschluss)
digiphenoms-ml status f148e40c-ec8b-4f99-8de4-8177ac4bc8c8 [--wait]

# Artefakte herunterladen (ZIP wird automatisch entpackt)
digiphenoms-ml download-dataset f148e40c-ec8b-4f99-8de4-8177ac4bc8c8 --output data/
digiphenoms-ml download-report 58e3fc43-e385-4c09-8bfd-103a177bdaae --output reports/

# OpenAPI-Spezifikation abrufen
digiphenoms-ml openapi --output openapi.json
```

### 7.2 Pipeline: synthetischen Datensatz direkt verarbeiten

`digiphenoms-fhir --ml-dataset-job <SYNTHESE_JOB_ID>` lädt den Datensatz vor dem Mapping in das Datenverzeichnis (CSV-Dateien werden flach entpackt) und führt anschließend die reguläre Pipeline aus — auf Wunsch inklusive `$cohort-submit`:

```bash
# 1. SSH-Tunnel starten (separates Terminal, siehe Abschnitt 1)
# 2. Token setzen
export API_AUTH_TOKEN=<token>

# 3. Synthetische Daten → FHIR → HAPI Server
digiphenoms-fhir \
  --config pipeline/config \
  --data data/synthetic \
  --output output/ \
  --ml-dataset-job f148e40c-ec8b-4f99-8de4-8177ac4bc8c8 \
  --submit --fhir-endpoint http://localhost:8080/fhir
```

Weitere Flags: `--ml-server-url` (überschreibt `$ML_SERVER_URL`), `--ml-wait` (wartet auf Job-Abschluss, `--ml-poll-interval` steuert das Intervall).

### 7.3 FHIR-Operationen auf dem HAPI Server

Die Server-Extension stellt die ML-Job-Verwaltung zusätzlich als **systemweite FHIR-Operationen** bereit (Provider: `MlJobOperation`, Client: `MlServerClient`):

| Operation        | HTTP         | Parameter                                | Wirkung                 |
| ---------------- | ------------ | ---------------------------------------- | ----------------------- |
| `$ml-train`      | `POST`       | —                                        | Trainings-Job starten   |
| `$ml-synthesize` | `POST`       | `trainingJobId` (Pflicht), `scaleFactor` | Synthese-Job starten    |
| `$ml-evaluate`   | `POST`       | `synthesisJobId` (Pflicht)               | Evaluations-Job starten |
| `$ml-job-status` | `GET`/`POST` | `jobId` (Pflicht)                        | Job-Status abfragen     |

Antwort ist jeweils eine `Parameters`-Ressource mit den Teilen `jobId`, `jobType`, `status` (sofern im Server-Response enthalten) sowie dem rohen Job-JSON in `job`.

```bash
# Synthese-Job über FHIR anstoßen ($ in Single Quotes, sonst Shell-Expansion)
curl -X POST 'http://localhost:8080/fhir/$ml-synthesize' \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Parameters",
    "parameter": [
      {"name": "trainingJobId", "valueString": "ee81f8cd-70d4-4db3-b2e1-02eb54b99a21"},
      {"name": "scaleFactor", "valueDecimal": 1.0}
    ]
  }'

# Status per GET
curl "http://localhost:8080/fhir/\$ml-job-status?jobId=f148e40c-ec8b-4f99-8de4-8177ac4bc8c8"
```

**Konfiguration** (Umgebungsvariablen des FHIR-Servers):

| Variable                             | Bedeutung                      | Standard                |
| ------------------------------------ | ------------------------------ | ----------------------- |
| `ML_SERVER_URL`                      | Basis-URL des ML-Servers       | `http://localhost:8000` |
| `ML_SERVER_TOKEN` / `API_AUTH_TOKEN` | Bearer-Token                   | — (Pflicht)             |
| `ML_SERVER_TIMEOUT`                  | Timeout je Request in Sekunden | `60`                    |

Im Docker-Setup zeigt `ML_SERVER_URL` standardmäßig auf `http://host.docker.internal:8000`, da der SSH-Tunnel auf dem Docker-Host läuft (`extra_hosts: host-gateway` ist in `docker-compose.yml` gesetzt). Der Download der Artefakte erfolgt bewusst **nicht** über FHIR, sondern über die Python-Seite (`digiphenoms-ml download-dataset` bzw. `--ml-dataset-job`).

## 8. Fehlerbehebung

| Symptom                                                     | Ursache / Lösung                                                                                     |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `Connection ... failed. Is the SSH port forwarding active?` | Tunnel nicht aktiv — SSH-Befehl aus Abschnitt 1 in separatem Terminal starten                        |
| HTTP 401/403                                                | Token fehlt oder ist ungültig — `API_AUTH_TOKEN` prüfen                                              |
| HTTP 404 bei `/dataset` bzw. `/report`                      | Falsche Job-ID oder falscher Job-Typ (Datensatz nur bei Synthese-, Report nur bei Evaluations-Jobs)  |
| FHIR-Operation liefert HTTP 500 mit Token-Hinweis           | `ML_SERVER_TOKEN`/`API_AUTH_TOKEN` ist im FHIR-Server-Container nicht gesetzt (`docker/.env` prüfen) |
| Docker: Verbindung zum Tunnel schlägt fehl                  | `ML_SERVER_URL=http://host.docker.internal:8000` verwenden, nicht `localhost`                        |
