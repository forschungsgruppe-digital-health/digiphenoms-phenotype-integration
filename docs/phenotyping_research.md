# Digitale Phänotypisierung bei Multipler Sklerose — Literaturrecherche, Methoden und Anwendung auf DigiPhenoMS

## 1. Einleitung

Dieses Dokument fasst die Ergebnisse einer Literaturrecherche zu digitalen Phänotypen zusammen, prüft deren Relevanz für das Krankheitsbild Multiple Sklerose (MS), erörtert bestehende Methoden zur Phänotypisierung und wendet einen konkreten Ansatz auf die im DigiPhenoMS-Projekt vorliegenden Datenschemata an. Abschließend werden visuelle Darstellungsformen für individuelle Patientenphänotypen vorgestellt.

---

## 2. Literaturrecherche: Digitale Phänotypen

### 2.1 Begriffsklärung

Digitale Phänotypisierung beschreibt die datengetriebene Charakterisierung von Patient\*innen anhand digital erhobener Daten — von Smartphone-Sensordaten über iPad-basierte Leistungstests bis hin zu automatisiert ausgewerteten MRT-Bildern. Das Konzept wurde 2015 an der Harvard University eingeführt und umfasst die kontinuierliche, echtzeitnahe Erfassung von Verhaltens-, psychologischen und physiologischen Zuständen über digitale Endgeräte.

### 2.2 Verifizierte Schlüsselpublikationen mit MS-Bezug

Die folgende Tabelle listet die recherchierten und verifizierten Publikationen auf, geordnet nach thematischer Relevanz:

#### Gruppe A: Digitale Phänotypisierung direkt bei MS

| Publikation | Zeitschrift / Quelle | Jahr | Kernaussage |
|-------------|---------------------|------|-------------|
| Longitudinal Digital Phenotyping of MS Severity Using Passively Sensed Behaviors and Ecological Momentary Assessments | Journal of Medical Internet Research (JMIR) | 2025 | ML-Modelle auf Smartphone- und Fitness-Tracker-Daten sagen depressive Symptome (80,6% Accuracy), MS-Symptombelastung (77,3%), Fatigue (73,8%) und Schlafqualität (72,0%) vorher. |
| AI-driven reclassification of MS progression | Nature Medicine | 2025 | Probabilistische ML-Analyse von ~8.000 Patienten, ~118.000 Visiten und >35.000 MRT-Scans ermöglicht eine datengetriebene Reklassifikation der MS-Progressionsformen. |
| Identifying MS subtypes using unsupervised ML and MRI data | Nature Communications | 2021 | Unsupervised ML auf 6.322 MS-Patienten definiert MRT-basierte Subtypen: Kortex-geführt, NAWM-geführt und Läsions-geführt — mit unterschiedlicher Progressionsrate. |
| Modeling MS using mobile and wearable sensor data | npj Digital Medicine | 2024 | Sensor-Features aus Smartphones und Wearables unterscheiden MS-Patient\*innen von gesunden Kontrollen und erkennen Behinderungs- und Fatigue-Grade (55 MS-Patienten, 24 Kontrollen, 489 Tage). |
| Lesion features on MRI discriminate MS patients | European Journal of Neurology | 2021 | Hierarchisches Clustering auf Läsions-MRT-Merkmalen (MWF, Volumen, Thalamus) identifiziert zwei distinkte Cluster, die mit EDSS korrelieren. |
| Data-driven deep phenotyping of MS using PROMs | Neurology (Abstract) | 2024 | Deep Phenotyping über Patient-Reported Outcome Measures zur Subgruppenidentifikation. |

#### Gruppe B: MSPT-Plattform (direkt relevant für DigiPhenoMS-Daten)

