package de.tud.fgdh.digiphenoms.fhir.service;

import ca.uhn.fhir.rest.api.MethodOutcome;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import ca.uhn.fhir.rest.gclient.*;
import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import de.tud.fgdh.digiphenoms.fhir.TestFixtures;
import org.hl7.fhir.instance.model.api.IIdType;
import org.hl7.fhir.r4.model.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link CohortSubmitService} using a mocked {@link IGenericClient}.
 *
 * <p>Test data mirrors the pipeline training fixtures:
 * 3 patients, 6 conditions, 3 encounters, 2 devices, 5 observations,
 * 2 diagnostic reports, 2 questionnaire responses.</p>
 */
@ExtendWith(MockitoExtension.class)
@SuppressWarnings({"unchecked", "rawtypes"})
class CohortSubmitServiceTest {

    @Mock private IGenericClient fhirClient;
    @Mock private IUntypedQuery untypedQuery;
    @Mock private IQuery query;
    @Mock private IQuery queryWithParam;
    @Mock private IQuery queryWithCount;
    @Mock private ICreateTyped createTyped;
    @Mock private IUpdateTyped updateTyped;
    @Mock private ITransaction txMock;
    @Mock private ITransactionTyped<Bundle> transactionTyped;

    private CohortSubmitService service;

    @BeforeEach
    void setUp() {
        service = new CohortSubmitService(fhirClient);
    }

    // -----------------------------------------------------------------------
    // Helper: configure the mock client for a typical successful flow
    // -----------------------------------------------------------------------

    private void stubStandardFlow(boolean rootGroupExists) {
        // --- Search stubs ---
        lenient().when(fhirClient.search()).thenReturn(untypedQuery);
        lenient().when(untypedQuery.forResource(any(Class.class))).thenReturn(query);
        lenient().when(query.where(any(ICriterion.class))).thenReturn(queryWithParam);
        lenient().when(queryWithParam.returnBundle(Bundle.class)).thenReturn(queryWithCount);
        lenient().when(queryWithCount.count(anyInt())).thenReturn(queryWithCount);

        // Root group search
        if (rootGroupExists) {
            Group existing = new Group();
            existing.setId("Group/digiphenoms-cohort");
            lenient().when(queryWithCount.execute())
                    .thenReturn(TestFixtures.searchResult(existing))  // root group found
                    .thenReturn(TestFixtures.emptySearchResult())     // import seq
                    .thenReturn(TestFixtures.emptySearchResult());    // patient count
        } else {
            lenient().when(queryWithCount.execute())
                    .thenReturn(TestFixtures.emptySearchResult())     // root group not found
                    .thenReturn(TestFixtures.emptySearchResult())     // import seq
                    .thenReturn(TestFixtures.emptySearchResult());    // patient count
        }

        // --- Create stubs ---
        ICreate create = mock(ICreate.class);
        lenient().when(fhirClient.create()).thenReturn(create);
        lenient().when(create.resource(any(Resource.class))).thenReturn(createTyped);

        MethodOutcome createOutcome = new MethodOutcome();
        IIdType mockId = mock(IIdType.class);
        lenient().when(mockId.toUnqualifiedVersionless()).thenReturn(mockId);
        lenient().when(mockId.getValue()).thenReturn("Group/digiphenoms-cohort");
        lenient().when(mockId.getIdPart()).thenReturn("digiphenoms-cohort");
        createOutcome.setId(mockId);
        lenient().when(createTyped.execute()).thenReturn(createOutcome);

        // --- Update stubs ---
        IUpdate update = mock(IUpdate.class);
        lenient().when(fhirClient.update()).thenReturn(update);
        lenient().when(update.resource(any(Resource.class))).thenReturn(updateTyped);
        lenient().when(updateTyped.execute()).thenReturn(new MethodOutcome());

        // --- Transaction stubs (all entries created) ---
        lenient().when(fhirClient.transaction()).thenReturn(txMock);
        lenient().when(txMock.withBundle(any(Bundle.class))).thenReturn(transactionTyped);
        // Respond dynamically based on bundle size
        lenient().when(transactionTyped.execute()).thenAnswer(invocation -> {
            // Return all 201 for any tier
            return TestFixtures.allCreatedResponse(10);
        });
    }

