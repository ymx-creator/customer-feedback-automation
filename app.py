# app.py - Script unifié pour Render
import os
import time
import schedule
import threading
import logging
import json
from flask import Flask, jsonify, render_template_string, request, redirect, session, url_for
from datetime import datetime, timedelta
import pytz
import random
import hashlib
import secrets
from functools import wraps
from typing import Dict, List

# Importez vos scripts existants
from scripts.mcdo_standard_automation import automatiser_sondage_mcdo
from scripts.mcdo_morning_automation import automatiser_sondage_mcdo_morning
from scripts.mcdo_night_automation import automatiser_sondage_mcdo_night

# Configuration Flask sécurisée
app = Flask(__name__)

# Configuration sécurisée pour l'authentification
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
AUTH_PASSWORD_HASH = None

def init_auth():
    """Initialise le système d'authentification de manière sécurisée"""
    global AUTH_PASSWORD_HASH
    
    # Récupérer le mot de passe depuis les variables d'environnement
    auth_password = os.environ.get('AUTH_PASSWORD', 'admin123')  # Mot de passe par défaut pour dev
    
    # Hasher le mot de passe avec sel pour la sécurité
    salt = os.environ.get('AUTH_SALT', 'mcdo_bot_2024')
    AUTH_PASSWORD_HASH = hashlib.pbkdf2_hmac('sha256', 
                                           auth_password.encode('utf-8'), 
                                           salt.encode('utf-8'), 
                                           100000)  # 100k itérations pour la sécurité
    
    logging.info("🔐 Système d'authentification initialisé")

# Initialiser l'auth au démarrage
init_auth()

def verify_password(password):
    """Vérifie le mot de passe de manière sécurisée"""
    global AUTH_PASSWORD_HASH
    if not AUTH_PASSWORD_HASH:
        return False
    
    # Hasher le mot de passe fourni avec le même sel
    salt = os.environ.get('AUTH_SALT', 'mcdo_bot_2024')
    provided_hash = hashlib.pbkdf2_hmac('sha256', 
                                      password.encode('utf-8'), 
                                      salt.encode('utf-8'), 
                                      100000)
    
    # Comparaison sécurisée pour éviter les attaques par timing
    return secrets.compare_digest(AUTH_PASSWORD_HASH, provided_hash)

def require_auth(f):
    """Décorateur pour protéger les routes avec authentification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Vérifier si l'utilisateur est authentifié
        if not session.get('authenticated'):
            # Rediriger vers la page de login
            return redirect(url_for('login'))
        
        # Vérifier l'expiration de la session (4 heures)
        login_time = session.get('login_time')
        if not login_time or (time.time() - login_time) > 14400:  # 4 heures = 14400 secondes
            session.clear()
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

# Variable globale pour s'assurer que le scheduler ne démarre qu'une fois
scheduler_initialized = False

# Variable globale pour éviter les tests simultanés
test_in_progress = {"status": False, "script": None, "start_time": None}

# Variable globale pour l'arrêt d'urgence
stop_requested = False

# Actions en cours détaillées pour le monitoring
current_actions = {
    "main_action": None,  # "SESSION_STANDARD", "SESSION_MORNING", etc.
    "sub_action": None,   # "SONDAGE_3/10", "PAUSE_15min", etc.
    "progress": 0,        # Pourcentage de progression
    "next_step": None,    # "Prochain sondage à 14:35", etc.
    "can_stop": False     # Si on peut arrêter maintenant
}

# Configuration du calendrier de planification
calendar_config = {
    "enabled": False,     # False = tous les jours, True = jours sélectionnés seulement
    "selected_days": []   # Liste des jours du mois [1,2,5,10...] quand enabled=True
}

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Système de monitoring SIMPLIFIÉ pour Render Free
last_executions = {
    "STANDARD": {"timestamp": None, "success": None, "duration": 0},
    "MORNING": {"timestamp": None, "success": None, "duration": 0}, 
    "NIGHT": {"timestamp": None, "success": None, "duration": 0}
}
global_stats = {"total": 0, "success": 0, "failed": 0}

def log_execution(script_name: str, success: bool, duration: float):
    """Enregistre l'exécution simple pour Render Free Tier"""
    global last_executions, global_stats
    
    # Mettre à jour seulement la dernière exécution (économie mémoire)
    paris_tz = pytz.timezone('Europe/Paris')
    last_executions[script_name] = {
        "timestamp": datetime.now(paris_tz).strftime("%H:%M %d/%m"),
        "success": success,
        "duration": round(duration, 1)
    }
    
    # Stats globales minimales
    global_stats["total"] += 1
    if success:
        global_stats["success"] += 1
    else:
        global_stats["failed"] += 1
    
    # Log essentiel seulement
    status = "✅" if success else "❌"
    logging.info(f"{status} {script_name}: {duration:.1f}s")

def update_current_action(main_action=None, sub_action=None, progress=0, next_step=None, can_stop=False):
    """Met à jour les actions en cours pour le monitoring"""
    global current_actions
    if main_action is not None:
        current_actions["main_action"] = main_action
    if sub_action is not None:
        current_actions["sub_action"] = sub_action
    current_actions["progress"] = progress
    if next_step is not None:
        current_actions["next_step"] = next_step
    current_actions["can_stop"] = can_stop

def clear_current_action():
    """Efface les actions en cours"""
    global current_actions
    current_actions = {
        "main_action": None,
        "sub_action": None, 
        "progress": 0,
        "next_step": None,
        "can_stop": False
    }

def check_stop_requested():
    """Vérifie si un arrêt a été demandé"""
    global stop_requested
    if stop_requested:
        logging.info("🛑 ARRÊT DEMANDÉ - Interruption en cours...")
        return True
    return False

def should_execute_today():
    """Vérifie si on doit exécuter les sondages aujourd'hui selon la planification"""
    global calendar_config
    
    # Si le calendrier n'est pas activé, exécuter tous les jours (comportement par défaut)
    if not calendar_config["enabled"]:
        return True
    
    # Si le calendrier est activé, vérifier si aujourd'hui est dans les jours sélectionnés
    today = datetime.now().day
    is_scheduled = today in calendar_config["selected_days"]
    
    if not is_scheduled:
        logging.info(f"📅 Exécution annulée pour aujourd'hui (jour {today}) - Non planifié dans le calendrier")
    
    return is_scheduled

@app.route('/')
def home():
    """Page d'accueil avec informations sur le bot"""
    paris_tz = pytz.timezone('Europe/Paris')
    current_time = datetime.now(paris_tz)
    
    return jsonify({
        "status": "🍟 McDonald's Survey Bot Active",
        "service": "Running on Render Free Tier",
        "version": "2.0.0",
        "time_paris": current_time.strftime("%H:%M:%S %d/%m/%Y"),
        "timezone": "Europe/Paris",
        "scripts": {
            "standard": {
                "description": "Restaurant/Drive orders",
                "schedule": "Daily at 12:00 Paris (10:00 UTC)",
                "mode": "Standard"
            },
            "morning": {
                "description": "Delivery orders - Morning",
                "schedule": "Daily at 10:00 Paris (08:00 UTC)",
                "mode": "Livraison Matin"
            },
            "night": {
                "description": "Delivery orders - Evening", 
                "schedule": "Daily at 19:00 Paris (17:00 UTC)",
                "mode": "Livraison Soir"
            }
        },
        "monitoring": {
            "dashboard": "/dashboard",
            "health_check": "/health",
            "status": "/status",
            "last_run": "/last-run",
            "full_monitoring": "/monitoring"
        },
        "testing": {
            "test_standard": "/test/standard",
            "test_morning": "/test/morning", 
            "test_night": "/test/night",
            "test_all": "/test/all",
            "test_status": "/test/status"
        }
    })

