# auth-service

Service d'authentification, JWT, gestion des utilisateurs et permissions.

Django + Django REST Framework + Simple JWT, géré avec [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync
cp .env.example .env    # ajuster DJANGO_SECRET_KEY et le reste au besoin
git config core.hooksPath .githooks   # active les hooks locaux (une fois)
uv run python manage.py migrate
uv run python manage.py runserver
```

## Routes

| Route | Méthode | Rôle |
|---|---|---|
| `/api/health/` | GET | Healthcheck |
| `/api/token/` | POST | Login → `{access, refresh}` |
| `/api/token/refresh/` | POST | Renouvelle un `access` à partir d'un `refresh` |
