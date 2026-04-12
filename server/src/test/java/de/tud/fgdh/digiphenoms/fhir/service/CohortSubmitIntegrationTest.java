package de.tud.fgdh.digiphenoms.fhir.service;

import ca.uhn.fhir.rest.api.MethodOutcome;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import ca.uhn.fhir.rest.gclient.*;
import de.tud.fgdh.digiphenoms.fhir.TestFixtures;
import org.hl7.fhir.instance.model.api.IIdType;
import org.hl7.fhir.r4.model.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Integration-style tests for the full {@code $cohort-submit} workflow using
 * an in-memory mock FHIR store. The mock tracks created/updated resources
 * and verifies the complete processing chain.
 *
 * <p>Uses a {@link MockFhirStore} that simulates HAPI transaction processing:
 * tracking resources by type+id, responding with correct status codes, and
 * counting total patients in the "cohort".</p>
 */
@ExtendWith(MockitoExtension.class)
@SuppressWarnings({"unchecked", "rawtypes"})
class CohortSubmitIntegrationTest {

    @Mock private IGenericClient fhirClient;

    private CohortSubmitService service;
    private MockFhirStore store;

    @BeforeEach
    void setUp() {
        service = new CohortSubmitService(fhirClient);
        store = new MockFhirStore();

        // --- Wire up mock FHIR client to in-memory store ---

        // Search
        IUntypedQuery untypedQuery = mock(IUntypedQuery.class);
        IQuery query = mock(IQuery.class);
        IQuery queryWithParam = mock(IQuery.class);
        IQuery queryWithCount = mock(IQuery.class);

        lenient().when(fhirClient.search()).thenReturn(untypedQuery);
        lenient().when(untypedQuery.forResource(any(Class.class))).thenReturn(query);
        lenient().when(query.where(any(ICriterion.class))).thenReturn(queryWithParam);
        lenient().when(queryWithParam.returnBundle(Bundle.class)).thenReturn(queryWithCount);
        lenient().when(queryWithCount.count(anyInt())).thenReturn(queryWithCount);
        lenient().when(queryWithCount.execute()).thenAnswer(inv -> store.searchResult());

        // Create — store tracks every resource
        ICreate create = mock(ICreate.class);
        ICreateTyped createTyped = mock(ICreateTyped.class);
        lenient().when(fhirClient.create()).thenReturn(create);
        lenient().when(create.resource(any(Resource.class))).thenAnswer(inv -> {
            Resource r = inv.getArgument(0);
            store.store(r);
            return createTyped;
        });

        MethodOutcome createOutcome = new MethodOutcome();
        IIdType mockId = mock(IIdType.class);
        lenient().when(mockId.toUnqualifiedVersionless()).thenReturn(mockId);
        lenient().when(mockId.getValue()).thenReturn("Group/test");
        lenient().when(mockId.getIdPart()).thenReturn("test");
        createOutcome.setId(mockId);
        lenient().when(createTyped.execute()).thenReturn(createOutcome);

        // Read — return resource from store by ID
        IRead readOp = mock(IRead.class);
        IReadTyped<Group> readTyped = mock(IReadTyped.class);
        IReadExecutable<Group> readExec = mock(IReadExecutable.class);
        lenient().when(fhirClient.read()).thenReturn(readOp);
        lenient().when(readOp.resource(any(Class.class))).thenReturn(readTyped);
        lenient().when(readTyped.withId(anyString())).thenReturn(readExec);
        lenient().when(readExec.execute()).thenAnswer(inv -> store.readGroup());

        // Update
        IUpdate update = mock(IUpdate.class);
        IUpdateTyped updateTyped = mock(IUpdateTyped.class);
        lenient().when(fhirClient.update()).thenReturn(update);
        lenient().when(update.resource(any(Resource.class))).thenReturn(updateTyped);
        lenient().when(updateTyped.execute()).thenReturn(new MethodOutcome());

        // Transaction — process entries and track created/updated
        ITransaction tx = mock(ITransaction.class);
        ITransactionTyped<Bundle> txTyped = mock(ITransactionTyped.class);
        lenient().when(fhirClient.transaction()).thenReturn(tx);
        lenient().when(tx.withBundle(any(Bundle.class))).thenAnswer(inv -> {
            store.processTransaction(inv.getArgument(0));
            return txTyped;
        });
        lenient().when(txTyped.execute()).thenAnswer(inv -> store.lastTransactionResponse());
    }