@app.route('/health')
def health_check():
    """Health check endpoint pour UptimeRobot"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "message": "Bot is alive and running",
        "uptime": "Render Free Tier 750h/month"
    }), 200

@app.route('/status')
@require_auth
def status():
    """Informations détaillées sur le planning"""
    paris_tz = pytz.timezone('Europe/Paris')
    current_time = datetime.now(paris_tz)
    
    # Calcul des prochaines exécutions
    next_runs = []
    
    # Prochaine exécution standard (12h Paris)
    next_standard = current_time.replace(hour=12, minute=0, second=0, microsecond=0)
    if current_time.hour >= 12:
        next_standard = next_standard.replace(day=next_standard.day + 1)
    
    # Prochaine exécution morning (10h Paris)
    next_morning = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
    if current_time.hour >= 10:
        next_morning = next_morning.replace(day=next_morning.day + 1)
    
    # Prochaine exécution night (19h Paris)
    next_night = current_time.replace(hour=19, minute=0, second=0, microsecond=0)
    if current_time.hour >= 19:
        next_night = next_night.replace(day=next_night.day + 1)
    
    return jsonify({
        "current_time_paris": current_time.strftime("%H:%M:%S %d/%m/%Y"),
        "next_executions": {
            "standard": {
                "next_run": next_standard.strftime("%H:%M %d/%m/%Y"),
                "utc_time": "10:00 UTC",
                "description": "Restaurant/Drive surveys"
            },
            "morning": {
                "next_run": next_morning.strftime("%H:%M %d/%m/%Y"),
                "utc_time": "08:00 UTC", 
                "description": "Delivery surveys - Morning"
            },
            "night": {
                "next_run": next_night.strftime("%H:%M %d/%m/%Y"),
                "utc_time": "17:00 UTC",
                "description": "Delivery surveys - Evening"
            }
        },
        "scheduler_active": True,
        "environment": "Render"
    })

@app.route('/last-run')
@require_auth
def last_run():
    """Informations sur les dernières exécutions"""
    return jsonify({
        "last_executions": last_executions,
        "global_stats": global_stats,
        "success_rate": round((global_stats["success"] / max(global_stats["total"], 1)) * 100, 1)
    })

@app.route('/monitoring')
@require_auth
def monitoring():
    """Endpoint de monitoring simplifié pour Render Free"""
    paris_tz = pytz.timezone('Europe/Paris')
    current_time = datetime.now(paris_tz)
    
    # Prochaines exécutions
    next_standard = current_time.replace(hour=12, minute=0, second=0, microsecond=0)
    if current_time.hour >= 12:
        from datetime import timedelta
        next_standard = next_standard + timedelta(days=1)
    
    next_morning = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
    if current_time.hour >= 10:
        from datetime import timedelta
        next_morning = next_morning + timedelta(days=1)
    
    next_night = current_time.replace(hour=19, minute=0, second=0, microsecond=0)
    if current_time.hour >= 19:
        from datetime import timedelta
        next_night = next_night + timedelta(days=1)
    
    return jsonify({
        "service_status": "🟢 ACTIVE",
        "current_time": current_time.strftime("%H:%M %d/%m/%Y"),
        "last_executions": last_executions,
        "global_stats": global_stats,
        "success_rate": f"{round((global_stats['success'] / max(global_stats['total'], 1)) * 100, 1)}%",
        "next_runs": {
            "STANDARD": next_standard.strftime("%H:%M %d/%m"),
            "MORNING": next_morning.strftime("%H:%M %d/%m"),
            "NIGHT": next_night.strftime("%H:%M %d/%m")
        }
    })

@app.route('/test/standard')
@require_auth
def test_standard():
    """Test manuel du script standard en production"""
    global test_in_progress
    
    # Vérifier qu'aucun test n'est en cours
    if test_in_progress["status"]:
        return jsonify({
            "status": "error",
            "message": f"Test déjà en cours: {test_in_progress['script']}",
            "current_test": test_in_progress
        }), 409
    
    # Marquer le test comme en cours
    test_in_progress = {
        "status": True,
        "script": "standard",
        "start_time": time.time()
    }
    
    try:
        logging.info("🧪 ========== TEST MANUEL SCRIPT STANDARD ==========")
        start_time = time.time()
        
        result = run_standard_survey()
        
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        
        # Réinitialiser le statut de test
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "completed",
            "script": "standard",
            "success": result,
            "duration": duration,
            "message": "Test standard complété avec succès" if result else "Test standard échoué",
            "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
        })
        
    except Exception as e:
        # Réinitialiser le statut de test en cas d'erreur
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "failed",
            "script": "standard",
            "success": False,
            "error": str(e),
            "message": f"Erreur lors du test standard: {str(e)}"
        }), 500

@app.route('/test/morning')
@require_auth
def test_morning():
    """Test manuel du script morning en production"""
    global test_in_progress
    
    # Vérifier qu'aucun test n'est en cours
    if test_in_progress["status"]:
        return jsonify({
            "status": "error",
            "message": f"Test déjà en cours: {test_in_progress['script']}",
            "current_test": test_in_progress
        }), 409
    
    # Marquer le test comme en cours
    test_in_progress = {
        "status": True,
        "script": "morning",
        "start_time": time.time()
    }
    
    try:
        logging.info("🧪 ========== TEST MANUEL SCRIPT MORNING ==========")
        start_time = time.time()
        
        result = run_morning_survey()
        
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        
        # Réinitialiser le statut de test
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "completed",
            "script": "morning",
            "success": result,
            "duration": duration,
            "message": "Test morning complété avec succès" if result else "Test morning échoué",
            "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
        })
        
    except Exception as e:
        # Réinitialiser le statut de test en cas d'erreur
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "failed",
            "script": "morning",
            "success": False,
            "error": str(e),
            "message": f"Erreur lors du test morning: {str(e)}"
        }), 500

@app.route('/test/night')
@require_auth
def test_night():
    """Test manuel du script night en production"""
    global test_in_progress
    
    # Vérifier qu'aucun test n'est en cours
    if test_in_progress["status"]:
        return jsonify({
            "status": "error",
            "message": f"Test déjà en cours: {test_in_progress['script']}",
            "current_test": test_in_progress
        }), 409
    
    # Marquer le test comme en cours
    test_in_progress = {
        "status": True,
        "script": "night",
        "start_time": time.time()
    }
    
    try:
        logging.info("🧪 ========== TEST MANUEL SCRIPT NIGHT ==========")
        start_time = time.time()
        
        result = run_night_survey()
        
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        
        # Réinitialiser le statut de test
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "completed",
            "script": "night",
            "success": result,
            "duration": duration,
            "message": "Test night complété avec succès" if result else "Test night échoué",
            "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
        })
        
    except Exception as e:
        # Réinitialiser le statut de test en cas d'erreur
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "failed",
            "script": "night",
            "success": False,
            "error": str(e),
            "message": f"Erreur lors du test night: {str(e)}"
        }), 500

@app.route('/test/all')
@require_auth
def test_all():
    """Test manuel de tous les scripts en séquence"""
    global test_in_progress
    
    # Vérifier qu'aucun test n'est en cours
    if test_in_progress["status"]:
        return jsonify({
            "status": "error",
            "message": f"Test déjà en cours: {test_in_progress['script']}",
            "current_test": test_in_progress
        }), 409
    
    # Marquer le test comme en cours
    test_in_progress = {
        "status": True,
        "script": "all",
        "start_time": time.time()
    }
    
    results = {
        "morning": {"success": False, "duration": 0, "error": None},
        "standard": {"success": False, "duration": 0, "error": None},
        "night": {"success": False, "duration": 0, "error": None}
    }
    
    total_start_time = time.time()
    
    try:
        logging.info("🧪 ========== TEST MANUEL - TOUS LES SCRIPTS ==========")
        
        # Test Morning
        logging.info("🌅 Test MORNING en cours...")
        start_time = time.time()
        try:
            results["morning"]["success"] = run_morning_survey()
            results["morning"]["duration"] = round(time.time() - start_time, 2)
        except Exception as e:
            results["morning"]["error"] = str(e)
            results["morning"]["duration"] = round(time.time() - start_time, 2)
        
        # Test Standard
        logging.info("🍟 Test STANDARD en cours...")
        start_time = time.time()
        try:
            results["standard"]["success"] = run_standard_survey()
            results["standard"]["duration"] = round(time.time() - start_time, 2)
        except Exception as e:
            results["standard"]["error"] = str(e)
            results["standard"]["duration"] = round(time.time() - start_time, 2)
        
        # Test Night
        logging.info("🌙 Test NIGHT en cours...")
        start_time = time.time()
        try:
            results["night"]["success"] = run_night_survey()
            results["night"]["duration"] = round(time.time() - start_time, 2)
        except Exception as e:
            results["night"]["error"] = str(e)
            results["night"]["duration"] = round(time.time() - start_time, 2)
        
        total_duration = round(time.time() - total_start_time, 2)
        total_success = sum(1 for r in results.values() if r["success"])
        
        # Réinitialiser le statut de test
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "completed",
            "script": "all",
            "total_duration": total_duration,
            "success_count": total_success,
            "total_tests": 3,
            "success_rate": round((total_success / 3) * 100, 1),
            "results": results,
            "message": f"Tests terminés: {total_success}/3 succès",
            "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
        })
        
    except Exception as e:
        # Réinitialiser le statut de test en cas d'erreur
        test_in_progress = {"status": False, "script": None, "start_time": None}
        
        return jsonify({
            "status": "failed",
            "script": "all",
            "success": False,
            "error": str(e),
            "results": results,
            "message": f"Erreur lors des tests: {str(e)}"
        }), 500

@app.route('/test/status')
@require_auth
def test_status():
    """Statut des tests en cours"""
    global test_in_progress
    
    if test_in_progress["status"]:
        duration = round(time.time() - test_in_progress["start_time"], 2)
        return jsonify({
            "test_in_progress": True,
            "script": test_in_progress["script"],
            "duration": duration,
            "start_time": test_in_progress["start_time"]
        })
    else:
        return jsonify({
            "test_in_progress": False,
            "message": "Aucun test en cours"
        })

@app.route('/dashboard')
@require_auth
def dashboard():
    """Page de monitoring simple avec contrôles"""
    html_template = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🍟 McDonald's Bot - Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: hsl(224, 71%, 4%);
            color: hsl(213, 31%, 91%);
            min-height: 100vh; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { 
            background: hsl(224, 71%, 4%);
            border: 1px solid hsl(216, 34%, 17%);
            border-radius: 12px; padding: 20px; 
            margin-bottom: 20px; 
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }
        .header { text-align: center; color: hsl(213, 31%, 91%); margin-bottom: 30px; }
        .header h1 { font-weight: 600; margin-bottom: 8px; }
        .header p { color: hsl(215, 20%, 65%); font-size: 0.875rem; }
        
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .btn { 
            padding: 12px 16px; border: none; border-radius: 8px; 
            font-weight: 500; cursor: pointer; transition: all 0.2s;
            text-decoration: none; display: inline-block; text-align: center;
            font-size: 14px;
        }
        .btn-success { background: hsl(142, 76%, 36%); color: hsl(355, 7%, 97%); }
        .btn-success:hover { background: hsl(142, 76%, 33%); }
        .btn-warning { background: hsl(48, 96%, 53%); color: hsl(224, 71%, 4%); }
        .btn-warning:hover { background: hsl(48, 96%, 50%); }
        .btn-danger { background: hsl(0, 84%, 60%); color: hsl(355, 7%, 97%); }
        .btn-danger:hover { background: hsl(0, 84%, 57%); }
        .btn-info { background: hsl(199, 89%, 48%); color: hsl(355, 7%, 97%); }
        .btn-info:hover { background: hsl(199, 89%, 45%); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        .action-display {
            background: hsl(220, 13%, 9%);
            border: 1px solid hsl(216, 34%, 17%);
            border-left: 3px solid hsl(262, 83%, 58%);
            padding: 16px; border-radius: 8px; margin: 16px 0;
        }
        .progress-bar {
            background: hsl(216, 34%, 17%); border-radius: 10px; height: 8px; 
            overflow: hidden; margin: 12px 0;
        }
        .progress-fill {
            background: hsl(262, 83%, 58%);
            height: 100%; transition: width 0.5s ease;
        }
        .status-indicator {
            display: inline-block; width: 8px; height: 8px;
            border-radius: 50%; margin-right: 8px;
        }
        .status-online { background: hsl(142, 76%, 36%); }
        .status-busy { background: hsl(48, 96%, 53%); }
        .status-offline { background: hsl(0, 84%, 60%); }
        
        .stats { display: flex; justify-content: space-around; text-align: center; }
        .stat-item h3 { color: hsl(262, 83%, 58%); font-size: 2em; margin-bottom: 5px; font-weight: 600; }
        .stat-item p { color: hsl(215, 20%, 65%); font-size: 0.875rem; }
        
        h2 { color: hsl(213, 31%, 91%); font-weight: 600; margin-bottom: 16px; font-size: 1.25rem; }
        
        #next-executions li { color: hsl(215, 20%, 65%); margin-bottom: 4px; }
        #last-executions p { color: hsl(215, 20%, 65%); margin-bottom: 4px; }
        
        /* Styles du calendrier */
        .calendar-grid {
            display: grid; 
            grid-template-columns: repeat(7, 1fr); 
            gap: 8px; 
            margin-bottom: 16px;
        }
        
        .calendar-day {
            width: 40px; height: 40px; border: 1px solid hsl(216, 34%, 17%);
            background: hsl(224, 71%, 4%); color: hsl(213, 31%, 91%);
            border-radius: 8px; cursor: pointer; transition: all 0.2s;
            display: flex; align-items: center; justify-content: center;
            font-weight: 500; font-size: 14px;
            min-width: 0; /* Permet au flex item de rétrécir */
        }
        .calendar-day:hover {
            border-color: hsl(262, 83%, 58%);
            background: hsl(224, 71%, 6%);
        }
        .calendar-day.selected {
            background: hsl(262, 83%, 58%);
            border-color: hsl(262, 83%, 58%);
            color: hsl(210, 40%, 98%);
        }
        .calendar-day.today {
            border-color: hsl(142, 76%, 36%);
            box-shadow: 0 0 0 2px hsl(142, 76%, 36%, 0.3);
        }
        
        @media (max-width: 768px) {
            .container { padding: 16px; }
            .status-grid { grid-template-columns: 1fr; }
            body { padding: 16px; }
            
            /* Calendrier responsive */
            .calendar-grid {
                gap: 6px;
            }
            
            .calendar-day {
                width: 36px; 
                height: 36px;
                font-size: 12px;
            }
        }
        
        @media (max-width: 480px) {
            /* Très petits écrans */
            .calendar-grid {
                gap: 4px;
            }
            
            .calendar-day {
                width: 32px; 
                height: 32px;
                font-size: 11px;
            }
        }
        
        @media (max-width: 360px) {
            /* Très très petits écrans */
            .calendar-grid {
                gap: 3px;
            }
            
            .calendar-day {
                width: 28px; 
                height: 28px;
                font-size: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🍟 McDonald's Survey Bot</h1>
            <p>Dashboard de Monitoring - Render Free Tier</p>
            <p id="current-time">Chargement...</p>
        </div>

        <!-- Actions en cours -->
        <div class="card">
            <h2>🚀 Actions en cours</h2>
            <div id="current-actions" class="action-display">
                <div id="main-action">Aucune action en cours</div>
                <div id="sub-action" style="color: #666; font-size: 0.9em;"></div>
                <div id="progress-container" style="display: none;">
                    <div class="progress-bar">
                        <div id="progress-fill" class="progress-fill" style="width: 0%;"></div>
                    </div>
                    <div id="progress-text"></div>
                </div>
                <div id="next-step" style="margin-top: 10px; color: #007bff;"></div>
            </div>
        </div>

        <!-- Contrôles -->
        <div class="card">
            <h2>🎮 Contrôles</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
                <button class="btn btn-success" onclick="testQuick('standard')">🍟 Test Standard</button>
                <button class="btn btn-success" onclick="testQuick('morning')">🌅 Test Morning</button>
                <button class="btn btn-success" onclick="testQuick('night')">🌙 Test Night</button>
                <button class="btn btn-danger" onclick="stopTests()" id="stop-btn">🛑 ARRÊT D'URGENCE</button>
                <button class="btn btn-info" onclick="refreshData()">🔄 Actualiser</button>
                <button class="btn btn-warning" onclick="clearLogs()">🗑️ Clear Logs</button>
                <a href="/logout" class="btn" style="background: #6c757d; color: white;">🚪 Déconnexion</a>
            </div>
        </div>

        <div class="status-grid">
            <!-- Statut du service -->
            <div class="card">
                <h2>📊 Statut du Service</h2>
                <div id="service-status">
                    <p><span id="status-indicator" class="status-indicator status-online"></span><span id="status-text">En ligne</span></p>
                    <p><strong>Prochaines exécutions:</strong></p>
                    <ul id="next-executions">
                        <li>Chargement...</li>
                    </ul>
                </div>
            </div>

            <!-- Dernières exécutions -->
            <div class="card">
                <h2>📈 Dernières Exécutions</h2>
                <div id="last-executions">Chargement...</div>
            </div>

            <!-- Statistiques globales -->
            <div class="card">
                <h2>📊 Statistiques</h2>
                <div class="stats">
                    <div class="stat-item">
                        <h3 id="total-count">-</h3>
                        <p>Total</p>
                    </div>
                    <div class="stat-item">
                        <h3 id="success-count">-</h3>
                        <p>Succès</p>
                    </div>
                    <div class="stat-item">
                        <h3 id="success-rate">-</h3>
                        <p>Taux</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Planification Calendaire -->
        <div class="card">
            <h2>📅 Planification Calendaire</h2>
            <div style="margin-bottom: 16px;">
                <label style="display: flex; align-items: center; margin-bottom: 12px; cursor: pointer;">
                    <input type="checkbox" id="calendar-enabled" style="margin-right: 8px; width: 16px; height: 16px;">
                    <span>Activer la planification personnalisée (sinon exécution quotidienne)</span>
                </label>
            </div>
            
            <div id="calendar-section" style="display: none;">
                <div style="margin-bottom: 16px;">
                    <button class="btn btn-info" onclick="selectWeekdays()" style="margin-right: 8px; font-size: 12px; padding: 8px 12px;">📅 Jours de semaine</button>
                    <button class="btn btn-info" onclick="selectWeekends()" style="margin-right: 8px; font-size: 12px; padding: 8px 12px;">🎉 Week-ends</button>
                    <button class="btn btn-warning" onclick="clearSelection()" style="font-size: 12px; padding: 8px 12px;">🗑️ Tout effacer</button>
                </div>
                
                <div id="calendar-grid" class="calendar-grid">
                    <!-- Les jours seront générés par JavaScript -->
                </div>
                
                <div style="text-align: center;">
                    <button class="btn btn-success" onclick="saveCalendar()">💾 Sauvegarder la planification</button>
                </div>
            </div>
            
            <div id="calendar-status" style="margin-top: 16px; padding: 12px; background: hsl(220, 13%, 9%); border-radius: 8px; border: 1px solid hsl(216, 34%, 17%);">
                Chargement de la configuration...
            </div>
        </div>
    </div>

    <script>
        let refreshInterval;
        
        function updateTime() {
            const now = new Date();
            const paris = new Date(now.toLocaleString("en-US", {timeZone: "Europe/Paris"}));
            document.getElementById('current-time').textContent = 
                '🕐 ' + paris.toLocaleString('fr-FR');
        }
        
        function refreshData() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateDashboard(data);
                })
                .catch(error => {
                    console.error('Erreur:', error);
                    document.getElementById('status-indicator').className = 'status-indicator status-offline';
                    document.getElementById('status-text').textContent = 'Erreur de connexion';
                });
        }
        
        function updateDashboard(data) {
            // Statut du service
            document.getElementById('status-indicator').className = 'status-indicator status-online';
            document.getElementById('status-text').textContent = 'En ligne';
            
            // Actions en cours
            const actions = data.current_actions;
            if (actions.main_action) {
                document.getElementById('main-action').innerHTML = 
                    '<strong>' + actions.main_action + '</strong>';
                document.getElementById('sub-action').textContent = actions.sub_action || '';
                
                if (actions.progress > 0) {
                    document.getElementById('progress-container').style.display = 'block';
                    document.getElementById('progress-fill').style.width = actions.progress + '%';
                    document.getElementById('progress-text').textContent = actions.progress + '%';
                } else {
                    document.getElementById('progress-container').style.display = 'none';
                }
                
                document.getElementById('next-step').textContent = actions.next_step || '';
                
                // Bouton stop
                document.getElementById('stop-btn').disabled = !actions.can_stop;
                if (actions.can_stop) {
                    document.getElementById('status-indicator').className = 'status-indicator status-busy';
                    document.getElementById('status-text').textContent = 'Occupé';
                }
            } else {
                document.getElementById('main-action').textContent = 'Aucune action en cours';
                document.getElementById('sub-action').textContent = '';
                document.getElementById('progress-container').style.display = 'none';
                document.getElementById('next-step').textContent = '';
                document.getElementById('stop-btn').disabled = true;
            }
            
            // Prochaines exécutions
            const nextExec = data.next_executions;
            document.getElementById('next-executions').innerHTML = 
                '<li>🍟 Standard: ' + nextExec.STANDARD + '</li>' +
                '<li>🌅 Morning: ' + nextExec.MORNING + '</li>' +
                '<li>🌙 Night: ' + nextExec.NIGHT + '</li>';
            
            // Dernières exécutions
            const lastExec = data.last_executions;
            document.getElementById('last-executions').innerHTML = 
                Object.keys(lastExec).map(key => {
                    const exec = lastExec[key];
                    const status = exec.success === null ? '⏳' : (exec.success ? '✅' : '❌');
                    return '<p>' + status + ' ' + key + ': ' + (exec.timestamp || 'Jamais') + 
                           (exec.duration ? ' (' + exec.duration + 's)' : '') + '</p>';
                }).join('');
            
            // Statistiques
            const stats = data.global_stats;
            document.getElementById('total-count').textContent = stats.total;
            document.getElementById('success-count').textContent = stats.success;
            document.getElementById('success-rate').textContent = 
                stats.total > 0 ? Math.round((stats.success / stats.total) * 100) + '%' : '0%';
        }
        
        function testQuick(script) {
            if (confirm('Lancer un test rapide ' + script + ' (1 sondage) ?')) {
                fetch('/test/quick/' + script, {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message || 'Test lancé');
                        refreshData();
                    });
            }
        }
        
        function stopTests() {
            if (confirm('ARRÊTER tous les tests en cours ?')) {
                fetch('/api/stop', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message || 'Arrêt demandé');
                        refreshData();
                    });
            }
        }
        
        function clearLogs() {
            if (confirm('Effacer les logs et statistiques ?')) {
                fetch('/api/clear', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message || 'Logs effacés');
                        refreshData();
                    });
            }
        }
        
        // Initialisation
        updateTime();
        refreshData();
        setInterval(updateTime, 1000);
        
        // Auto-refresh toutes les 30 secondes si la page est visible
        function startAutoRefresh() {
            refreshInterval = setInterval(() => {
                if (!document.hidden) {
                    refreshData();
                }
            }, 30000);
        }
        
        // Pause si la page n'est pas visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                clearInterval(refreshInterval);
            } else {
                startAutoRefresh();
            }
        });
        
        startAutoRefresh();
        
        // ========== FONCTIONS CALENDRIER ==========
        let calendarConfig = { enabled: false, selected_days: [] };
        
        function initCalendar() {
            const grid = document.getElementById('calendar-grid');
            const today = new Date().getDate();
            
            // Créer 31 jours
            for (let day = 1; day <= 31; day++) {
                const dayElement = document.createElement('div');
                dayElement.className = 'calendar-day';
                dayElement.textContent = day;
                dayElement.dataset.day = day;
                
                if (day === today) {
                    dayElement.classList.add('today');
                }
                
                dayElement.addEventListener('click', () => toggleDay(day));
                grid.appendChild(dayElement);
            }
            
            // Charger la configuration
            loadCalendarConfig();
        }
        
        function toggleDay(day) {
            const dayElement = document.querySelector(`[data-day="${day}"]`);
            const index = calendarConfig.selected_days.indexOf(day);
            
            if (index > -1) {
                calendarConfig.selected_days.splice(index, 1);
                dayElement.classList.remove('selected');
            } else {
                calendarConfig.selected_days.push(day);
                dayElement.classList.add('selected');
            }
            
            updateCalendarStatus();
        }
        
        function selectWeekdays() {
            // Jours de semaine (approximatif): 1,2,3,4,5,8,9,10,11,12,15,16,17,18,19,22,23,24,25,26,29,30,31
            const weekdays = [];
            for (let day = 1; day <= 31; day++) {
                const date = new Date(2024, 0, day); // Janvier 2024 comme référence
                const dayOfWeek = date.getDay(); // 0=dimanche, 1=lundi, ..., 6=samedi
                if (dayOfWeek >= 1 && dayOfWeek <= 5) {
                    weekdays.push(day);
                }
            }
            
            calendarConfig.selected_days = [...weekdays];
            updateCalendarDisplay();
            updateCalendarStatus();
        }
        
        function selectWeekends() {
            // Week-ends (approximatif): samedi et dimanche
            const weekends = [];
            for (let day = 1; day <= 31; day++) {
                const date = new Date(2024, 0, day); // Janvier 2024 comme référence
                const dayOfWeek = date.getDay(); // 0=dimanche, 6=samedi
                if (dayOfWeek === 0 || dayOfWeek === 6) {
                    weekends.push(day);
                }
            }
            
            calendarConfig.selected_days = [...weekends];
            updateCalendarDisplay();
            updateCalendarStatus();
        }
        
        function clearSelection() {
            calendarConfig.selected_days = [];
            updateCalendarDisplay();
            updateCalendarStatus();
        }
        
        function updateCalendarDisplay() {
            // Mettre à jour l'affichage des jours sélectionnés
            document.querySelectorAll('.calendar-day').forEach(day => {
                const dayNum = parseInt(day.dataset.day);
                if (calendarConfig.selected_days.includes(dayNum)) {
                    day.classList.add('selected');
                } else {
                    day.classList.remove('selected');
                }
            });
        }
        
        function updateCalendarStatus() {
            const statusDiv = document.getElementById('calendar-status');
            const enabled = document.getElementById('calendar-enabled').checked;
            
            if (!enabled) {
                statusDiv.innerHTML = '🟢 <strong>Mode quotidien activé</strong> - Les sondages s\\'exécutent tous les jours automatiquement';
            } else if (calendarConfig.selected_days.length === 0) {
                statusDiv.innerHTML = '⚠️ <strong>Aucun jour sélectionné</strong> - Les sondages ne s\\'exécuteront jamais';
            } else {
                const sortedDays = [...calendarConfig.selected_days].sort((a, b) => a - b);
                statusDiv.innerHTML = `🗓️ <strong>Planification personnalisée</strong> - Exécution les jours: ${sortedDays.join(', ')} du mois`;
            }
        }
        
        function loadCalendarConfig() {
            fetch('/api/calendar')
                .then(response => response.json())
                .then(data => {
                    calendarConfig = data;
                    
                    // Mettre à jour l'interface
                    document.getElementById('calendar-enabled').checked = data.enabled;
                    toggleCalendarSection();
                    updateCalendarDisplay();
                    updateCalendarStatus();
                })
                .catch(error => {
                    console.error('Erreur de chargement calendrier:', error);
                    document.getElementById('calendar-status').innerHTML = '❌ Erreur de chargement de la configuration';
                });
        }
        
        function saveCalendar() {
            const enabled = document.getElementById('calendar-enabled').checked;
            const config = {
                enabled: enabled,
                selected_days: enabled ? calendarConfig.selected_days : []
            };
            
            fetch('/api/calendar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('✅ Configuration sauvegardée avec succès!');
                        calendarConfig = config;
                        updateCalendarStatus();
                    } else {
                        alert('❌ Erreur: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Erreur de sauvegarde:', error);
                    alert('❌ Erreur de sauvegarde');
                });
        }
        
        function toggleCalendarSection() {
            const enabled = document.getElementById('calendar-enabled').checked;
            const section = document.getElementById('calendar-section');
            section.style.display = enabled ? 'block' : 'none';
            updateCalendarStatus();
        }
        
        // Event listeners pour le calendrier
        document.getElementById('calendar-enabled').addEventListener('change', toggleCalendarSection);
        
        // Initialiser le calendrier au chargement
        setTimeout(initCalendar, 500);
    </script>
</body>
</html>
    '''
    return render_template_string(html_template)

@app.route('/api/status')
@require_auth
def api_status():
    """API endpoint pour les données du dashboard"""
    paris_tz = pytz.timezone('Europe/Paris')
    current_time = datetime.now(paris_tz)
    
    # Calcul des prochaines exécutions
    next_standard = current_time.replace(hour=12, minute=0, second=0, microsecond=0)
    if current_time.hour >= 12:
        next_standard = next_standard + timedelta(days=1)
    
    next_morning = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
    if current_time.hour >= 10:
        next_morning = next_morning + timedelta(days=1)
    
    next_night = current_time.replace(hour=19, minute=0, second=0, microsecond=0)
    if current_time.hour >= 19:
        next_night = next_night + timedelta(days=1)
    
    return jsonify({
        "current_time": current_time.strftime("%H:%M:%S %d/%m/%Y"),
        "current_actions": current_actions,
        "last_executions": last_executions,
        "global_stats": global_stats,
        "next_executions": {
            "STANDARD": next_standard.strftime("%H:%M %d/%m"),
            "MORNING": next_morning.strftime("%H:%M %d/%m"),
            "NIGHT": next_night.strftime("%H:%M %d/%m")
        },
        "test_in_progress": test_in_progress["status"],
        "stop_requested": stop_requested
    })

@app.route('/api/stop', methods=['POST'])
@require_auth
def api_stop():
    """Endpoint pour arrêter les tests en cours"""
    global stop_requested
    stop_requested = True
    
    logging.info("🛑 ARRÊT D'URGENCE demandé via API")
    
    return jsonify({
        "status": "success",
        "message": "Arrêt d'urgence activé. Les tests vont s'arrêter au prochain point de contrôle."
    })

@app.route('/api/clear', methods=['POST'])
@require_auth
def api_clear():
    """Endpoint pour effacer les logs et statistiques"""
    global last_executions, global_stats
    
    # Réinitialiser les statistiques
    last_executions = {
        "STANDARD": {"timestamp": None, "success": None, "duration": 0},
        "MORNING": {"timestamp": None, "success": None, "duration": 0}, 
        "NIGHT": {"timestamp": None, "success": None, "duration": 0}
    }
    global_stats = {"total": 0, "success": 0, "failed": 0}
    
    logging.info("🗑️ Logs et statistiques effacés via API")
    
    return jsonify({
        "status": "success",
        "message": "Logs et statistiques effacés avec succès."
    })

@app.route('/api/calendar', methods=['GET'])
@require_auth
def api_calendar_get():
    """Récupère la configuration du calendrier"""
    global calendar_config
    return jsonify(calendar_config)

@app.route('/api/calendar', methods=['POST'])
@require_auth
def api_calendar_post():
    """Met à jour la configuration du calendrier"""
    global calendar_config
    
    try:
        data = request.get_json()
        
        # Validation des données
        if 'enabled' not in data:
            return jsonify({"error": "Le champ 'enabled' est requis"}), 400
        
        enabled = bool(data['enabled'])
        selected_days = data.get('selected_days', [])
        
        # Validation des jours sélectionnés
        if enabled and not selected_days:
            return jsonify({"error": "Au moins un jour doit être sélectionné en mode calendrier"}), 400
        
        if selected_days:
            # Vérifier que tous les jours sont dans la plage 1-31
            if not all(isinstance(day, int) and 1 <= day <= 31 for day in selected_days):
                return jsonify({"error": "Les jours doivent être des entiers entre 1 et 31"}), 400
        
        # Mettre à jour la configuration
        calendar_config["enabled"] = enabled
        calendar_config["selected_days"] = sorted(list(set(selected_days)))  # Dédoublonner et trier
        
        # Log de la modification
        if enabled:
            logging.info(f"📅 Calendrier activé : {len(selected_days)} jours sélectionnés {selected_days}")
        else:
            logging.info("📅 Calendrier désactivé : mode quotidien rétabli")
        
        return jsonify({
            "status": "success",
            "message": f"Calendrier {'activé' if enabled else 'désactivé'} avec succès",
            "config": calendar_config
        })
        
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la mise à jour : {str(e)}"}), 500

@app.route('/test/quick/<script>', methods=['POST'])
@require_auth
def test_quick(script):
    """Test rapide avec un seul sondage"""
    global test_in_progress
    
    # Vérifier qu'aucun test n'est en cours
    if test_in_progress["status"]:
        return jsonify({
            "status": "error",
            "message": f"Test déjà en cours: {test_in_progress['script']}"
        }), 409
    
    # Scripts disponibles
    available_scripts = {
        "standard": automatiser_sondage_mcdo,
        "morning": automatiser_sondage_mcdo_morning,
        "night": automatiser_sondage_mcdo_night
    }
    
    if script not in available_scripts:
        return jsonify({
            "status": "error",
            "message": f"Script '{script}' non reconnu. Disponibles: {list(available_scripts.keys())}"
        }), 400
    
    # Marquer le test comme en cours
    test_in_progress = {
        "status": True,
        "script": f"quick_{script}",
        "start_time": time.time()
    }
    
    try:
        logging.info(f"🧪 ========== TEST RAPIDE {script.upper()} (1 SONDAGE) ==========")
        update_current_action(f"TEST_QUICK_{script.upper()}", "Exécution en cours...", 50, None, True)
        
        start_time = time.time()
        result = available_scripts[script](headless=True)
        duration = round(time.time() - start_time, 2)
        
        # Réinitialiser les statuts
        test_in_progress = {"status": False, "script": None, "start_time": None}
        clear_current_action()
        
        # Logger pour les statistiques
        log_execution(f"QUICK_{script.upper()}", result, duration)
        
        return jsonify({
            "status": "completed",
            "script": f"quick_{script}",
            "success": result,
            "duration": duration,
            "message": f"Test rapide {script} {'réussi' if result else 'échoué'} en {duration}s",
            "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
        })
        
    except Exception as e:
        # Réinitialiser les statuts en cas d'erreur
        test_in_progress = {"status": False, "script": None, "start_time": None}
        clear_current_action()
        
        return jsonify({
            "status": "failed",
            "script": f"quick_{script}",
            "success": False,
            "error": str(e),
            "message": f"Erreur lors du test rapide {script}: {str(e)}"
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de login sécurisée"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        # Vérification du mot de passe
        if verify_password(password):
            # Authentification réussie
            session['authenticated'] = True
            session['login_time'] = time.time()
            session.permanent = True
            
            logging.info("🔐 Connexion réussie")
            return redirect(url_for('dashboard'))
        else:
            # Mot de passe incorrect
            logging.warning("🔐 Tentative de connexion échouée")
            error_message = "Mot de passe incorrect"
    else:
        error_message = None
    
    # Afficher la page de login
    login_template = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔐 McDonald's Bot - Connexion</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: hsl(224, 71%, 4%);
            color: hsl(213, 31%, 91%);
            min-height: 100vh; 
            display: flex; align-items: center; justify-content: center;
        }
        .login-container {
            background: hsl(224, 71%, 4%);
            border: 1px solid hsl(216, 34%, 17%);
            border-radius: 12px; 
            padding: 40px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            max-width: 400px; 
            width: 90%;
        }
        .header {
            text-align: center; margin-bottom: 30px;
        }
        .header h1 {
            color: hsl(213, 31%, 91%);
            margin-bottom: 8px;
            font-weight: 600;
        }
        .header p {
            color: hsl(215, 20%, 65%);
            font-size: 0.875rem;
        }
        .form-group {
            margin-bottom: 24px;
        }
        .form-group input {
            width: 100%; 
            padding: 12px 16px; 
            background: hsl(224, 71%, 4%);
            border: 1px solid hsl(216, 34%, 17%);
            border-radius: 8px; 
            font-size: 16px;
            color: hsl(213, 31%, 91%);
            transition: all 0.2s;
        }
        .form-group input::placeholder {
            color: hsl(215, 20%, 65%);
        }
        .form-group input:focus {
            outline: none; 
            border-color: hsl(262, 83%, 58%);
            box-shadow: 0 0 0 2px hsl(262, 83%, 58%, 0.2);
        }
        .btn-login {
            width: 100%; 
            background: hsl(262, 83%, 58%);
            color: hsl(210, 40%, 98%);
            border: none; 
            padding: 12px 16px; 
            border-radius: 8px;
            font-size: 16px; 
            font-weight: 500;
            cursor: pointer; 
            transition: all 0.2s;
        }
        .btn-login:hover {
            background: hsl(262, 83%, 55%);
        }
        .btn-login:active {
            transform: translateY(0.5px);
        }
        .error-message {
            background: hsl(0, 84%, 60%, 0.1);
            color: hsl(0, 84%, 60%);
            padding: 12px 16px; 
            border-radius: 8px;
            margin-bottom: 20px; 
            border: 1px solid hsl(0, 84%, 60%, 0.2);
            font-size: 0.875rem;
        }
        @media (max-width: 768px) {
            .login-container { 
                padding: 32px 24px; 
                margin: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="login-container">
        {% if error_message %}
        <div class="error-message">
            {{ error_message }}
        </div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <input type="password" id="password" name="password" 
                       required autocomplete="current-password"
                       placeholder="Password">
            </div>
            
            <button type="submit" class="btn-login">
                GO
            </button>
        </form>
    </div>
</body>
</html>
    '''
    
    return render_template_string(login_template, error_message=error_message)

@app.route('/logout')
def logout():
    """Déconnexion et suppression de la session"""
    session.clear()
    logging.info("🔐 Déconnexion effectuée")
    return redirect(url_for('login'))

@app.route('/force/standard')
@require_auth
def force_standard():
    """Force l'exécution immédiate du script standard (pour debug)"""
    logging.info("🔧 FORCE MANUELLE - Exécution Standard demandée")
    
    # Exécuter dans un thread pour ne pas bloquer la requête
    thread = threading.Thread(target=run_standard_survey, daemon=True)
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": "Exécution Standard forcée",
        "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
    })

