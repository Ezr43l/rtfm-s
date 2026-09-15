# syntax=docker/dockerfile:1.7

FROM --platform=$BUILDPLATFORM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend

WORKDIR /build/web
COPY web/package.json web/package-lock.json web/tsconfig.json web/tsconfig.app.json web/tsconfig.node.json web/vite.config.ts web/index.html ./
COPY web/collect-third-party-licenses.mjs ./
COPY web/src ./src
COPY logo/icono.svg logo/icono.png ./public/
RUN npm ci --no-audit --no-fund \
    && npm run typecheck \
    && npm run build \
    && node collect-third-party-licenses.mjs node_modules /build/NPM_THIRD_PARTY_LICENSES.txt \
    && test -s /build/NPM_THIRD_PARTY_LICENSES.txt

FROM python:3.12-alpine@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31 AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DATA_DIR=/data \
    HOME=/home/rtfm \
    PORT=7400

WORKDIR /app
COPY requirements.txt requirements.lock scripts/collect-python-third-party-licenses.py ./
RUN mkdir -p /app/licenses \
    && chmod 0755 /app/licenses \
    && apk upgrade --no-cache \
    && apk add --no-cache \
        ca-certificates=20260611-r0 \
        git=2.54.0-r0 \
        iproute2=7.0.0-r0 \
    && pip install --no-cache-dir --require-hashes --requirement requirements.lock \
    && python collect-python-third-party-licenses.py /app/PYTHON_THIRD_PARTY_LICENSES.txt \
    && test -s /app/PYTHON_THIRD_PARTY_LICENSES.txt \
    && rm collect-python-third-party-licenses.py \
    && addgroup -S -g 10001 rtfm \
    && adduser -S -D -u 10001 -G rtfm -h /home/rtfm -s /sbin/nologin rtfm \
    && mkdir -p /data /home/rtfm \
    && chown -R 10001:10001 /data /home/rtfm

ADD --chmod=0644 --checksum=sha256:5b2198d1645f767585e8a88ac0499b04472164c0d2da22e75ecf97ef443ab32e \
    https://raw.githubusercontent.com/git/git/v2.54.0/COPYING \
    /app/licenses/git-COPYING
ADD --chmod=0644 --checksum=sha256:e6d6a009505e345fe949e1310334fcb0747f28dae2856759de102ab66b722cb4 \
    https://raw.githubusercontent.com/iproute2/iproute2/v7.0.0/COPYING \
    /app/licenses/iproute2-COPYING

COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 VERSION LICENSE THIRD_PARTY_NOTICES.md ./

FROM python-base AS tests
ARG RUN_BUILD_TESTS=0
COPY --chown=10001:10001 tests /tests
COPY --chown=10001:10001 scripts/export-public-release.py /scripts/export-public-release.py
USER 10001:10001
RUN if [ "$RUN_BUILD_TESTS" = "1" ]; then python -m unittest discover -s /tests -v; fi \
    && touch /tmp/rtfm-tests-passed

FROM python-base AS runtime

ARG BUILD_DATE=""
ARG VCS_REF="unknown"
ARG VERSION="0.4.11"
ARG SOURCE_URL="https://github.com/Ezr43l/rtfm-s"
ARG LICENSE="Apache-2.0"

LABEL org.opencontainers.image.title="RTFM" \
      org.opencontainers.image.description="Documentación operativa privada, versionada y replicable" \
      org.opencontainers.image.source="$SOURCE_URL" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_DATE" \
      org.opencontainers.image.licenses="$LICENSE" \
      io.ezr43l.image.third-party-notices="/app/THIRD_PARTY_NOTICES.md" \
      io.ezr43l.image.npm-third-party-licenses="/app/NPM_THIRD_PARTY_LICENSES.txt" \
      io.ezr43l.image.python-third-party-licenses="/app/PYTHON_THIRD_PARTY_LICENSES.txt"

ENV RTFM_VERSION="$VERSION"

COPY --from=tests --chown=10001:10001 /tmp/rtfm-tests-passed /app/.tests-passed
COPY --from=frontend --chown=10001:10001 /build/app/static ./app/static
COPY --from=frontend --chown=10001:10001 /build/NPM_THIRD_PARTY_LICENSES.txt ./

USER 10001:10001
VOLUME ["/data"]
EXPOSE 7400
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','7400')+'/api/health', timeout=3).read()"]

CMD ["python", "-m", "app.launcher"]
