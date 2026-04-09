# DigiPhenoMS — FHIR R4 Mapping-Konzept

## 1. Einleitung

Dieses Dokument beschreibt das Mapping der DigiPhenoMS-Datenschemata (CSV-Quellen) auf FHIR R4 Ressourcen. Es umfasst die Auswahl geeigneter FHIR-Zielressourcen mit Begründung, die Formalisierung der Mapping-Regeln in Konfigurationsdateien (YAML) und den Entwurf eines Python-basierten Mapping-Skripts, das als Pipeline-Schritt eingebettet werden kann.

### 1.1 Grundlagen FHIR R4

FHIR (Fast Healthcare Interoperability Resources) R4 ist der aktuelle normative Standard von HL7 für den Austausch klinischer Daten. Die Kernprinzipien:

- **Ressourcen:** Atomare Dateneinheiten (Patient, Observation, Encounter etc.) mit definierter Struktur
- **Referenzen:** Ressourcen verweisen aufeinander über `Reference`-Elemente (z. B. Observation → Patient)
- **Terminologien:** Kodierung über Systeme wie LOINC, SNOMED CT, ICD-10
- **Bundles:** Zusammenfassung mehrerer Ressourcen in einem Container (z. B. für Batch-Import)

### 1.2 Relevante FHIR R4 Ressourcen

| Ressource | Zweck | Relevanz für DigiPhenoMS |
|-----------|-------|--------------------------|
| **Patient** | Demografische und administrative Patientendaten | Stammdaten aus `patient_profile_data` |
| **Encounter** | Klinische Begegnung / Assessment-Sitzung | Assessment-Sitzung aus `wrapper_overview_data` |
| **Observation** | Einzelne Messwerte und Befunde | Testergebnisse aus LCLAT, MDT, NPST, WST, MRT |
| **DiagnosticReport** | Zusammenfassender Befundbericht | MRT-Befundbericht mit mehreren Observations |
| **QuestionnaireResponse** | Antworten auf strukturierte Fragebögen | Neuro-QoL (NQ), Medical History (MH) |
| **Condition** | Diagnosen und Erkrankungen | MS-Diagnose, Komorbiditäten aus Patient Profile und MH |
| **Device** | Medizinisches Gerät | iPad-Gerät aus Wrapper Overview, MRT-Scanner |

---

## 2. FHIR R4 Ressourcen-Mapping je Datenschema

### 2.1 `patient_profile_data` → **Patient** + **Condition**

**Primäre Zielressource: `Patient`**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Patient UUID` | `Patient.identifier[0].value` | System: `urn:oid:digipenoms:patient-uuid` |
| `Organization` | `Patient.managingOrganization` | Referenz auf Organization-Ressource |
| `DOB` | `Patient.birthDate` | Format: `YYYY-MM-DD` |
| `Gender` | `Patient.gender` | Mapping: female→female, male→male |
| `Handedness` | `Patient.extension[handedness].valueCode` | Custom Extension, da FHIR kein Standardfeld hat |
| `Preferred Language` | `Patient.communication[0].language` | BCP-47 Code: de, en, ru |
| `Created At` | `Patient.meta.lastUpdated` | |
| `Date of Diagnosis` | → **Condition** (siehe unten) | |
| `Comorbidities` | → **Condition** (siehe unten) | |
| `consent_status` | `Patient.extension[consent].valueCode` | Oder separater Consent-Ressource |

**Sekundäre Ressource: `Condition`** (für MS-Diagnose und Komorbiditäten)

| Datum/Wert | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| MS-Diagnose | `Condition.code` = SNOMED 24700007 | "Multiple sclerosis" |
| `Date of Diagnosis` | `Condition.onsetDateTime` | |
| Je Komorbidität | Separate `Condition`-Ressource | Mapping über ConceptMap: `high_blood_pressure` → ICD/SNOMED |

**Begründung:** `Patient` ist die einzige geeignete Ressource für Demografie. Für Diagnosen und Komorbiditäten ist `Condition` der FHIR-Standard — nicht `Patient.extension`, da Conditions eigene Attribute haben (Onset, klinischer Status, Verifikation).

---

### 2.2 `wrapper_overview_data` → **Encounter** + **Device**

**Primäre Zielressource: `Encounter`**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Assessment UUID` | `Encounter.identifier[0].value` | System: `urn:oid:digipenoms:assessment-uuid` |
| `Patient UUID` | `Encounter.subject` | Referenz auf Patient |
| `Assessor UUID` | `Encounter.participant[0].individual` | Referenz auf Practitioner |
| `Assessment Started At` | `Encounter.period.start` | ISO 8601 |
| `Assessment Ended At` | `Encounter.period.end` | ISO 8601 |
| `Successful Module Count` | `Encounter.extension[moduleCount].valueInteger` | Custom Extension |
| `Organization` | `Encounter.serviceProvider` | Referenz auf Organization |

