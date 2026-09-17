# 🍟 McDonald's Survey Automation Bot

Bot d'automatisation pour les sondages de satisfaction McDonald's, déployé sur Render.com (Free Tier).

## 📋 Aperçu

Ce bot automatise la complétion des sondages McDonald's à des heures programmées :

- **10:00 Paris** (08:00 UTC) : Sondages livraison matin
- **12:00 Paris** (10:00 UTC) : Sondages restaurant/drive standard
- **19:00 Paris** (17:00 UTC) : Sondages livraison soir

## 🏗️ Architecture

- **Flask Web App** (`app.py`) : Point d'entrée avec endpoints de monitoring
- **Scripts d'automatisation** (`scripts/`) : 3 scripts Selenium spécialisés
- **Docker** : Configuration optimisée pour Render avec Chrome headless
- **Scheduling** : Système de tâches programmées avec retry logic

## 🚀 Déploiement sur Dokploy

Le dépôt contient maintenant un `Dockerfile` et un `docker-compose.yml` prêts pour un déploiement Dokploy.

### Test local

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Le service `web` est publié uniquement sur `127.0.0.1:5000` du serveur Dokploy, jamais sur Internet. Il est donc accessible avec un tunnel SSH, mais pas directement depuis l'extérieur. Les logs du service `scheduler` contiennent les récapitulatifs `[SCHEDULER_RECAP]` et `[DAILY_RECAP]`. Les logs HTTP sont visibles séparément dans le service `web`.

### Accès privé par tunnel SSH

Depuis votre ordinateur :

```bash
ssh -N -L 5000:127.0.0.1:5000 utilisateur@serveur-dokploy
```

Puis ouvrir `http://localhost:5000/login`. Le terminal SSH doit rester ouvert. Le tunnel est chiffré et le port Docker reste inaccessible depuis Internet. Avec un reverse proxy HTTPS Dokploy à la place, définir `SESSION_COOKIE_SECURE=true`.

### Dokploy

1. Créer une application de type **Compose**.
2. Connecter le dépôt Git et sélectionner le fichier `docker-compose.yml`.
3. Déployer les deux services avec un seul replica chacun et un seul worker Gunicorn pour `web`.
4. Configurer le health check interne du service `web` sur `/health`.
5. Prévoir au moins 1 Go de mémoire par service pour Chromium, davantage si plusieurs sondages sont exécutés.

Configurer dans Dokploy les secrets `AUTH_PASSWORD`, `AUTH_SALT` et `SECRET_KEY`. Aucun mot de passe par défaut n'est accepté.

Le scheduler et HTTP sont volontairement deux services distincts. Ne pas augmenter leurs replicas, sinon les sondages seront déclenchés plusieurs fois.

## 🚀 Déploiement historique sur Render

### 1. Prérequis

- Compte Render.com (Free Tier)
- Repository Git avec les fichiers nécessaires
- Clé SSH configurée pour l'authentification GitHub

### 2. Configuration Render

1. Créer un nouveau **Web Service** sur Render
2. Connecter votre repository Git : `ymx-creator/customer-feedback-automation`
3. Configuration automatique via `Dockerfile`
4. Variables d'environnement (optionnel) :
   - `DEBUG=false`
   - `TZ=Europe/Paris`

### 3. Service Live

- **URL principale :** https://customer-feedback-automation.onrender.com
- **Déploiement :** ~5-10 minutes
- **Port :** 5000 (auto-détecté)
- **Status :** Service live 🎉

### 4. Fichiers déployés

```
app.py                    # Point d'entrée Flask
Dockerfile               # Configuration container
requirements.txt         # Dépendances Python
scripts/                 # Scripts d'automatisation
     mcdo_standard_automation.py
     mcdo_morning_automation.py
     mcdo_night_automation.py
```

## 📊 Monitoring en Production

### Endpoints de surveillance

#### `/monitoring` - Statut complet

```json
{
  "service_status": "🟢 ACTIVE",
  "current_time": "12:30 20/07/2025",
  "last_executions": {
    "STANDARD": {
      "timestamp": "12:00 20/07",
      "success": true,
      "duration": 45.2
    },
    "MORNING": {
      "timestamp": "10:00 20/07",
      "success": true,
      "duration": 38.1
    },
    "NIGHT": { "timestamp": "19:00 19/07", "success": false, "duration": 12.5 }
  },
  "success_rate": "87.5%",
  "next_runs": {
    "STANDARD": "12:00 21/07",
    "MORNING": "10:00 21/07",
    "NIGHT": "19:00 20/07"
  }
}
```

