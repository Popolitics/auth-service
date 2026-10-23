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

Les migrations sont conservées dans Git et appliquées au démarrage du conteneur.
Après une modification des modèles, générer la migration avec
`uv run python manage.py makemigrations`, puis ajouter le fichier généré au commit.
Vérifier avant la PR qu'aucune migration ne manque avec
`uv run python manage.py makemigrations --check --dry-run`.

## Tests

Avec PostgreSQL configuré dans `.env` : `uv run coverage run manage.py test --noinput`,
puis `uv run coverage report` et `uv run coverage xml`.
La CI exécute les migrations et les tests sur PostgreSQL 16, puis transmet la couverture à SonarCloud.

## Routes

| Route | Méthode | Rôle |
|---|---|---|
| `/api/health/` | GET | Healthcheck |
| `/api/register/` | POST | Création de compte |
| `/api/login/` | POST | Login → `{access, refresh}` |
| `/api/logout/` | POST | Révoque le refresh token fourni dans `{"refresh": "…"}` ; access token Bearer requis |
| `/api/token/refresh/` | POST | Renouvelle un `access` à partir d'un `refresh` |
| `/api/password-reset/` | POST | `{"email": "…"}` → envoie un lien de réinitialisation (réponse `200` identique que le compte existe ou non) |
| `/api/password-reset/confirm/` | POST | `{"uid", "token", "new_password"}` → `204`, change le mot de passe et révoque les refresh tokens |

Le lien de réinitialisation pointe vers `PASSWORD_RESET_URL?uid=…&token=…` (page frontend) ; il expire après 1 heure
et ne sert qu'une fois.

L'inscription demande un email et un mot de passe ; `username` est facultatif.
Après logout (`204`), supprimer les tokens côté client ; l'access token reste valide jusqu'à expiration (15 minutes maximum).

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