@app.route('/force/morning')
@require_auth  
def force_morning():
    """Force l'exécution immédiate du script morning (pour debug)"""
    logging.info("🔧 FORCE MANUELLE - Exécution Morning demandée")
    
    # Exécuter dans un thread pour ne pas bloquer la requête
    thread = threading.Thread(target=run_morning_survey, daemon=True)
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": "Exécution Morning forcée", 
        "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
    })

@app.route('/force/night')
@require_auth
def force_night():
    """Force l'exécution immédiate du script night (pour debug)"""
    logging.info("🔧 FORCE MANUELLE - Exécution Night demandée")
    
    # Exécuter dans un thread pour ne pas bloquer la requête
    thread = threading.Thread(target=run_night_survey, daemon=True)
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": "Exécution Night forcée",
        "timestamp": datetime.now(pytz.timezone('Europe/Paris')).strftime("%H:%M:%S %d/%m/%Y")
    })

def run_standard_survey():
    """Exécute le script standard 10 fois avec pauses aléatoires"""
    global stop_requested
    
    # Vérifier si on doit exécuter aujourd'hui selon la planification
    if not should_execute_today():
        logging.info("🍟 Session STANDARD annulée : jour non planifié dans le calendrier")
        return False
    
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🍟 ========== SESSION STANDARD : 10 SONDAGES ==========")
    update_current_action("SESSION_STANDARD", "Démarrage de la session...", 0, "10 sondages prévus", True)
    
    # Réinitialiser le flag d'arrêt pour cette session
    stop_requested = False
    
    for loop_num in range(1, 11):
        # Vérifier l'arrêt demandé
        if check_stop_requested():
            logging.info(f"🛑 Session STANDARD interrompue au sondage {loop_num}/10")
            update_current_action("SESSION_STANDARD", "Arrêtée par l'utilisateur", (loop_num-1)*10, f"Session interrompue", False)
            clear_current_action()
            return total_success > 0
        
        progress = (loop_num / 10) * 100
        update_current_action("SESSION_STANDARD", f"Sondage {loop_num}/10 en cours", progress, f"Exécution du sondage {loop_num}", True)
        
        logging.info(f"🍟 ========== SONDAGE STANDARD {loop_num}/10 ==========")
        
        try:
            start_time = time.time()
            result = automatiser_sondage_mcdo(headless=True)
            duration = round(time.time() - start_time, 2)
            
            if result:
                total_success += 1
                logging.info(f"✅ Sondage STANDARD {loop_num}/10 terminé avec succès en {duration}s")
            else:
                total_failed += 1
                logging.error(f"❌ Sondage STANDARD {loop_num}/10 échoué après {duration}s")
                
        except Exception as e:
            total_failed += 1
            logging.error(f"❌ Erreur sondage STANDARD {loop_num}/10: {str(e)}")
        
        # Vérifier l'arrêt demandé avant la pause
        if check_stop_requested():
            logging.info(f"🛑 Session STANDARD interrompue après sondage {loop_num}/10")
            clear_current_action()
            return total_success > 0
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(20, 30)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            next_step = f"Prochain sondage ({loop_num + 1}/10) à {next_time.strftime('%H:%M:%S')}"
            
            update_current_action("SESSION_STANDARD", f"Pause {pause_minutes}min {pause_seconds}s", progress, next_step, True)
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            # Pause avec vérification d'arrêt toutes les 30 secondes
            for sleep_chunk in range(0, total_pause, 30):
                if check_stop_requested():
                    logging.info(f"🛑 Session STANDARD interrompue pendant la pause")
                    clear_current_action()
                    return total_success > 0
                chunk_sleep = min(30, total_pause - sleep_chunk)
                time.sleep(chunk_sleep)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🍟 ========== FIN SESSION STANDARD ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
    clear_current_action()
    
    # Logger pour les statistiques globales
    log_execution("STANDARD", total_success > 0, session_duration)
    return total_success > 0

