package de.tud.fgdh.digiphenoms.fhir.operations;

import de.tud.fgdh.digiphenoms.fhir.TestFixtures;
import de.tud.fgdh.digiphenoms.fhir.service.CohortSubmitService;
import org.hl7.fhir.r4.model.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link CohortSubmitOperation} — the HAPI {@code @Operation}
 * provider that delegates to {@link CohortSubmitService}.
 *
 * <p>These tests verify parameter extraction and delegation, not the processing
 * logic itself (that is covered in {@code CohortSubmitServiceTest}).</p>
 */
@ExtendWith(MockitoExtension.class)
class CohortSubmitOperationTest {

    @Mock
    private CohortSubmitService service;

    private CohortSubmitOperation operation;

    @BeforeEach
    void setUp() {
        operation = new CohortSubmitOperation(service);
    }

    private Parameters successResponse() {
        Parameters p = new Parameters();
        OperationOutcome oo = new OperationOutcome();
        oo.addIssue()
                .setSeverity(OperationOutcome.IssueSeverity.INFORMATION)
                .setCode(OperationOutcome.IssueType.INFORMATIONAL)
                .setDiagnostics("OK");
        p.addParameter().setName("outcome").setResource(oo);
        p.addParameter().setName("importGroup")
                .setValue(new Reference("Group/import-test"));
        Parameters.ParametersParameterComponent stats = p.addParameter();
        stats.setName("statistics");
        stats.addPart().setName("resourcesCreated").setValue(new IntegerType(1));
        stats.addPart().setName("resourcesUpdated").setValue(new IntegerType(0));
        stats.addPart().setName("resourcesSkipped").setValue(new IntegerType(0));
        stats.addPart().setName("patientsInBatch").setValue(new IntegerType(1));
        stats.addPart().setName("patientsInCohort").setValue(new IntegerType(1));
        return p;
    }

    @Test
    @DisplayName("Delegates to service with extracted parameter values")
    void delegatesToService() {
        when(service.execute(any(), eq("merge"), eq("test-cohort"), eq("Test Label")))
                .thenReturn(successResponse());

        Bundle inputBundle = TestFixtures.minimalBundle();
        Parameters result = operation.cohortSubmit(
                inputBundle,
                new CodeType("merge"),
                new StringType("test-cohort"),
                new StringType("Test Label"));

        assertNotNull(result);
        verify(service).execute(inputBundle, "merge", "test-cohort", "Test Label");
    }

    @Test
    @DisplayName("Null mode is passed as 'merge' default")
    void nullModeDefaultsToMerge() {
        when(service.execute(any(), eq("merge"), isNull(), isNull()))
                .thenReturn(successResponse());

        operation.cohortSubmit(TestFixtures.minimalBundle(), null, null, null);

        verify(service).execute(any(), eq("merge"), isNull(), isNull());
    }

    @Test
    @DisplayName("Distinct mode is forwarded correctly")
    void distinctModeForwarded() {
        when(service.execute(any(), eq("distinct"), isNull(), isNull()))
                .thenReturn(successResponse());

        operation.cohortSubmit(TestFixtures.minimalBundle(),
                new CodeType("distinct"), null, null);

        verify(service).execute(any(), eq("distinct"), isNull(), isNull());
    }

    @Test
    @DisplayName("Realistic bundle is passed through unchanged")
    void realisticBundlePassedThrough() {
        ArgumentCaptor<Bundle> bundleCaptor = ArgumentCaptor.forClass(Bundle.class);
        when(service.execute(bundleCaptor.capture(), anyString(), any(), any()))
                .thenReturn(successResponse());

        Bundle realistic = TestFixtures.realisticCollectionBundle();
        operation.cohortSubmit(realistic, new CodeType("merge"), null, null);

        Bundle captured = bundleCaptor.getValue();
        assertSame(realistic, captured, "Bundle should be passed by reference");
        assertEquals(23, captured.getEntry().size(),
                "Realistic bundle should have 23 entries");
    }

    @Test
    @DisplayName("Service exception propagates to caller")
    void serviceExceptionPropagates() {
        when(service.execute(any(), anyString(), any(), any()))
                .thenThrow(new ca.uhn.fhir.rest.server.exceptions.InvalidRequestException(
                        "DIGIPHENOMS-001"));

        assertThrows(ca.uhn.fhir.rest.server.exceptions.InvalidRequestException.class,
                () -> operation.cohortSubmit(
                        TestFixtures.emptyBundle(),
                        new CodeType("merge"), null, null));
    }

    @Test
    @DisplayName("Returns Parameters response from service")
    void returnsParametersResponse() {
        Parameters expected = successResponse();
        when(service.execute(any(), anyString(), any(), any())).thenReturn(expected);

        Parameters result = operation.cohortSubmit(
                TestFixtures.minimalBundle(),
                new CodeType("merge"), null, null);

        assertSame(expected, result);
    }
}
