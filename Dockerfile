# Dockerfile pour Render - McDonald's Survey Bot
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="McDonald's Survey Bot"
LABEL description="Automated McDonald's survey bot running on Render"

# Installation des dépendances système pour Chrome
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libxss1 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Installation de Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Installation de ChromeDriver compatible avec Chrome version installée
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') \
    && CHROME_MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d '.' -f 1) \
    && CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json" | \
       python3 -c "import sys, json; data=json.load(sys.stdin); print(data['builds']['$CHROME_MAJOR_VERSION']['version'])") \
    && wget -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ \
    && rm -rf /tmp/chromedriver* \
    && chmod +x /usr/local/bin/chromedriver

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
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_DRIVER=/usr/local/bin/chromedriver
ENV PYTHONPATH=/app
ENV RENDER=true
ENV TZ=Europe/Paris

# Port exposé
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Commande de démarrage avec Gunicorn pour la production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "180", "--worker-class", "sync", "--max-requests", "50", "--max-requests-jitter", "10", "app:app"]