def run_morning_survey():
    """Exécute le script morning 10 fois avec pauses aléatoires"""
    global stop_requested
    
    # Vérifier si on doit exécuter aujourd'hui selon la planification
    if not should_execute_today():
        logging.info("🌅 Session MORNING annulée : jour non planifié dans le calendrier")
        return False
    
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🌅 ========== SESSION MORNING : 10 SONDAGES ==========")
    update_current_action("SESSION_MORNING", "Démarrage de la session...", 0, "10 sondages prévus", True)
    
    # Réinitialiser le flag d'arrêt pour cette session
    stop_requested = False
    
    for loop_num in range(1, 11):
        # Vérifier l'arrêt demandé
        if check_stop_requested():
            logging.info(f"🛑 Session MORNING interrompue au sondage {loop_num}/10")
            clear_current_action()
            return total_success > 0
        
        progress = (loop_num / 10) * 100
        update_current_action("SESSION_MORNING", f"Sondage {loop_num}/10 en cours", progress, f"Exécution du sondage {loop_num}", True)
        
        logging.info(f"🌅 ========== SONDAGE MORNING {loop_num}/10 ==========")
        
        try:
            start_time = time.time()
            result = automatiser_sondage_mcdo_morning(headless=True)
            duration = round(time.time() - start_time, 2)
            
            if result:
                total_success += 1
                logging.info(f"✅ Sondage MORNING {loop_num}/10 terminé avec succès en {duration}s")
            else:
                total_failed += 1
                logging.error(f"❌ Sondage MORNING {loop_num}/10 échoué après {duration}s")
                
        except Exception as e:
            total_failed += 1
            logging.error(f"❌ Erreur sondage MORNING {loop_num}/10: {str(e)}")
        
        # Vérifier l'arrêt demandé avant la pause
        if check_stop_requested():
            logging.info(f"🛑 Session MORNING interrompue après sondage {loop_num}/10")
            clear_current_action()
            return total_success > 0
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(15, 25)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            next_step = f"Prochain sondage ({loop_num + 1}/10) à {next_time.strftime('%H:%M:%S')}"
            
            update_current_action("SESSION_MORNING", f"Pause {pause_minutes}min {pause_seconds}s", progress, next_step, True)
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            # Pause avec vérification d'arrêt toutes les 30 secondes
            for sleep_chunk in range(0, total_pause, 30):
                if check_stop_requested():
                    logging.info(f"🛑 Session MORNING interrompue pendant la pause")
                    clear_current_action()
                    return total_success > 0
                chunk_sleep = min(30, total_pause - sleep_chunk)
                time.sleep(chunk_sleep)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🌅 ========== FIN SESSION MORNING ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
    clear_current_action()
    
    # Logger pour les statistiques globales
    log_execution("MORNING", total_success > 0, session_duration)
    return total_success > 0

