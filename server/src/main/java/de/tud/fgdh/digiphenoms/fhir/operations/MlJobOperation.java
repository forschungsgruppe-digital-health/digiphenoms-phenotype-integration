package de.tud.fgdh.digiphenoms.fhir.operations;

import ca.uhn.fhir.rest.annotation.Operation;
import ca.uhn.fhir.rest.annotation.OperationParam;
import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import com.fasterxml.jackson.databind.JsonNode;
import de.tud.fgdh.digiphenoms.fhir.service.MlServerClient;
import org.hl7.fhir.r4.model.DecimalType;
import org.hl7.fhir.r4.model.Parameters;
import org.hl7.fhir.r4.model.StringType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;

/**
 * HAPI FHIR plain provider exposing the DigiPhenoMS ML server job API as
 * system-level FHIR operations:
 *
 * <ul>
 *   <li>{@code $ml-train} — start a training job</li>
 *   <li>{@code $ml-synthesize} — start a synthesis job (requires {@code trainingJobId})</li>
 *   <li>{@code $ml-evaluate} — start an evaluation job (requires {@code synthesisJobId})</li>
 *   <li>{@code $ml-job-status} — query a job (requires {@code jobId}, GET-able)</li>
 * </ul>
 *
 * <p>Each operation returns a {@link Parameters} resource with the canonical
 * parts {@code jobId}, {@code jobType} and {@code status} (when present in the
 * server response) plus the raw job JSON in {@code job}. Dataset/report
 * artifacts are downloaded by the Python pipeline
 * ({@code digiphenoms-ml download-dataset}), not through FHIR.</p>
 *
 * <p>Provided as a bean via the extension's Spring Boot auto-configuration
 * and attached to the server through {@code hapi.fhir.custom_provider_classes}.
 * Delegates all HTTP communication to {@link MlServerClient}.</p>
 */
@Component
public class MlJobOperation {

    private static final Logger LOG = LoggerFactory.getLogger(MlJobOperation.class);

    private final MlServerClient client;

    public MlJobOperation(MlServerClient client) {
        this.client = client;
    }

    /**
     * Handle {@code POST /fhir/$ml-train} — start a training job on the ML server.
     */
    @Operation(name = "$ml-train", idempotent = false)
    public Parameters mlTrain() {
        LOG.info("$ml-train invoked");
        return toParameters(client.startTraining());
    }

    /**
     * Handle {@code POST /fhir/$ml-synthesize} — start a synthesis job.
     *
     * @param trainingJobId id of the completed training job providing the model (required)
     * @param scaleFactor   dataset scale factor (default: 1.0)
     */
    @Operation(name = "$ml-synthesize", idempotent = false)
    public Parameters mlSynthesize(
            @OperationParam(name = "trainingJobId") StringType trainingJobId,
            @OperationParam(name = "scaleFactor") DecimalType scaleFactor) {

        String trainingId = requireParam(trainingJobId, "trainingJobId");
        BigDecimal scale = scaleFactor != null ? scaleFactor.getValue() : BigDecimal.ONE;
        LOG.info("$ml-synthesize invoked — trainingJobId={}, scaleFactor={}", trainingId, scale);
        return toParameters(client.startSynthesis(trainingId, scale));
    }

    /**
     * Handle {@code POST /fhir/$ml-evaluate} — start an evaluation job.
     *
     * @param synthesisJobId id of the completed synthesis job to evaluate (required)
     */
    @Operation(name = "$ml-evaluate", idempotent = false)
    public Parameters mlEvaluate(
            @OperationParam(name = "synthesisJobId") StringType synthesisJobId) {

        String synthesisId = requireParam(synthesisJobId, "synthesisJobId");
        LOG.info("$ml-evaluate invoked — synthesisJobId={}", synthesisId);
        return toParameters(client.startEvaluation(synthesisId));
    }

    /**
     * Handle {@code GET/POST /fhir/$ml-job-status} — query job status.
     *
     * @param jobId id of the job to query (required)
     */
    @Operation(name = "$ml-job-status", idempotent = true)
    public Parameters mlJobStatus(
            @OperationParam(name = "jobId") StringType jobId) {

        String id = requireParam(jobId, "jobId");
        LOG.info("$ml-job-status invoked — jobId={}", id);
        return toParameters(client.getJob(id));
    }

    // ---- helpers -------------------------------------------------------------

    private static String requireParam(StringType value, String name) {
        if (value == null || value.getValue() == null || value.getValue().isBlank()) {
            throw new InvalidRequestException(
                    "Missing required parameter '" + name + "'");
        }
        return value.getValue();
    }

    /**
     * Map a job JSON document to a FHIR Parameters response. Key naming is
     * probed tolerantly — the ML server's OpenAPI spec is only reachable
     * through the SSH tunnel, so exact field names may vary.
     */
    private static Parameters toParameters(JsonNode job) {
        Parameters response = new Parameters();
        addIfPresent(response, "jobId", job, "job_id", "id", "jobId", "uuid");
        addIfPresent(response, "jobType", job, "job_type", "jobType", "type");
        addIfPresent(response, "status", job, "status", "state", "job_status");
        response.addParameter("job", new StringType(job.toString()));
        return response;
    }

    private static void addIfPresent(
            Parameters response, String parameterName, JsonNode job, String... keys) {
        for (String key : keys) {
            JsonNode value = job.get(key);
            if (value != null && !value.isNull()) {
                response.addParameter(parameterName,
                        new StringType(value.isTextual() ? value.asText() : value.toString()));
                return;
            }
        }
    }
}