| Publikation | Zeitschrift / Quelle | Jahr | Kernaussage |
|-------------|---------------------|------|-------------|
| The MSPT: An iPad-Based Disability Assessment Tool | Journal of Visualized Experiments (JoVE) / PMC | 2014 | Originalveröffentlichung des MSPT mit 5 Modulen: Walking Speed, Balance, MDT (9HPT), PST (SDMT), LCLA. Hohe Reproduzierbarkeit, starke Korrelation mit techniker-administrierten Tests. |
| MSPT: Technical Development and Usability | Advances in Therapy | 2019 | Validierungsstudie: 84% Completion-Rate bei 28 min Durchführungszeit in der Routineversorgung. |
| From implementation to discontinuation: MSPT as digital monitoring tool | Frontiers in Digital Health | 2025 | Erfahrungsbericht aus dem MS-Zentrum Dresden: Implementation (2020), klinische Nutzung, Diskontinuierung (2023). Direkt relevant für DigiPhenoMS. |
| Data Collection in MS: The MSDS Approach | Frontiers in Neurology | 2020 | Ziemssen et al.: Multiple Sclerosis Documentation System als eHealth-Plattform für multidimensionale Datenerfassung. |

#### Gruppe C: Methodik (Clustering, Process Mining, Phänotypisierung)

| Publikation | Zeitschrift / Quelle | Jahr | Kernaussage |
|-------------|---------------------|------|-------------|
| Phenotype clustering in health care: A narrative review | Frontiers in AI | 2022 | Übersicht über sechs Hauptmethoden: k-Means, hierarchisches Clustering, DBSCAN, Gaussian Mixture Models, Latent Class Analysis, Self-Organizing Maps. |
| Trace-based clustering for patient phenotyping | Knowledge-Based Systems | 2021 | 5-Schritt-Methodik für unüberwachte Phänotypisierung über zeitlich geordnete Patientenpfade (Traces). |
| Phenotyping Clusters of Patient Trajectories suffering from Chronic Complex Disease | arXiv | 2020 | Clustering longitudinaler Krankheitsverläufe bei chronischen Erkrankungen mittels Trajectory-Mining. |
| Comprehensive clinical benefits of digital phenotyping | npj Digital Medicine | 2025 | Aktueller Review: Smartphones, Wearables und IoT-Sensoren für kontinuierliches Gesundheitsmonitoring bei chronischen Erkrankungen. |

---

## 3. Ansätze und Methoden zur Phänotypisierung

Aus der Literatur lassen sich vier Hauptansätze zur digitalen Phänotypisierung bei MS ableiten:

### 3.1 MRT-basierte Subtypisierung (Bildgebung)

Dieser Ansatz nutzt ausschließlich oder primär MRT-Daten (Läsionsvolumen, Atrophiemaße, Gewebesegmentierung) zur Identifikation von Krankheitssubtypen. Eshaghi et al. (2021, Nature Communications) definierten drei MRT-Subtypen anhand unsupervised ML auf >6.000 Patienten: Kortex-geführt (corticale Atrophie dominiert), NAWM-geführt (Veränderungen in normal erscheinender weißer Substanz) und Läsions-geführt (Läsionslast dominiert). Der läsions-geführte Subtyp zeigte die höchste Progressionsrate.

**Methoden:** Hauptkomponentenanalyse (PCA) zur Dimensionsreduktion, agglomeratives hierarchisches Clustering, k-Means.

**Anwendbarkeit auf DigiPhenoMS:** Direkt umsetzbar mit den `mrt_data`-Variablen (BPF, T2-Läsionsvolumen, Gewebefraktionen, Thalamusvolumen, Läsionslokalisationen).

### 3.2 Multimodale Funktions-Phänotypisierung (Klinische Tests + PROs)

Dieser Ansatz kombiniert die Ergebnisse funktioneller Tests (MSFC/MSPT-Komponenten) mit patientenberichteten Outcomes zu einem multidimensionalen Patientenprofil. Die JMIR-Studie (2025) demonstriert, dass ML-Modelle auf passiv erhobenen Daten klinisch relevante Symptomprofile mit hoher Genauigkeit vorhersagen können.

**Methoden:** Supervised ML (Random Forest, Gradient Boosting) für Symptomvorhersage; unsupervised Clustering (k-Means, LCA) für Subgruppenidentifikation.

**Anwendbarkeit auf DigiPhenoMS:** Hervorragend geeignet. Die Z-Scores aus MDT, NPST, WST und die T-Scores aus NQ bilden bereits normierte, vergleichbare Feature-Vektoren. Ergänzt durch LCLAT-Ergebnisse und MH-Daten.

### 3.3 Trace-basierte Pfadanalyse (Process Mining)

