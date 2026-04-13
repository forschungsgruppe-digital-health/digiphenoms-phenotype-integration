FROM python:3.12-slim
WORKDIR /app

# Install pipeline with submit extras
COPY pipeline/ ./
RUN pip install --no-cache-dir ".[submit]"

# Config is baked in; data is mounted at runtime
ENTRYPOINT ["digiphenoms-fhir"]
