# app.py - Script unifié pour Render
import os
import time
import schedule
import threading
import logging
import json
from flask import Flask, jsonify
from datetime import datetime, timedelta
import pytz
import random
from typing import Dict, List

# Importez vos scripts existants
from scripts.mcdo_standard_automation import automatiser_sondage_mcdo
from scripts.mcdo_morning_automation import automatiser_sondage_mcdo_morning
from scripts.mcdo_night_automation import automatiser_sondage_mcdo_night

# Configuration Flask pour éviter le sleep
app = Flask(__name__)

# Variable globale pour s'assurer que le scheduler ne démarre qu'une fois
scheduler_initialized = False

# Variable globale pour éviter les tests simultanés
test_in_progress = {"status": False, "script": None, "start_time": None}

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

@app.route('/test/standard')
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

def run_standard_survey():
    """Exécute le script standard 10 fois avec pauses aléatoires"""
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🍟 ========== SESSION STANDARD : 10 SONDAGES ==========")
    
    for loop_num in range(1, 11):
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
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(20, 30)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            time.sleep(total_pause)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🍟 ========== FIN SESSION STANDARD ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
    # Logger pour les statistiques globales
    log_execution("STANDARD", total_success > 0, session_duration)
    return total_success > 0

def run_morning_survey():
    """Exécute le script morning 10 fois avec pauses aléatoires"""
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🌅 ========== SESSION MORNING : 10 SONDAGES ==========")
    
    for loop_num in range(1, 11):
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
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(15, 25)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            time.sleep(total_pause)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🌅 ========== FIN SESSION MORNING ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
    # Logger pour les statistiques globales
    log_execution("MORNING", total_success > 0, session_duration)
    return total_success > 0

def run_night_survey():
    """Exécute le script night 10 fois avec pauses aléatoires"""
    session_start_time = time.time()
    total_success = 0
    total_failed = 0
    
    logging.info("🌙 ========== SESSION NIGHT : 10 SONDAGES ==========")
    
    for loop_num in range(1, 11):
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
        
        # Pause aléatoire entre les sondages (sauf pour le dernier)
        if loop_num < 10:
            pause_minutes = random.randint(25, 35)
            pause_seconds = random.randint(0, 59)
            total_pause = (pause_minutes * 60) + pause_seconds
            
            logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
            
            # Calculer l'heure de la prochaine exécution
            next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
            logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
            
            time.sleep(total_pause)
    
    # Statistiques finales
    session_duration = round(time.time() - session_start_time, 2)
    success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
    
    logging.info(f"🌙 ========== FIN SESSION NIGHT ==========")
    logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%)")
    logging.info(f"⏱️ Durée totale session: {session_duration}s ({round(session_duration/60, 1)} minutes)")
    
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