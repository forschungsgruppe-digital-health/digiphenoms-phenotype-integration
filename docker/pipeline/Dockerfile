FROM python:3.12-slim
WORKDIR /app

# Copy both pipeline
COPY pipeline/ ./

# Install pipeline with submit extras
RUN pip install --no-cache-dir ".[submit]"

# Config is baked in; data is mounted at runtime
ENTRYPOINT ["digiphenoms-fhir"]