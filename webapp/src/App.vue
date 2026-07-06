<script setup>
import { onMounted, ref } from "vue";
import CohortView from "./views/CohortView.vue";
import PatientView from "./views/PatientView.vue";
import MlJobsView from "./views/MlJobsView.vue";
import { store, loadDemo, loadLive } from "./services/fhirStore.js";

const tab = ref("cohort"); // "cohort" | "ml"
const selectedPatientId = ref(null);
const sourceChoice = ref("demo"); // radio state
const liveUrl = ref(store.baseUrl);

// deep links for sharing: ?tab=ml | ?patient=<id> | ?fhir=<base-url>
onMounted(async () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("tab") === "ml") tab.value = "ml";
  const fhir = params.get("fhir");
  if (fhir) {
    sourceChoice.value = "live";
    liveUrl.value = fhir;
    await loadLive(fhir);
  } else {
    await loadDemo();
  }
  const patient = params.get("patient");
  if (patient) selectedPatientId.value = patient;
});

async function applySource() {
  selectedPatientId.value = null;
  if (sourceChoice.value === "demo") {
    await loadDemo();
  } else {
    await loadLive(liveUrl.value);
  }
}
</script>

<template>
  <header class="app-header">
    <h1>DigiPhenoMS Demonstrator</h1>
    <span class="synthetic-badge">🧪 ausschließlich synthetische Daten</span>
  </header>

  <div class="banner">
    Demonstrator für das DigiPhenoMS-Projekt. Es werden ausschließlich
    <strong>synthetische Daten</strong> angezeigt — es dürfen keine echten
    Patientendaten verwendet werden. Der ML-Server ist gemockt.
  </div>

  <div class="source-row">
    <strong>Datenquelle:</strong>
    <label>
      <input v-model="sourceChoice" type="radio" value="demo" @change="applySource" />
      Demo-Daten (gebündelt)
    </label>
    <label>
      <input v-model="sourceChoice" type="radio" value="live" />
      HAPI FHIR Server
    </label>
    <template v-if="sourceChoice === 'live'">
      <input
        v-model="liveUrl"
        type="url"
        placeholder="http://localhost:8080/fhir"
        @keydown.enter="applySource"
      />
      <button class="primary" :disabled="store.loading" @click="applySource">
        Verbinden
      </button>
    </template>
    <span class="conn-state">
      <template v-if="store.loading">Lade…</template>
      <template v-else-if="store.loadedFrom">✓ {{ store.loadedFrom }}</template>
    </span>
  </div>

  <div v-if="store.error" class="error-box">{{ store.error }}</div>

  <nav class="tabs">
    <button :class="{ active: tab === 'cohort' }" @click="tab = 'cohort'">
      Kohorte
    </button>
    <button :class="{ active: tab === 'ml' }" @click="tab = 'ml'">
      ML-Server (Mock)
    </button>
  </nav>

  <main>
    <template v-if="tab === 'cohort'">
      <PatientView
        v-if="selectedPatientId"
        :patient-id="selectedPatientId"
        @back="selectedPatientId = null"
      />
      <CohortView v-else @select-patient="selectedPatientId = $event" />
    </template>
    <MlJobsView v-else />
  </main>

  <footer class="app-footer">
    DigiPhenoMS — Digitale Phänotypisierung für das intelligente Management der
    Multiplen Sklerose · Demonstrator mit synthetischen Daten · FHIR R4 ·
    <a
      href="https://github.com/forschungsgruppe-digital-health/digiphenoms-phenotype-integration"
      target="_blank"
      rel="noreferrer"
      >Repository</a
    >
  </footer>
</template>