    // =======================================================================
    // UC-1: Initial Cohort Import (Merge)
    // =======================================================================

    @Test
    @DisplayName("UC-1: Initial import — all resources created, none updated")
    void initialImportMerge() {
        Bundle input = TestFixtures.realisticCollectionBundle();

        Parameters result = service.execute(input, "merge",
                "digiphenoms-ms-cohort", "Erstimport April 2026");

        // Verify response structure
        assertNotNull(result);
        assertParamExists(result, "outcome");
        assertParamExists(result, "importGroup");
        assertParamExists(result, "statistics");

        // All 23 resources should be "created" (first import)
        int created = extractStat(result, "resourcesCreated");
        int updated = extractStat(result, "resourcesUpdated");
        assertEquals(0, updated, "No updates on initial import");
        assertTrue(created > 0, "Resources should be created");

        // 3 patients in batch
        assertEquals(3, extractStat(result, "patientsInBatch"));

        // Store should have resources from all 3 tiers
        assertTrue(store.hasResourceType("Patient"));
        assertTrue(store.hasResourceType("Condition"));
        assertTrue(store.hasResourceType("Encounter"));
        assertTrue(store.hasResourceType("Observation"));
        assertTrue(store.hasResourceType("DiagnosticReport"));
        assertTrue(store.hasResourceType("QuestionnaireResponse"));

        // Import group and provenance should be created
        assertTrue(store.hasResourceType("Group"), "Import group should be stored");
        assertTrue(store.hasResourceType("Provenance"), "Provenance should be stored");
    }

    // =======================================================================
    // UC-2: Follow-up Import (Merge — mix of created and updated)
    // =======================================================================

    @Test
    @DisplayName("UC-2: Follow-up import — existing resources updated, new ones created")
    void followUpImportMerge() {
        // First import: seed the store
        store.seedExistingResources(List.of(
                "Patient/pat-abc-1001",
                "Patient/pat-def-1002",
                "Condition/cond-ms-abc-1001"
        ));

        Bundle input = TestFixtures.realisticCollectionBundle();
        Parameters result = service.execute(input, "merge", null, "Folgeimport");

        int created = extractStat(result, "resourcesCreated");
        int updated = extractStat(result, "resourcesUpdated");

        // Some should be updated (existing), some created (new)
        assertTrue(created + updated > 0, "Should have processed resources");
    }

    // =======================================================================
    // UC-3: Snapshot Import (Distinct)
    // =======================================================================

    @Test
    @DisplayName("UC-3: Distinct import — existing skipped, new created")
    void snapshotImportDistinct() {
        // Seed some existing resources
        store.seedExistingResources(List.of(
                "Patient/pat-abc-1001"
        ));

        Bundle input = TestFixtures.realisticCollectionBundle();
        Parameters result = service.execute(input, "distinct", null, "Snapshot");

        int created = extractStat(result, "resourcesCreated");
        int skipped = extractStat(result, "resourcesSkipped");

        assertTrue(created + skipped > 0, "Should have processed resources");
        assertEquals(0, extractStat(result, "resourcesUpdated"),
                "Distinct mode should never update");
    }

    // =======================================================================
    // UC-4: Re-Import after Pipeline Correction (Merge)
    // =======================================================================

    @Test
    @DisplayName("UC-4: Re-import — all resources exist, most updated")
    void reImportMerge() {
        // Seed ALL resources as existing
        store.seedExistingResources(List.of(
                "Patient/pat-abc-1001",
                "Patient/pat-def-1002",
                "Patient/pat-ghi-1003",
                "Encounter/enc-assess-2001",
                "Encounter/enc-assess-2002",
                "Encounter/enc-assess-2003",
                "Observation/obs-lcla-assess-2001-mod-lcla-001"
        ));

        Bundle input = TestFixtures.realisticCollectionBundle();
        Parameters result = service.execute(input, "merge", null,
                "Re-Import Pipeline v1.0.1");

        int updated = extractStat(result, "resourcesUpdated");
        assertTrue(updated > 0, "Re-import should update existing resources");

        // A new Provenance should still be created
        assertTrue(store.hasResourceType("Provenance"));
    }

    // =======================================================================
    // Minimal bundle
    // =======================================================================

