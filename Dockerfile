# syntax=docker/dockerfile:1.7
# Docketbell container image: web server (gunicorn) and reminder worker in one image.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY docketbell ./docketbell
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=dev
ARG BUILD_NUMBER=dev
ARG GIT_SHA=""
ARG BUILD_DATE=""

LABEL org.opencontainers.image.title="Docketbell" \
      org.opencontainers.image.description="Court date text reminders with a staff dashboard" \
      org.opencontainers.image.source="https://github.com/lobojoel2003/Docketbell" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=docketbell.settings \
    STATIC_ROOT=/app/staticfiles \
    DOCKETBELL_BUILD_NUMBER=${BUILD_NUMBER} \
    DOCKETBELL_GIT_SHA=${GIT_SHA} \
    DOCKETBELL_BUILD_DATE=${BUILD_DATE}

RUN useradd --system --uid 10001 --create-home --home-dir /app docketbell
COPY --from=build /opt/venv /opt/venv
COPY docker/entrypoint.sh /usr/local/bin/docketbell-entrypoint
WORKDIR /app
RUN SECRET_KEY=collectstatic-only docketbell collectstatic --noinput -v0 \
    && chown -R docketbell:docketbell /app

USER docketbell
EXPOSE 8000
ENTRYPOINT ["docketbell-entrypoint"]
CMD ["web"]
