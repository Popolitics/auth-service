#!/bin/sh
set -e

echo "==> Génération des migrations Django si nécessaires..."
python manage.py makemigrations accounts --noinput

echo "==> Attente et exécution des migrations Django..."
python manage.py migrate --noinput

echo "==> Rassemblement des fichiers statiques (CSS/JS)..."
python manage.py collectstatic --noinput

echo "==> Démarrage de auth-service..."
exec "$@"