def run_night_survey():
    """Exécute le script night 10 fois avec pauses aléatoires"""
    global stop_requested
    
    # Vérifier si on doit exécuter aujourd'hui selon la planification
    if not should_execute_today():
        logging.info("🌙 Session NIGHT annulée : jour non planifié dans le calendrier")
        return False
    
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🌙 ========== SESSION NIGHT : 10 SONDAGES ==========")
    update_current_action("SESSION_NIGHT", "Démarrage de la session...", 0, "10 sondages prévus", True)
    
    # Réinitialiser le flag d'arrêt pour cette session
    stop_requested = False
    
    for loop_num in range(1, 11):
        # Vérifier l'arrêt demandé
        if check_stop_requested():
            logging.info(f"🛑 Session NIGHT interrompue au sondage {loop_num}/10")
            clear_current_action()
            return total_success > 0
        
        progress = (loop_num / 10) * 100
        update_current_action("SESSION_NIGHT", f"Sondage {loop_num}/10 en cours", progress, f"Exécution du sondage {loop_num}", True)
        
        logging.info(f"🌙 ========== SONDAGE NIGHT {loop_num}/10 ==========")
        
        try:
            start_time = time.time()
            result = automatiser_sondage_mcdo_night(headless=True)
            duration = round(time.time() - start_time, 2)
            
            if result:
                total_success += 1
                logging.info(f"✅ Sondage NIGHT {loop_num}/10 terminé avec succès en {duration}s")
            else:
                total_failed += 1
                logging.error(f"❌ Sondage NIGHT {loop_num}/10 échoué après {duration}s")
                
        except Exception as e:
            total_failed += 1
            logging.error(f"❌ Erreur sondage NIGHT {loop_num}/10: {str(e)}")
        
        # Vérifier l'arrêt demandé avant la pause
        if check_stop_requested():
            logging.info(f"🛑 Session NIGHT interrompue après sondage {loop_num}/10")
            clear_current_action()
            return total_success > 0
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(25, 35)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            next_step = f"Prochain sondage ({loop_num + 1}/10) à {next_time.strftime('%H:%M:%S')}"
            
            update_current_action("SESSION_NIGHT", f"Pause {pause_minutes}min {pause_seconds}s", progress, next_step, True)
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            # Pause avec vérification d'arrêt toutes les 30 secondes
            for sleep_chunk in range(0, total_pause, 30):
                if check_stop_requested():
                    logging.info(f"🛑 Session NIGHT interrompue pendant la pause")
                    clear_current_action()
                    return total_success > 0
                chunk_sleep = min(30, total_pause - sleep_chunk)
                time.sleep(chunk_sleep)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🌙 ========== FIN SESSION NIGHT ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
    clear_current_action()
    
    # Logger pour les statistiques globales
    log_execution("NIGHT", total_success > 0, session_duration)
    return total_success > 0

