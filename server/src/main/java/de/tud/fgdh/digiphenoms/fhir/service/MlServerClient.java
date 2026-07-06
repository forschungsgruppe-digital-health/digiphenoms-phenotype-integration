package de.tud.fgdh.digiphenoms.fhir.service;

import ca.uhn.fhir.rest.server.exceptions.InternalErrorException;
import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import ca.uhn.fhir.rest.server.exceptions.ResourceNotFoundException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

/**
 * HTTP client for the DigiPhenoMS ML server job API (synthetic data generation).
 *
 * <p>The ML server sits behind a restrictive proxy and is reached through an SSH
 * port forwarding (default {@code http://localhost:8000}). Host and credentials
 * are provided by the ML team (see {@code docs/ml_server_api.md}):</p>
 *
 * <pre>ssh -L 8000:localhost:8000 "$ML_SERVER_SSH_USER@$ML_SERVER_SSH_HOST" -N</pre>
 *
 * <p>Documented endpoints (see {@code docs/ml_server_api.md}):</p>
 * <ul>
 *   <li>{@code POST /jobs} — start a training / synthesis / evaluation job</li>
 *   <li>{@code GET /jobs/{id}} — query job status</li>
 * </ul>
 *
 * <p>Configuration properties (overridable via environment variables):</p>
 * <ul>
 *   <li>{@code ml.server.url} / {@code ML_SERVER_URL} — base URL</li>
 *   <li>{@code ml.server.token} / {@code ML_SERVER_TOKEN} or {@code API_AUTH_TOKEN}
 *       — Bearer token (never stored in the repository)</li>
 *   <li>{@code ml.server.timeout-seconds} — per-request timeout</li>
 * </ul>
 */
@Service
public class MlServerClient {

    private static final Logger LOG = LoggerFactory.getLogger(MlServerClient.class);

    public static final String JOB_TYPE_TRAINING = "training";
    public static final String JOB_TYPE_SYNTHESIS = "synthesis";
    public static final String JOB_TYPE_EVALUATION = "evaluation";

    private final String baseUrl;
    private final String token;
    private final Duration requestTimeout;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Autowired
    public MlServerClient(
            @Value("${ml.server.url:http://localhost:8000}") String baseUrl,
            @Value("${ml.server.token:${API_AUTH_TOKEN:}}") String token,
            @Value("${ml.server.timeout-seconds:60}") long timeoutSeconds) {
        this(baseUrl, token, timeoutSeconds,
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build());
    }

    /** Test constructor with injectable {@link HttpClient}. */
    MlServerClient(String baseUrl, String token, long timeoutSeconds, HttpClient httpClient) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.token = token;
        this.requestTimeout = Duration.ofSeconds(timeoutSeconds);
        this.httpClient = httpClient;
    }

    // ---- job management ----------------------------------------------------

    /** Start a training job ({@code POST /jobs}). */
    public JsonNode startTraining() {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("job_type", JOB_TYPE_TRAINING);
        return postJob(body);
    }

    /** Start a synthesis job based on a completed training job. */
    public JsonNode startSynthesis(String trainingJobId, BigDecimal scaleFactor) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("job_type", JOB_TYPE_SYNTHESIS);
        body.put("training_job_id", trainingJobId);
        body.put("scale_factor", scaleFactor != null ? scaleFactor : BigDecimal.ONE);
        return postJob(body);
    }

    /** Start an evaluation job based on a completed synthesis job. */
    public JsonNode startEvaluation(String synthesisJobId) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("job_type", JOB_TYPE_EVALUATION);
        body.put("synthesis_job_id", synthesisJobId);
        return postJob(body);
    }

    /** Fetch job details/status ({@code GET /jobs/{id}}). */
    public JsonNode getJob(String jobId) {
        HttpRequest request = requestBuilder("/jobs/" + jobId).GET().build();
        return execute(request);
    }

    // ---- internals -----------------------------------------------------------

    private JsonNode postJob(ObjectNode body) {
        HttpRequest request = requestBuilder("/jobs")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                .build();
        return execute(request);
    }

    private HttpRequest.Builder requestBuilder(String path) {
        requireToken();
        return HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(requestTimeout)
                .header("Authorization", "Bearer " + token);
    }

    private void requireToken() {
        if (token == null || token.isBlank()) {
            throw new InternalErrorException(
                    "ML server API token is not configured — set the ML_SERVER_TOKEN "
                            + "or API_AUTH_TOKEN environment variable");
        }
    }

    private JsonNode execute(HttpRequest request) {
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (HttpTimeoutException e) {
            throw new InternalErrorException(
                    "Request to ML server timed out after " + requestTimeout.toSeconds() + "s", e);
        } catch (IOException e) {
            throw new InternalErrorException(
                    "Connection to ML server at " + baseUrl + " failed: " + e.getMessage()
                            + ". Is the SSH port forwarding active? "
                            + "(ssh -L 8000:localhost:8000 <user>@<ml-server-host> -N, "
                            + "see docs/ml_server_api.md)", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new InternalErrorException("Request to ML server was interrupted", e);
        }

        int status = response.statusCode();
        String body = response.body() != null ? response.body() : "";

        if (status >= 200 && status < 300) {
            try {
                return objectMapper.readTree(body);
            } catch (IOException e) {
                throw new InternalErrorException("ML server returned invalid JSON", e);
            }
        }

        String detail = extractDetail(body);
        LOG.warn("ML server request {} {} failed: HTTP {} — {}",
                request.method(), request.uri(), status, detail);

        if (status == 401 || status == 403) {
            throw new InternalErrorException(
                    "ML server rejected the API token (HTTP " + status
                            + ") — check ML_SERVER_TOKEN / API_AUTH_TOKEN");
        }
        if (status == 404) {
            throw new ResourceNotFoundException(
                    "ML server job not found (HTTP 404)" + suffix(detail));
        }
        if (status == 400 || status == 422) {
            throw new InvalidRequestException(
                    "ML server rejected the request (HTTP " + status + ")" + suffix(detail));
        }
        throw new InternalErrorException(
                "ML server error (HTTP " + status + ")" + suffix(detail));
    }

    private String extractDetail(String body) {
        if (body == null || body.isBlank()) {
            return "";
        }
        try {
            JsonNode node = objectMapper.readTree(body);
            for (String key : new String[] {"detail", "message", "error"}) {
                JsonNode value = node.get(key);
                if (value != null && !value.isNull()) {
                    return value.isTextual() ? value.asText() : value.toString();
                }
            }
        } catch (IOException ignored) {
            // not JSON — fall through to raw body
        }
        return body.length() > 200 ? body.substring(0, 200) : body;
    }

    private static String suffix(String detail) {
        return detail.isBlank() ? "" : ": " + detail;
    }
}
