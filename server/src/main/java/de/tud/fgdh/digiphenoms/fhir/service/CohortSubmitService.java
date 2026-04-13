package de.tud.fgdh.digiphenoms.fhir.service;

import ca.uhn.fhir.rest.api.MethodOutcome;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import ca.uhn.fhir.rest.server.exceptions.InternalErrorException;
import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import ca.uhn.fhir.rest.server.exceptions.UnprocessableEntityException;
import org.hl7.fhir.r4.model.*;
import org.hl7.fhir.r4.model.Bundle.BundleEntryComponent;
import org.hl7.fhir.r4.model.Bundle.BundleEntryResponseComponent;
import org.hl7.fhir.r4.model.Bundle.BundleType;
import org.hl7.fhir.r4.model.Bundle.HTTPVerb;
import org.hl7.fhir.r4.model.Group.GroupCharacteristicComponent;
import org.hl7.fhir.r4.model.Group.GroupMemberComponent;
import org.hl7.fhir.r4.model.Provenance.ProvenanceAgentComponent;
import org.hl7.fhir.r4.model.Provenance.ProvenanceEntityComponent;
import org.hl7.fhir.r4.model.Provenance.ProvenanceEntityRole;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Implements the 9-step processing logic for the {@code $cohort-submit} operation.
 *
 * <p>Steps:
 * <ol>
 *   <li>Input validation</li>
 *   <li>Ensure root group (Wurzelgruppe)</li>
 *   <li>Sort resources by dependency tier</li>
 *   <li>Send transaction bundles per tier</li>
 *   <li>Evaluate per-entry results</li>
 *   <li>Create import group (Importgruppe)</li>
 *   <li>Update root group with new import group</li>
 *   <li>Create Provenance</li>
 *   <li>Assemble response</li>
 * </ol>
 *
 * <p>Depends only on {@link IGenericClient} (DIP) for all FHIR server
 * interactions — the client is injected by Spring.</p>
 */
@Service
public class CohortSubmitService {

    private static final Logger LOG = LoggerFactory.getLogger(CohortSubmitService.class);

    // --- Identifier systems (spec §3, §10) ---
    static final String COHORT_IDENTIFIER_SYSTEM =
            "https://digiphenoms.tu-dresden.de/fhir/cohort";
    static final String IMPORT_BATCH_SYSTEM =
            "https://digiphenoms.tu-dresden.de/fhir/import-batch";
    static final String IMPORT_METADATA_SYSTEM =
            "https://digiphenoms.tu-dresden.de/fhir/CodeSystem/import-metadata";
    static final String IMPORT_MODE_SYSTEM =
            "https://digiphenoms.tu-dresden.de/fhir/CodeSystem/import-mode";

    // --- Dependency tiers (spec §7.1) ---
    /** Tier 1 — no incoming FHIR references, safe to create first. */
    static final Set<String> TIER_1 = Set.of("Patient", "Condition");
    /** Tier 2 — references Patient. */
    static final Set<String> TIER_2 = Set.of("Encounter", "Device");
    /** Tier 3 — references Patient and Encounter. */
    static final Set<String> TIER_3 = Set.of(
            "Observation", "DiagnosticReport", "QuestionnaireResponse");

    private static final String DEFAULT_COHORT_ID = "digiphenoms-ms-cohort";

    private final IGenericClient fhirClient;

    public CohortSubmitService(IGenericClient fhirClient) {
        this.fhirClient = fhirClient;
    }

    // =======================================================================
    // Public API
    // =======================================================================

    /**
     * Execute the full {@code $cohort-submit} workflow.
     *
     * @param inputBundle collection bundle with cohort resources
     * @param mode        "merge" (default) or "distinct"
     * @param cohortId    identifier of the root group
     * @param batchLabel  human-readable label for this import
     * @return FHIR {@link Parameters} response
     */
    public Parameters execute(Bundle inputBundle, String mode,
                              String cohortId, String batchLabel) {

        // Step 1: Input validation
        validateInput(inputBundle, mode);

        String effectiveCohortId = isBlank(cohortId) ? DEFAULT_COHORT_ID : cohortId;
        String effectiveLabel = isBlank(batchLabel)
                ? "Import " + LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE)
                : batchLabel;

        List<Resource> resources = extractResources(inputBundle);

        // Step 2: Ensure root group
        Group rootGroup = ensureRootGroup(effectiveCohortId);