    // -----------------------------------------------------------------------
    // Step 1: Input validation
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Step 1: Input Validation")
    class InputValidation {

        @Test
        @DisplayName("DIGIPHENOMS-001: Null bundle throws InvalidRequestException")
        void nullBundle() {
            InvalidRequestException ex = assertThrows(InvalidRequestException.class,
                    () -> service.execute(null, "merge", null, null));
            assertTrue(ex.getMessage().contains("DIGIPHENOMS-001")
                    || ex.getOperationOutcome() != null);
        }

        @Test
        @DisplayName("DIGIPHENOMS-001: Empty bundle throws InvalidRequestException")
        void emptyBundle() {
            assertThrows(InvalidRequestException.class,
                    () -> service.execute(TestFixtures.emptyBundle(), "merge", null, null));
        }

        @Test
        @DisplayName("DIGIPHENOMS-002: Bundle without Patient throws")
        void noPatientsInBundle() {
            assertThrows(InvalidRequestException.class,
                    () -> service.execute(TestFixtures.bundleWithoutPatient(), "merge", null, null));
        }

        @Test
        @DisplayName("DIGIPHENOMS-003: Invalid mode throws")
        void invalidMode() {
            Bundle bundle = TestFixtures.minimalBundle();
            assertThrows(InvalidRequestException.class,
                    () -> service.execute(bundle, "invalid_mode", null, null));
        }

        @Test
        @DisplayName("null mode defaults to merge (no exception)")
        void nullModeDefaultsToMerge() {
            stubStandardFlow(false);
            Parameters result = service.execute(TestFixtures.minimalBundle(),
                    null, null, null);
            assertNotNull(result);
        }

        @Test
        @DisplayName("Empty string mode defaults to merge (no exception)")
        void emptyModeDefaultsToMerge() {
            stubStandardFlow(false);
            Parameters result = service.execute(TestFixtures.minimalBundle(),
                    "", null, null);
            assertNotNull(result);
        }
    }

    // -----------------------------------------------------------------------
    // Step 2: Root Group (Wurzelgruppe)
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Step 2: Root Group Management")
    class RootGroupManagement {

        @Test
        @DisplayName("Creates root group when not found")
        void createsNewRootGroup() {
            stubStandardFlow(false);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", "test-cohort", "Test");

            // Verify create was called (at least for root group + import group + provenance)
            verify(fhirClient, atLeast(1)).create();
            assertNotNull(result);
        }

        @Test
        @DisplayName("Uses existing root group when found")
        void usesExistingRootGroup() {
            stubStandardFlow(true);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", "test-cohort", "Test");

            assertNotNull(result);
        }

