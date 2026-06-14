FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/proofrail

COPY pyproject.toml README.md PROOFRAIL.md ./
COPY proofrail ./proofrail
COPY integrations ./integrations
COPY examples ./examples
COPY schemas ./schemas

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 proofrail \
    && mkdir -p /var/lib/proofrail \
    && chown -R proofrail:proofrail /var/lib/proofrail

USER proofrail
VOLUME ["/var/lib/proofrail"]

ENTRYPOINT ["proofrail"]
CMD ["--help"]