        // Step 3: Sort by dependency tier
        Map<Integer, List<Resource>> tiers = sortByTier(resources);

        // Steps 4+5: Process each tier
        ImportStatistics stats = new ImportStatistics();
        for (int tier = 1; tier <= 3; tier++) {
            List<Resource> tierResources = tiers.getOrDefault(tier, List.of());
            if (!tierResources.isEmpty()) {
                LOG.info("Processing tier {} — {} resources", tier, tierResources.size());
                processTransactionBundle(tierResources, mode, stats);
            }
        }

        // Collect patient references for import group
        List<String> patientRefs = resources.stream()
                .filter(r -> "Patient".equals(r.fhirType()))
                .map(r -> "Patient/" + r.getIdElement().getIdPart())
                .distinct()
                .collect(Collectors.toList());
        stats.setPatientsInBatch(patientRefs.size());

        // Step 6: Create import group
        String importGroupId = createImportGroup(patientRefs, mode, effectiveLabel);

        // Step 7: Update root group
        updateRootGroup(rootGroup, importGroupId);

        // Count total patients in cohort (from all import groups)
        stats.setPatientsInCohort(countCohortPatients(rootGroup));

        // Step 8: Create Provenance
        boolean isInitial = rootGroup.getMember().size() <= 1;
        createProvenance(importGroupId, isInitial, effectiveLabel);

