FROM python:3.10-slim AS build

ARG APP_NAME=openmower
ARG APP_CONSOLE_SCRIPT=openmower

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install --yes git

WORKDIR /src

# Copy metadata first for better caching
COPY pyproject.toml* setup.cfg* setup.py* requirements*.txt* ./
# Install shiv
RUN pip install --no-cache-dir --upgrade pip shiv

# Copy the rest of your source
COPY . .

# Build the zipapp:
# -p sets shebang to use env python3 on the target system
# -c selects the console_script entry point
# We include the current project (.) and, if present, requirements*.txt
RUN mkdir -p /out && \
    shiv \
      -p "/usr/bin/env python3" \
      -c "${APP_CONSOLE_SCRIPT}" \
      -o "/out/${APP_NAME}" \
      $( [ -f requirements.txt ] && echo "-r requirements.txt" ) \
      .

# -----------------------------------------------------------------------------
# Stage 2: export-only stage
# This stage contains *only* the artifact so `docker build -o` can export it.
# -----------------------------------------------------------------------------
FROM scratch AS artifact
COPY --from=build /out/ /