**`Encounter.class`**: `AMB` (ambulant) — die MSPT-Assessments finden im Rahmen ambulanter Visiten statt.

**Sekundäre Ressource: `Device`**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Device Type` | `Device.type.text` | z. B. "iPad7,5" |
| `Device Name` | `Device.deviceName[0].name` | |
| `App Version` | `Device.version[0].value` | Softwareversion |
| `App Build` | `Device.extension[build].valueString` | |
| `IOS Version` | `Device.property[os].valueString` | |
| `Vendor Identifier` | `Device.identifier[0].value` | |

**Begründung:** `Encounter` modelliert die Assessment-Sitzung als klinische Begegnung, an die alle Testergebnisse (Observations) referenzieren. Alternative wäre `Procedure`, aber `Encounter` bildet den Kontext besser ab, da die Sitzung mehrere Module umfasst. `Device` ist Standard für das Erhebungsgerät.

---

### 2.3 `lclat_data` (Summary) → **Observation**

**Zielressource: `Observation`** — eine Observation pro Assessment mit Multi-Component-Struktur.

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Assessment UUID` | `Observation.encounter` | Referenz auf Encounter |
| `Patient UUID` | `Observation.subject` | Referenz auf Patient |
| `Module Started At` | `Observation.effectiveDateTime` | |
| `Observation.code` | Custom `lcla-test` | Kein LOINC; SNOMED 251686008 "Contrast sensitivity" |
| `Observation.category` | `exam` | Clinical Test |
| `Total Number Correct` | `Observation.component[0].valueQuantity` | Code: custom `lclat-total-correct` |
| `Total Number Correct at 100%` | `Observation.component[1].valueQuantity` | Code: custom `lclat-correct-100pct` |
| `Total Number Correct at 2.5%` | `Observation.component[2].valueQuantity` | Code: custom `lclat-correct-2.5pct` |
| `Module Duration` | `Observation.component[3].valueQuantity` | Unit: seconds |
| `Canceled` | `Observation.status` | True → `cancelled`, False → `final` |
| `Cancel Reason` | `Observation.note[0].text` | |

**Begründung Multi-Component vs. separate Observations:** Die Kontrastschwellen-Werte gehören zusammen zu einem LCLA-Test und werden klinisch als Einheit interpretiert. Die FHIR-Spezifikation empfiehlt `component` für zusammengehörige Messwerte innerhalb einer Observation. Separate Observations wären valide, aber weniger kohärent.

---

### 2.4 `mdt_data` (Summary) → **Observation**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Observation.code` | LOINC `83141-2` | + SNOMED 273648008 "Nine hole peg test" |
| `Z-Score Dominant` | `Observation.component[0].valueQuantity` | Unit: `{z-score}` |
| `Z-Score Nondominant` | `Observation.component[1].valueQuantity` | |
| `Left Hand Time` | `Observation.component[2].valueQuantity` | Unit: seconds |
| `Right Hand Time` | `Observation.component[3].valueQuantity` | Unit: seconds |
| `Dominant Hand` | `Observation.component[4].valueCodeableConcept` | right/left |
| `Pegs Dropped` | `Observation.component[5].valueQuantity` | |
| `Trial Duration` | `Observation.component[6].valueQuantity` | Unit: seconds |

---

### 2.5 `npst_data` (Summary) → **Observation**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Observation.code` | Custom `sdmt-test` | Kein LOINC; SNOMED 273857000 "Symbol digit modalities test" |
| `Total Number Correct` | `Observation.valueQuantity` | Primärer Messwert |
| `Total Number Incorrect` | `Observation.component[0].valueQuantity` | |
| `Z-Score` | `Observation.component[1].valueQuantity` | Unit: `{z-score}` |