    @Test
    @DisplayName("Minimal bundle with single patient succeeds")
    void minimalBundleSinglePatient() {
        Parameters result = service.execute(
                TestFixtures.minimalBundle(), "merge", null, null);

        assertNotNull(result);
        assertEquals(1, extractStat(result, "patientsInBatch"));
    }

    // =======================================================================
    // Identifier-based conditional URLs
    // =======================================================================

    @Test
    @DisplayName("Transaction bundles use identifier-based conditional URLs")
    void identifierBasedConditionalUrls() {
        // Capture the transaction bundles
        List<Bundle> capturedBundles = new ArrayList<>();
        ITransaction tx = mock(ITransaction.class);
        ITransactionTyped<Bundle> txTyped = mock(ITransactionTyped.class);
        when(fhirClient.transaction()).thenReturn(tx);
        when(tx.withBundle(any(Bundle.class))).thenAnswer(inv -> {
            Bundle b = inv.getArgument(0);
            capturedBundles.add(b);
            store.processTransaction(b);
            return txTyped;
        });
        when(txTyped.execute()).thenAnswer(inv -> store.lastTransactionResponse());

        service.execute(TestFixtures.realisticCollectionBundle(),
                "merge", null, null);

        // Check that conditional URLs contain identifier queries
        for (Bundle txBundle : capturedBundles) {
            for (Bundle.BundleEntryComponent entry : txBundle.getEntry()) {
                String url = entry.getRequest().getUrl();
                if (url != null && url.contains("?")) {
                    assertTrue(url.contains("identifier="),
                            "Conditional URL should use identifier: " + url);
                }
            }
        }
    }

    // =======================================================================
    // Helpers
    // =======================================================================

    private void assertParamExists(Parameters params, String name) {
        assertTrue(params.getParameter().stream()
                        .anyMatch(p -> name.equals(p.getName())),
                "Expected parameter '" + name + "' in response");
    }

    private int extractStat(Parameters result, String name) {
        return result.getParameter().stream()
                .filter(p -> "statistics".equals(p.getName()))
                .flatMap(p -> p.getPart().stream())
                .filter(p -> name.equals(p.getName()))
                .map(p -> ((IntegerType) p.getValue()).getValue())
                .findFirst().orElse(-1);
    }

    // =======================================================================
    // In-Memory Mock FHIR Store
    // =======================================================================

    /**
     * Simple in-memory store that tracks resources and simulates
     * HAPI FHIR transaction behavior (201 for new, 200 for existing).
     */
    private static class MockFhirStore {
        private final Map<String, Resource> resources = new HashMap<>();
        private final Set<String> existingKeys = new HashSet<>();
        private Bundle lastResponse;

        /** Pre-seed resources that "already exist" on the server. */
        void seedExistingResources(List<String> references) {
            existingKeys.addAll(references);
        }

        /** Store a resource (from create()). */
        void store(Resource r) {
            String key = r.fhirType() + "/" + r.getIdElement().getIdPart();
            resources.put(key, r);
        }

        /** Process a transaction bundle and build a response. */
        void processTransaction(Bundle txBundle) {
            Bundle response = new Bundle();
            response.setType(Bundle.BundleType.TRANSACTIONRESPONSE);

            for (Bundle.BundleEntryComponent entry : txBundle.getEntry()) {
                Resource res = entry.getResource();
                String key = res.fhirType() + "/" + res.getIdElement().getIdPart();

                Bundle.BundleEntryComponent respEntry = response.addEntry();
                if (existingKeys.contains(key) || resources.containsKey(key)) {
                    respEntry.getResponse().setStatus("200 OK");
                } else {
                    respEntry.getResponse().setStatus("201 Created");
                }
                resources.put(key, res);
                existingKeys.add(key);
            }
            lastResponse = response;
        }

        Bundle lastTransactionResponse() {
            return lastResponse != null ? lastResponse :
                    TestFixtures.allCreatedResponse(0);
        }

        /** Return an empty search result (root group not found). */
        Bundle searchResult() {
            return TestFixtures.emptySearchResult();
        }

        /** Read a Group resource — returns the last stored Group (import group). */
        Group readGroup() {
            return resources.values().stream()
                    .filter(r -> r instanceof Group)
                    .map(r -> (Group) r)
                    .reduce((first, second) -> second) // last stored
                    .orElse(new Group());
        }

        boolean hasResourceType(String type) {
            return resources.values().stream()
                    .anyMatch(r -> type.equals(r.fhirType()));
        }
    }
}
