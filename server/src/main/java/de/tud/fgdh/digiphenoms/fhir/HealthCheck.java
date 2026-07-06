package de.tud.fgdh.digiphenoms.fhir;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Minimal HTTP healthcheck for the distroless HAPI container.
 *
 * <p>The {@code hapiproject/hapi} runtime image is distroless — no shell,
 * no curl — so Docker healthchecks can only exec {@code java}. This class
 * is shipped inside the extension JAR and invoked as:</p>
 *
 * <pre>java -cp /app/extra-classes/digiphenoms-extension.jar \
 *     de.tud.fgdh.digiphenoms.fhir.HealthCheck http://localhost:8080/fhir/metadata</pre>
 *
 * <p>Exit code 0 on HTTP 2xx/3xx, 1 otherwise.</p>
 */
public final class HealthCheck {

    private HealthCheck() {}

    public static void main(String[] args) {
        String url = args.length > 0 ? args[0] : "http://localhost:8080/fhir/metadata";
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            int status = client.send(request, HttpResponse.BodyHandlers.discarding()).statusCode();
            System.exit(status >= 200 && status < 400 ? 0 : 1);
        } catch (Exception e) {
            System.exit(1);
        }
    }
}
