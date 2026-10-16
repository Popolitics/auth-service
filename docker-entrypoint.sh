#!/bin/sh
set -e

echo "==> Exécution des migrations Django versionnées..."
python manage.py migrate --noinput

echo "==> Rassemblement des fichiers statiques (CSS/JS)..."
python manage.py collectstatic --noinput

echo "==> Démarrage de auth-service..."
exec "$@"