**Begründung valueQuantity vs. component:** Der SDMT hat einen klaren Primärwert (Total Correct), der in `Observation.value[x]` abgebildet wird. Z-Score und Fehlerzahl sind ergänzende Metriken → `component`.

---

### 2.6 `wst_data` (Summary) → **Observation**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Observation.code` | Custom `t25fw-test` | Kein LOINC; SNOMED 724237005 "Gait speed" |
| `Walk Duration` | `Observation.valueQuantity` | Unit: seconds |
| `Z-Score` | `Observation.component[0].valueQuantity` | |
| `Walking Aid Used` | `Observation.component[1].valueBoolean` | |
| `Walking Aid Choice` | `Observation.component[2].valueCodeableConcept` | |
| `AFO Used` | `Observation.component[3].valueBoolean` | |

---

### 2.7 `nq_data` → **QuestionnaireResponse** (Detail) + **Observation** (Aggregierte T-Scores)

Hier gibt es zwei valide Mapping-Strategien:

#### Option A: QuestionnaireResponse (empfohlen für Detail-Daten)

Die Neuro-QoL-Daten sind Antworten auf einen adaptiven Fragebogen. `QuestionnaireResponse` bildet die Item-Struktur (Frage → Antwort) natürlich ab.

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `Assessment UUID` | `QuestionnaireResponse.encounter` | Referenz auf Encounter |
| `Patient UUID` | `QuestionnaireResponse.subject` | Referenz auf Patient |
| `Module Started At` | `QuestionnaireResponse.authored` | |
| `Key` (Subdomäne) | `QuestionnaireResponse.questionnaire` | Referenz auf Questionnaire-Definition |
| `Question Title` | `QuestionnaireResponse.item[n].text` | |
| `Response Value` | `QuestionnaireResponse.item[n].answer[0].valueInteger` | |
| `User Response` | `QuestionnaireResponse.item[n].answer[0].valueString` | |
| `T Score` | Separate **Observation** (s.u.) | |

#### Option B: Observation (für aggregierte Scores)

Die T-Scores je Subdomäne werden als eigenständige Observations abgebildet:

| Wert | FHIR-Pfad | Hinweise |
|------|-----------|----------|
| `T Score` | `Observation.valueQuantity` | Unit: `{T-score}` |
| `Standard Error` | `Observation.component[0].valueQuantity` | |
| `Key` (Subdomäne) | `Observation.code` | ConceptMap: `upper_extremity` → LOINC/Custom Code |

**Pro QuestionnaireResponse:** Bildet die adaptive Fragebogenstruktur korrekt ab, jede Frage-Antwort ist nachvollziehbar. **Contra:** T-Scores passen nicht natürlich in QR, benötigen separate Observations.

**Pro Observation only:** Einfacher, weniger Ressourcen. **Contra:** Verlust der Fragebogenstruktur.

**Empfehlung:** Hybridansatz — `QuestionnaireResponse` für die Item-Level-Daten, ergänzende `Observation` für die aggregierten T-Scores je Subdomäne.

---

### 2.8 `mh_data` → **QuestionnaireResponse** + **Condition**

| Datentyp | FHIR-Ressource | Begründung |
|----------|---------------|-----------|
| Fragebogen-Antworten | `QuestionnaireResponse` | MH ist ein strukturierter Fragebogen |
| Komorbiditäten (aus Antworten) | `Condition` | Eigenständige klinische Entitäten |
| Medikation (aus Antworten) | `MedicationStatement` | Falls Medikationsdaten extrahiert werden |

---

### 2.9 `mrt_data` → **DiagnosticReport** + **Observation** + **Device**

Die MRT-Daten sind Ergebnisse einer automatisierten Bildauswertung — ein klassischer Befundbericht mit quantitativen Einzelergebnissen.

**Primäre Ressource: `DiagnosticReport`**

| CSV-Spalte | FHIR-Pfad | Hinweise |
|-----------|-----------|----------|
| `patientalias` | `DiagnosticReport.subject` | Referenz auf Patient |
| `sty_date` | `DiagnosticReport.effectiveDateTime` | MRT-Datum |
| `DiagnosticReport.code` | LOINC `30799-1` | "MR Brain WO contrast" (oder spezifischer) |
| `DiagnosticReport.category` | `imaging` | |
| `prog_ver` | `DiagnosticReport.extension[softwareVersion]` | Pipeline-Version |
| `scanner` | → **Device** | Referenz |
| `segvisqc` | `DiagnosticReport.conclusion` | PASS/FAIL |
| Alle Messwerte | → **Observation** (referenziert) | s.u. |

