# app.py - Script unifié pour Render
import os
import time
import schedule
import threading
import logging
import json
from flask import Flask, jsonify
from datetime import datetime
import pytz
from typing import Dict, List

# Importez vos scripts existants
from scripts.mcdo_standard_automation import automatiser_sondage_mcdo
from scripts.mcdo_morning_automation import automatiser_sondage_mcdo_morning
from scripts.mcdo_night_automation import automatiser_sondage_mcdo_night

# Configuration Flask pour éviter le sleep
app = Flask(__name__)

# Variable globale pour s'assurer que le scheduler ne démarre qu'une fois
scheduler_initialized = False

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
            "health_check": "/health",
            "status": "/status",
            "last_run": "/last-run"
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
def last_run():
    """Informations sur les dernières exécutions"""
    return jsonify({
        "last_executions": last_executions,
        "global_stats": global_stats,
        "success_rate": round((global_stats["success"] / max(global_stats["total"], 1)) * 100, 1)
    })

@app.route('/monitoring')
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

def run_standard_survey():
    """Exécute le script standard avec retry logic et monitoring"""
    max_retries = 2
    final_success = False
    final_duration = 0
    final_error = None
    
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"🍟 ========== DÉMARRAGE SCRIPT STANDARD (Tentative {attempt + 1}/{max_retries + 1}) ==========")
            start_time = time.time()
            
            result = automatiser_sondage_mcdo(headless=True)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            final_duration = duration
            
            if result:
                logging.info(f"✅ Script STANDARD terminé avec succès en {duration}s")
                final_success = True
                log_execution("STANDARD", True, duration)
                return True
            else:
                logging.error(f"❌ Script STANDARD échoué après {duration}s")
                final_error = f"Script failed after {duration}s"
                if attempt < max_retries:
                    logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                    time.sleep(30)
                    continue
                
        except Exception as e:
            error_msg = str(e)
            logging.error(f"❌ Erreur script STANDARD (tentative {attempt + 1}): {error_msg}")
            final_error = error_msg
            final_duration = time.time() - start_time if 'start_time' in locals() else 0
            if attempt < max_retries:
                logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                time.sleep(30)
                continue
        
        logging.info("🍟 ========== FIN SCRIPT STANDARD ==========")
    
    logging.error("❌ Échec définitif du script STANDARD après toutes les tentatives")
    log_execution("STANDARD", False, final_duration)
    return False

def run_morning_survey():
    """Exécute le script morning avec retry logic"""
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"🌅 ========== DÉMARRAGE SCRIPT MORNING (Tentative {attempt + 1}/{max_retries + 1}) ==========")
            start_time = time.time()
            
            result = automatiser_sondage_mcdo_morning(headless=True)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            if result:
                logging.info(f"✅ Script MORNING terminé avec succès en {duration}s")
                return True
            else:
                logging.error(f"❌ Script MORNING échoué après {duration}s")
                if attempt < max_retries:
                    logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                    time.sleep(30)
                    continue
                
        except Exception as e:
            logging.error(f"❌ Erreur script MORNING (tentative {attempt + 1}): {str(e)}")
            if attempt < max_retries:
                logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                time.sleep(30)
                continue
        
        logging.info("🌅 ========== FIN SCRIPT MORNING ==========")
    
    logging.error("❌ Échec définitif du script MORNING après toutes les tentatives")
    return False

def run_night_survey():
    """Exécute le script night avec retry logic"""
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"🌙 ========== DÉMARRAGE SCRIPT NIGHT (Tentative {attempt + 1}/{max_retries + 1}) ==========")
            start_time = time.time()
            
            result = automatiser_sondage_mcdo_night(headless=True)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            if result:
                logging.info(f"✅ Script NIGHT terminé avec succès en {duration}s")
                return True
            else:
                logging.error(f"❌ Script NIGHT échoué après {duration}s")
                if attempt < max_retries:
                    logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                    time.sleep(30)
                    continue
                
        except Exception as e:
            logging.error(f"❌ Erreur script NIGHT (tentative {attempt + 1}): {str(e)}")
            if attempt < max_retries:
                logging.info(f"🔄 Nouvelle tentative dans 30 secondes...")
                time.sleep(30)
                continue
        
        logging.info("🌙 ========== FIN SCRIPT NIGHT ==========")
    
    logging.error("❌ Échec définitif du script NIGHT après toutes les tentatives")
    return False

def schedule_surveys():
    """Programme tous les sondages selon les horaires Paris avec monitoring robuste"""
    
    # Script Standard : 12h00 Paris = 10h00 UTC
    schedule.every().day.at("10:00").do(run_standard_survey)
    
    # Script Morning : 10h00 Paris = 08h00 UTC  
    schedule.every().day.at("08:00").do(run_morning_survey)
    
    # Script Night : 19h00 Paris = 17h00 UTC
    schedule.every().day.at("17:00").do(run_night_survey)
    
    logging.info("📅 ========== PLANNING CONFIGURÉ ==========")
    logging.info("   🍟 Standard: 10:00 UTC (12:00 Paris)")
    logging.info("   🌅 Morning:  08:00 UTC (10:00 Paris)")
    logging.info("   🌙 Night:    17:00 UTC (19:00 Paris)")
    logging.info("📅 =========================================")
    
    last_heartbeat = time.time()
    
    # Scheduler optimisé pour Render Free Tier
    while True:
        try:
            schedule.run_pending()
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