Dieser Ansatz modelliert den Krankheitsverlauf als zeitlich geordnete Sequenz von Ereignissen (Trace) und identifiziert typische Verlaufsmuster durch Sequenz-Clustering. Besonders relevant für den im DigiPhenoMS-Projektantrag beschriebenen Schwerpunkt 1 (Intelligente Patientenpfade).

**Methoden:** Process Mining (Event-Log-Extraktion, Process Discovery), Trace-Clustering (z. B. über Edit-Distance-basierte Ähnlichkeitsmaße), gerichtete Graphen als Pfadmodelle.

**Anwendbarkeit auf DigiPhenoMS:** Die longitudinalen Assessments (identifizierbar über Patient UUID + zeitgeordnete Assessment-Zeitstempel) können als Event-Logs modelliert werden. Jede Assessment-Sitzung wird ein Knoten im Patientenpfad, annotiert mit den funktionellen Testergebnissen und MRT-Befunden.

### 3.4 Probabilistische Progressionsmodellierung

Der Nature-Medicine-Ansatz (2025) nutzt probabilistische ML zur Reklassifikation von Progressionsformen. Statt der klassischen MS-Verlaufstypen (RRMS, SPMS, PPMS) werden datengetriebene Progressionskategorien definiert.

**Methoden:** Hidden Markov Models, Gaussian Process Models, Bayesian Nonparametrics.

**Anwendbarkeit auf DigiPhenoMS:** Erfordert umfangreiche longitudinale Daten, ist aber konzeptionell mit den verfügbaren Zeitreihen (wiederholte MSPT-Assessments + MRT-Verlauf) kompatibel.

---

## 4. Anwendung auf DigiPhenoMS: Vorgeschlagener Phänotypisierungs-Ansatz

### 4.1 Empfohlener Ansatz: Multimodale Cluster-Phänotypisierung

Auf Basis der Literaturanalyse und der verfügbaren Datenschemata empfehle ich einen **zweistufigen, multimodalen Clustering-Ansatz**, der die Stärken der Ansätze 3.1 und 3.2 kombiniert:

**Stufe 1 — Feature-Extraktion (pro Patient und Zeitpunkt):**

Aus den Datenschemata werden pro Assessment-Zeitpunkt folgende normierte Features extrahiert:

| Dimension | Quelle | Features |
|-----------|--------|----------|
| Kognition | `npst_data` (Summary) | Z-Score, Total Number Correct |
| Feinmotorik | `mdt_data` (Summary) | Z-Score Dominant, Z-Score Nondominant, Trial Duration |
| Gehfähigkeit | `wst_data` (Summary) | Z-Score, Walk Duration, Walking Aid Used |
| Sehfunktion | `lclat_data` (Summary) | Total Number Correct at 100%, at 2.5% |
| Lebensqualität | `nq_data` (Detail) | T-Scores je Subdomäne (upper_extremity etc.) |
| Bildgebung | `mrt_data` | BPF, T2-Läsionsvolumen, Thalamusvolumen, cgmf, neue Läsionen |
| Kontext | `patient_profile_data` | Alter (berechnet aus DOB), Geschlecht, Krankheitsdauer (berechnet aus Date of Diagnosis), Komorbiditäten-Anzahl |

**Stufe 2 — Clustering und Phänotyp-Zuweisung:**

1. **Normierung:** Alle Features werden z-standardisiert (Mean=0, SD=1), um Skalenunterschiede auszugleichen. Die Z-Scores aus MDT/NPST/WST sind bereits normiert.
2. **Dimensionsreduktion (optional):** Bei hoher Feature-Zahl PCA oder UMAP zur Reduktion auf die erklärungsstärksten Komponenten.
3. **Clustering:** k-Means (mit Silhouettenanalyse zur Bestimmung der optimalen Clusterzahl) oder Gaussian Mixture Models (GMM) für weichere Clustergrenzen.
4. **Phänotyp-Interpretation:** Jeder Cluster wird anhand seiner Centroide klinisch interpretiert — z. B. „kognitiv-betont", „motorisch-betont", „MRT-aktiv mit geringer funktioneller Einschränkung".
5. **Longitudinale Erweiterung:** Durch Zuordnung jedes Assessment-Zeitpunkts zu einem Cluster entstehen Phänotyp-Trajektorien (Pfade zwischen Clustern über die Zeit).

