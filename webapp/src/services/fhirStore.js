/**
 * Unified FHIR data access for the demonstrator.
 *
 * Two sources behind one interface:
 *  - "demo": the bundled synthetic collection Bundle (generated from the
 *    pipeline's synthetic test fixtures — never real patient data).
 *  - "live": a HAPI FHIR server REST endpoint (e.g. the docker-compose
 *    stack). The demonstrator must only ever be pointed at servers that
 *    hold synthetic data.
 */

import { reactive } from "vue";

export const RESOURCE_TYPES = [
  "Patient",
  "Condition",
  "Encounter",
  "Device",
  "Observation",
  "DiagnosticReport",
  "QuestionnaireResponse",
];

const MAX_PER_TYPE = 500; // demonstrator cap per resource type

export const store = reactive({
  mode: "demo", // "demo" | "live"
  baseUrl: "http://localhost:8080/fhir",
  loading: false,
  error: null,
  loadedFrom: null, // human-readable source description after load
  resources: Object.fromEntries(RESOURCE_TYPES.map((t) => [t, []])),
});

function resetResources() {
  for (const t of RESOURCE_TYPES) store.resources[t] = [];
}

/** Load the bundled synthetic demo dataset. */
export async function loadDemo() {
  store.loading = true;
  store.error = null;
  try {
    const url = `${import.meta.env.BASE_URL}demo-data/demo-bundle.json`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const bundle = await response.json();
    resetResources();
    for (const entry of bundle.entry ?? []) {
      const resource = entry.resource;
      if (resource && store.resources[resource.resourceType]) {
        store.resources[resource.resourceType].push(resource);
      }
    }
    store.mode = "demo";
    store.loadedFrom = "Synthetische Demo-Daten (gebündelt)";
  } catch (err) {
    store.error = `Demo-Daten konnten nicht geladen werden: ${err.message}`;
  } finally {
    store.loading = false;
  }
}

/** Page through a HAPI search across `link[relation=next]`. */
async function fetchAll(baseUrl, resourceType) {
  const collected = [];
  let url = `${baseUrl.replace(/\/+$/, "")}/${resourceType}?_count=100`;
  while (url && collected.length < MAX_PER_TYPE) {
    const response = await fetch(url, {
      headers: { Accept: "application/fhir+json" },
    });
    if (!response.ok) {
      throw new Error(`${resourceType}: HTTP ${response.status}`);
    }
    const bundle = await response.json();
    for (const entry of bundle.entry ?? []) {
      if (entry.resource?.resourceType === resourceType) {
        collected.push(entry.resource);
      }
    }
    url = (bundle.link ?? []).find((l) => l.relation === "next")?.url ?? null;
  }
  return collected;
}

/** Load from a live HAPI FHIR server (synthetic data only!). */
export async function loadLive(baseUrl) {
  store.loading = true;
  store.error = null;
  try {
    // connectivity probe first — clearer error than per-type failures
    const meta = await fetch(`${baseUrl.replace(/\/+$/, "")}/metadata`, {
      headers: { Accept: "application/fhir+json" },
    });
    if (!meta.ok) throw new Error(`metadata: HTTP ${meta.status}`);

    const results = await Promise.all(
      RESOURCE_TYPES.map((t) => fetchAll(baseUrl, t)),
    );
    resetResources();
    RESOURCE_TYPES.forEach((t, i) => {
      store.resources[t] = results[i];
    });
    store.mode = "live";
    store.baseUrl = baseUrl;
    store.loadedFrom = `HAPI FHIR Server — ${baseUrl}`;
  } catch (err) {
    store.error =
      `Verbindung zu ${baseUrl} fehlgeschlagen: ${err.message}. ` +
      "Läuft der Server (docker compose up fhir-server) und ist CORS aktiv?";
  } finally {
    store.loading = false;
  }
}

/* ------------------------------------------------------------------ */
/* Selectors                                                           */
/* ------------------------------------------------------------------ */

const CODE_SYSTEM = "https://digiphenoms.tu-dresden.de/fhir/CodeSystem/digiphenoms";

/** Instruments keyed by their primary Observation code. */
export const INSTRUMENTS = {
  "lcla-test": {
    key: "lcla",
    title: "LCLA — Kontrastsehschärfe",
    valueLabel: "Gesamt korrekt",
    unit: "richtig",
  },
  "83141-2": {
    key: "9hpt",
    title: "9HPT — Handfeinmotorik",
    valueLabel: "Zeit",
    unit: "s",
  },
  "sdmt-test": {
    key: "sdmt",
    title: "SDMT — Verarbeitungsgeschwindigkeit",
    valueLabel: "Gesamt korrekt",
    unit: "richtig",
  },
  "t25fw-test": {
    key: "t25fw",
    title: "T25FW — Gehgeschwindigkeit",
    valueLabel: "Zeit",
    unit: "s",
  },
  "neuro-qol-tscore": {
    key: "nq",
    title: "Neuro-QoL — T-Scores",
    valueLabel: "T-Score",
    unit: "T",
  },
};

export function codeOf(resource) {
  return (resource?.code?.coding ?? [])
    .map((c) => c.code)
    .filter(Boolean);
}

export function primaryInstrument(observation) {
  for (const code of codeOf(observation)) {
    if (INSTRUMENTS[code]) return INSTRUMENTS[code];
  }
  return null;
}

export function patientRef(resource) {
  return resource?.subject?.reference ?? null;
}

export function patientIdOf(resource) {
  const ref = patientRef(resource);
  return ref?.startsWith("Patient/") ? ref.slice("Patient/".length) : null;
}

export function patients() {
  return store.resources.Patient;
}

export function observationsFor(patientId) {
  return store.resources.Observation.filter(
    (o) => patientIdOf(o) === patientId,
  );
}

export function conditionsFor(patientId) {
  return store.resources.Condition.filter((c) => patientIdOf(c) === patientId);
}

export function encountersFor(patientId) {
  return store.resources.Encounter.filter((e) => patientIdOf(e) === patientId);
}

export function reportsFor(patientId) {
  return store.resources.DiagnosticReport.filter(
    (r) => patientIdOf(r) === patientId,
  );
}

export function questionnaireResponsesFor(patientId) {
  return store.resources.QuestionnaireResponse.filter(
    (q) => patientIdOf(q) === patientId,
  );
}

export function componentValue(observation, componentCode) {
  const component = (observation.component ?? []).find((c) =>
    (c.code?.coding ?? []).some((coding) => coding.code === componentCode),
  );
  return component?.valueQuantity?.value ?? component?.valueBoolean ?? null;
}

export function effectiveDate(observation) {
  const raw =
    observation.effectiveDateTime ?? observation.effectivePeriod?.start ?? null;
  return raw ? new Date(raw) : null;
}

export function displayDate(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

/** Neuro-QoL domain (second coding on the score Observation). */
export function nqDomain(observation) {
  const codings = observation.code?.coding ?? [];
  const domain = codings.find((c) => c.code !== "neuro-qol-tscore");
  return domain?.display ?? domain?.code ?? "unbekannt";
}

export function isMriObservation(observation) {
  return codeOf(observation).some((c) => c.startsWith("mri-"));
}

export { CODE_SYSTEM };