        // Step 9: Assemble response
        return buildResponse(stats, importGroupId);
    }

    // =======================================================================
    // Step 1: Input Validation
    // =======================================================================

    private void validateInput(Bundle inputBundle, String mode) {
        if (inputBundle == null || !inputBundle.hasEntry()) {
            String msg = "DIGIPHENOMS-001: Input bundle is missing or empty.";
            throw new InvalidRequestException(msg, errorOutcome(
                    "DIGIPHENOMS-001", msg,
                    OperationOutcome.IssueSeverity.ERROR,
                    OperationOutcome.IssueType.REQUIRED));
        }

        boolean hasPatient = inputBundle.getEntry().stream()
                .filter(BundleEntryComponent::hasResource)
                .anyMatch(e -> "Patient".equals(e.getResource().fhirType()));
        if (!hasPatient) {
            String msg = "DIGIPHENOMS-002: Input bundle must contain at least one Patient resource.";
            throw new InvalidRequestException(msg, errorOutcome(
                    "DIGIPHENOMS-002", msg,
                    OperationOutcome.IssueSeverity.ERROR,
                    OperationOutcome.IssueType.REQUIRED));
        }

        if (mode != null && !mode.isBlank()
                && !"merge".equals(mode) && !"distinct".equals(mode)) {
            String msg = "DIGIPHENOMS-003: Invalid import mode '" + mode
                    + "'. Must be 'merge' or 'distinct'.";
            throw new InvalidRequestException(msg, errorOutcome(
                    "DIGIPHENOMS-003", msg,
                    OperationOutcome.IssueSeverity.ERROR,
                    OperationOutcome.IssueType.VALUE));
        }
    }

    // =======================================================================
    // Step 2: Ensure Root Group (Wurzelgruppe)
    // =======================================================================

    private Group ensureRootGroup(String cohortId) {
        Bundle searchResult = fhirClient.search()
                .forResource(Group.class)
                .where(Group.IDENTIFIER.exactly()
                        .systemAndIdentifier(COHORT_IDENTIFIER_SYSTEM, cohortId))
                .returnBundle(Bundle.class)
                .execute();

        if (searchResult.hasEntry()) {
            LOG.info("Root group found: {}", cohortId);
            return (Group) searchResult.getEntryFirstRep().getResource();
        }

        LOG.info("Root group not found — creating: {}", cohortId);
        Group rootGroup = new Group();
        rootGroup.addIdentifier(new Identifier()
                .setSystem(COHORT_IDENTIFIER_SYSTEM)
                .setValue(cohortId));
        rootGroup.setType(Group.GroupType.PERSON);
        rootGroup.setActual(true);
        rootGroup.setName("DigiPhenoMS MS-Kohorte");
        rootGroup.setCode(new CodeableConcept(new Coding()
                .setSystem("http://snomed.info/sct")
                .setCode("24700007")
                .setDisplay("Multiple sclerosis")));
        rootGroup.setManagingEntity(new Reference()
                .setReference("Organization/dresden-carus")
                .setDisplay("Universitätsklinikum Carl Gustav Carus Dresden"));

        try {
            MethodOutcome outcome = fhirClient.create().resource(rootGroup).execute();
            rootGroup.setId(outcome.getId().toUnqualifiedVersionless());
            LOG.info("Root group created: {}", rootGroup.getIdElement().getValue());
            return rootGroup;
        } catch (Exception e) {
            String msg = "DIGIPHENOMS-005: Failed to create root group: " + e.getMessage();
            throw new InternalErrorException(msg, errorOutcome(
                    "DIGIPHENOMS-005", msg,
                    OperationOutcome.IssueSeverity.FATAL,
                    OperationOutcome.IssueType.EXCEPTION));
        }
    }

    // =======================================================================
    // Step 3: Sort Resources by Tier
    // =======================================================================

    private List<Resource> extractResources(Bundle inputBundle) {
        return inputBundle.getEntry().stream()
                .filter(BundleEntryComponent::hasResource)
                .map(BundleEntryComponent::getResource)
                .collect(Collectors.toList());
    }

    private Map<Integer, List<Resource>> sortByTier(List<Resource> resources) {
        Map<Integer, List<Resource>> tiers = new HashMap<>();
        for (Resource res : resources) {
            int tier = assignTier(res.fhirType());
            tiers.computeIfAbsent(tier, k -> new ArrayList<>()).add(res);
        }
        return tiers;
    }

    private int assignTier(String resourceType) {
        if (TIER_1.contains(resourceType)) return 1;
        if (TIER_2.contains(resourceType)) return 2;
        if (TIER_3.contains(resourceType)) return 3;
        LOG.warn("Unknown resource type '{}' — assigning to tier 3", resourceType);
        return 3;
    }

    // =======================================================================
    // Steps 4+5: Process Transaction Bundle per Tier
    // =======================================================================

    private void processTransactionBundle(List<Resource> resources, String mode,
                                          ImportStatistics stats) {
        Bundle txBundle = new Bundle();
        txBundle.setType(BundleType.TRANSACTION);

        boolean isMerge = !"distinct".equals(mode);

        for (Resource res : resources) {
            BundleEntryComponent entry = txBundle.addEntry();
            entry.setResource(res);
            entry.setFullUrl("urn:uuid:" + UUID.randomUUID());

            Bundle.BundleEntryRequestComponent request = entry.getRequest();
            String identifierQuery = buildIdentifierQuery(res);

            if (isMerge) {
                request.setMethod(HTTPVerb.PUT);
                request.setUrl(identifierQuery != null
                        ? res.fhirType() + "?" + identifierQuery
                        : res.fhirType() + "/" + res.getIdElement().getIdPart());
            } else {
                request.setMethod(HTTPVerb.POST);
                request.setUrl(res.fhirType());
                if (identifierQuery != null) {
                    request.setIfNoneExist(identifierQuery);
                }
            }
        }

        try {
            Bundle responseBundle = fhirClient.transaction().withBundle(txBundle).execute();
            evaluateResponse(responseBundle, isMerge, stats);
        } catch (Exception e) {
            LOG.error("Transaction bundle failed: {}", e.getMessage());
            String msg = "DIGIPHENOMS-004: Transaction bundle failed: " + e.getMessage();
            throw new UnprocessableEntityException(msg, errorOutcome(
                    "DIGIPHENOMS-004", msg,
                    OperationOutcome.IssueSeverity.ERROR,
                    OperationOutcome.IssueType.PROCESSING));
        }
    }

    // ---- Identifier extraction (SRP: separated from query building) ----

    /**
     * Build an identifier-based conditional URL query for a resource.
     *
     * @return query string like {@code "identifier=system|value"}, or
     *         {@code null} if the resource has no usable identifier.
     */
    private String buildIdentifierQuery(Resource res) {
        Identifier id = extractFirstIdentifier(res);
        if (id != null && id.hasSystem() && id.hasValue()) {
            return "identifier=" + id.getSystem() + "|" + id.getValue();
        }
        return null;
    }

    /**
     * Extract the first identifier from a resource, regardless of type.
     *
     * <p>Handles the HAPI R4 model difference where most resources expose
     * {@code getIdentifierFirstRep()} (list-based) while
     * {@link QuestionnaireResponse} exposes {@code getIdentifier()} (singular).</p>
     */
    private Identifier extractFirstIdentifier(Resource res) {
        if (res instanceof Patient r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof Condition r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof Encounter r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof Device r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof Observation r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof DiagnosticReport r && r.hasIdentifier()) return r.getIdentifierFirstRep();
        if (res instanceof QuestionnaireResponse r && r.hasIdentifier()) return r.getIdentifier();
        return null;
    }

    // ---- Response evaluation ----

    private void evaluateResponse(Bundle responseBundle, boolean isMerge,
                                  ImportStatistics stats) {
        if (responseBundle == null || !responseBundle.hasEntry()) return;

        for (BundleEntryComponent entry : responseBundle.getEntry()) {
            BundleEntryResponseComponent resp = entry.getResponse();
            if (resp == null || resp.getStatus() == null) continue;

            String status = resp.getStatus();
            if (status.startsWith("201")) {
                stats.incrementCreated();
            } else if (status.startsWith("200")) {
                if (isMerge) {
                    stats.incrementUpdated();
                } else {
                    stats.incrementSkipped();
                }
            }
        }
    }

    // =======================================================================
    // Step 6: Create Import Group (Importgruppe)
    // =======================================================================

    private String createImportGroup(List<String> patientRefs, String mode,
                                     String batchLabel) {
        String today = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE);
        String importId = "import-" + today + "-"
                + String.format("%03d", nextImportSeq(today));

        Group importGroup = new Group();
        importGroup.addIdentifier(new Identifier()
                .setSystem(IMPORT_BATCH_SYSTEM)
                .setValue(importId));
        importGroup.setType(Group.GroupType.PERSON);
        importGroup.setActual(true);
        importGroup.setName(batchLabel);

        // Characteristic: import mode
        GroupCharacteristicComponent modeChar = importGroup.addCharacteristic();
        modeChar.setCode(new CodeableConcept(new Coding()
                .setSystem(IMPORT_METADATA_SYSTEM).setCode("import-mode")));
        modeChar.setValue(new CodeableConcept(new Coding()
                .setSystem(IMPORT_MODE_SYSTEM)
                .setCode(mode != null ? mode : "merge")));
        modeChar.setExclude(false);

        // Characteristic: pipeline version
        GroupCharacteristicComponent versionChar = importGroup.addCharacteristic();
        versionChar.setCode(new CodeableConcept(new Coding()
                .setSystem(IMPORT_METADATA_SYSTEM).setCode("pipeline-version")));
        versionChar.setValue(new CodeableConcept().setText("1.0.0"));
        versionChar.setExclude(false);

        // Members: patient references
        Date now = new Date();
        for (String ref : patientRefs) {
            GroupMemberComponent member = importGroup.addMember();
            member.setEntity(new Reference(ref));
            member.setPeriod(new Period().setStart(now));
        }

        try {
            MethodOutcome outcome = fhirClient.create()
                    .resource(importGroup).execute();
            String createdId = outcome.getId().toUnqualifiedVersionless().getValue();
            LOG.info("Import group created: {}", createdId);
            return createdId;
        } catch (Exception e) {
            String msg = "DIGIPHENOMS-006: Failed to create import group: " + e.getMessage();
            throw new InternalErrorException(msg, errorOutcome(
                    "DIGIPHENOMS-006", msg,
                    OperationOutcome.IssueSeverity.FATAL,
                    OperationOutcome.IssueType.EXCEPTION));
        }
    }

    private int nextImportSeq(String todayStr) {
        try {
            Bundle existing = fhirClient.search()
                    .forResource(Group.class)
                    .where(Group.IDENTIFIER.exactly()
                            .systemAndIdentifier(IMPORT_BATCH_SYSTEM,
                                    "import-" + todayStr))
                    .returnBundle(Bundle.class)
                    .count(0)
                    .execute();
            return existing.getTotal() + 1;
        } catch (Exception e) {
            LOG.warn("Could not determine import sequence — defaulting to 1: {}",
                    e.getMessage());
            return 1;
        }
    }

    // =======================================================================
    // Step 7: Update Root Group
    // =======================================================================

    private void updateRootGroup(Group rootGroup, String importGroupId) {
        GroupMemberComponent member = rootGroup.addMember();
        member.setEntity(new Reference(importGroupId));
        member.setPeriod(new Period().setStart(new Date()));

        fhirClient.update().resource(rootGroup).execute();
        LOG.info("Root group updated with import group: {}", importGroupId);
    }

    // =======================================================================
    // Step 8: Create Provenance
    // =======================================================================

    private void createProvenance(String importGroupId, boolean isInitial,
                                  String label) {
        Provenance provenance = new Provenance();
        provenance.addTarget(new Reference(importGroupId));
        provenance.setRecorded(new Date());

        String activityCode = isInitial ? "CREATE" : "UPDATE";
        provenance.setActivity(new CodeableConcept(new Coding()
                .setSystem("http://terminology.hl7.org/CodeSystem/v3-DataOperation")
                .setCode(activityCode)
                .setDisplay(activityCode.toLowerCase())));

        ProvenanceAgentComponent agent = provenance.addAgent();
        agent.setType(new CodeableConcept(new Coding()
                .setSystem("http://terminology.hl7.org/CodeSystem/provenance-participant-type")
                .setCode("assembler")
                .setDisplay("Assembler")));
        agent.setWho(new Reference().setDisplay("DigiPhenoMS FHIR Mapper v1.0.0"));

        ProvenanceEntityComponent entity = provenance.addEntity();
        entity.setRole(ProvenanceEntityRole.SOURCE);
        entity.setWhat(new Reference().setDisplay(label));

        fhirClient.create().resource(provenance).execute();
        LOG.info("Provenance created for import group: {}", importGroupId);
    }

    // =======================================================================
    // Cohort Patient Counting
    // =======================================================================

    /**
     * Count distinct patients across all import groups in the cohort.
     */
    private int countCohortPatients(Group rootGroup) {
        Set<String> uniquePatientRefs = new HashSet<>();
        for (GroupMemberComponent member : rootGroup.getMember()) {
            String importGroupRef = member.getEntity().getReference();
            if (importGroupRef == null) continue;
            try {
                Group importGroup = fhirClient.read()
                        .resource(Group.class)
                        .withId(importGroupRef.replace("Group/", ""))
                        .execute();
                for (GroupMemberComponent patMember : importGroup.getMember()) {
                    String patRef = patMember.getEntity().getReference();
                    if (patRef != null && patRef.startsWith("Patient/")) {
                        uniquePatientRefs.add(patRef);
                    }
                }
            } catch (Exception e) {
                LOG.warn("Could not read import group {}: {}",
                        importGroupRef, e.getMessage());
            }
        }
        return uniquePatientRefs.size();
    }

    // =======================================================================
    // Step 9: Build Response
    // =======================================================================

    private Parameters buildResponse(ImportStatistics stats, String importGroupId) {
        Parameters response = new Parameters();

        // Outcome
        OperationOutcome outcome = new OperationOutcome();
        outcome.addIssue()
                .setSeverity(OperationOutcome.IssueSeverity.INFORMATION)
                .setCode(OperationOutcome.IssueType.INFORMATIONAL)
                .setDiagnostics(String.format(
                        "Import completed successfully. Created: %d, Updated: %d, Skipped: %d.",
                        stats.getResourcesCreated(),
                        stats.getResourcesUpdated(),
                        stats.getResourcesSkipped()));
        response.addParameter().setName("outcome").setResource(outcome);

        // Import group reference
        response.addParameter()
                .setName("importGroup")
                .setValue(new Reference(importGroupId));

        // Statistics (5 parts per spec §5.1)
        Parameters.ParametersParameterComponent statsParam = response.addParameter();
        statsParam.setName("statistics");
        statsParam.addPart().setName("resourcesCreated")
                .setValue(new IntegerType(stats.getResourcesCreated()));
        statsParam.addPart().setName("resourcesUpdated")
                .setValue(new IntegerType(stats.getResourcesUpdated()));
        statsParam.addPart().setName("resourcesSkipped")
                .setValue(new IntegerType(stats.getResourcesSkipped()));
        statsParam.addPart().setName("patientsInBatch")
                .setValue(new IntegerType(stats.getPatientsInBatch()));
        statsParam.addPart().setName("patientsInCohort")
                .setValue(new IntegerType(stats.getPatientsInCohort()));

        return response;
    }

    // =======================================================================
    // Utilities
    // =======================================================================

    /** Build an OperationOutcome with a machine-readable error code. */
    static OperationOutcome errorOutcome(String code, String diagnostics,
                                          OperationOutcome.IssueSeverity severity,
                                          OperationOutcome.IssueType type) {
        OperationOutcome oo = new OperationOutcome();
        oo.addIssue()
                .setSeverity(severity)
                .setCode(type)
                .setDiagnostics(diagnostics)
                .setDetails(new CodeableConcept().setText(code));
        return oo;
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
    }
}