### 4.2 Konkretes Feature-Mapping auf die Datenschemata

```
Patient p zum Zeitpunkt t:

feature_vector(p, t) = [
    # Kognition (npst_summary)
    npst.z_score,
    npst.total_number_correct,

    # Feinmotorik (mdt_summary)
    mdt.z_score_dominant,
    mdt.z_score_nondominant,

    # Gehfähigkeit (wst_summary)
    wst.z_score,
    wst.walk_duration,
    wst.walking_aid_used,        # binär: 0/1

    # Sehfunktion (lclat_summary)
    lclat.total_correct_100pct,
    lclat.total_correct_2_5pct,

    # Lebensqualität (nq_detail, aggregiert pro Subdomäne)
    nq.t_score_upper_extremity,
    nq.t_score_lower_extremity,
    nq.t_score_fatigue,
    nq.t_score_...,              # je nach verfügbaren Subdomänen

    # Bildgebung (mrt_data, nächstliegender MRT-Zeitpunkt)
    mrt.bpf,
    mrt.t2lesvol,
    mrt.thalvol,
    mrt.cgmf,
    mrt.nt2lescn,                # neue Läsionen (falls Verlaufsdaten)

    # Kontext (patient_profile, zeitinvariant)
    age_at_assessment,
    disease_duration_years,
    gender,                      # binär kodiert
    comorbidity_count
]
```

### 4.3 Verknüpfung Assessment ↔ MRT

Die Verknüpfung erfolgt über `Patient UUID` (Assessment-System) ↔ `patientalias` (MRT-System). Da MRT-Untersuchungen nicht bei jedem Assessment stattfinden, wird dem nächstliegenden Assessment-Zeitpunkt der jeweils letzte MRT-Datensatz zugeordnet (Last-Observation-Carried-Forward).

### 4.4 Erwartete Phänotypen (Hypothese)

Auf Basis der Literatur zu MS-Subgruppen und der verfügbaren Dimensionen sind folgende Cluster plausibel:

| Phänotyp | Erwartetes Profil |
|----------|------------------|
| **A — Gering beeinträchtigt** | Hohe Z-Scores in allen Funktionsbereichen, niedrige Läsionslast, hohe Lebensqualität |
| **B — Kognitiv-betont** | Niedriger NPST-Z-Score bei relativ erhaltener Motorik, ggf. erhöhte Läsionslast |
| **C — Motorisch-betont** | Niedrige Z-Scores in MDT/WST, Gehhilfe-Nutzung, bei erhaltener Kognition |
| **D — Multimodal beeinträchtigt** | Niedrige Werte in Kognition, Motorik und Sehfunktion, hohe Läsionslast, niedrige BPF |
| **E — MRT-aktiv, klinisch stabil** | Hohe Läsionsaktivität (neue Läsionen), aber noch kompensierte Funktionswerte |

---

## 5. Visuelle Darstellungsformen für den Patientenphänotyp

### 5.1 Übersicht der Darstellungsformen

Die Literatur beschreibt mehrere Visualisierungsansätze für multivariate Patientenprofile:

| Darstellungsform | Beschreibung | Stärken | Limitationen |
|-----------------|-------------|---------|-------------|
| **Radar-/Spiderplot** | Kreisförmige Achsenanordnung, ein Polygon pro Patient | Intuitiv, zeigt Profil auf einen Blick | Fläche hängt von Achsenreihenfolge ab, kann irreführend sein |
| **Origami-Plot** | Weiterentwicklung des Radarplots mit zusätzlichen Hilfsachsen | Flächeninvarianz gegenüber Achsenreihenfolge, R-Paket verfügbar | Weniger etabliert, komplexer zu lesen |
| **Heatmap (Phänotyp-Matrix)** | Zeilen = Patienten, Spalten = Features, Farbe = Ausprägung | Gut für Kohorten-Überblick, zeigt Cluster visuell | Nicht für Einzelpatienten-Kommunikation geeignet |
| **UMAP/t-SNE-Embedding** | 2D-Projektion des hochdimensionalen Feature-Raums | Zeigt Clusterstruktur und Patientenposition in der Kohorte | Abstrakt, schwer klinisch interpretierbar |
| **Temporal Trajectory Plot** | Zeitachse mit Phänotyp-Zugehörigkeit je Zeitpunkt | Zeigt Verlauf und Phänotyp-Wechsel | Erfordert longitudinale Daten |
| **Digital-Twin-Dashboard** | Integriertes Dashboard mit Einzelpatient im Kohortenkontext | Umfassend, klinisch nutzbar | Hoher Implementierungsaufwand |

