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

## JWT en RS256 (clé privée/publique)

Seul `auth-service` signe des tokens (clé privée). Tout autre service qui doit
les vérifier (ex. `data-service`) ne reçoit **que** la clé publique — jamais
la clé privée. Génération d'une paire pour un environnement :

```bash
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

Coller le contenu de chaque fichier dans `.env`, avec des `\n` littéraux à la
place des retours à la ligne (voir `.env.example`). Distribuer `public.pem`
aux services consommateurs, garder `private.pem` uniquement ici. En cas de
compromission d'un service consommateur, seule la clé publique fuite —
aucun risque de forger de nouveaux tokens.
