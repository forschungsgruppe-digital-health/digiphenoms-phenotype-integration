# ---------- Stage 1: Build the extension JAR ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build

# Cache dependencies first (layer caching)
COPY server/pom.xml ./
RUN mvn dependency:go-offline -B

# Compile and package (thin JAR — no Spring Boot plugin)
COPY server/src ./src
RUN mvn package -DskipTests -B

# ---------- Stage 2: HAPI FHIR Server + Extension ----------
# The hapiproject/hapi image uses PropertiesLauncher with
# loader.path=/app/extra-classes/ — JARs placed there are
# automatically added to the classpath at startup.
FROM hapiproject/hapi:v7.6.0

USER root
COPY --from=build /build/target/digiphenoms-cohort-submit-*.jar /app/extra-classes/
USER 65532