### 5.2 Empfehlung für DigiPhenoMS

Für die Darstellung eines individuellen Patientenphänotyps innerhalb der Kohorte empfehle ich eine **Kombination aus drei Visualisierungen**:

#### Visualisierung 1: Origami-Plot / Radar-Chart (Einzelpatient-Profil)

Ein Origami-Plot (oder alternativ ein klassischer Radarplot) mit 6–8 Achsen stellt das individuelle Profil eines Patienten dar. Die Achsen repräsentieren die normierten Funktionsdimensionen:

```
Achsen des Origami-/Radar-Plots:

1. Kognition           → NPST Z-Score
2. Feinmotorik (dom.)  → MDT Z-Score Dominant
3. Feinmotorik (n-dom.)→ MDT Z-Score Nondominant
4. Gehfähigkeit        → WST Z-Score
5. Sehfunktion         → LCLAT Total Correct (normiert)
6. Hirnatrophie        → BPF (invertiert: höher = weniger Atrophie)
7. Läsionslast         → T2-Läsionsvolumen (invertiert)
8. Lebensqualität      → NQ T-Score (Mittel über Subdomänen)
```

Das Patientenprofil wird als farbiges Polygon dargestellt, überlagert mit dem Cluster-Centroid (gestrichelt) und optional dem Kohortenmedian (grau). Werte nahe der Peripherie signalisieren gute Funktion, Werte nahe dem Zentrum Beeinträchtigung.

Der Origami-Plot (Steyerberg et al., 2023) löst das Problem der Flächenabhängigkeit von der Achsenreihenfolge und ist als R-Paket `OrigamiPlot` verfügbar.

#### Visualisierung 2: Kohortenembedding mit Patientenmarkierung

Ein UMAP- oder t-SNE-Plot zeigt die gesamte Kohorte als Punktwolke, eingefärbt nach Phänotyp-Cluster. Der aktuelle Patient wird als hervorgehobener Punkt mit Beschriftung dargestellt. Dies zeigt dem klinischen Personal, wo der Patient im Vergleich zur Gesamtkohorte steht.

```
Beispiel-Layout:

    ○ ○ ●               ○ = anderer Patient
  ○ ○ ○ ●  ○            ● = Cluster-Zugehörigkeit (Farbe)
    ○ ★ ○               ★ = aktueller Patient
  ○ ○ ○                  Achsen: UMAP-1, UMAP-2
       ● ●
    ● ● ●
```

#### Visualisierung 3: Temporale Phänotyp-Trajektorie

Für longitudinale Daten zeigt ein Zeitreihendiagramm die Phänotyp-Zugehörigkeit des Patienten über die Zeit. Jeder Zeitpunkt (Assessment-Datum) wird als farbig kodierter Punkt dargestellt, verbunden durch Linien. Phänotyp-Wechsel werden als Farbübergänge sichtbar.

```
Beispiel-Layout:

Phänotyp  |  A ─── A ─── A ─── B ─── B ─── C
          |  ●─────●─────●─────●─────●─────●
          |  t1    t2    t3    t4    t5    t6
          └──────────────────────────────────→ Zeit
```

### 5.3 Technische Umsetzungshinweise

| Aspekt | Empfehlung |
|--------|-----------|
| Sprache | Python (sklearn, umap-learn, matplotlib/plotly) oder R (OrigamiPlot, ggplot2, umap) |
| Clustering | `sklearn.cluster.KMeans` mit `silhouette_score` für Clusteranzahl; alternativ `sklearn.mixture.GaussianMixture` |
| Radar-/Origami-Plot | R: `OrigamiPlot`-Paket; Python: `plotly` (Scatterpolar) |
| Embedding | `umap-learn` (Python) oder `uwot` (R) |
| Dashboard | Streamlit (Python) oder R Shiny für interaktive Exploration |

