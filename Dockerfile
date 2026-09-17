# Dockerfile pour Render - McDonald's Survey Bot
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="McDonald's Survey Bot"
LABEL description="Automated McDonald's survey bot running on Render"

# Installation reproductible de Chromium et ChromeDriver
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Création d'un utilisateur non-root pour la sécurité
RUN useradd --create-home --shell /bin/bash mcdo-bot

# Répertoire de travail
WORKDIR /app

# Copie et installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

# Création du dossier scripts s'il n'existe pas
RUN mkdir -p scripts

# Permissions pour l'utilisateur mcdo-bot
RUN chown -R mcdo-bot:mcdo-bot /app

# Basculer vers l'utilisateur non-root
USER mcdo-bot

# Variables d'environnement
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONPATH=/app
ENV RENDER=true
ENV TZ=Europe/Paris

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"

# Commande de démarrage avec Gunicorn pour la production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "180", "--worker-class", "sync", "--access-logfile", "-", "--max-requests", "50", "--max-requests-jitter", "10", "app:app"]