**Sekundäre Ressourcen: `Observation`** (je Messwert-Gruppe)

| Observation | CSV-Spalten | LOINC/Code |
|------------|------------|-----------|
| Brain Parenchymal Fraction | `bpf`, `bpf_chg` | Custom: `mri-bpf` |
| T2-Läsionsvolumen | `t2lesvol`, `t2overbv` | Custom: `mri-t2-lesion-volume` |
| Neue T2-Läsionen | `nt2lescn`, `nt2lesgt`, `nt2lesvo` | Custom: `mri-new-t2-lesions` |
| Gewebefraktionen | `gmf`, `wmf`, `cgmvol`, `dgmvol` | Custom: `mri-tissue-fractions` |
| Thalamusvolumen | `thalvol`, `thalf` | Custom: `mri-thalamus-volume` |
| Läsionslokalisationen | `t2voljux`, `t2volprv`, `t2volinf`, `t2voloth` | Custom: `mri-lesion-locations` |

**Alternative: Nur Observations (ohne DiagnosticReport)**

**Pro:** Einfacher, weniger Ressourcen. **Contra:** Verlust des Berichtsrahmens — die MRT-Werte gehören klinisch zusammen als ein Befund zu einem Zeitpunkt. DiagnosticReport gruppiert sie sinnvoll und ermöglicht QC-Informationen.

**Empfehlung:** DiagnosticReport als Container, Observations für die Einzelwerte. Dies entspricht dem FHIR-Diagnostics-Module-Muster.

---

## 3. Zusammenfassung Ressourcen-Landschaft

```
                    ┌──────────────┐
                    │   Patient    │ ← patient_profile_data
                    └──────┬───────┘
                           │ subject
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Encounter  │ │  Condition  │ │   Device    │
    │ (Sitzung)   │ │ (MS, Komor.)│ │ (iPad/MRT)  │
    └──────┬──────┘ └─────────────┘ └─────────────┘
           │ encounter
    ┌──────┴──────────────────────────────┐
    │                                     │
    │  ┌─────────────────┐                │
    ├──┤  Observation     │ ← LCLAT, MDT, │
    │  │  (Funktionstest) │   NPST, WST   │
    │  └─────────────────┘                │
    │  ┌─────────────────┐                │
    ├──┤  Questionnaire-  │ ← NQ, MH      │
    │  │  Response        │               │
    │  └─────────────────┘                │
    │  ┌─────────────────┐                │
    └──┤  Diagnostic-     │ ← MRT         │
       │  Report          │               │
       │  └→ Observation  │               │
       └─────────────────┘                │
```

---

## 4. Ansatz zum konfigurierbaren Datenmapping

### 4.1 Gewählter Ansatz: YAML-basierte Mapping-Konfiguration

Nach Recherche der verfügbaren Ansätze (FHIR StructureMap, ConceptMap, CSV-basiertes Mapping, custom YAML/JSON) empfehle ich **YAML-Konfigurationsdateien** aus folgenden Gründen:

| Ansatz | Pro | Contra | Bewertung |
|--------|-----|--------|-----------|
| **FHIR StructureMap** | FHIR-nativer Standard, maschinenlesbar | Komplexe Syntax, wenig Python-Tooling, Overhead für CSV-Quellen | Für DigiPhenoMS-Kontext zu komplex |
| **FHIR ConceptMap** | Gut für Terminologie-Mappings (Codes) | Nur für Konzept→Konzept, nicht für Strukturmapping | Ergänzend nutzbar |
| **Custom YAML** | Lesbar, flexibel, Python-nativ (`PyYAML`), erweiterbar, versionierbar (Git) | Kein FHIR-Standard | **Empfohlen** als Hauptkonfiguration |
| **Custom JSON** | Maschinenlesbar, Python-nativ | Weniger lesbar als YAML, keine Kommentare | Alternative zu YAML |

### 4.2 Architektur der Konfiguration

