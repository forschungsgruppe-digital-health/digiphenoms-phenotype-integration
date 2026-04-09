# DigiPhenoMS — Zusammenfassung der Datenschemata

## 1. Überblick

Das Projekt DigiPhenoMS („Digital Phenotyping for intelligent management of Multiple Sclerosis") erhebt multidimensionale Daten zur Charakterisierung von MS-Patient\*innen. Die vorliegenden Datenschemata umfassen **9 Einzeldateien**, die sich in vier funktionale Gruppen gliedern lassen:

| Gruppe | Dateien | Inhalt |
|--------|---------|--------|
| Klinische Funktions­tests | `lclat_data`, `mdt_data`, `npst_data`, `wst_data` | Digitalisierte Leistungstests für Sehfunktion, Handmotorik, Kognition und Gehfähigkeit |
| Patientenberichtete Daten | `nq_data`, `mh_data` | Lebensqualität (Neuro-QoL) und medizinische Historie (Komorbiditäten, Medikation) |
| Bildgebung | `mrt_data` | MRT-basierte Volumetrie, Läsionsanalyse und Atrophiemaße |
| Stammdaten und Metadaten | `patient_profile_data`, `wrapper_overview_data` | Demografie, Diagnose­zeitpunkt, Geräteinformationen, Assessment-Metadaten |

Alle Datensätze stammen aus dem MS-Zentrum **Dresden Carus** und liegen pseudonymisiert vor (Patient UUID). Jeder Datensatz enthält ein Feld `consent_status` (ausschließlich Wert `granted`).

**Hinweis zur Pseudonymisierung:** In den Funktionstests und Neuro-QoL-Daten enthaltene `DOB`-Felder verwenden ein pseudonymisiertes Geburtsdatum (Format: MM-DD-YYYY, immer 1. Januar + Geburtsjahr). Zusätzlich enthält der Neuro-QoL-Datensatz ein Feld `KIS ID / Orbis ID`, das eine Verknüpfung zum Krankenhausinformationssystem (ORBIS) ermöglicht.

---

## 2. Gemeinsame Datenstruktur

Die meisten Datensätze (mit Ausnahme von `mrt_data` und `patient_profile_data`) folgen einem einheitlichen Grundschema, das aus dem iPad-basierten Assessment-System stammt:

**Gemeinsame Kernspalten:**

| Spalte | Beschreibung |
|--------|-------------|
| `Organization` | Erhebungsort (durchgängig „Dresden Carus") |
| `Assessment UUID` | Eindeutige Sitzungs-ID |
| `Patient UUID` | Pseudonymisierte Patienten-ID |
| `Assessor UUID` | ID der durchführenden Person |
| `Module UUID` | ID des Testmoduls |
| `Module Configuration UUID` | Konfigurationsversion des Moduls |
| `Assessment Started/Ended At` | Zeitstempel der Gesamtsitzung |
| `Module Started/Ended At` | Zeitstempel des Einzelmoduls |
| `Version` | Softwareversion der Test-App |
| `Canceled` / `Cancel Reason` | Abbruchstatus und -grund |
| `consent_status` | Einwilligungsstatus (`granted`) |

Die Daten liegen jeweils in zwei Granularitäts­stufen vor: **Detail** (Einzelereignis-Ebene, z. B. jede Antwort, jeder Peg-Event) und **Summary** (aggregierte Ergebnisse pro Assessment/Modul). Die MRT-Daten und das Patientenprofil weichen von diesem Schema ab, da sie nicht über das iPad-Assessment-System erhoben werden.

---

## 3. Beschreibung der Einzelschemata

### 3.1 LCLAT — Low-Contrast Letter Acuity Test (Sehfunktion)

**Klinisches Instrument:** Low-Contrast Letter Acuity Test (LCLA), digitalisierte Version auf iPad. Patienten erkennen Buchstaben (Optotypen) bei verschiedenen Kontraststufen.

**Projektbezug:** Der LCLA-Test erfasst die visuelle Funktion, die bei MS häufig durch Optikusneuritis beeinträchtigt ist. Im Projektantrag wird die Erfassung klinischer und paraklinischer Daten für das Monitoring als zentral beschrieben. Der Test ist Bestandteil des digitalen MS-Funktionsassessments und liefert objektive, quantitative Marker für den Krankheitsverlauf.

**Detail-Tabelle** (`lclat_detail_training`): Jede Zeile entspricht einer einzelnen Buchstabenantwort. Enthält die angezeigte Kontraststufe (`Contrast`, 0.025–1.0), den LogMAR-Wert (`Logmar`), den angezeigten und eingegebenen Buchstaben, Korrektheit, Fehlertyp sowie Antwortzeiten.

**Summary-Tabelle** (`lclat_summary_training`, ~1.137 Zeilen): Aggregiert die korrekt beantworteten Items je Kontraststufe: `Total Number Correct at 100%`, `at 2.5%`, `at 10%`, `at 5%`, `at 1.25%`. Enthält die Moduldauer. Kontraststufen 10%, 5% und 1.25% weisen hohe Missing-Raten auf (1.137 fehlend), da diese Stufen nur bei bestimmten Konfigurationen erhoben werden.

---

### 3.2 MDT — Manual Dexterity Test / 9-Hole Peg Test (Handmotorik)

**Klinisches Instrument:** 9-Hole Peg Test (9HPT), digitalisiert. Patienten stecken Stifte in ein Brett und entfernen sie — jeweils mit dominanter und nicht-dominanter Hand.

**Projektbezug:** Der 9HPT ist ein Standardinstrument zur Messung der oberen Extremitätenfunktion bei MS und Bestandteil des MSFC (Multiple Sclerosis Functional Composite). Im Kontext von DigiPhenoMS liefert er einen quantitativen Marker für die Feinmotorik, der in die Phänotypisierung und Pfadmodellierung einfließt.

**Detail-Tabelle** (`mdt_detail_training`, 94.434 Zeilen): Jedes Einzelereignis (Peg aufnehmen/ablegen) wird aufgezeichnet: `Peg ID`, `Is Up Action`, `Event Time`, `Hand Used`, `Dominant Hand`, `Trial State` (Completed/Restarted/Timed Out). Fallengelassene Pegs werden gezählt (`Pegs Dropped`, Skala 0–5). Zeitlimit pro Trial: 120 Sekunden.

**Summary-Tabelle** (`mdt_summary_training`, 2.244 Zeilen): Aggregiert Trial-Dauer je Hand (`Left Hand Time`, `Right Hand Time`), Z-Scores für dominante und nicht-dominante Hand (`Z-Score Dominant`, `Z-Score Nondominant`), normiert gegen Referenzmodell `GENERAL-NM-1.0`.

---

### 3.3 NPST — Neuropsychological Symbol Test / SDMT (Kognition)

**Klinisches Instrument:** Symbol Digit Modalities Test (SDMT), digitalisiert. Patienten ordnen Symbole Ziffern zu — misst Informationsverarbeitungs­geschwindigkeit und kognitive Leistung.

**Projektbezug:** Der SDMT ist der empfohlene kognitive Screening-Test bei MS und ebenfalls Teil des MSFC. Kognitive Beeinträchtigungen betreffen bis zu 70% der MS-Patient\*innen und sind ein zentraler Parameter für die digitale Phänotypisierung im Projekt.

**Detail-Tabelle** (`npst_detail_training`, 68.699 Zeilen): Jede Symbol-Zuordnung wird einzeln erfasst: `Symbol` (ID 27–54), `Answer` (1–9), `Correct`, `Time` (Reaktionszeit in Sekunden), `Row Index`, `Practice` (Übungstrial ja/nein). Trials können den Status `Completed`, `Canceled`, `Started` oder `Timed Out` haben.

**Summary-Tabelle** (`npst_summary_training`, 2.279 Zeilen): Enthält `Total Number Correct` (0–105), `Total Number Incorrect` (0–70), `Z-Score` (−3.78 bis 4.98), normiert gegen `GENERAL-NM-1.0`.

---

### 3.4 WST — Walking Speed Test / Timed 25-Foot Walk (Gehfähigkeit)

**Klinisches Instrument:** Timed 25-Foot Walk (T25FW), digitalisiert. Patienten gehen eine 25-Fuß-Strecke so schnell wie möglich. Hilfsmittelnutzung wird dokumentiert.

**Projektbezug:** Der T25FW misst die Gehfähigkeit und Beinfunktion — bei MS ein zentraler Marker für die Behinderungsprogression. Zusammen mit 9HPT und SDMT bildet er den MSFC, der im Projekt als Kernkomponente des Monitoring-Systems dient. Die Erhebung von Hilfsmitteln (Gehhilfe, Orthese) liefert zusätzliche Kontextinformation für die Pfadanalyse.

**Detail-Tabelle** (`wst_detail_training`, 1.156 Zeilen): Einzelne Gehversuche mit `Walk Duration`, `Walking Aid Used/Choice` (walker_rollator, cane, crutch, other), `AFO Used/Choice` (Fußorthese), `Start/Stop Device` (App Screen, Remote), `Trial State`.

**Summary-Tabelle** (`wst_summary_training`): Aggregierte Gehzeit (`Walk Duration`, 2.66–38.59 s), Hilfsmittelnutzung, erfolgreiche/nicht erfolgreiche Trials, `Z-Score` (−27.22 bis 2.79), normiert gegen `GENERAL-NM-1.0`.

---

### 3.5 NQ — Neuro-QoL (Lebensqualität)

**Klinisches Instrument:** Neuro-QoL (Neurological Quality of Life), durchgeführt als Computerized Adaptive Test (CAT). Erfasst funktionale Einschränkungen und Lebensqualität in mehreren Subdomänen (z. B. `upper_extremity`, u.a.).

**Projektbezug:** Als patientenberichtetes Outcome-Maß (PRO) ist Neuro-QoL ein zentrales Element des im Projektantrag beschriebenen Patient Empowerment und der partizipativen Versorgung. Die Daten fließen in die multidimensionale Phänotypisierung ein, da sie die Patientenperspektive neben den objektiven klinischen Messwerten abbilden.

**Detail-Tabelle** (`nq_detail_training`, 34.984 Zeilen): Jede Frage-Antwort-Kombination mit `T Score` (15.70–81.74), `Raw Score`, `Standard Error`, `Question Title`, `User Response`, `Response Value` (1–5). CAT-Parameter: 4–8 Fragen, Abbruch bei Standard Error ≤ 0.3. Subtest-Indices und -Dauern werden erfasst. Der Schlüssel `Key` identifiziert die Subdomäne.

---

### 3.6 MH — Medical History (Medizinische Anamnese)

**Klinisches Instrument:** Strukturierter digitaler Fragebogen zur Erfassung der medizinischen Historie, einschließlich Komorbiditäten seit dem letzten Besuch, aktueller Medikation und Beziehungsstatus.

**Projektbezug:** Die medizinische Historie liefert den klinischen Kontext, der für die Pfadmodellierung und die Phänotypisierung essenziell ist. Im Projektantrag wird die Integration von Diagnose-, Therapie- und Monitoring-Daten als Voraussetzung für individualisierte Patientenpfade beschrieben. Die MH-Daten sind dabei der Brückenschlag zwischen klinischen Messungen und dem tatsächlichen Behandlungsverlauf.

**Detail-Tabelle** (`mh_detail_training`, 29.945 Zeilen): Fragebogenformat mit `Section Name` (additional_questions, patient_profile), `Question Key` (35 verschiedene), `Question Type` (selection, multi_select_button u.a.), `Response Key` (maschinenlesbar) und `Entered Response` (Klartext). 25 Zeilen mit fehlenden Werten in Strukturspalten deuten auf abgebrochene Module hin.

---

### 3.7 MRT — Magnetresonanztomographie (Bildgebung)

**Klinisches Instrument:** Kraniale MRT mit automatisierter Läsionssegmentierung und Volumetrie. Die Daten stammen aus einer Bildverarbeitungs-Pipeline (nicht aus dem iPad-Assessment-System).

**Projektbezug:** Die MRT-Daten repräsentieren die paraklinische Dimension des DigiPhenoMS-Datenmodells. Der Projektantrag betont die Integration paraklinischer, klinischer und patientenberichteter Daten. Die MRT-basierte Läsionslast und Atrophiemaße sind etablierte Biomarker für die MS-Krankheitsaktivität und -progression und damit Schlüsselparameter für die digitale Phänotypisierung.

**Tabelle** (`mrt_data`, 6.226 Zeilen): Abweichendes Schema — kein Assessment-UUID-System, stattdessen `patientalias`, `sty_date` (Untersuchungsdatum), `pri_date` (Bildverarbeitung), `run_by`, `prog_ver`, `scanner` (z. B. MAGNETOM Vida).

Kernvariablen:

| Bereich | Variablen | Beschreibung |
|---------|-----------|-------------|
| Globale Atrophie | `bpf`, `bpf_chg` | Brain Parenchymal Fraction und Änderung zum Vorzeitpunkt |
| T2-Läsionen | `t2lesvol`, `t2overbv`, `nt2lescn`, `nt2lesgt`, `nt2lesvo` | Volumen, relative Last, Anzahl und Volumen neuer/vergrößerter Läsionen |
| Läsions­lokalisation | `t2voljux`, `t2volprv`, `t2volinf`, `t2voloth` | Juxtakortikal, periventrikulär, infratentoriell, andere |
| Gewebefraktionen | `gmf`, `wmf`, `cgmvol`, `dgmvol`, `cgmf`, `dgmf` | Graue/weiße Substanz (global und spezifisch) |
| Thalamus | `thalvol`, `thalf` | Volumen und Fraktion |
| Qualitäts­kontrolle | `segvisqc`, `segcomm` | Visuelle QC (PASS/FAIL) und Kommentar |
| Pipeline | `flrdcpp`, `t1dcpp` | FLAIR-/T1-basierte Postprocessing-Flags |

Hinweis: `nt2lescn`, `nt2lesgt`, `nt2lesvo` müssen aus Längsschnittvergleichen generiert werden (nicht direkt aus Einzeluntersuchung ableitbar). `pri_date` entspricht dem vorherigen `sty_date` bei Folgeuntersuchungen.

---

### 3.8 Patient Profile (Stammdaten)

**Inhalt:** Demografische und medizinische Grunddaten je Patient.

**Projektbezug:** Das Patientenprofil bildet die Verknüpfungsebene zwischen allen anderen Datensätzen und ist Grundlage für die Stratifizierung in der Pfadanalyse. Variablen wie Diagnosezeitpunkt und Komorbiditäten sind zentrale Eingangsgrössen für die ML-basierte Phänotypisierung.

**Tabelle** (`patient_profile_overview_training`, 1.100 Zeilen): `DOB` (Geburtsdatum), `Gender` (female/male, 4 Missing), `Handedness` (right/left, 4 Missing), `Date of Diagnosis` (43 Missing), `Preferred Language` (de/en/ru), `Comorbidities` (durch `#` getrennte Liste, z. B. `high_blood_pressure#anxiety_disorder`, 307 Missing), `Created At`.

---

### 3.9 Wrapper Overview (Assessment-Metadaten)

**Inhalt:** Technische Informationen zur Assessment-Sitzung und dem verwendeten Gerät.

**Projektbezug:** Die Wrapper-Daten dokumentieren die technische Infrastruktur des iPad-basierten Erhebungssystems und ermöglichen Qualitätssicherung sowie Nachvollziehbarkeit der Testbedingungen.

**Tabelle** (`wrapper_overview_training`, 1.134 Zeilen): `Successful Module Count` (1–7), `Device Type` (iPad7,5), `Device Name`, `App Build` (4640), `App Version` (2.2.1), `IOS Version` (15.7/15.7.1), `Vendor Identifier`. Kein Tutorial in fast allen Fällen gestartet (1.129 von 1.134 Missing bei `Tutorial Started At`).

---

## 4. Bezug zum Projektantrag: Untersuchungen und Instrumente

### 4.1 Zuordnung der Datenschemata zu Erhebungsinstrumenten

Der Projektantrag beschreibt die Sammlung multidimensionaler Parameter aus Diagnose, Therapie und Monitoring. Die folgende Tabelle stellt den Bezug zwischen den Datenschemata und den im Projekt verwendeten klinischen Instrumenten her:

| Datenschema | Klinisches Instrument | Datentyp lt. Projektantrag | Gemessene Dimension |
|-------------|----------------------|---------------------------|---------------------|
| `lclat_data` | Low-Contrast Letter Acuity Test (LCLA) | Klinische Daten / Monitoring | Visuelle Funktion |
| `mdt_data` | 9-Hole Peg Test (9HPT) | Klinische Daten / Monitoring | Feinmotorik obere Extremität |
| `npst_data` | Symbol Digit Modalities Test (SDMT) | Klinische Daten / Monitoring | Kognitive Informationsverarbeitung |
| `wst_data` | Timed 25-Foot Walk (T25FW) | Klinische Daten / Monitoring | Gehfähigkeit untere Extremität |
| `nq_data` | Neuro-QoL (CAT) | Patientenberichtete Daten | Lebensqualität, funktionelle Einschränkungen |
| `mh_data` | Strukturierter Anamnesefragebogen | Klinische Daten / Diagnose | Komorbiditäten, Medikation, Sozialanamnese |
| `mrt_data` | Kraniale MRT + automatisierte Segmentierung | Paraklinische Daten | Läsionslast, Hirnatrophie, Gewebevolumina |
| `patient_profile_data` | Patientenregistrierung | Stammdaten | Demografie, Diagnose, Händigkeit |
| `wrapper_overview_data` | iPad-Assessment-System (MSPT-Plattform) | Kontextparameter | Gerät, Software, Sitzungsmetadaten |

### 4.2 Einbettung in das MSPT-Framework

Die vier klinischen Funktionstests (LCLA, 9HPT, SDMT, T25FW) bilden zusammen den **Multiple Sclerosis Performance Test (MSPT)** — eine iPad-basierte, digitale Version des klassischen **MSFC (Multiple Sclerosis Functional Composite)**. Dies wird durch mehrere Merkmale der Daten bestätigt: alle vier Tests werden im selben Assessment-System erhoben (gemeinsame Assessment-UUIDs), auf identischen iPads (iPad7,5) mit konsistenter Software (App Version 2.2.0–2.2.1), und die `wrapper_overview` dokumentiert bis zu 7 erfolgreich durchgeführte Module pro Sitzung.

Der MSPT ergänzt den klassischen MSFC um den LCLA-Test (Sehfunktion) und die computeradaptive Neuro-QoL-Erhebung, was dem im Projektantrag beschriebenen Anspruch einer multidimensionalen Datenerfassung entspricht.

### 4.3 Abdeckung der im Projektantrag genannten Datendimensionen

Der Projektantrag nennt folgende Datenkategorien als notwendig für die digitale Phänotypisierung:

| Datenkategorie (Projektantrag) | Abdeckung durch Datenschemata | Status |
|-------------------------------|-------------------------------|--------|
| Klinische Daten | LCLA, 9HPT, SDMT, T25FW, MH | Vorhanden |
| Paraklinische Daten | MRT (Läsionen, Atrophie, Volumetrie) | Vorhanden |
| Patientenberichtete Daten | Neuro-QoL, medizinische Historie | Vorhanden |
| Kontextparameter | Wrapper Overview, Patient Profile | Vorhanden |
| Neurobiologische Daten | — | Nicht in Schemata enthalten |
| Immunologische Daten | — | Nicht in Schemata enthalten |
| Multi-OMICS | — | Nicht in Schemata enthalten |
| Therapie-/Behandlungsdaten | Teilweise über MH (Medikation) | Teilweise |

Die Datenschemata decken die zentralen klinischen, paraklinischen und patientenberichteten Dimensionen ab. Neurobiologische und immunologische Daten (z. B. Liquordiagnostik, Blutmarker) sowie Multi-OMICS-Daten, die im Projektantrag als Teil der umfassenden Datenbasis genannt werden, sind in den vorliegenden Schemata nicht enthalten. Ebenso fehlen detaillierte Therapiedaten (z. B. DMT-Typ, Dosierung, Therapiewechsel), die über die im MH-Fragebogen erfasste Medikationsinformation hinausgehen.

### 4.4 Relevanz für die Projektziele

Die vorliegenden Datenschemata bilden die Grundlage für die beiden im Projektantrag definierten Schwerpunkte:

**Schwerpunkt 1 — Intelligente Patientenpfade und Digitaler Phänotyp:** Die longitudinalen Assessments (identifizierbar über Patient UUID und zeitlich geordnete Assessment-Zeitstempel) ermöglichen die Extraktion individueller Patientenpfade. Die Z-Scores in MDT, NPST und WST liefern normierte Verlaufsmarker, die MRT-Daten ergänzen paraklinische Progressionsmarker (BPF-Änderung, neue Läsionen). Durch Process Mining und Clusteranalyse — wie im Projektantrag beschrieben — können aus diesen multidimensionalen Zeitreihen Phänotypen abgeleitet werden.

**Schwerpunkt 2 — Adaptive Expertensysteme und Patienteninteraktion:** Die Neuro-QoL-Daten und der MH-Fragebogen liefern die patientenberichtete Perspektive, die für das im Projektantrag beschriebene Patient Empowerment und die partizipative Versorgungsgestaltung benötigt wird. Die Detail-Daten (Reaktionszeiten, Fehlertypen, Abbruchgründe) ermöglichen feinkörnige Analysen, die in ein adaptives Dashboard einfließen können.

---

## 5. Datenvolumen und Qualitätshinweise

| Datensatz | Zeilen (Detail) | Zeilen (Summary) | Patienten (ca.) |
|-----------|----------------|-------------------|-----------------|
| LCLAT | ~110.000 | ~1.137 | ~1.099 |
| MDT | 94.434 | 2.244 | ~1.099 |
| NPST | 68.699 | 2.279 | ~1.099 |
| WST | 1.156 | ~1.134 | ~1.099 |
| NQ | 34.984 | — | ~1.099 |
| MH | 29.945 | — | ~1.099 |
| MRT | 6.226 | — | variabel |
| Patient Profile | 1.100 | — | 1.100 |
| Wrapper Overview | 1.134 | — | ~1.099 |

Qualitätshinweise: Abbruchgründe (`Cancel Reason`) sind in allen Funktionstests dokumentiert (z. B. `unable-frustrated`, `incomplete-unable-to-complete`). MRT-Daten enthalten eine Qualitätskontrollspalte (`segvisqc`: PASS/FAIL). Einige Kontraststufen im LCLAT und die Läsions-Änderungswerte im MRT weisen systematisch hohe Missing-Raten auf, was auf konfigurationsbedingte oder longitudinale Berechnungslogik zurückzuführen ist.
