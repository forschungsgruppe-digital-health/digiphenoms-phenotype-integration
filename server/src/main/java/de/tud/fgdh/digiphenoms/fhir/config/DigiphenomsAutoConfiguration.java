package de.tud.fgdh.digiphenoms.fhir.config;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

/**
 * Auto-configuration entry point for the DigiPhenoMS extension JAR.
 *
 * <p>The HAPI JPA starter has no mechanism to component-scan arbitrary
 * packages from an extra-classes JAR. This class is therefore registered
 * via {@code META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports}
 * and pulls all extension beans ({@code @Component}/{@code @Service}/
 * {@code @Configuration} under {@code de.tud.fgdh.digiphenoms.fhir}) into
 * the starter's application context.</p>
 *
 * <p>The operation providers additionally have to be attached to the
 * {@code RestfulServer} — that happens through
 * {@code hapi.fhir.custom_provider_classes} in the server configuration
 * (see {@code docker/hapi/application.yaml}), which resolves each listed
 * class as a bean from this context.</p>
 */
@AutoConfiguration
@ComponentScan(basePackages = "de.tud.fgdh.digiphenoms.fhir")
public class DigiphenomsAutoConfiguration {}