def schedule_surveys():
    """Programme tous les sondages selon les horaires Paris avec monitoring robuste"""
    
    # Script Standard : 12h00 Paris = 10h00 UTC
    schedule.every().day.at("10:00").do(run_standard_survey)
    
    # Script Morning : 10h00 Paris = 08h00 UTC  
    schedule.every().day.at("08:00").do(run_morning_survey)
    
    # Script Night : 19h00 Paris = 17h00 UTC
    schedule.every().day.at("17:00").do(run_night_survey)
    
    # Afficher les heures actuelles pour debug
    paris_tz = pytz.timezone('Europe/Paris')
    utc_tz = pytz.timezone('UTC')
    now_paris = datetime.now(paris_tz)
    now_utc = datetime.now(utc_tz)
    
    logging.info("📅 ========== PLANNING CONFIGURÉ ==========")
    logging.info(f"🕐 Heure actuelle Paris: {now_paris.strftime('%H:%M %d/%m/%Y')}")
    logging.info(f"🕐 Heure actuelle UTC: {now_utc.strftime('%H:%M %d/%m/%Y')}")
    logging.info("   🍟 Standard: 10:00 UTC (12:00 Paris)")
    logging.info("   🌅 Morning:  08:00 UTC (10:00 Paris)")
    logging.info("   🌙 Night:    17:00 UTC (19:00 Paris)")
    
    # Prochaines exécutions
    for job in schedule.jobs:
        logging.info(f"⏰ Prochaine {job.job_func.__name__}: {job.next_run}")
    
    logging.info("📅 =========================================")
    
    loop_count = 0
    
    # Scheduler optimisé pour Render Free Tier
    while True:
        try:
            # Log périodique pour confirmer que le scheduler fonctionne
            loop_count += 1
            if loop_count % 10 == 0:  # Toutes les 10 minutes
                current_time = datetime.now(utc_tz)
                logging.info(f"💓 Scheduler actif - UTC: {current_time.strftime('%H:%M:%S')} - Cycle {loop_count}")
                
                # Log des prochaines exécutions
                for job in schedule.jobs:
                    time_until = (job.next_run - datetime.now()).total_seconds()
                    hours_until = time_until / 3600
                    logging.info(f"⏰ {job.job_func.__name__} dans {hours_until:.1f}h ({job.next_run.strftime('%H:%M %d/%m')})")
            
            # Vérifier les jobs en attente
            pending_jobs = schedule.run_pending()
            if pending_jobs:
                logging.info(f"🚀 Exécution de {len(pending_jobs)} job(s) planifié(s)")
            
            time.sleep(60)  # Vérification simple chaque minute
        except Exception as e:
            logging.error(f"❌ Scheduler error: {str(e)}")
            time.sleep(60)