```
config/
├── mapping/
│   ├── patient_profile.mapping.yaml    # Patient + Condition
│   ├── wrapper_overview.mapping.yaml   # Encounter + Device
│   ├── lclat_summary.mapping.yaml      # Observation (LCLA)
│   ├── mdt_summary.mapping.yaml        # Observation (9HPT)
│   ├── npst_summary.mapping.yaml       # Observation (SDMT)
│   ├── wst_summary.mapping.yaml        # Observation (T25FW)
│   ├── nq_detail.mapping.yaml          # QuestionnaireResponse + Observation
│   ├── mh_detail.mapping.yaml          # QuestionnaireResponse
│   └── mrt.mapping.yaml               # DiagnosticReport + Observation
├── terminology/
│   ├── comorbidity_conceptmap.yaml     # Komorbidität → SNOMED/ICD
│   └── cancel_reason_conceptmap.yaml   # Cancel Reason → FHIR status
└── pipeline.yaml                       # Pipeline-Konfiguration (Reihenfolge, Pfade)
```

### 4.3 Struktur einer Mapping-YAML-Datei

Jede Mapping-Datei folgt diesem Schema:

```yaml
source:
  file_pattern: "*_lclat-summary_training.csv"
  id_column: "Assessment UUID"
  patient_column: "Patient UUID"

targets:
  - resource_type: Observation
    profile: "DigiPhenoMS-LCLA-Observation"
    id_template: "obs-lcla-{Assessment UUID}"

    static_fields:
      category:
        system: "http://terminology.hl7.org/CodeSystem/observation-category"
        code: "exam"
      code:
        system: "https://digiphenoms.tu-dresden.de/fhir/CodeSystem/digiphenoms"
        code: "lcla-test"
        display: "Low-Contrast Letter Acuity Test (LCLA)"
        additional_codings:
          - system: "http://snomed.info/sct"
            code: "251686008"
            display: "Contrast sensitivity"

    field_mappings:
      - source: "Patient UUID"
        target: "subject"
        type: "reference"
        reference_type: "Patient"

      - source: "Assessment UUID"
        target: "encounter"
        type: "reference"
        reference_type: "Encounter"

      - source: "Module Started At"
        target: "effectiveDateTime"
        type: "datetime"
        format: "%a, %d %b %Y %H:%M:%S %z"

    status_mapping:
      source: "Canceled"
      true_value: "cancelled"
      false_value: "final"

    components:
      - source: "Total Number Correct"
        code:
          system: "urn:oid:digipenoms"
          code: "lclat-total-correct"
          display: "LCLA Total Correct"
        value_type: "valueQuantity"
        unit: "{score}"

      - source: "Total Number Correct at 100%"
        code:
          system: "urn:oid:digipenoms"
          code: "lclat-correct-100pct"
          display: "LCLA Correct at 100% Contrast"
        value_type: "valueQuantity"
        unit: "{score}"
```

---

## 5. Semantisches Mapping und Terminologien

### 5.1 Überblick Terminologiesysteme

Für die semantische Anreicherung der FHIR-Ressourcen werden folgende internationale Terminologiesysteme eingesetzt:

| System | Verwendung | URL |
|--------|-----------|-----|
| **SNOMED CT** | Klinische Befunde, Body Sites, Diagnosen, Handedness, Walking Aids | `http://snomed.info/sct` |
| **LOINC** | Test-Codes (9HPT, Neuro-QoL), DiagnosticReport-Codes | `http://loinc.org` |
| **ICD-10-GM** | Komorbiditäten (sekundäres Coding) | `http://fhir.de/CodeSystem/bfarm/icd-10-gm` |
| **UCUM** | Einheiten (Sekunden, Scores, Ratios, mL) | `http://unitsofmeasure.org` |
| **DigiPhenoMS Custom** | Projektspezifische Codes für Tests ohne Standard-Code | `https://digiphenoms.tu-dresden.de/fhir/CodeSystem/digiphenoms` |

### 5.2 Terminologie-Status je Observation

Die Recherche in LOINC und SNOMED CT ergab folgendes Bild:

| Observation | Primärcode | System | Status | Anmerkung |
|-------------|-----------|--------|--------|-----------|
| **LCLA** | `lcla-test` | Custom | Kein Standard-LOINC | SNOMED 251686008 (Contrast sensitivity) als Zusatz |
| **9HPT** | `83141-2` | LOINC | Verifiziert (NIH Toolbox) | SNOMED 273648008 (Nine hole peg test) als Zusatz |
| **SDMT** | `sdmt-test` | Custom | Kein Standard-LOINC | SNOMED 273857000 (Symbol digit modalities test) als Zusatz |
| **T25FW** | `t25fw-test` | Custom | Nicht verifizierbar | SNOMED 724237005 (Gait speed) als Zusatz |
| **Neuro-QoL T-Score** | `neuro-qol-tscore` | Custom | Subdomänen via LOINC | z.B. Anxiety=67903-5, Fatigue=67905-0 |
| **MRI Atrophy** | `mri-brain-atrophy` | Custom | SNOMED 278849000 (✓ RF2) | Body Site: 12738006 (Brain structure) |
| **MRI T2 Lesions** | `mri-t2-lesions` | Custom | SNOMED 1145374006 (✓ RF2) | Body Site: 68523003 (Cerebral white matter) |
| **MRI Tissue** | `mri-tissue-fractions` | Custom | Kein Standard-Code | Body Site: SNOMED 12738006 (Brain structure) |
| **MRI Thalamus** | `mri-thalamus` | Custom | Kein Standard-Code | Body Site: SNOMED 42695009 (Thalamic structure) |
| **MRT DiagReport** | `30799-1` | LOINC | Verifiziert | SNOMED 698354004 (MRI brain volume) als Zusatz |

### 5.3 SNOMED CT Zusatzinformationen

Alle SNOMED CT-Codes wurden gegen das offizielle **SNOMED CT International RF2 Release 20260401** verifiziert. Wo Standard-LOINC-Codes fehlen, werden SNOMED CT-Konzepte als `additional_codings` und `bodySite` eingesetzt:

**Body Sites (Anatomische Strukturen):**
- `12738006` — Brain structure (body structure) — für Atrophie, Tissue Fractions
- `68523003` — Cerebral white matter structure (body structure) — für T2-Läsionen
- `42695009` — Thalamic structure (body structure) — für Thalamus-Volumetrie
- `40146001` — Cerebral cortex (body structure) — Synonym: "Cerebral grey matter"

**Klinische Befunde (Findings/Disorders):**
- `278849000` — Cerebral atrophy (disorder) — für Brain Atrophy Observation
- `1145374006` — Focal white matter lesion (disorder) — für T2 Lesion Observation
- `24700007` — Multiple sclerosis (disorder) — MS-Diagnose als Condition

**Assessment Scales und Observable Entities:**
- `251686008` — Contrast sensitivity (observable entity) — für LCLA
- `273857000` — Symbol digit modalities test (assessment scale) — für SDMT
- `273648008` — Nine hole peg test (assessment scale) — für 9HPT
- `724237005` — Gait speed (observable entity) — für T25FW

**Verfahren (Procedures):**
- `698354004` — Magnetic resonance imaging for measurement of brain volume (procedure) — MRI-Volumetrie
- `716214002` — Assessment using Symbol Digit Modalities Test (procedure)
- `445789007` — Assessment using nine hole peg test (procedure)

**Handedness (Findings):**
- `46669005` — Right handed (finding)
- `87683000` — Left handed (finding)
- `23088002` — Ambidextrous (finding)

**Walking Aids (Physical Objects):**
- `360006004` — Walking stick (physical object)
- `74566002` — Crutch, device (physical object)
- `1255320005` — Wheeled walker / Rollator (physical object)
- `266731002` — Walking frame (physical object)
- `58938008` — Wheelchair device (physical object)
- `183160000` — Rigid ankle-foot orthosis (physical object)
- `183135000` — Mobility aids (physical object) — Fallback

### 5.4 ConceptMap-Dateien

Die Terminologie-Mappings sind in separaten YAML-Dateien formalisiert:

| Datei | Inhalt | Quell-System → Ziel-System |
|-------|--------|---------------------------|
| `comorbidity_conceptmap.yaml` | 7 Komorbiditäten | DigiPhenoMS → SNOMED CT + ICD-10-GM |
| `neuroqol_domains_conceptmap.yaml` | 8 Neuro-QoL-Subdomänen | DigiPhenoMS → LOINC |
| `walking_aids_conceptmap.yaml` | 5 Gehhilfen | DigiPhenoMS → SNOMED CT |
| `handedness_conceptmap.yaml` | 3 Händigkeiten | DigiPhenoMS → SNOMED CT |