#### `/health` - Health check

```json
{
  "status": "healthy",
  "timestamp": 1690123456,
  "message": "Bot is alive and running"
}
```

#### `/last-run` - Dernières exécutions

```json
{
  "last_executions": {...},
  "global_stats": {"total": 24, "success": 21, "failed": 3},
  "success_rate": 87.5
}
```

### 🔍 Détection des problèmes

| Indicateur         | État                | Action                     |
| ------------------ | ------------------- | -------------------------- |
| `"success": true`  | ✅ Sondage complété | RAS                        |
| `"success": false` | ❌ Échec            | Vérifier logs Render       |
| `duration < 20s`   | ⚠️ Échec précoce    | Problème de connexion/site |
| `duration > 120s`  | ⏰ Timeout probable | Surcharge ou blocage       |
| Pas d'exécution    | 🔴 Service arrêté   | Redémarrer le service      |

### 📡 Surveillance UptimeRobot

**Configuration automatique :**

- **Monitor URL :** https://customer-feedback-automation.onrender.com/health
- **Intervalle :** 5 minutes
- **Timeout :** 30 secondes
- **Page de statut :** https://stats.uptimerobot.com/7Xy9sa1Qmi

**Avantages :**

- ✅ Service jamais endormi (Free Tier Render)
- ✅ Alertes automatiques en cas de panne
- ✅ Historique public 90 jours
- ✅ Temps de réponse en temps réel

## 💻 Développement Local

### Installation

```bash
# Cloner le repo
git clone https://github.com/ymx-creator/customer-feedback-automation.git
cd customer-feedback-automation

# Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer dépendances
pip install -r requirements.txt
```

### Tests individuels (mode visuel)

```bash
# Désactiver temporairement headless dans les scripts
# Puis lancer :
python3 scripts/mcdo_morning_automation.py
python3 scripts/mcdo_standard_automation.py
python3 scripts/mcdo_night_automation.py
```

### Lancement local de l'app

```bash
python3 app.py
# Visite http://localhost:5000
```

## ⚙️ Configuration Technique

### Optimisations Render Free Tier

- **Mémoire** : Configuration Chrome allégée (~200MB max)
- **CPU** : Scheduling efficace avec retry logic
- **Logs** : Monitoring simplifié (dernière exécution seulement)
- **Timeouts** : 180s Gunicorn, 25s Selenium

### Sélection d'âge aléatoire

Le bot sélectionne aléatoirement parmi :

- 15-24 ans
- 25-34 ans
- 35-49 ans

(Exclut automatiquement "Moins de 15 ans" et "50 ans et plus")

### Retry Logic

- **3 tentatives** par script en cas d'échec
- **30 secondes** d'attente entre tentatives
- **Logging détaillé** de chaque tentative

## 📋 Logs Render

Les logs Render montrent :

```
2025-07-20 08:00:15 INFO ✅ MORNING: 38.1s
2025-07-20 10:00:22 INFO ✅ STANDARD: 45.2s
2025-07-20 17:00:18 INFO ❌ NIGHT: 12.5s
```

## ⚠️ Limites Render Free Tier

- **750h/mois** : Service s'arrête après épuisement
- **512MB RAM** : Optimisations mémoire appliquées
- **Veille** : Service dort après 15min d'inactivité (réveil automatique)
- **Build time** : ~5-10 minutes pour déployer

## 🔒 Sécurité

- Utilisateur non-root dans Docker (`mcdo-bot`)
- Pas de données sensibles stockées
- Connexions HTTPS uniquement
- Logs anonymisés (pas d'infos personnelles)

## 📈 Performance Attendue

- **Temps d'exécution** : 30-60 secondes par sondage
- **Taux de succès** : >85% en conditions normales
- **Pages complétées** : 8-9 pages par sondage
- **Consommation** : ~30 minutes/jour de compute time

---

**Support** : Vérifiez les logs Render et l'endpoint `/monitoring` pour diagnostiquer les problèmes.