def start_scheduler():
    """Démarre le planificateur en arrière-plan"""
    scheduler_thread = threading.Thread(target=schedule_surveys, daemon=True)
    scheduler_thread.start()
    logging.info("🔄 Planificateur démarré en arrière-plan")

def test_scripts():
    """Fonction de test optionnelle pour vérifier que les scripts fonctionnent"""
    logging.info("🧪 ========== TEST DES SCRIPTS ==========")
    
    # Décommentez pour tester un script spécifique
    # logging.info("Test du script STANDARD...")
    # run_standard_survey()
    
    # logging.info("Test du script MORNING...")
    # run_morning_survey()
    
    # logging.info("Test du script NIGHT...")
    # run_night_survey()
    
    logging.info("🧪 Tests terminés (commentés par défaut)")

# Initialisation automatique du scheduler pour Gunicorn
def initialize_scheduler_for_gunicorn():
    """Démarre le scheduler automatiquement même avec Gunicorn"""
    global scheduler_initialized
    if not scheduler_initialized:
        print("🚀 INITIALISATION AUTOMATIQUE DU SCHEDULER (GUNICORN)")
        print(f"🔄 Worker PID: {os.getpid()}")
        
        # Vérifier si on doit démarrer le scheduler sur ce worker
        worker_id = os.environ.get('WORKER_ID', '0')
        print(f"👷 Worker ID: {worker_id}")
        
        start_scheduler()
        scheduler_initialized = True
        print("✅ SCHEDULER INITIALISÉ POUR GUNICORN")

