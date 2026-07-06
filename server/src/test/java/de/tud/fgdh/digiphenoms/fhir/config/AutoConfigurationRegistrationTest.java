package de.tud.fgdh.digiphenoms.fhir.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.lang.annotation.Annotation;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the Spring Boot auto-configuration wiring: without a valid
 * AutoConfiguration.imports entry the HAPI server silently starts without
 * any extension bean (exactly the failure mode of the former, unsupported
 * {@code custom_bean_packages} setting).
 */
class AutoConfigurationRegistrationTest {

    private static final String IMPORTS_RESOURCE =
            "/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    @Test
    @DisplayName("AutoConfiguration.imports names loadable classes")
    void importsFileNamesLoadableClasses() throws Exception {
        List<String> classNames = readImports();
        assertTrue(
                classNames.contains(DigiphenomsAutoConfiguration.class.getName()),
                "imports file must register DigiphenomsAutoConfiguration");
        for (String className : classNames) {
            Class.forName(className); // throws if the entry has a typo
        }
    }

    @Test
    @DisplayName("auto-configuration scans the extension package")
    void autoConfigurationScansExtensionPackage() {
        Annotation componentScan = Arrays.stream(
                        DigiphenomsAutoConfiguration.class.getAnnotations())
                .filter(a -> a.annotationType().getSimpleName().equals("ComponentScan"))
                .findFirst()
                .orElse(null);
        assertNotNull(componentScan, "DigiphenomsAutoConfiguration must declare @ComponentScan");
        assertTrue(
                componentScan.toString().contains("de.tud.fgdh.digiphenoms.fhir"),
                "@ComponentScan must cover the extension base package");
    }

    private static List<String> readImports() throws IOException {
        try (InputStream in =
                AutoConfigurationRegistrationTest.class.getResourceAsStream(IMPORTS_RESOURCE)) {
            assertNotNull(in, IMPORTS_RESOURCE + " missing from the JAR resources");
            String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            return content.lines().map(String::trim).filter(l -> !l.isEmpty()).toList();
        }
    }
}