---

## 6. Zusammenfassung

Die Literaturrecherche zeigt, dass digitale Phänotypisierung bei MS ein aktives Forschungsfeld ist, das von einfachen MRT-Clusterings bis zu multimodalen, longitudinalen Ansätzen reicht. Das DigiPhenoMS-Projekt ist mit seinen MSPT-basierten Funktionsdaten, der MRT-Volumetrie und den patientenberichteten Neuro-QoL-Daten hervorragend für einen multimodalen Clustering-Ansatz aufgestellt. Die vorgeschlagene Kombination aus Feature-Extraktion über alle Datenschemata, k-Means-/GMM-Clustering und dreifacher Visualisierung (Origami-Plot, Kohortenembedding, Temporale Trajektorie) bietet einen konkreten, umsetzbaren Rahmen für die digitale Phänotypisierung im Projekt.

---

## Quellen

### Digitale Phänotypisierung bei MS
- [Longitudinal Digital Phenotyping of MS Severity (JMIR, 2025)](https://www.jmir.org/2025/1/e70871)
- [AI-driven reclassification of MS progression (Nature Medicine, 2025)](https://www.nature.com/articles/s41591-025-03901-6)
- [Identifying MS subtypes using unsupervised ML and MRI data (Nature Communications, 2021)](https://www.nature.com/articles/s41467-021-22265-2)
- [Modeling MS using mobile and wearable sensor data (npj Digital Medicine, 2024)](https://www.nature.com/articles/s41746-024-01025-8)
- [Lesion features on MRI discriminate MS patients (PMC, 2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8727028/)
- [Data-driven deep phenotyping of MS using PROMs (Neurology, 2024)](https://www.neurology.org/doi/10.1212/WNL.0000000000202693)
- [MS risk stratification and cost prediction (Communications Medicine, 2025)](https://www.nature.com/articles/s43856-025-01229-3)

### MSPT-Plattform und Dresdner MS-Zentrum
- [The MSPT: An iPad-Based Disability Assessment Tool (PMC, 2014)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4209820/)
- [MSPT: Technical Development and Usability (Advances in Therapy, 2019)](https://link.springer.com/article/10.1007/s12325-019-00958-x)
- [From implementation to discontinuation: MSPT in Dresden (Frontiers, 2025)](https://www.frontiersin.org/journals/digital-health/articles/10.3389/fdgth.2025.1672732/full)
- [Data Collection in MS: The MSDS Approach (Frontiers, 2020)](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2020.00445/full)
- [AI-enabled Living Labs in MS care (Ziemssen et al., 2026)](https://journals.sagepub.com/doi/10.1177/13524585261424136)

### Methodik: Clustering und Phänotypisierung
- [Phenotype clustering in health care: A narrative review (Frontiers in AI, 2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9411746/)
- [Trace-based clustering for patient phenotyping (Knowledge-Based Systems, 2021)](https://www.sciencedirect.com/science/article/pii/S0950705121007310)
- [Comprehensive clinical benefits of digital phenotyping (npj Digital Medicine, 2025)](https://www.nature.com/articles/s41746-025-01602-5)
- [Phenotyping Clusters of Patient Trajectories (arXiv, 2020)](https://arxiv.org/abs/2011.08356)

### Visualisierung
- [Origami plot: improving radar chart (Journal of Clinical Epidemiology, 2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10599795/)
- [OrigamiPlot R Package (CRAN)](https://cran.r-project.org/web/packages/OrigamiPlot/OrigamiPlot.pdf)
- [Radar plots for multivariate health care data (ResearchGate)](https://www.researchgate.net/publication/5537797_Radar_plots_A_useful_way_for_presenting_multivariate_health_care_data)
- [Digital Representation of Patients as Medical Digital Twins (JMIR, 2025)](https://medinform.jmir.org/2025/1/e53542)
- [Visualising disease trajectories from population-wide data (PMC, 2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9946689/)
- [Systematic Review of Patient-Facing Visualizations (PMC, 2019)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6785326/)
