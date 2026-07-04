package de.tud.fgdh.digiphenoms.fhir.service;

import ca.uhn.fhir.rest.server.exceptions.InternalErrorException;
import ca.uhn.fhir.rest.server.exceptions.InvalidRequestException;
import ca.uhn.fhir.rest.server.exceptions.ResourceNotFoundException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Tests for {@link MlServerClient} against an embedded HTTP server that
 * plays the role of the ML server behind the SSH tunnel.
 */
class MlServerClientTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private HttpServer server;
    private String baseUrl;

    private final AtomicReference<String> lastMethod = new AtomicReference<>();
    private final AtomicReference<String> lastPath = new AtomicReference<>();
    private final AtomicReference<String> lastAuth = new AtomicReference<>();
    private final AtomicReference<String> lastBody = new AtomicReference<>();

    private volatile int responseStatus = 200;
    private volatile String responseBody = "{}";

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            lastMethod.set(exchange.getRequestMethod());
            lastPath.set(exchange.getRequestURI().getPath());
            lastAuth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            lastBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] bytes = responseBody.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(responseStatus, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    private MlServerClient client() {
        return client("test-token");
    }

    private MlServerClient client(String token) {
        return new MlServerClient(baseUrl, token, 5, HttpClient.newHttpClient());
    }

    // ---- request construction -----------------------------------------------

    @Test
    @DisplayName("startTraining POSTs job_type=training with Bearer token")
    void startTrainingPostsJobType() throws Exception {
        responseBody = "{\"job_id\":\"abc\",\"job_type\":\"training\",\"status\":\"queued\"}";

        JsonNode job = client().startTraining();

        assertEquals("POST", lastMethod.get());
        assertEquals("/jobs", lastPath.get());
        assertEquals("Bearer test-token", lastAuth.get());
        JsonNode sent = MAPPER.readTree(lastBody.get());
        assertEquals("training", sent.get("job_type").asText());
        assertEquals("abc", job.get("job_id").asText());
    }

    @Test
    @DisplayName("startSynthesis sends training_job_id and scale_factor")
    void startSynthesisSendsParameters() throws Exception {
        responseBody = "{\"job_id\":\"syn-1\"}";

        client().startSynthesis("train-1", new BigDecimal("2.5"));

        JsonNode sent = MAPPER.readTree(lastBody.get());
        assertEquals("synthesis", sent.get("job_type").asText());
        assertEquals("train-1", sent.get("training_job_id").asText());
        assertEquals(new BigDecimal("2.5"), sent.get("scale_factor").decimalValue());
    }

    @Test
    @DisplayName("startSynthesis defaults scale_factor to 1 when null")
    void startSynthesisDefaultsScaleFactor() throws Exception {
        responseBody = "{\"job_id\":\"syn-2\"}";

        client().startSynthesis("train-1", null);

        JsonNode sent = MAPPER.readTree(lastBody.get());
        assertEquals(BigDecimal.ONE, sent.get("scale_factor").decimalValue());
    }

    @Test
    @DisplayName("startEvaluation sends synthesis_job_id")
    void startEvaluationSendsSynthesisJobId() throws Exception {
        responseBody = "{\"job_id\":\"eval-1\"}";

        client().startEvaluation("syn-1");

        JsonNode sent = MAPPER.readTree(lastBody.get());
        assertEquals("evaluation", sent.get("job_type").asText());
        assertEquals("syn-1", sent.get("synthesis_job_id").asText());
    }

    @Test
    @DisplayName("getJob GETs /jobs/{id}")
    void getJobUsesJobPath() {
        responseBody = "{\"job_id\":\"j-9\",\"status\":\"running\"}";

        JsonNode job = client().getJob("j-9");

        assertEquals("GET", lastMethod.get());
        assertEquals("/jobs/j-9", lastPath.get());
        assertEquals("running", job.get("status").asText());
    }

    // ---- error handling -------------------------------------------------------

    @Test
    @DisplayName("missing token fails fast without a request")
    void missingTokenFailsFast() {
        InternalErrorException ex = assertThrows(
                InternalErrorException.class, () -> client("").startTraining());
        assertTrue(ex.getMessage().contains("API_AUTH_TOKEN"));
        assertNull(lastMethod.get(), "no HTTP request may be sent without a token");
    }

    @Test
    @DisplayName("HTTP 401 maps to InternalErrorException with token hint")
    void unauthorizedMapsToInternalError() {
        responseStatus = 401;
        responseBody = "{\"detail\":\"invalid token\"}";

        InternalErrorException ex = assertThrows(
                InternalErrorException.class, () -> client().startTraining());
        assertTrue(ex.getMessage().contains("401"));
    }

    @Test
    @DisplayName("HTTP 404 maps to ResourceNotFoundException")
    void notFoundMapsToResourceNotFound() {
        responseStatus = 404;
        responseBody = "{\"detail\":\"job not found\"}";

        ResourceNotFoundException ex = assertThrows(
                ResourceNotFoundException.class, () -> client().getJob("nope"));
        assertTrue(ex.getMessage().contains("job not found"));
    }

    @Test
    @DisplayName("HTTP 422 maps to InvalidRequestException with detail")
    void unprocessableMapsToInvalidRequest() {
        responseStatus = 422;
        responseBody = "{\"detail\":\"training_job_id required\"}";

        InvalidRequestException ex = assertThrows(
                InvalidRequestException.class, () -> client().startSynthesis("x", null));
        assertTrue(ex.getMessage().contains("training_job_id required"));
    }

    @Test
    @DisplayName("HTTP 500 maps to InternalErrorException")
    void serverErrorMapsToInternalError() {
        responseStatus = 500;
        responseBody = "boom";

        InternalErrorException ex = assertThrows(
                InternalErrorException.class, () -> client().startTraining());
        assertTrue(ex.getMessage().contains("500"));
    }

    @Test
    @DisplayName("connection failure mentions the SSH port forwarding")
    void connectionFailureMentionsTunnel() {
        int port = server.getAddress().getPort();
        server.stop(0);
        MlServerClient unreachable = new MlServerClient(
                "http://127.0.0.1:" + port, "test-token", 2, HttpClient.newHttpClient());

        InternalErrorException ex = assertThrows(
                InternalErrorException.class, unreachable::startTraining);
        assertTrue(ex.getMessage().contains("SSH port forwarding"));
    }
}
