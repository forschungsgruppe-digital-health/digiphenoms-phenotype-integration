<script setup>
import { computed, ref } from "vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  mlStore,
  jobsOfType,
  startTraining,
  startSynthesis,
  startEvaluation,
} from "../services/mlMock.js";

const TYPE_LABELS = {
  training: "Training",
  synthesis: "Synthese",
  evaluation: "Evaluation",
};

const trainingJobs = computed(() => jobsOfType("training", "completed"));
const synthesisJobs = computed(() => jobsOfType("synthesis", "completed"));

const selectedTraining = ref(trainingJobs.value[0]?.job_id ?? "");
const selectedSynthesis = ref(synthesisJobs.value[0]?.job_id ?? "");
const scaleFactor = ref(1.0);
const actionError = ref(null);

function run(action) {
  actionError.value = null;
  try {
    action();
  } catch (err) {
    actionError.value = err.message;
  }
}

const shortId = (id) => `${id.slice(0, 8)}…`;

const fmtDateTime = (iso) =>
  new Date(iso).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
</script>

<template>
  <div class="banner">
    <strong>ML-Server gemockt.</strong> Der echte ML-Server ist nur über ein
    SSH-Port-Forwarding erreichbar und wird in diesem Demonstrator durch
    Dummy-Antworten simuliert (Job-Lebenszyklus wartend → läuft →
    abgeschlossen). Schnittstelle und Job-IDs entsprechen
    <code>docs/ml_server_api.md</code>.
  </div>

  <div class="ml-actions">
    <div class="card">
      <h3>Training</h3>
      <p class="chart-sub">Modell auf den (synthetischen) Quelldaten trainieren.</p>
      <button class="primary" @click="run(() => startTraining())">
        Trainings-Job starten
      </button>
    </div>

    <div class="card">
      <h3>Synthese</h3>
      <label class="field">
        Trainings-Job
        <select v-model="selectedTraining">
          <option v-for="job in trainingJobs" :key="job.job_id" :value="job.job_id">
            {{ shortId(job.job_id) }}
          </option>
        </select>
      </label>
      <label class="field">
        Scale-Faktor
        <input v-model.number="scaleFactor" type="number" min="0.1" step="0.1" />
      </label>
      <button
        class="primary"
        :disabled="!selectedTraining"
        @click="run(() => startSynthesis(selectedTraining, scaleFactor))"
      >
        Synthese-Job starten
      </button>
    </div>

    <div class="card">
      <h3>Evaluation</h3>
      <label class="field">
        Synthese-Job
        <select v-model="selectedSynthesis">
          <option v-for="job in synthesisJobs" :key="job.job_id" :value="job.job_id">
            {{ shortId(job.job_id) }}
          </option>
        </select>
      </label>
      <button
        class="primary"
        :disabled="!selectedSynthesis"
        @click="run(() => startEvaluation(selectedSynthesis))"
      >
        Evaluations-Job starten
      </button>
    </div>
  </div>

  <div v-if="actionError" class="error-box">{{ actionError }}</div>

  <h2>Jobs</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Job-ID</th>
          <th>Typ</th>
          <th>Status</th>
          <th>Erstellt</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="job in mlStore.jobs" :key="job.job_id">
          <td class="mono" :title="job.job_id">{{ shortId(job.job_id) }}</td>
          <td>{{ TYPE_LABELS[job.job_type] ?? job.job_type }}</td>
          <td><StatusBadge :status="job.status" /></td>
          <td>{{ fmtDateTime(job.created_at) }}</td>
          <td>
            <details class="job-json">
              <summary>JSON</summary>
              <pre>{{ JSON.stringify(job, null, 2) }}</pre>
            </details>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
