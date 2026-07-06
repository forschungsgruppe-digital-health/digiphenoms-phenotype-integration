/**
 * Mocked ML server.
 *
 * The real ML server sits behind a restrictive proxy and an SSH tunnel and
 * is therefore NOT reachable from this demonstrator. This module simulates
 * the documented job API (POST /jobs, GET /jobs/{id}) with dummy data:
 * jobs move queued → running → completed on timers, and the three job IDs
 * documented in docs/ml_server_api.md are pre-seeded.
 *
 * Response shapes mirror the documented API (job_id, job_type, status, …)
 * so the UI would work unchanged against the real server.
 */

import { reactive } from "vue";

export const DOCUMENTED_JOBS = {
  training: "ee81f8cd-70d4-4db3-b2e1-02eb54b99a21",
  synthesis: "f148e40c-ec8b-4f99-8de4-8177ac4bc8c8",
  evaluation: "58e3fc43-e385-4c09-8bfd-103a177bdaae",
};

const SYNTH_TABLES = ["Patienten", "MRT", "LCLAT", "WST"];

function nowIso() {
  return new Date().toISOString();
}

function uuid() {
  return crypto.randomUUID();
}

export const mlStore = reactive({
  jobs: [
    {
      job_id: DOCUMENTED_JOBS.training,
      job_type: "training",
      status: "completed",
      created_at: "2026-05-11T09:14:02Z",
      finished_at: "2026-05-11T11:47:55Z",
      artifact: { type: "model", downloadable: false },
      note: "Vordokumentierter Job (siehe docs/ml_server_api.md)",
    },
    {
      job_id: DOCUMENTED_JOBS.synthesis,
      job_type: "synthesis",
      status: "completed",
      created_at: "2026-05-12T08:03:41Z",
      finished_at: "2026-05-12T08:26:12Z",
      training_job_id: DOCUMENTED_JOBS.training,
      scale_factor: 1.0,
      artifact: { type: "dataset", tables: SYNTH_TABLES, rows: 1284 },
      note: "Vordokumentierter Job (siehe docs/ml_server_api.md)",
    },
    {
      job_id: DOCUMENTED_JOBS.evaluation,
      job_type: "evaluation",
      status: "completed",
      created_at: "2026-05-12T09:00:07Z",
      finished_at: "2026-05-12T09:41:30Z",
      synthesis_job_id: DOCUMENTED_JOBS.synthesis,
      artifact: {
        type: "report",
        metrics: { fidelity: 0.87, utility: 0.81, privacy: 0.93 },
      },
      note: "Vordokumentierter Job (siehe docs/ml_server_api.md)",
    },
  ],
});

function schedule(job, queuedMs, runningMs, onComplete) {
  setTimeout(() => {
    job.status = "running";
    setTimeout(() => {
      job.status = "completed";
      job.finished_at = nowIso();
      onComplete?.(job);
    }, runningMs);
  }, queuedMs);
}

export function getJob(jobId) {
  return mlStore.jobs.find((j) => j.job_id === jobId) ?? null;
}

export function jobsOfType(jobType, status = null) {
  return mlStore.jobs.filter(
    (j) => j.job_type === jobType && (status === null || j.status === status),
  );
}

export function startTraining() {
  const job = reactive({
    job_id: uuid(),
    job_type: "training",
    status: "queued",
    created_at: nowIso(),
  });
  mlStore.jobs.unshift(job);
  schedule(job, 1500, 6000, (j) => {
    j.artifact = { type: "model", downloadable: false };
  });
  return job;
}

export function startSynthesis(trainingJobId, scaleFactor = 1.0) {
  const training = getJob(trainingJobId);
  if (!training || training.job_type !== "training") {
    throw new Error("training_job_id unbekannt");
  }
  if (training.status !== "completed") {
    throw new Error("Trainings-Job ist noch nicht abgeschlossen");
  }
  const job = reactive({
    job_id: uuid(),
    job_type: "synthesis",
    status: "queued",
    created_at: nowIso(),
    training_job_id: trainingJobId,
    scale_factor: scaleFactor,
  });
  mlStore.jobs.unshift(job);
  schedule(job, 1500, 4500, (j) => {
    j.artifact = {
      type: "dataset",
      tables: SYNTH_TABLES,
      rows: Math.round(1284 * scaleFactor),
    };
  });
  return job;
}

export function startEvaluation(synthesisJobId) {
  const synthesis = getJob(synthesisJobId);
  if (!synthesis || synthesis.job_type !== "synthesis") {
    throw new Error("synthesis_job_id unbekannt");
  }
  if (synthesis.status !== "completed") {
    throw new Error("Synthese-Job ist noch nicht abgeschlossen");
  }
  const job = reactive({
    job_id: uuid(),
    job_type: "evaluation",
    status: "queued",
    created_at: nowIso(),
    synthesis_job_id: synthesisJobId,
  });
  mlStore.jobs.unshift(job);
  schedule(job, 1500, 5000, (j) => {
    j.artifact = {
      type: "report",
      metrics: {
        fidelity: +(0.8 + Math.random() * 0.15).toFixed(2),
        utility: +(0.75 + Math.random() * 0.15).toFixed(2),
        privacy: +(0.88 + Math.random() * 0.1).toFixed(2),
      },
    };
  });
  return job;
}
