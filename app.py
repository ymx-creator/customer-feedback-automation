# app.py - Script unifié pour Render
import os
import time
import schedule
import threading
import logging
import json
from flask import Flask, jsonify, render_template_string
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

@app.route('/dashboard')
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333; min-height: 100vh; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { 
            background: white; border-radius: 12px; padding: 20px; 
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header { text-align: center; color: white; margin-bottom: 30px; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .btn { 
            padding: 12px 24px; border: none; border-radius: 8px; 
            font-weight: bold; cursor: pointer; transition: all 0.3s;
            text-decoration: none; display: inline-block; text-align: center;
        }
        .btn-success { background: #28a745; color: white; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-info { background: #17a2b8; color: white; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        
        .action-display {
            background: #f8f9fa; border-left: 4px solid #007bff;
            padding: 15px; border-radius: 8px; margin: 15px 0;
        }
        .progress-bar {
            background: #e9ecef; border-radius: 10px; height: 20px; 
            overflow: hidden; margin: 10px 0;
        }
        .progress-fill {
            background: linear-gradient(90deg, #28a745, #20c997);
            height: 100%; transition: width 0.5s ease;
        }
        .status-indicator {
            display: inline-block; width: 12px; height: 12px;
            border-radius: 50%; margin-right: 8px;
        }
        .status-online { background: #28a745; }
        .status-busy { background: #ffc107; }
        .status-offline { background: #dc3545; }
        
        .stats { display: flex; justify-content: space-around; text-align: center; }
        .stat-item h3 { color: #007bff; font-size: 2em; margin-bottom: 5px; }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .status-grid { grid-template-columns: 1fr; }
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
    </script>
</body>
</html>
    '''
    return render_template_string(html_template)

@app.route('/api/status')
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

@app.route('/test/quick/<script>', methods=['POST'])
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

def run_standard_survey():
    """Exécute le script standard 10 fois avec pauses aléatoires"""
    global stop_requested
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