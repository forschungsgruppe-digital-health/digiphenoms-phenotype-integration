<script setup>
import { computed } from "vue";
import StatTile from "../components/StatTile.vue";
import {
  store,
  patients,
  conditionsFor,
  encountersFor,
  observationsFor,
  displayDate,
} from "../services/fhirStore.js";

const emit = defineEmits(["select-patient"]);

const GENDERS = { female: "weiblich", male: "männlich", other: "divers", unknown: "unbekannt" };

const tiles = computed(() => [
  { label: "Patient:innen", value: store.resources.Patient.length },
  { label: "Assessments", value: store.resources.Encounter.length },
  { label: "Messwerte", value: store.resources.Observation.length },
  { label: "MRT-Berichte", value: store.resources.DiagnosticReport.length },
  { label: "Fragebögen", value: store.resources.QuestionnaireResponse.length },
]);

const rows = computed(() =>
  patients().map((patient) => {
    const ms = conditionsFor(patient.id).find((c) =>
      (c.code?.coding ?? []).some((coding) => coding.code === "24700007"),
    );
    return {
      id: patient.id,
      gender: GENDERS[patient.gender] ?? patient.gender ?? "—",
      birthDate: displayDate(patient.birthDate),
      msOnset: ms?.onsetDateTime ? displayDate(ms.onsetDateTime) : "—",
      encounters: encountersFor(patient.id).length,
      observations: observationsFor(patient.id).length,
    };
  }),
);
</script>

<template>
  <div class="tile-row">
    <StatTile v-for="tile in tiles" :key="tile.label" v-bind="tile" />
  </div>

  <h2>Patient:innen (synthetisch)</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Pseudonym</th>
          <th>Geschlecht</th>
          <th>Geburtsdatum</th>
          <th>MS-Diagnose</th>
          <th>Assessments</th>
          <th>Messwerte</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          class="clickable"
          @click="emit('select-patient', row.id)"
        >
          <td class="mono">{{ row.id }}</td>
          <td>{{ row.gender }}</td>
          <td>{{ row.birthDate }}</td>
          <td>{{ row.msOnset }}</td>
          <td>{{ row.encounters }}</td>
          <td>{{ row.observations }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="rows.length === 0" class="empty-note">Keine Patient:innen geladen.</p>
  </div>
</template>
