<script setup>
import { computed } from "vue";
import LineChart from "../components/LineChart.vue";
import BarChart from "../components/BarChart.vue";
import DataTable from "../components/DataTable.vue";
import {
  store,
  observationsFor,
  conditionsFor,
  encountersFor,
  codeOf,
  componentValue,
  effectiveDate,
  displayDate,
  nqDomain,
} from "../services/fhirStore.js";

const props = defineProps({
  patientId: { type: String, required: true },
});

defineEmits(["back"]);

const GENDERS = { female: "weiblich", male: "männlich", other: "divers", unknown: "unbekannt" };

const patient = computed(() =>
  store.resources.Patient.find((p) => p.id === props.patientId),
);

const conditions = computed(() =>
  conditionsFor(props.patientId).map(
    (c) => c.code?.coding?.[0]?.display ?? c.code?.coding?.[0]?.code ?? "Diagnose",
  ),
);

const encounterCount = computed(() => encountersFor(props.patientId).length);

function observationsWithCode(code) {
  return observationsFor(props.patientId)
    .filter((o) => codeOf(o).includes(code))
    .sort((a, b) => (effectiveDate(a) ?? 0) - (effectiveDate(b) ?? 0));
}

const fmt = (v, d = 1) =>
  v == null
    ? "—"
    : Number(v).toLocaleString("de-DE", { maximumFractionDigits: d });

/* CSS custom properties are design-token indirections; charts need hex at
   render time, resolved from the live theme. */
function tokenColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/* ---- LCLA ---- */
const lcla = computed(() => observationsWithCode("lcla-test"));
const lclaSeries = computed(() => [
  {
    name: "Gesamt korrekt",
    color: tokenColor("--series-1"),
    points: lcla.value
      .filter((o) => o.valueQuantity)
      .map((o) => ({ x: effectiveDate(o), y: o.valueQuantity.value })),
  },
]);
const lclaRows = computed(() =>
  lcla.value.map((o) => ({
    date: displayDate(effectiveDate(o)),
    status: o.status,
    total: fmt(o.valueQuantity?.value, 0),
    pct100: fmt(componentValue(o, "lclat-correct-100pct"), 0),
    pct25: fmt(componentValue(o, "lclat-correct-2.5pct"), 0),
    duration: fmt(componentValue(o, "module-duration"), 0),
  })),
);

/* ---- 9HPT (two series: left/right hand) ---- */
const nineHpt = computed(() => observationsWithCode("83141-2"));
const nineHptSeries = computed(() =>
  [
    {
      name: "Linke Hand",
      color: tokenColor("--series-1"),
      code: "9hpt-left-hand-time",
    },
    {
      name: "Rechte Hand",
      color: tokenColor("--series-2"),
      code: "9hpt-right-hand-time",
    },
  ].map((series) => ({
    name: series.name,
    color: series.color,
    points: nineHpt.value
      .map((o) => ({ x: effectiveDate(o), y: componentValue(o, series.code) }))
      .filter((p) => p.y != null),
  })),
);
const nineHptRows = computed(() =>
  nineHpt.value.map((o) => ({
    date: displayDate(effectiveDate(o)),
    left: fmt(componentValue(o, "9hpt-left-hand-time")),
    right: fmt(componentValue(o, "9hpt-right-hand-time")),
    zDom: fmt(componentValue(o, "9hpt-zscore-dominant"), 2),
    zNonDom: fmt(componentValue(o, "9hpt-zscore-nondominant"), 2),
  })),
);

/* ---- SDMT ---- */
const sdmt = computed(() => observationsWithCode("sdmt-test"));
const sdmtSeries = computed(() => [
  {
    name: "Gesamt korrekt",
    color: tokenColor("--series-1"),
    points: sdmt.value
      .filter((o) => o.valueQuantity)
      .map((o) => ({ x: effectiveDate(o), y: o.valueQuantity.value })),
  },
]);
const sdmtRows = computed(() =>
  sdmt.value.map((o) => ({
    date: displayDate(effectiveDate(o)),
    correct: fmt(o.valueQuantity?.value, 0),
    incorrect: fmt(componentValue(o, "sdmt-total-incorrect"), 0),
    z: fmt(componentValue(o, "sdmt-zscore"), 2),
  })),
);