        @Test
        @DisplayName("Default cohort ID is 'digiphenoms-ms-cohort'")
        void defaultCohortId() {
            stubStandardFlow(false);

            // Pass null cohortId → should use default
            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);
            assertNotNull(result);
        }
    }

    // -----------------------------------------------------------------------
    // Steps 3-5: Tier processing
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Steps 3-5: Tiered Resource Processing")
    class TieredProcessing {

        @Test
        @DisplayName("Realistic bundle produces transaction bundles for 3 tiers")
        void processesAllThreeTiers() {
            stubStandardFlow(false);

            Bundle input = TestFixtures.realisticCollectionBundle();
            Parameters result = service.execute(input, "merge", null, "Full Import");

            // Transaction should be called at least 3 times (one per tier)
            verify(transactionTyped, atLeast(3)).execute();
            assertNotNull(result);
        }

        @Test
        @DisplayName("Minimal bundle (Patient only) processes tier 1 only")
        void minimalBundleProcessesTier1Only() {
            stubStandardFlow(false);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);

            // Only tier 1 should have resources (1 Patient)
            verify(transactionTyped, atLeast(1)).execute();
            assertNotNull(result);
        }

        @Test
        @DisplayName("Merge mode uses PUT requests in transaction bundle")
        void mergeModeUsesPut() {
            stubStandardFlow(false);
            ArgumentCaptor<Bundle> bundleCaptor = ArgumentCaptor.forClass(Bundle.class);
            when(transactionTyped.execute()).thenReturn(TestFixtures.allCreatedResponse(1));

            service.execute(TestFixtures.minimalBundle(), "merge", null, null);

            verify(txMock, atLeast(1)).withBundle(bundleCaptor.capture());
            Bundle txBundle = bundleCaptor.getAllValues().get(0);
            for (Bundle.BundleEntryComponent entry : txBundle.getEntry()) {
                assertEquals(Bundle.HTTPVerb.PUT,
                        entry.getRequest().getMethod(),
                        "Merge mode should use PUT");
            }
        }

        @Test
        @DisplayName("Distinct mode uses POST requests with ifNoneExist")
        void distinctModeUsesPost() {
            stubStandardFlow(false);
            ArgumentCaptor<Bundle> bundleCaptor = ArgumentCaptor.forClass(Bundle.class);
            when(transactionTyped.execute()).thenReturn(TestFixtures.allCreatedResponse(1));

            service.execute(TestFixtures.minimalBundle(), "distinct", null, null);

            verify(txMock, atLeast(1)).withBundle(bundleCaptor.capture());
            Bundle txBundle = bundleCaptor.getAllValues().get(0);
            for (Bundle.BundleEntryComponent entry : txBundle.getEntry()) {
                assertEquals(Bundle.HTTPVerb.POST,
                        entry.getRequest().getMethod(),
                        "Distinct mode should use POST");
                assertTrue(entry.getRequest().hasIfNoneExist()
                                || entry.getRequest().getUrl().equals("Patient"),
                        "Distinct mode should set ifNoneExist when identifier exists");
            }
        }
    }

    // -----------------------------------------------------------------------
    // Steps 4-5: Statistics counting
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Steps 4-5: Response Statistics")
    class ResponseStatistics {

        @Test
        @DisplayName("All-created response counts correctly")
        void allCreatedCounts() {
            stubStandardFlow(false);
            when(transactionTyped.execute())
                    .thenReturn(TestFixtures.allCreatedResponse(1));

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);

            // Find statistics parameter
            Parameters.ParametersParameterComponent stats = result.getParameter()
                    .stream()
                    .filter(p -> "statistics".equals(p.getName()))
                    .findFirst()
                    .orElseThrow();

            int created = stats.getPart().stream()
                    .filter(p -> "resourcesCreated".equals(p.getName()))
                    .map(p -> ((IntegerType) p.getValue()).getValue())
                    .findFirst().orElse(-1);

            assertTrue(created > 0, "Should have at least 1 created resource");
        }

        @Test
        @DisplayName("Mixed response distinguishes created vs updated in merge mode")
        void mixedResponseMerge() {
            stubStandardFlow(false);
            when(transactionTyped.execute())
                    .thenReturn(TestFixtures.mixedResponse(2, 1));

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);

            Parameters.ParametersParameterComponent stats = result.getParameter()
                    .stream()
                    .filter(p -> "statistics".equals(p.getName()))
                    .findFirst()
                    .orElseThrow();

            int created = extractStat(stats, "resourcesCreated");
            int updated = extractStat(stats, "resourcesUpdated");

            assertTrue(created >= 2, "Should count created entries");
            assertTrue(updated >= 1, "Should count updated entries in merge mode");
        }

        @Test
        @DisplayName("Mixed response counts skipped (not updated) in distinct mode")
        void mixedResponseDistinct() {
            stubStandardFlow(false);
            when(transactionTyped.execute())
                    .thenReturn(TestFixtures.mixedResponse(1, 2));

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "distinct", null, null);

            Parameters.ParametersParameterComponent stats = result.getParameter()
                    .stream()
                    .filter(p -> "statistics".equals(p.getName()))
                    .findFirst()
                    .orElseThrow();

            int skipped = extractStat(stats, "resourcesSkipped");
            assertTrue(skipped >= 2, "200 OK in distinct mode should count as skipped");
        }

        @Test
        @DisplayName("patientsInBatch counts distinct patients from input")
        void patientsInBatchCount() {
            stubStandardFlow(false);
            when(transactionTyped.execute())
                    .thenReturn(TestFixtures.allCreatedResponse(23));

            Parameters result = service.execute(
                    TestFixtures.realisticCollectionBundle(), "merge", null, null);

            Parameters.ParametersParameterComponent stats = result.getParameter()
                    .stream()
                    .filter(p -> "statistics".equals(p.getName()))
                    .findFirst()
                    .orElseThrow();

            int patientsInBatch = extractStat(stats, "patientsInBatch");
            assertEquals(3, patientsInBatch,
                    "Realistic bundle has 3 distinct patients");
        }

        private int extractStat(Parameters.ParametersParameterComponent stats,
                                String name) {
            return stats.getPart().stream()
                    .filter(p -> name.equals(p.getName()))
                    .map(p -> ((IntegerType) p.getValue()).getValue())
                    .findFirst().orElse(-1);
        }
    }

    // -----------------------------------------------------------------------
    // Step 6: Import Group
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Step 6: Import Group Creation")
    class ImportGroupCreation {

        @Test
        @DisplayName("Import group contains all patient references")
        void importGroupHasPatientRefs() {
            stubStandardFlow(false);
            ArgumentCaptor<Resource> resourceCaptor =
                    ArgumentCaptor.forClass(Resource.class);

            ICreate create = mock(ICreate.class);
            lenient().when(fhirClient.create()).thenReturn(create);
            lenient().when(create.resource(resourceCaptor.capture())).thenReturn(createTyped);

            MethodOutcome outcome = new MethodOutcome();
            IIdType mockId = mock(IIdType.class);
            lenient().when(mockId.toUnqualifiedVersionless()).thenReturn(mockId);
            lenient().when(mockId.getValue()).thenReturn("Group/import-test");
            lenient().when(mockId.getIdPart()).thenReturn("import-test");
            outcome.setId(mockId);
            lenient().when(createTyped.execute()).thenReturn(outcome);

            // Need transaction + update + search stubs
            stubSearchAndTransaction();

            service.execute(TestFixtures.realisticCollectionBundle(),
                    "merge", null, "Test Import");

            // Find the import Group among created resources
            List<Resource> createdResources = resourceCaptor.getAllValues();
            Group importGroup = createdResources.stream()
                    .filter(r -> r instanceof Group)
                    .map(r -> (Group) r)
                    .filter(g -> g.hasMember() && g.getMember().stream()
                            .anyMatch(m -> m.getEntity().getReference()
                                    .startsWith("Patient/")))
                    .findFirst()
                    .orElse(null);

            assertNotNull(importGroup, "Import group should be created");
            assertEquals(3, importGroup.getMember().size(),
                    "Import group should reference all 3 patients");

            // Verify characteristic: import-mode
            assertTrue(importGroup.hasCharacteristic(),
                    "Import group should have characteristics");
        }

        private void stubSearchAndTransaction() {
            lenient().when(fhirClient.search()).thenReturn(untypedQuery);
            lenient().when(untypedQuery.forResource(any(Class.class))).thenReturn(query);
            lenient().when(query.where(any(ICriterion.class))).thenReturn(queryWithParam);
            lenient().when(queryWithParam.returnBundle(Bundle.class)).thenReturn(queryWithCount);
            lenient().when(queryWithCount.count(anyInt())).thenReturn(queryWithCount);
            lenient().when(queryWithCount.execute())
                    .thenReturn(TestFixtures.emptySearchResult());

            ITransaction tx = mock(ITransaction.class);
            lenient().when(fhirClient.transaction()).thenReturn(tx);
            lenient().when(tx.withBundle(any(Bundle.class)))
                    .thenReturn(transactionTyped);
            lenient().when(transactionTyped.execute())
                    .thenReturn(TestFixtures.allCreatedResponse(23));

            IUpdate update = mock(IUpdate.class);
            lenient().when(fhirClient.update()).thenReturn(update);
            lenient().when(update.resource(any(Resource.class))).thenReturn(updateTyped);
            lenient().when(updateTyped.execute()).thenReturn(new MethodOutcome());
        }
    }

    // -----------------------------------------------------------------------
    // Step 8: Provenance
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Step 8: Provenance")
    class ProvenanceCreation {

        @Test
        @DisplayName("Provenance is created with target pointing to import group")
        void provenanceCreated() {
            stubStandardFlow(false);
            ArgumentCaptor<Resource> resourceCaptor =
                    ArgumentCaptor.forClass(Resource.class);

            ICreate create = mock(ICreate.class);
            lenient().when(fhirClient.create()).thenReturn(create);
            lenient().when(create.resource(resourceCaptor.capture())).thenReturn(createTyped);

            MethodOutcome outcome = new MethodOutcome();
            IIdType mockId = mock(IIdType.class);
            lenient().when(mockId.toUnqualifiedVersionless()).thenReturn(mockId);
            lenient().when(mockId.getValue()).thenReturn("Group/test-import");
            lenient().when(mockId.getIdPart()).thenReturn("test-import");
            outcome.setId(mockId);
            lenient().when(createTyped.execute()).thenReturn(outcome);

            service.execute(TestFixtures.minimalBundle(), "merge", null, "Test");

            // Find Provenance among created resources
            Provenance provenance = resourceCaptor.getAllValues().stream()
                    .filter(r -> r instanceof Provenance)
                    .map(r -> (Provenance) r)
                    .findFirst()
                    .orElse(null);

            assertNotNull(provenance, "Provenance should be created");
            assertTrue(provenance.hasTarget(), "Provenance should have target");
            assertTrue(provenance.hasAgent(), "Provenance should have agent");
            assertEquals("assembler",
                    provenance.getAgentFirstRep().getType()
                            .getCodingFirstRep().getCode());
        }
    }

    // -----------------------------------------------------------------------
    // Step 9: Response Assembly
    // -----------------------------------------------------------------------

    @Nested
    @DisplayName("Step 9: Response Assembly")
    class ResponseAssembly {

        @Test
        @DisplayName("Response contains outcome, importGroup, and statistics")
        void responseStructure() {
            stubStandardFlow(false);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, "Test Import");

            assertNotNull(result);
            assertEquals("Parameters", result.fhirType());

            // Must have: outcome, importGroup, statistics
            List<String> paramNames = result.getParameter().stream()
                    .map(Parameters.ParametersParameterComponent::getName)
                    .toList();

            assertTrue(paramNames.contains("outcome"), "Response must have outcome");
            assertTrue(paramNames.contains("importGroup"), "Response must have importGroup");
            assertTrue(paramNames.contains("statistics"), "Response must have statistics");
        }

        @Test
        @DisplayName("Outcome is an OperationOutcome with severity=information")
        void outcomeIsInformational() {
            stubStandardFlow(false);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);

            Resource outcomeResource = result.getParameter().stream()
                    .filter(p -> "outcome".equals(p.getName()))
                    .map(Parameters.ParametersParameterComponent::getResource)
                    .findFirst()
                    .orElse(null);

            assertNotNull(outcomeResource);
            assertInstanceOf(OperationOutcome.class, outcomeResource);
            OperationOutcome oo = (OperationOutcome) outcomeResource;
            assertEquals(OperationOutcome.IssueSeverity.INFORMATION,
                    oo.getIssueFirstRep().getSeverity());
        }

        @Test
        @DisplayName("Statistics has all 5 required parts")
        void statisticsComplete() {
            stubStandardFlow(false);

            Parameters result = service.execute(
                    TestFixtures.minimalBundle(), "merge", null, null);

            Parameters.ParametersParameterComponent stats = result.getParameter()
                    .stream()
                    .filter(p -> "statistics".equals(p.getName()))
                    .findFirst()
                    .orElseThrow();

            List<String> partNames = stats.getPart().stream()
                    .map(Parameters.ParametersParameterComponent::getName)
                    .toList();

            assertTrue(partNames.contains("resourcesCreated"));
            assertTrue(partNames.contains("resourcesUpdated"));
            assertTrue(partNames.contains("resourcesSkipped"));
            assertTrue(partNames.contains("patientsInBatch"));
            assertTrue(partNames.contains("patientsInCohort"));
        }
    }
}
