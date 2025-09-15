# app.py - Script optimisé pour serveur Debian low-spec avec logging détaillé
import os
import time
import threading
import logging
import gc  # Pour la gestion mémoire
from flask import Flask, jsonify
from datetime import datetime, timedelta
import pytz
import random
import json
import re

# Importez vos scripts existants
from scripts.mcdo_standard_automation import automatiser_sondage_mcdo
from scripts.mcdo_morning_automation import automatiser_sondage_mcdo_morning
from scripts.mcdo_night_automation import automatiser_sondage_mcdo_night

# Configuration Flask minimale
app = Flask(__name__)

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Système de monitoring SIMPLIFIÉ
last_executions = {
    "STANDARD": {"timestamp": None, "success": None, "duration": 0},
    "MORNING": {"timestamp": None, "success": None, "duration": 0}, 
    "NIGHT": {"timestamp": None, "success": None, "duration": 0}
}
global_stats = {"total": 0, "success": 0, "failed": 0}

# Protection contre les collisions de threads
active_threads = {
    'standard': None,
    'morning': None, 
    'night': None
}

def log_session_details(script_name, start_time, end_time, total_success, total_failed, session_duration):
    """Enregistrer les détails de session dans un fichier log quotidien"""
    try:
        paris_tz = pytz.timezone('Europe/Paris')
        log_date = datetime.now(paris_tz).strftime('%Y-%m-%d')
        log_filename = f"logs/mcdo_bot_{log_date}.log"
        
        # Créer le dossier logs s'il n'existe pas
        os.makedirs('logs', exist_ok=True)
        
        # Préparer les données de session
        session_data = {
            "script": script_name,
            "date": log_date,
            "start_time": datetime.fromtimestamp(start_time, paris_tz).strftime('%H:%M:%S'),
            "end_time": datetime.fromtimestamp(end_time, paris_tz).strftime('%H:%M:%S'),
            "duration_minutes": round(session_duration / 60, 1),
            "total_surveys": total_success + total_failed,
            "successful_surveys": total_success,
            "failed_surveys": total_failed,
            "success_rate": round((total_success / (total_success + total_failed)) * 100, 1) if (total_success + total_failed) > 0 else 0,
            "status": "SUCCESS" if total_success > 0 else "FAILED"
        }
        
        # Écrire dans le fichier log
        with open(log_filename, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now(paris_tz).strftime('%H:%M:%S')}] SESSION {script_name.upper()}\n")
            f.write(f"  📅 Date: {log_date}\n")
            f.write(f"  🕐 Début: {session_data['start_time']} | Fin: {session_data['end_time']} | Durée: {session_data['duration_minutes']}min\n")
            f.write(f"  📊 Sondages: {session_data['successful_surveys']}/{session_data['total_surveys']} réussis ({session_data['success_rate']}%)\n")
            f.write(f"  🎯 Statut: {session_data['status']}\n")
            f.write(f"  📋 Détails JSON: {json.dumps(session_data, ensure_ascii=False)}\n")
            f.write(f"  {'='*80}\n\n")
        
        # Créer aussi un fichier de résumé quotidien
        create_daily_summary(log_date)
        
        logging.info(f"📝 Session {script_name} loggée dans {log_filename}")
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de l'écriture du log: {str(e)}")