/* ---- T25FW ---- */
const t25fw = computed(() => observationsWithCode("t25fw-test"));
const t25fwSeries = computed(() => [
  {
    name: "Gehzeit",
    color: tokenColor("--series-1"),
    points: t25fw.value
      .filter((o) => o.valueQuantity)
      .map((o) => ({ x: effectiveDate(o), y: o.valueQuantity.value })),
  },
]);
const t25fwRows = computed(() =>
  t25fw.value.map((o) => ({
    date: displayDate(effectiveDate(o)),
    time: fmt(o.valueQuantity?.value, 2),
    z: fmt(componentValue(o, "t25fw-zscore"), 2),
    aid: componentValue(o, "walking-aid-used") ? "ja" : "nein",
  })),
);

/* ---- Neuro-QoL: latest T-score per domain ---- */
const nq = computed(() => observationsWithCode("neuro-qol-tscore"));
const nqItems = computed(() => {
  const latest = new Map();
  for (const o of nq.value) {
    if (o.valueQuantity) latest.set(nqDomain(o), o.valueQuantity.value);
  }
  return [...latest.entries()].map(([label, value]) => ({ label, value }));
});
const nqRows = computed(() =>
  nq.value.map((o) => ({
    date: displayDate(effectiveDate(o)),
    domain: nqDomain(o),
    tscore: fmt(o.valueQuantity?.value),
    se: fmt(componentValue(o, "standard-error"), 2),
    raw: fmt(componentValue(o, "raw-score"), 0),
  })),
);

/* ---- MRT ---- */
const mriAtrophy = computed(() => observationsWithCode("mri-brain-atrophy"));
const mriLesions = computed(() => observationsWithCode("mri-t2-lesions"));
const bpfSeries = computed(() => [
  {
    name: "BPF",
    color: tokenColor("--series-1"),
    points: mriAtrophy.value
      .map((o) => ({ x: effectiveDate(o), y: componentValue(o, "bpf") }))
      .filter((p) => p.y != null),
  },
]);
const lesionSeries = computed(() => [
  {
    name: "T2-Läsionsvolumen",
    color: tokenColor("--series-1"),
    points: mriLesions.value
      .map((o) => ({ x: effectiveDate(o), y: componentValue(o, "t2-lesion-volume") }))
      .filter((p) => p.y != null),
  },
]);
const mriRows = computed(() =>
  mriAtrophy.value.map((atrophy) => {
    const date = effectiveDate(atrophy);
    const lesion = mriLesions.value.find(
      (o) => effectiveDate(o)?.getTime() === date?.getTime(),
    );
    return {
      date: displayDate(date),
      bpf: fmt(componentValue(atrophy, "bpf"), 3),
      bpfChange: fmt(componentValue(atrophy, "bpf-change"), 3),
      lesionVol: fmt(lesion ? componentValue(lesion, "t2-lesion-volume") : null, 2),
      newLesions: fmt(lesion ? componentValue(lesion, "new-t2-lesion-count") : null, 0),
    };
  }),
);
</script>