# Démarrer automatiquement le scheduler
initialize_scheduler_for_gunicorn()

if __name__ == "__main__":
    print("🚀 ========== DÉMARRAGE McDONALD'S SURVEY BOT ==========")
    print("🐳 Plateforme: Render Free Tier")
    print("⏰ Timezone: Europe/Paris")
    print("🔄 Mode: Automatique avec planificateur")
    logging.info("🚀 ========== DÉMARRAGE McDONALD'S SURVEY BOT ==========")
    logging.info("🐳 Plateforme: Render Free Tier")
    logging.info("⏰ Timezone: Europe/Paris")
    logging.info("🔄 Mode: Automatique avec planificateur")
    
    # Variables d'environnement
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("DEBUG", "false").lower() == "true"
    
    # Test optionnel au démarrage (décommentez si nécessaire)
    # test_scripts()
    
    # Démarrer le planificateur
    print("🔄 Démarrage du scheduler...")
    start_scheduler()
    print("✅ Scheduler démarré")
    
    # Message de démarrage
    print(f"🌐 Serveur Flask démarrant sur le port {port}")
    logging.info(f"🌐 Serveur Flask démarrant sur le port {port}")
    logging.info("📡 Endpoints disponibles:")
    logging.info("   - / : Informations générales")
    logging.info("   - /health : Health check (pour UptimeRobot)")
    logging.info("   - /status : Planning détaillé")
    logging.info("   - /last-run : Dernières exécutions")
    
    # Démarrer l'API Flask (obligatoire pour éviter le sleep Render)
    app.run(host="0.0.0.0", port=port, debug=debug_mode)