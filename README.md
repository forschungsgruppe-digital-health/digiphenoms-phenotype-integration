# DigiPhenoMS FHIR Integration

Konfigurationsgetriebene Pipeline zur Transformation klinischer CSV-Daten des **DigiPhenoMS**-Projekts (_Digitale Phänotypisierung für das intelligente Management der Multiplen Sklerose_) in [FHIR R4](https://hl7.org/fhir/R4/) Ressourcen und deren Import in einen HAPI FHIR Server.

## Projektübersicht

Das DigiPhenoMS-Projekt am Universitätsklinikum Carl Gustav Carus Dresden erfasst klinische Daten von MS-Patienten über verschiedene digitale Assessments. Diese Pipeline überführt die erhobenen CSV-Rohdaten in standardisierte FHIR-Ressourcen und stellt mit der `$cohort-submit`-Operation einen strukturierten Import in einen HAPI FHIR Server bereit — für Webanwendungen zur Visualisierung von Kohorten- und individuellen Patientenprofilen.

```
CSV-Rohdaten → FHIR Mapping → Collection Bundle → $cohort-submit → HAPI FHIR Server → FHIR REST API
```

### Erfasste klinische Instrumente

| Instrument             | CSV-Quelle         | FHIR-Ressource                      | Beschreibung                                                          |
| ---------------------- | ------------------ | ----------------------------------- | --------------------------------------------------------------------- |
| **LCLA**               | `lclat_summary`    | Observation                         | Low-Contrast Letter Acuity Test — Kontrastsehschärfe                  |
| **9HPT**               | `mdt_summary`      | Observation                         | Nine-Hole Peg Test — Handfeinmotorik                                  |
| **SDMT**               | `npst_summary`     | Observation                         | Symbol Digit Modalities Test — kognitive Verarbeitungsgeschwindigkeit |
| **T25FW**              | `wst_summary`      | Observation                         | Timed 25-Foot Walk — Gehgeschwindigkeit                               |
| **Neuro-QoL**          | `nq_detail`        | QuestionnaireResponse + Observation | Patient-Reported Outcomes (CAT)                                       |
| **Anamnese**           | `mh_detail`        | QuestionnaireResponse               | Medizinische Vorgeschichte                                            |
| **MRT**                | `mrt`              | DiagnosticReport + Observation      | Hirn-Volumetrie und Läsionssegmentierung                              |
| **Patientenprofil**    | `patient_profile`  | Patient + Condition                 | Demografie, MS-Diagnose, Komorbiditäten                               |
| **Assessment-Wrapper** | `wrapper_overview` | Encounter + Device                  | Sitzungsmetadaten und Geräteinformationen                             |

## Projektstruktur

```
DigiPhenoMS/
├── pipeline/                           # Python-Mapping-Pipeline
│   ├── config/                         # YAML-Konfigurationen
│   │   ├── pipeline.yaml               # Pipeline-Schritte und Ausführungsreihenfolge
│   │   ├── mapping/                    # Mapping-Regeln (je ein YAML pro CSV-Typ)
│   │   └── terminology/                # Terminologie-Mappings (ConceptMaps)
│   ├── src/digiphenoms_fhir/           # Python-Paket
│   │   ├── __init__.py
│   │   ├── mapper.py                   # Mapping-Engine (ResourceBuilder, Pipeline)
│   │   └── __main__.py                 # CLI-Einstiegspunkt
│   ├── tests/                          # Pytest-Testsuite
│   │   ├── fixtures/                   # Synthetische Testdaten (CSV)
│   │   ├── test_resource_builder.py    # Unit-Tests für Ressourcen-Erzeugung
│   │   └── test_pipeline.py            # Integrationstests
│   └── pyproject.toml                  # Python-Projektdefinition
├── server/                             # $cohort-submit Spring Extension (JAR)
│   ├── src/main/java/de/tud/fgdh/digiphenoms/fhir/
│   │   ├── operations/
│   │   │   └── CohortSubmitOperation.java  # $cohort-submit Provider
│   │   ├── service/
│   │   │   ├── CohortSubmitService.java    # 9-Stufen-Verarbeitungslogik
│   │   │   └── ImportStatistics.java       # Zähler für Import-Statistik
│   │   └── config/
│   │       └── FhirClientConfig.java       # FHIR-Client-Konfiguration
│   └── pom.xml                             # Maven-Projektdefinition (Thin JAR)
├── docker/                             # Container-Deployment
│   ├── docker-compose.yml              # HAPI + PostgreSQL + Pipeline
│   ├── hapi/
│   │   ├── Dockerfile                  # Multi-Stage Build (Maven → HAPI Image)
│   │   └── application.yaml            # HAPI FHIR Server-Konfiguration
│   ├── pipeline/Dockerfile             # Python-Pipeline-Container
│   └── .env.example                    # Umgebungsvariablen-Vorlage
├── docs/                               # Dokumentation
│   ├── data_schema_summary.md
│   ├── fhir_mapping_concept.md
│   ├── cohort_submit_specification.md
│   └── phenotyping_research.md
├── .github/workflows/ci.yml           # GitHub Actions CI
└── LICENSE
```

## Installation

### Pipeline (Python)

```bash
cd pipeline

# Virtuelle Umgebung anlegen und aktivieren
python -m venv .venv
source .venv/bin/activate    # Linux/macOS

# Basis-Installation (Mapping)
pip install -e .

# Mit Kohortenimport ($cohort-submit Client)
pip install -e ".[submit]"

# Mit Entwicklungsabhängigkeiten (pytest, httpx)
pip install -e ".[dev]"
```

### Server (Java Extension JAR)

```bash
cd server
mvn package
```

Das erzeugte JAR wird beim Docker-Build automatisch in das HAPI FHIR Image kopiert (`/app/extra-classes/`) und beim Start über den `PropertiesLauncher` geladen.

### Docker (empfohlen)

```bash
cd docker
cp .env.example .env    # Konfiguration anpassen

# Server + Datenbank starten
docker compose up -d fhir-server

# Pipeline ausführen (CSV-Daten in DATA_DIR bereitstellen)
docker compose run pipeline
```

## Verwendung

### Pipeline als CLI-Tool

```bash
cd pipeline

# Vollständige Pipeline ausführen
digiphenoms-fhir --config config/ --data data/ --output output/

# Nur bestimmte Schritte ausführen
digiphenoms-fhir --config config/ --data data/ --output output/ --steps patient_profile lclat_summary
```

### Pipeline als Python-Bibliothek

```python
from digiphenoms_fhir import Pipeline

pipeline = Pipeline(config_dir="pipeline/config/")
results = pipeline.run(data_dir="data/", output_dir="output/")

for step_name, resources in results.items():
    print(f"{step_name}: {len(resources)} Ressourcen")
```

### Docker-basierter Import

```bash
cd docker

# FHIR Server starten
docker compose up -d fhir-server

# Warten bis Server bereit ist
docker compose logs -f fhir-server  # bis "Started Application"

# Pipeline mit Kohortenimport ausführen
DATA_DIR=/pfad/zu/csv-daten docker compose run pipeline

# Server-Status prüfen
curl http://localhost:8080/fhir/metadata
```

## Architektur

Die Integration gliedert sich in zwei Phasen: **Mapping** (CSV → FHIR-Ressourcen) und **Import** (FHIR-Ressourcen → HAPI FHIR Server).

### Mapping-Pipeline

Die Pipeline nutzt einen **konfigurationsgetriebenen Ansatz**: Die gesamte Mapping-Logik ist in YAML-Dateien definiert, der Python-Code ist ein generischer Interpreter.

```
CSV-Datei → MappingConfig (YAML) → ResourceBuilder → FHIR-Ressource (dict) → Collection Bundle (JSON)
```

Kernkomponenten:

- **`MappingConfig`** — lädt und validiert YAML-Mapping-Konfigurationen
- **`ResourceBuilder`** — erzeugt FHIR-Ressourcen aus CSV-Zeilen + Konfiguration
- **`FHIRMapper`** — orchestriert das Mapping für einen einzelnen CSV-Typ
- **`Pipeline`** — führt alle Schritte in Abhängigkeitsreihenfolge aus (topologische Sortierung)
- **`TerminologyMap`** — übersetzt Quellcodes in SNOMED CT / LOINC / ICD-10 via ConceptMaps

### HAPI FHIR Server + $cohort-submit

Die benutzerdefinierte Operation `$cohort-submit` wird als Thin-JAR-Extension gebaut und beim Start des offiziellen `hapiproject/hapi:v7.6.0`-Images über `loader.path=/app/extra-classes/` geladen. Wesentliche Merkmale:

- **Referenzielle Integrität** — dreistufige Verarbeitung (Patienten → Encounters → Observations/Reports) gemäß Ressourcen-Abhängigkeitsgraph
- **Group-Hierarchie** — Wurzelgruppe (Kohorte) → Importgruppen (je Importvorgang) → Patientenreferenzen, für vollständige Nachvollziehbarkeit
- **Zwei Import-Modi** — _Merge_ (Conditional PUT, Upsert) und _Distinct_ (Conditional POST, nur Anlegen neuer Ressourcen)
- **Provenance** — automatische Audit-Trail-Dokumentation je Import

Details: [`docs/cohort_submit_specification.md`](docs/cohort_submit_specification.md)

## Terminologie und Kodierung

Alle klinischen Codes wurden gegen die **SNOMED CT International RF2 Release (April 2026)** verifiziert. Verwendete Terminologiesysteme:

- **SNOMED CT** — klinische Befunde, Verfahren, Assessmentskalen
- **LOINC** — Laborparameter und standardisierte Fragebögen (9HPT, Neuro-QoL)
- **ICD-10-GM** — Komorbiditäten (Sekundärkodierung)
- **UCUM** — Maßeinheiten

Details zur Terminologie: [`docs/fhir_mapping_concept.md`](docs/fhir_mapping_concept.md), Abschnitt 5.

## Tests ausführen

```bash
# Pipeline-Tests
cd pipeline
pytest -v
pytest --cov=digiphenoms_fhir --cov-report=term-missing

# Server-Build + Tests
cd server
mvn verify
```

## Dokumentation

| Dokument                                                                     | Inhalt                                                                                                                          |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| [`docs/data_schema_summary.md`](docs/data_schema_summary.md)                 | Zusammenfassung aller 9 CSV-Datenschemata mit Spalten, Wertebereichen und Missing-Raten                                         |
| [`docs/fhir_mapping_concept.md`](docs/fhir_mapping_concept.md)               | FHIR-Mapping-Konzept, Ressourcen-Zuordnung, Terminologie-Status                                                                 |
| [`docs/cohort_submit_specification.md`](docs/cohort_submit_specification.md) | `$cohort-submit` Schnittstellenspezifikation — OperationDefinition, Import-Modi, Anwendungsfälle, Sequenz- und Klassendiagramme |
| [`docs/phenotyping_research.md`](docs/phenotyping_research.md)               | Literaturrecherche zu digitaler Phänotypisierung bei MS                                                                         |

## Lizenz

MIT License — siehe [LICENSE](LICENSE).