def create_daily_summary(log_date):
    """Créer un résumé quotidien de toutes les sessions"""
    try:
        log_filename = f"logs/mcdo_bot_{log_date}.log"
        summary_filename = f"logs/daily_summary_{log_date}.txt"
        
        if not os.path.exists(log_filename):
            return
        
        # Lire le fichier de log et extraire les sessions
        sessions = []
        with open(log_filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extraire les données JSON de chaque session
        json_matches = re.findall(r'📋 Détails JSON: ({.*?})\n', content)
        
        for match in json_matches:
            try:
                session_data = json.loads(match)
                sessions.append(session_data)
            except:
                continue
        
        # Créer le résumé
        with open(summary_filename, 'w', encoding='utf-8') as f:
            f.write(f"📊 RÉSUMÉ QUOTIDIEN - {log_date}\n")
            f.write(f"{'='*50}\n\n")
            
            if not sessions:
                f.write("❌ Aucune session enregistrée aujourd'hui\n")
                return
            
            total_surveys = sum(s['total_surveys'] for s in sessions)
            total_success = sum(s['successful_surveys'] for s in sessions)
            total_failed = sum(s['failed_surveys'] for s in sessions)
            
            f.write(f"📈 STATISTIQUES GLOBALES:\n")
            f.write(f"  • Sessions exécutées: {len(sessions)}\n")
            f.write(f"  • Total sondages: {total_surveys}\n")
            f.write(f"  • Sondages réussis: {total_success}\n")
            f.write(f"  • Sondages échoués: {total_failed}\n")
            f.write(f"  • Taux de réussite global: {round((total_success/total_surveys)*100, 1) if total_surveys > 0 else 0}%\n\n")
            
            f.write(f"📋 DÉTAIL PAR SESSION:\n")
            for session in sessions:
                status_icon = "✅" if session['status'] == 'SUCCESS' else "❌"
                f.write(f"  {status_icon} {session['script'].upper()}: {session['start_time']}-{session['end_time']} | {session['successful_surveys']}/{session['total_surveys']} ({session['success_rate']}%)\n")
            
            f.write(f"\n💡 PROCHAINES EXÉCUTIONS PRÉVUES:\n")
            f.write(f"  🌅 Morning: 10:00\n")
            f.write(f"  🍟 Standard: 15:00\n")
            f.write(f"  🌙 Night: 19:00\n")
        
        logging.info(f"📋 Résumé quotidien créé: {summary_filename}")
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de la création du résumé: {str(e)}")

def update_execution_stats(script_name, success, duration):
    """Mettre à jour les statistiques d'exécution"""
    global global_stats
    global_stats["total"] += 1
    if success:
        global_stats["success"] += 1
    else:
        global_stats["failed"] += 1
    
    # Mettre à jour seulement la dernière exécution (économie mémoire)
    paris_tz = pytz.timezone('Europe/Paris')
    last_executions[script_name] = {
        "timestamp": datetime.now(paris_tz).strftime("%H:%M %d/%m"),
        "success": success,
        "duration": round(duration, 1)
    }

@app.route('/health')
def health_check():
    """Health check endpoint pour monitoring externe"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "message": "Bot is alive and running"
    }), 200

def run_standard_survey():
    """Exécuter une session complète de 10 sondages STANDARD"""
    global active_threads
    active_threads['standard'] = threading.current_thread()
    
    session_start_time = time.time()
    
    try:
        logging.info("🍟 ========== DÉBUT SESSION STANDARD ==========")
        
        total_success = 0
        total_failed = 0
        
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
                
                # Nettoyage mémoire après chaque sondage
                gc.collect()
                    
            except Exception as e:
                total_failed += 1
                logging.error(f"❌ Erreur sondage STANDARD {loop_num}/10: {str(e)}")
            
            # Pause aléatoire entre les sondages (sauf pour le dernier)
            if loop_num < 10:
                pause_minutes = random.randint(20, 30)
                pause_seconds = random.randint(0, 59)
                total_pause = (pause_minutes * 60) + pause_seconds
                
                next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
                logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
                logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
                
                time.sleep(total_pause)
        
        # Statistiques finales
        session_end_time = time.time()
        session_duration = round(session_end_time - session_start_time, 2)
        success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
        
        logging.info(f"🍟 ========== FIN SESSION STANDARD ==========")
        logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%) en {session_duration}s")
        
        # Logger les détails de la session
        log_session_details("STANDARD", session_start_time, session_end_time, total_success, total_failed, session_duration)
        
        # Forcer le garbage collection en fin de session
        gc.collect()
        
        # Mettre à jour les statistiques
        update_execution_stats("STANDARD", total_success > 0, session_duration)
        return total_success > 0
    
    finally:
        # Nettoyer le thread actif
        active_threads['standard'] = None

def run_morning_survey():
    """Exécuter une session complète de 10 sondages MORNING"""
    global active_threads
    active_threads['morning'] = threading.current_thread()
    
    session_start_time = time.time()
    
    try:
        logging.info("🌅 ========== DÉBUT SESSION MORNING ==========")
        
        total_success = 0
        total_failed = 0
        
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
                
                # Nettoyage mémoire après chaque sondage
                gc.collect()
                    
            except Exception as e:
                total_failed += 1
                logging.error(f"❌ Erreur sondage MORNING {loop_num}/10: {str(e)}")
            
            # Pause aléatoire entre les sondages - RÉDUITE (sauf pour le dernier)
            if loop_num < 10:
                pause_minutes = random.randint(10, 15)  # Réduit de 15-25 à 10-15
                pause_seconds = random.randint(0, 59)
                total_pause = (pause_minutes * 60) + pause_seconds
                
                next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
                logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
                logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
                
                time.sleep(total_pause)
        
        # Statistiques finales
        session_end_time = time.time()
        session_duration = round(session_end_time - session_start_time, 2)
        success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
        
        logging.info(f"🌅 ========== FIN SESSION MORNING ==========")
        logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%) en {session_duration}s")
        
        # Logger les détails de la session
        log_session_details("MORNING", session_start_time, session_end_time, total_success, total_failed, session_duration)
        
        # Forcer le garbage collection en fin de session
        gc.collect()
        
        # Mettre à jour les statistiques
        update_execution_stats("MORNING", total_success > 0, session_duration)
        return total_success > 0
    
    finally:
        # Nettoyer le thread actif
        active_threads['morning'] = None

def run_night_survey():
    """Exécuter une session complète de 10 sondages NIGHT"""
    global active_threads
    active_threads['night'] = threading.current_thread()
    
    session_start_time = time.time()
    
    try:
        logging.info("🌙 ========== DÉBUT SESSION NIGHT ==========")
        
        total_success = 0
        total_failed = 0
        
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
                
                # Nettoyage mémoire après chaque sondage
                gc.collect()
                    
            except Exception as e:
                total_failed += 1
                logging.error(f"❌ Erreur sondage NIGHT {loop_num}/10: {str(e)}")
            
            # Pause aléatoire entre les sondages (sauf pour le dernier)
            if loop_num < 10:
                pause_minutes = random.randint(25, 35)
                pause_seconds = random.randint(0, 59)
                total_pause = (pause_minutes * 60) + pause_seconds
                
                next_time = datetime.now(pytz.timezone('Europe/Paris')) + timedelta(seconds=total_pause)
                logging.info(f"⏰ Pause de {pause_minutes}min {pause_seconds}s avant sondage {loop_num + 1}/10")
                logging.info(f"🕐 Prochain sondage prévu à {next_time.strftime('%H:%M:%S')}")
                
                time.sleep(total_pause)
        
        # Statistiques finales
        session_end_time = time.time()
        session_duration = round(session_end_time - session_start_time, 2)
        success_rate = round((total_success / 10) * 100, 1) if total_success > 0 else 0
        
        logging.info(f"🌙 ========== FIN SESSION NIGHT ==========")
        logging.info(f"📊 Résultats: {total_success}/10 succès ({success_rate}%) en {session_duration}s")
        
        # Logger les détails de la session
        log_session_details("NIGHT", session_start_time, session_end_time, total_success, total_failed, session_duration)
        
        # Forcer le garbage collection en fin de session
        gc.collect()
        
        # Mettre à jour les statistiques
        update_execution_stats("NIGHT", total_success > 0, session_duration)
        return total_success > 0
    
    finally:
        # Nettoyer le thread actif
        active_threads['night'] = None

def is_thread_active(script_name):
    """Vérifier si un thread est encore actif"""
    thread = active_threads.get(script_name)
    return thread is not None and thread.is_alive()

def schedule_surveys():
    """Scheduler avec protection contre les collisions"""
    
    print("📅 ========== SCHEDULER ANTI-COLLISION + LOGGING DÉMARRÉ ==========")
    print("   🌅 Morning:  10:00 Paris (pauses réduites 10-15min)") 
    print("   🍟 Standard: 15:00 Paris (décalé pour éviter collision)")
    print("   🌙 Night:    19:00 Paris")
    print("   📝 Logs: dossier ./logs/ (résumés quotidiens)")
    
    logging.info("📅 ========== SCHEDULER ANTI-COLLISION + LOGGING DÉMARRÉ ==========")
    logging.info("   🌅 Morning:  10:00 Paris (pauses réduites 10-15min)")
    logging.info("   🍟 Standard: 15:00 Paris (décalé pour éviter collision)")
    logging.info("   🌙 Night:    19:00 Paris")
    logging.info("   📝 Logs: dossier ./logs/ (résumés quotidiens)")
    
    executed_today = {
        'standard': False,
        'morning': False, 
        'night': False
    }
    
    last_date = datetime.now(pytz.timezone('Europe/Paris')).date()
    
    while True:
        try:
            paris_tz = pytz.timezone('Europe/Paris')
            current_time = datetime.now(paris_tz)
            current_hour = current_time.hour
            current_minute = current_time.minute
            current_date = current_time.date()
            
            # Reset quotidien
            if current_date != last_date:
                executed_today = {'standard': False, 'morning': False, 'night': False}
                last_date = current_date
                logging.info(f"🗓️ Nouveau jour - Reset des exécutions: {current_date}")
            
            # Morning: 10:00 Paris
            if (current_hour == 10 and current_minute == 0 and 
                not executed_today['morning'] and 
                not is_thread_active('morning')):
                logging.info("🌅 DÉCLENCHEMENT Morning - 10:00 Paris")
                executed_today['morning'] = True
                thread = threading.Thread(target=run_morning_survey, daemon=True)
                thread.start()
            
            # Standard: 15:00 Paris (décalé pour éviter collision avec Morning)
            elif (current_hour == 15 and current_minute == 0 and 
                  not executed_today['standard'] and 
                  not is_thread_active('standard')):
                logging.info("🍟 DÉCLENCHEMENT Standard - 15:00 Paris")
                executed_today['standard'] = True
                thread = threading.Thread(target=run_standard_survey, daemon=True)
                thread.start()
            
            # Night: 19:00 Paris
            elif (current_hour == 19 and current_minute == 0 and 
                  not executed_today['night'] and 
                  not is_thread_active('night')):
                logging.info("🌙 DÉCLENCHEMENT Night - 19:00 Paris")
                executed_today['night'] = True
                thread = threading.Thread(target=run_night_survey, daemon=True)
                thread.start()
            
            # Vérification des collisions (optionnel - pour monitoring)
            active_count = sum(1 for name in ['standard', 'morning', 'night'] if is_thread_active(name))
            if active_count > 1:
                active_scripts = [name for name in ['standard', 'morning', 'night'] if is_thread_active(name)]
                logging.warning(f"⚠️ {active_count} scripts actifs simultanément: {active_scripts}")
            
            # Pause de 60 secondes entre les vérifications
            time.sleep(60)
            
        except Exception as e:
            logging.error(f"❌ Erreur dans le scheduler: {str(e)}")
            time.sleep(60)

if __name__ == '__main__':
    # Démarrer le scheduler dans un thread séparé
    scheduler_thread = threading.Thread(target=schedule_surveys, daemon=True)
    scheduler_thread.start()
    
    # Configuration Flask pour faible consommation
    app.config.update(
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max
        SEND_FILE_MAX_AGE_DEFAULT=3600,  # Cache 1h
        THREADED=False,  # Pas de multithreading
        DEBUG=False,
        JSONIFY_PRETTYPRINT_REGULAR=False
    )
    
    # Récupérer le port depuis les variables d'environnement ou utiliser 5000 par défaut
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    logging.info(f"🚀 Démarrage du bot McDonald's sur le port {port}")
    
    # Lancer Flask avec configuration optimisée
    app.run(
        host="0.0.0.0", 
        port=port, 
        debug=debug_mode,
        threaded=False,  # Désactiver le multithreading
        processes=1      # Un seul processus
    )