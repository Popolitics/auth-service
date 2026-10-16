FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Installation de uv
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

# Copie des dépendances
COPY pyproject.toml uv.lock .python-version ./

# Création et installation dans le venv du conteneur
RUN uv sync --frozen --no-cache --no-dev --no-build

# Copie du code source
COPY accounts/ ./accounts/
COPY authentication/ ./authentication/
COPY config/ ./config/
COPY manage.py ./

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app \
    && mkdir -p /app/staticfiles \
    && chown app:app /app/staticfiles

USER app

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
