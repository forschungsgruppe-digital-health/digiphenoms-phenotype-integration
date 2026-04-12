package de.tud.fgdh.digiphenoms.fhir.config;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Provides an internal {@link IGenericClient} that the {@code $cohort-submit}
 * service uses to interact with the co-located HAPI JPA store.
 *
 * <p>The {@link FhirContext} bean is provided by the HAPI FHIR JPA Starter
 * and injected here — this extension does <b>not</b> create its own context.</p>
 */
@Configuration
public class FhirClientConfig {

    @Value("${hapi.fhir.server_address:http://localhost:8080/fhir}")
    private String serverAddress;

    @Bean
    public IGenericClient fhirClient(FhirContext fhirContext) {
        return fhirContext.newRestfulGenericClient(serverAddress);
    }
}