<template>
  <button class="back-link" @click="$emit('back')">← Zurück zur Kohorte</button>

  <div class="card" v-if="patient">
    <h3>
      Patient:in <code>{{ patient.id }}</code>
      <span class="synthetic-badge" style="margin-left: 8px">synthetisch</span>
    </h3>
    <p style="margin: 4px 0; color: var(--text-secondary)">
      {{ GENDERS[patient.gender] ?? patient.gender ?? "—" }} · geboren
      {{ displayDate(patient.birthDate) }} · {{ encounterCount }} Assessments
    </p>
    <div class="chips" v-if="conditions.length">
      <span v-for="c in conditions" :key="c" class="chip">{{ c }}</span>
    </div>
  </div>

  <div class="grid-2">
    <div v-if="lcla.length" class="chart-card">
      <div class="chart-title">LCLA — Kontrastsehschärfe</div>
      <div class="chart-sub">Gesamtzahl korrekt gelesener Buchstaben</div>
      <LineChart :series="lclaSeries" unit="richtig" :y-decimals="0" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'status', label: 'Status' },
          { key: 'total', label: 'Gesamt' },
          { key: 'pct100', label: '100 %' },
          { key: 'pct25', label: '2,5 %' },
          { key: 'duration', label: 'Dauer (s)' },
        ]"
        :rows="lclaRows"
      />
    </div>

    <div v-if="nineHpt.length" class="chart-card">
      <div class="chart-title">9HPT — Handfeinmotorik</div>
      <div class="chart-sub">Zeit pro Durchgang in Sekunden</div>
      <LineChart :series="nineHptSeries" unit="s" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'left', label: 'Links (s)' },
          { key: 'right', label: 'Rechts (s)' },
          { key: 'zDom', label: 'Z dominant' },
          { key: 'zNonDom', label: 'Z nicht-dom.' },
        ]"
        :rows="nineHptRows"
      />
    </div>

    <div v-if="sdmt.length" class="chart-card">
      <div class="chart-title">SDMT — Verarbeitungsgeschwindigkeit</div>
      <div class="chart-sub">Korrekte Zuordnungen in 90 s</div>
      <LineChart :series="sdmtSeries" unit="richtig" :y-decimals="0" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'correct', label: 'Korrekt' },
          { key: 'incorrect', label: 'Inkorrekt' },
          { key: 'z', label: 'Z-Score' },
        ]"
        :rows="sdmtRows"
      />
    </div>

    <div v-if="t25fw.length" class="chart-card">
      <div class="chart-title">T25FW — Gehgeschwindigkeit</div>
      <div class="chart-sub">Zeit für 25 Fuß (7,62 m) in Sekunden</div>
      <LineChart :series="t25fwSeries" unit="s" :y-decimals="2" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'time', label: 'Zeit (s)' },
          { key: 'z', label: 'Z-Score' },
          { key: 'aid', label: 'Gehhilfe' },
        ]"
        :rows="t25fwRows"
      />
    </div>

    <div v-if="nqItems.length" class="chart-card">
      <div class="chart-title">Neuro-QoL — T-Scores</div>
      <div class="chart-sub">Aktuellste T-Scores je Domäne (Ø 50, SD 10)</div>
      <BarChart :items="nqItems" unit="T" :decimals="1" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'domain', label: 'Domäne' },
          { key: 'tscore', label: 'T-Score' },
          { key: 'se', label: 'SE' },
          { key: 'raw', label: 'Rohwert' },
        ]"
        :rows="nqRows"
      />
    </div>

    <div v-if="mriAtrophy.length || mriLesions.length" class="chart-card">
      <div class="chart-title">MRT — Volumetrie</div>
      <div class="chart-sub">Brain Parenchymal Fraction (BPF)</div>
      <LineChart :series="bpfSeries" :y-decimals="3" :height="150" />
      <div class="chart-sub" style="margin-top: 10px">T2-Läsionsvolumen (mL)</div>
      <LineChart :series="lesionSeries" unit="mL" :y-decimals="2" :height="150" />
      <DataTable
        :columns="[
          { key: 'date', label: 'Datum' },
          { key: 'bpf', label: 'BPF' },
          { key: 'bpfChange', label: 'Δ BPF' },
          { key: 'lesionVol', label: 'T2-Vol. (mL)' },
          { key: 'newLesions', label: 'Neue Läsionen' },
        ]"
        :rows="mriRows"
      />
    </div>
  </div>
</template>
