package de.tud.fgdh.digiphenoms.fhir.service;

/**
 * Tracks counts of resources created, updated, and skipped during a
 * {@code $cohort-submit} import run.
 */
public class ImportStatistics {
    private int resourcesCreated;
    private int resourcesUpdated;
    private int resourcesSkipped;
    private int patientsInBatch;
    private int patientsInCohort;

    public void incrementCreated()  { resourcesCreated++; }
    public void incrementUpdated()  { resourcesUpdated++; }
    public void incrementSkipped()  { resourcesSkipped++; }

    public int getResourcesCreated()  { return resourcesCreated; }
    public int getResourcesUpdated()  { return resourcesUpdated; }
    public int getResourcesSkipped()  { return resourcesSkipped; }
    public int getPatientsInBatch()   { return patientsInBatch; }
    public int getPatientsInCohort()  { return patientsInCohort; }

    public void setPatientsInBatch(int n)  { this.patientsInBatch = n; }
    public void setPatientsInCohort(int n) { this.patientsInCohort = n; }
}