### 5.5 Custom CodeSystem: DigiPhenoMS

Für Tests und Messwerte ohne internationale Standard-Codes wird ein projektspezifisches CodeSystem definiert:

**URL:** `https://digiphenoms.tu-dresden.de/fhir/CodeSystem/digiphenoms`

Dieses CodeSystem umfasst:
- Test-Identifikatoren: `lcla-test`, `sdmt-test`, `t25fw-test`, `9hpt-test`
- Messwert-Codes: `bpf`, `bpf-change`, `t2-lesion-volume`, `thalamus-volume`, `grey-matter-fraction`, etc.
- Komponentencodes: `lclat-total-correct`, `lclat-correct-100pct`, `9hpt-zscore-dominant`, etc.
- Neuro-QoL-Score: `neuro-qol-tscore`

Wo möglich werden über `additional_codings` Referenzen zu SNOMED CT oder LOINC hinzugefügt, sodass die klinische Bedeutung auch ohne Kenntnis des projektspezifischen CodeSystems erschlossen werden kann.

### 5.6 Empfehlungen und offene Punkte

1. **LOINC-Anträge:** Für LCLA, SDMT und T25FW existieren keine dedizierten LOINC-Codes. SNOMED CT bietet jedoch direkte Assessment-Scale-Konzepte (273857000 für SDMT, 273648008 für 9HPT). Eine LOINC-Submission wäre dennoch sinnvoll für interinstitutionelle Vergleichbarkeit.
2. **MRI-Volumetrie:** Keine LOINC-Codes für BPF, T2-Läsionsvolumen oder Thalamus-Volumetrie. SNOMED CT 698354004 (MRI for measurement of brain volume) deckt den Verfahrensaspekt ab.
3. **Neuro-QoL LOINC:** Die gefundenen LOINC-Codes (67903-5 etc.) beziehen sich auf Short-Form-Versionen (v1.0). Falls DigiPhenoMS CAT-Versionen oder neuere Versionen verwendet, sollten die Codes entsprechend angepasst werden.
4. **SNOMED CT Maintenance:** Inactive Codes (363753007, 705403001) wurden durch aktive Alternativen ersetzt. Bei zukünftigen SNOMED CT-Releases sollten die Codes auf Statusänderungen geprüft werden.

---

## 6. Quellen

**FHIR R4 Spezifikation:**
- [FHIR R4 Observation](https://hl7.org/fhir/R4/observation.html)
- [FHIR R4 Patient](https://hl7.org/fhir/R4/patient.html)
- [FHIR R4 Encounter](https://hl7.org/fhir/R4/encounter.html)
- [FHIR R4 DiagnosticReport](https://hl7.org/fhir/R4/diagnosticreport.html)
- [FHIR R4 QuestionnaireResponse](https://hl7.org/fhir/R4/questionnaireresponse.html)
- [FHIR R4 Diagnostics Module](https://www.hl7.org/fhir/R4/diagnostics-module.html)
- [FHIR StructureMap](https://build.fhir.org/structuremap.html)
- [FHIR ConceptMap](https://build.fhir.org/conceptmap.html)

**Terminologien:**
- [LOINC (Logical Observation Identifiers Names and Codes)](https://loinc.org)
- [SNOMED CT Browser](https://browser.ihtsdotools.org)
- [ICD-10-GM (BfArM)](https://www.bfarm.de/DE/Kodiersysteme/Klassifikationen/ICD/ICD-10-GM/)
- [UCUM (Unified Code for Units of Measure)](https://ucum.org)
- [LOINC 83141-2: 9-Hole Pegboard Dexterity Test](https://loinc.org/83141-2)
- [LOINC Neuro-QoL Panels](https://loinc.org/panels/category/survey-instruments/quality-of-life-outcomes-in-neurological-disorders-neuro-qol/)

**Tooling:**
- [fhir.resources (Python, PyPI)](https://pypi.org/project/fhir.resources/)
- [FHIR Mapping Tutorial](https://build.fhir.org/mapping-tutorial.html)
