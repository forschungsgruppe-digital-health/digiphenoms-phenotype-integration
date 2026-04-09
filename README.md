# DigiPhenoMS FHIR Mapping

Konfigurationsgetriebene Mapping-Pipeline zur Transformation klinischer CSV-Daten des **DigiPhenoMS**-Projekts (*Digitale Phänotypisierung für das intelligente Management der Multiplen Sklerose*) in [FHIR R4](https://hl7.org/fhir/R4/) Ressourcen.

## Projektübersicht

Das DigiPhenoMS-Projekt am Universitätsklinikum Carl Gustav Carus Dresden erfasst klinische Daten von MS-Patienten über verschiedene digitale Assessments. Diese Pipeline überführt die erhobenen CSV-Rohdaten in standardisierte FHIR-Ressourcen, um Interoperabilität und Sekundärnutzung zu ermöglichen.

### Erfasste klinische Instrumente

| Instrument | CSV-Quelle | FHIR-Ressource | Beschreibung |
|-----------|-----------|----------------|-------------|
| **LCLA** | `lclat_summary` | Observation | Low-Contrast Letter Acuity Test — Kontrastsehschärfe |
| **9HPT** | `mdt_summary` | Observation | Nine-Hole Peg Test — Handfeinmotorik |
| **SDMT** | `npst_summary` | Observation | Symbol Digit Modalities Test — kognitive Verarbeitungsgeschwindigkeit |
| **T25FW** | `wst_summary` | Observation | Timed 25-Foot Walk — Gehgeschwindigkeit |
| **Neuro-QoL** | `nq_detail` | QuestionnaireResponse + Observation | Patient-Reported Outcomes (CAT) |
| **Anamnese** | `mh_detail` | QuestionnaireResponse | Medizinische Vorgeschichte |
| **MRT** | `mrt` | DiagnosticReport + Observation | Hirn-Volumetrie und Läsionssegmentierung |
| **Patientenprofil** | `patient_profile` | Patient + Condition | Demografie, MS-Diagnose, Komorbiditäten |
| **Assessment-Wrapper** | `wrapper_overview` | Encounter + Device | Sitzungsmetadaten und Geräteinformationen |

## Projektstruktur

```
DigiPhenoMS/
├── config/                         # YAML-Konfigurationen
│   ├── pipeline.yaml               # Pipeline-Schritte und Ausführungsreihenfolge
│   ├── mapping/                    # Mapping-Regeln (je ein YAML pro CSV-Typ)
│   │   ├── patient_profile.mapping.yaml
│   │   ├── wrapper_overview.mapping.yaml
│   │   ├── lclat_summary.mapping.yaml
│   │   ├── mdt_summary.mapping.yaml
│   │   ├── npst_summary.mapping.yaml
│   │   ├── wst_summary.mapping.yaml
│   │   ├── nq_detail.mapping.yaml
│   │   ├── mh_detail.mapping.yaml
│   │   └── mrt.mapping.yaml
│   └── terminology/                # Terminologie-Mappings (ConceptMaps)
│       ├── comorbidity_conceptmap.yaml
│       ├── handedness_conceptmap.yaml
│       ├── walking_aids_conceptmap.yaml
│       └── neuroqol_domains_conceptmap.yaml
├── src/digiphenoms_fhir/           # Python-Paket
│   ├── __init__.py
│   ├── mapper.py                   # Mapping-Engine (ResourceBuilder, Pipeline)
│   └── __main__.py                 # CLI-Einstiegspunkt
├── tests/                          # Pytest-Testsuite
│   ├── fixtures/                   # Synthetische Testdaten (CSV)
│   ├── test_resource_builder.py    # Unit-Tests für Ressourcen-Erzeugung
│   └── test_pipeline.py            # Integrationstests
├── docs/                           # Dokumentation
│   ├── data_schema_summary.md      # Zusammenfassung aller 9 Datenschemata
│   ├── fhir_mapping_concept.md     # FHIR-Mapping-Konzept mit Terminologie
│   └── phenotyping_research.md     # Literaturrecherche digitale Phänotypisierung
├── .github/workflows/ci.yml        # GitHub Actions CI
├── pyproject.toml                  # Python-Projektdefinition
└── LICENSE
```

## Installation

```bash
# Basis-Installation
pip install -e .

# Mit Entwicklungsabhängigkeiten (pytest)
pip install -e ".[dev]"

# Mit FHIR-Validierung (fhir.resources)
pip install -e ".[validation]"
```

## Verwendung

### Als CLI-Tool

```bash
# Vollständige Pipeline ausführen
digiphenoms-fhir --config config/ --data data/ --output output/

# Oder als Python-Modul
python -m digiphenoms_fhir --config config/ --data data/ --output output/

# Nur bestimmte Schritte ausführen
digiphenoms-fhir --config config/ --data data/ --output output/ --steps patient_profile lclat_summary
```

### Als Python-Bibliothek

```python
from digiphenoms_fhir import Pipeline

pipeline = Pipeline(config_dir="config/")
results = pipeline.run(data_dir="data/", output_dir="output/")

# results: dict[str, list[dict]] — Schritt-Name → FHIR-Ressourcen
for step_name, resources in results.items():
    print(f"{step_name}: {len(resources)} Ressourcen")
```

## Architektur

Die Pipeline nutzt einen **konfigurationsgetriebenen Ansatz**: Die gesamte Mapping-Logik ist in YAML-Dateien definiert, der Python-Code ist ein generischer Interpreter.

```
CSV-Datei → MappingConfig (YAML) → ResourceBuilder → FHIR-Ressource (dict) → Bundle (JSON)
```

Kernkomponenten:

- **`MappingConfig`** — lädt und validiert YAML-Mapping-Konfigurationen
- **`ResourceBuilder`** — erzeugt FHIR-Ressourcen aus CSV-Zeilen + Konfiguration
- **`FHIRMapper`** — orchestriert das Mapping für einen einzelnen CSV-Typ
- **`Pipeline`** — führt alle Schritte in Abhängigkeitsreihenfolge aus (topologische Sortierung)
- **`TerminologyMap`** — übersetzt Quellcodes in SNOMED CT / LOINC / ICD-10 via ConceptMaps

## Terminologie und Kodierung

Alle klinischen Codes wurden gegen die **SNOMED CT International RF2 Release (April 2026)** verifiziert. Verwendete Terminologiesysteme:

- **SNOMED CT** — klinische Befunde, Verfahren, Assessmentskalen
- **LOINC** — Laborparameter und standardisierte Fragebögen (9HPT, Neuro-QoL)
- **ICD-10-GM** — Komorbiditäten (Sekundärkodierung)
- **UCUM** — Maßeinheiten

Details zur Terminologie: [`docs/fhir_mapping_concept.md`](docs/fhir_mapping_concept.md), Abschnitt 5.

## Tests ausführen

```bash
pytest -v
pytest --cov=digiphenoms_fhir --cov-report=term-missing
```

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [`docs/data_schema_summary.md`](docs/data_schema_summary.md) | Zusammenfassung aller 9 CSV-Datenschemata mit Spalten, Wertebereichen und Missing-Raten |
| [`docs/fhir_mapping_concept.md`](docs/fhir_mapping_concept.md) | FHIR-Mapping-Konzept, Ressourcen-Zuordnung, Terminologie-Status |
| [`docs/phenotyping_research.md`](docs/phenotyping_research.md) | Literaturrecherche zu digitaler Phänotypisierung bei MS |

## Lizenz

MIT License — siehe [LICENSE](LICENSE).
