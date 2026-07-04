package de.tud.fgdh.digiphenoms.fhir.operations;

import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import com.fasterxml.jackson.databind.ObjectMapper;
import de.tud.fgdh.digiphenoms.fhir.service.MlServerClient;
import org.hl7.fhir.r4.model.DecimalType;
import org.hl7.fhir.r4.model.Parameters;
import org.hl7.fhir.r4.model.StringType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Tests for the {@code $ml-*} operation provider {@link MlJobOperation}.
 */
@ExtendWith(MockitoExtension.class)
class MlJobOperationTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Mock
    private MlServerClient client;

    private MlJobOperation operation() {
        return new MlJobOperation(client);
    }

    private static String part(Parameters parameters, String name) {
        return parameters.getParameter().stream()
                .filter(p -> name.equals(p.getName()))
                .findFirst()
                .map(p -> p.getValue().primitiveValue())
                .orElse(null);
    }

    @Test
    @DisplayName("$ml-train delegates and maps the job response")
    void mlTrainDelegates() throws Exception {
        when(client.startTraining()).thenReturn(MAPPER.readTree(
                "{\"job_id\":\"j1\",\"job_type\":\"training\",\"status\":\"queued\"}"));

        Parameters response = operation().mlTrain();

        assertEquals("j1", part(response, "jobId"));
        assertEquals("training", part(response, "jobType"));
        assertEquals("queued", part(response, "status"));
        assertTrue(part(response, "job").contains("\"job_id\":\"j1\""));
    }

    @Test
    @DisplayName("$ml-synthesize forwards trainingJobId and scaleFactor")
    void mlSynthesizeForwardsParameters() throws Exception {
        when(client.startSynthesis("train-1", new BigDecimal("2.5")))
                .thenReturn(MAPPER.readTree("{\"job_id\":\"syn-1\"}"));

        Parameters response = operation().mlSynthesize(
                new StringType("train-1"), new DecimalType("2.5"));

        verify(client).startSynthesis("train-1", new BigDecimal("2.5"));
        assertEquals("syn-1", part(response, "jobId"));
    }

    @Test
    @DisplayName("$ml-synthesize defaults scaleFactor to 1.0")
    void mlSynthesizeDefaultsScaleFactor() throws Exception {
        when(client.startSynthesis("train-1", BigDecimal.ONE))
                .thenReturn(MAPPER.readTree("{\"job_id\":\"syn-2\"}"));

        operation().mlSynthesize(new StringType("train-1"), null);

        verify(client).startSynthesis("train-1", BigDecimal.ONE);
    }

    @Test
    @DisplayName("$ml-synthesize without trainingJobId is rejected")
    void mlSynthesizeRequiresTrainingJobId() {
        assertThrows(InvalidRequestException.class,
                () -> operation().mlSynthesize(null, null));
        assertThrows(InvalidRequestException.class,
                () -> operation().mlSynthesize(new StringType(""), null));
    }

    @Test
    @DisplayName("$ml-evaluate forwards synthesisJobId")
    void mlEvaluateForwardsSynthesisJobId() throws Exception {
        when(client.startEvaluation("syn-1"))
                .thenReturn(MAPPER.readTree("{\"job_id\":\"eval-1\",\"status\":\"queued\"}"));

        Parameters response = operation().mlEvaluate(new StringType("syn-1"));

        verify(client).startEvaluation("syn-1");
        assertEquals("eval-1", part(response, "jobId"));
    }

    @Test
    @DisplayName("$ml-evaluate without synthesisJobId is rejected")
    void mlEvaluateRequiresSynthesisJobId() {
        assertThrows(InvalidRequestException.class,
                () -> operation().mlEvaluate(null));
    }

    @Test
    @DisplayName("$ml-job-status delegates to getJob")
    void mlJobStatusDelegates() throws Exception {
        when(client.getJob("j-9")).thenReturn(MAPPER.readTree(
                "{\"job_id\":\"j-9\",\"status\":\"running\"}"));

        Parameters response = operation().mlJobStatus(new StringType("j-9"));

        assertEquals("j-9", part(response, "jobId"));
        assertEquals("running", part(response, "status"));
    }

    @Test
    @DisplayName("$ml-job-status without jobId is rejected")
    void mlJobStatusRequiresJobId() {
        assertThrows(InvalidRequestException.class,
                () -> operation().mlJobStatus(null));
    }

    @Test
    @DisplayName("response mapping tolerates alternative key names")
    void toParametersToleratesAlternativeKeys() throws Exception {
        when(client.getJob("u1")).thenReturn(MAPPER.readTree(
                "{\"uuid\":\"u1\",\"state\":\"RUNNING\",\"type\":\"synthesis\"}"));

        Parameters response = operation().mlJobStatus(new StringType("u1"));

        assertEquals("u1", part(response, "jobId"));
        assertEquals("RUNNING", part(response, "status"));
        assertEquals("synthesis", part(response, "jobType"));
    }

    @Test
    @DisplayName("response mapping omits canonical parts when keys are absent")
    void toParametersOmitsMissingKeys() throws Exception {
        when(client.getJob("x")).thenReturn(MAPPER.readTree("{\"foo\":\"bar\"}"));

        Parameters response = operation().mlJobStatus(new StringType("x"));

        assertNull(part(response, "jobId"));
        assertNull(part(response, "status"));
        assertTrue(part(response, "job").contains("\"foo\":\"bar\""));
    }
}
