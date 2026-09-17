from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
import time
import random
import logging
import datetime
import argparse
import os

# Variables globales
eatIn = None

def config_logging():
    """Configure le système de journalisation"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # Uniquement console pour Render
        ]
    )

def setup_chrome_for_render():
    """Configuration Chrome optimisée pour Render"""
    options = webdriver.ChromeOptions()
    
    # Options obligatoires pour Render
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--window-size=1920,1080")
    # Optimisations mémoire pour Render
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-component-extensions-with-background-pages")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-ipc-flooding-protection")
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Détection environnement Render
    chrome_binary = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    if os.path.exists(chrome_binary):
        options.binary_location = chrome_binary
    
    try:
        driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        service = Service(driver_path) if os.path.exists(driver_path) else Service()
        driver = webdriver.Chrome(service=service, options=options)
        logging.info("✅ Chrome initialisé avec le driver système")
        return driver
    except Exception as e:
        logging.error(f"❌ Impossible d'initialiser Chrome: {str(e)}")
        raise

def automatiser_sondage_mcdo(headless=True, ticket_code=None):
    """
    Automatise le sondage McDonald's en mode standard (sur place ou à emporter)
    Version adaptée pour Render
    
    Args:
        headless (bool): Exécute le navigateur en arrière-plan si True
        ticket_code (str): Code du ticket de caisse si disponible
    """
    config_logging()
    logging.info("🍟 Démarrage automatisation sondage - Mode STANDARD")
    
    # Variables globales
    global eatIn
    eatIn = None
    
    try:
        # Utiliser la configuration Render
        driver = setup_chrome_for_render()
    except Exception as e:
        logging.error(f"❌ Impossible d'initialiser Chrome: {str(e)}")
        return False
    
    try:
        # Accéder à la page du sondage
        driver.get("https://survey2.medallia.eu/?hellomcdo")
        logging.info("📄 Page du sondage ouverte")
        
        # Attendre que le bouton "Commencer l'enquête" soit cliquable
        wait = WebDriverWait(driver, 25)  # Timeout augmenté pour Render + JS loading
        bouton_commencer = wait.until(
            EC.element_to_be_clickable((By.ID, "buttonBegin"))
        )
        
        # Ajouter une pause aléatoire pour simuler un comportement humain
        time.sleep(random.uniform(1.0, 3.0))
        
        # Cliquer sur le bouton "Commencer l'enquête"
        bouton_commencer.click()
        logging.info("🚀 Enquête commencée")
        
        # Boucle principale pour remplir les pages du sondage
        page_actuelle = 1
        max_pages = 20  # Protection contre une boucle infinie
        
        while page_actuelle <= max_pages:
            try:
                # Attendre que la page soit chargée 
                # Pause plus longue pour éviter les détections anti-bot
                time.sleep(random.uniform(3.0, 5.0))
                
                logging.info(f"📝 Remplissage de la page {page_actuelle}")
                
                # Identifier le type de question sur la page actuelle et y répondre
                repondre_a_la_question(driver, page_actuelle)
                
                # Autre pause aléatoire avant de cliquer sur le bouton suivant
                time.sleep(random.uniform(1.0, 2.0))
                
                # Chercher et cliquer sur le bouton "Suivant"
                bouton_selector = "button[name='forward_main-pager']"
                bouton_suivant = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, bouton_selector))
                )
                
                # Avant de cliquer, vérifions si la page est la dernière
                if "100%" in driver.page_source:
                    logging.info("🏁 Dernière page détectée")
                    
                bouton_suivant.click()
                logging.info(f"➡️ Passage à la page suivante")
                
                page_actuelle += 1
                
            except TimeoutException:
                # Si le bouton "Suivant" n'est pas trouvé, c'est probablement la fin du sondage
                logging.info("✅ Sondage terminé ou bouton suivant non trouvé")
                break
            
            except Exception as e:
                logging.error(f"❌ Erreur sur la page {page_actuelle}: {str(e)}")
                break
                
        logging.info(f"🎉 Sondage STANDARD complété avec succès : {page_actuelle-1} pages remplies")
        return True
        
    except Exception as e:
        logging.error(f"❌ Une erreur est survenue: {str(e)}")
        return False
    
    finally:
        # Fermer le navigateur
        try:
            driver.quit()
            logging.info("🔒 Navigateur fermé")
        except:
            pass

def repondre_a_la_question(driver, page_num):
    """
    Fonction qui identifie le type de question et y répond de manière appropriée pour le mode standard
    """
    # Déclarer l'utilisation des variables globales
    global eatIn
    
    # Identification spécifique de la page du questionnaire basée sur le texte visible
    page_text = driver.page_source
    
    # Déterminer sur quelle page nous sommes
    if "Quel est votre âge" in page_text:
        logging.info("👤 Page: Sélection de l'âge")
        # Exclure "Moins de 15 ans" (première option) et "50 ans et plus" (dernière option)
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        if len(radio_buttons) >= 5:  # Vérifier que nous avons toutes les options
            # Choisir aléatoirement parmi les options 2, 3, 4 (indices 1, 2, 3)
            option_index = random.randint(1, 3)
            radio_buttons[option_index].click()
            logging.info(f"✅ Âge sélectionné: option {option_index+1}")
            return
            
    # Page date, heure et numéro de restaurant
    elif "Jour" in page_text and "Heure" in page_text and "Numéro de restaurant" in page_text:
        logging.info("📅 Page: Informations du ticket")
        
        # 1. Date (1-7 jours avant aujourd'hui pour plus de variété)
        today = datetime.datetime.now()
        days_ago = random.randint(1, 7)
        visit_date = today - datetime.timedelta(days=days_ago)
        date_str = visit_date.strftime("%d/%m/%Y")
        
        date_field = driver.find_element(By.CSS_SELECTOR, "input[id^='cal_q_mc_q_date']")
        date_field.send_keys(date_str)
        logging.info(f"📅 Date saisie: {date_str}")
        
        # 2. Heure réaliste pour standard (déjeuner 12h-14h30 et dîner 18h-21h30)
        lunch_hours = list(range(12, 15))  # 12h-14h
        dinner_hours = list(range(18, 22))  # 18h-21h
        
        # Choisir aléatoirement entre déjeuner et dîner
        if random.choice([True, False]):
            hour = random.choice(lunch_hours)
        else:
            hour = random.choice(dinner_hours)
        
        minutes = random.choice([0, 15, 30, 45])
        
        # Ajustements spéciaux
        if hour == 14 and minutes > 30:
            minutes = 30  # Pas trop tard pour le déjeuner
        elif hour == 21 and minutes > 30:
            minutes = 30  # Pas trop tard pour le dîner
        
        # Formater l'heure et les minutes
        hour_str = str(hour).zfill(2)
        minute_str = str(minutes).zfill(2)
        
        hour_field = driver.find_element(By.CSS_SELECTOR, "input[id^='spl_rng_q_mc_q_hour']")
        hour_field.send_keys(hour_str)
        
        minute_field = driver.find_element(By.CSS_SELECTOR, "input[id^='spl_rng_q_mc_q_minute']")
        minute_field.send_keys(minute_str)
        logging.info(f"⏰ Heure saisie: {hour_str}:{minute_str}")
        
        # 3. Numéro de restaurant
        restaurant_field = driver.find_element(By.CSS_SELECTOR, "input[id^='spl_rng_q_mc_q_idrestaurant']")
        restaurant_field.send_keys("1198")
        logging.info("🏪 Numéro de restaurant saisi: 1198")
        return
        
    # Page "Où avez-vous passé votre commande"
    elif "Où avez-vous passé votre commande" in page_text:
        logging.info("🛒 Page: Où avez-vous passé votre commande")
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        # Mode standard: choisir aléatoirement entre en restaurant ou drive
        option_index = random.randint(0, 1)
        radio_buttons[option_index].click()
        mode = "En restaurant" if option_index == 0 else "Au drive"
        logging.info(f"✅ Mode de commande sélectionné: {mode}")
        return
        
    # Page "Avez-vous : Consommé sur place / Pris à emporter"
    elif "Avez-vous :" in page_text and "Consommé sur place" in page_text:
        logging.info("🍽️ Page: Consommé sur place ou à emporter")
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        if len(radio_buttons) >= 2:
            # Choix aléatoire entre sur place et à emporter
            option_index = random.randint(0, 1)
            radio_buttons[option_index].click()
            
            # Sauvegarder ce choix pour la prochaine page
            eatIn = (option_index == 0)  # True si consommé sur place
            mode = "sur place" if eatIn else "à emporter"
            logging.info(f"✅ Mode de consommation: {mode}")
            return
    
    # Page "Où avez-vous récupéré votre commande"
    elif "Où avez-vous récupéré votre commande" in page_text:
        logging.info("📦 Page: Où avez-vous récupéré votre commande")
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        
        selected_index = 0
        
        # Si on a mangé sur place (eatIn=True), sélectionner "En service à table"
        if eatIn:
            logging.info("🔍 Mode 'Consommé sur place' - Recherche de l'option 'En service à table'")
            service_table_found = False
            
            for i, button in enumerate(radio_buttons):
                if button.is_displayed() and button.is_enabled():
                    element_id = button.get_attribute("id")
                    if element_id:
                        label_elements = driver.find_elements(By.CSS_SELECTOR, f"label[for='{element_id}']")
                        if not label_elements:
                            try:
                                parent = button.find_element(By.XPATH, "./ancestor::div[contains(@class, 'option_optionContainer')]")
                                label_elements = parent.find_elements(By.CSS_SELECTOR, "span.option_caption")
                            except:
                                continue
                        
                        if label_elements and len(label_elements) > 0:
                            label_text = label_elements[0].text.lower()
                            
                            if "service à table" in label_text or "en service à table" in label_text or "table" in label_text:
                                selected_index = i
                                service_table_found = True
                                logging.info("✅ Option 'En service à table' trouvée")
                                break
            
            # Si "Service à table" n'est pas trouvé, essayer la dernière option
            if not service_table_found and len(radio_buttons) > 2:
                selected_index = len(radio_buttons) - 1
                logging.info("⚠️ Sélection de la dernière option comme 'Service à table'")
        else:
            # Pour "À emporter", rechercher "Au comptoir"
            logging.info("🔍 Mode 'Pris à emporter' - Recherche de l'option 'Au comptoir'")
            comptoir_found = False
            
            for i, button in enumerate(radio_buttons):
                if button.is_displayed() and button.is_enabled():
                    element_id = button.get_attribute("id")
                    if element_id:
                        label_elements = driver.find_elements(By.CSS_SELECTOR, f"label[for='{element_id}']")
                        if not label_elements:
                            try:
                                parent = button.find_element(By.XPATH, "./ancestor::div[contains(@class, 'option_optionContainer')]")
                                label_elements = parent.find_elements(By.CSS_SELECTOR, "span.option_caption")
                            except:
                                continue
                        
                        if label_elements and len(label_elements) > 0:
                            label_text = label_elements[0].text.lower()
                            
                            if "comptoir" in label_text or "au comptoir" in label_text:
                                selected_index = i
                                comptoir_found = True
                                logging.info("✅ Option 'Au comptoir' trouvée")
                                break
            
            # Si "Au comptoir" n'est pas trouvé, sélectionner la première option
            if not comptoir_found:
                logging.info("⚠️ Sélection de la première option comme 'Au comptoir'")
        
        # Cliquer sur l'option sélectionnée
        radio_buttons[selected_index].click()
        selected_option = "En service à table" if eatIn else "Au comptoir"
        logging.info(f"✅ Récupération de commande sélectionnée: {selected_option}")
        return
    
    # Page sur la qualité de l'expérience "satisfait(e) de cette expérience"
    elif "satisfait(e) de cette expérience" in page_text:
        logging.info("⭐ Page: Satisfaction globale")
        try:
            # Trouver le premier bouton radio du groupe (très satisfait)
            first_option = driver.find_element(By.ID, "onf_q_feedback_m_based_upon_this_visit_to_this_6_1")
            first_option.click()
            logging.info("✅ Satisfaction globale: Très satisfait(e) (sélectionné par ID)")
            return
        except:
            # Si l'ID ne fonctionne pas, essayer la méthode habituelle
            radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if radio_buttons:
                radio_buttons[0].click()
                logging.info("✅ Satisfaction globale: Très satisfait(e)")
            return
            
    # Page des dimensions de satisfaction
    elif "Et dans quelle mesure avez-vous été satisfait(e) de chacune de ces dimensions" in page_text:
        logging.info("📊 Page: Dimensions de satisfaction")
        
        # Liste des IDs connus des dimensions pour le mode standard
        standard_dimension_ids = [
            "onf_q_mc_q_cleanliness_exterior_aspect_restaurant_1",  # Propreté du restaurant
            "onf_q_mc_q_speed_service_1",                          # Rapidité du service
            "onf_q_mc_q_quality_of_food_and_drink_1",              # Qualité des produits
            "onf_q_mc_q_friendliness_crew_1"                       # Amabilité du personnel
        ]
        
        # Essayer chaque ID
        dimensions_clicked = 0
        for dim_id in standard_dimension_ids:
            try:
                option = driver.find_element(By.ID, dim_id)
                option.click()
                dimensions_clicked += 1
                logging.info(f"✅ Dimension {dim_id}: Très satisfait(e)")
                time.sleep(0.5)  # Pause entre chaque sélection
            except:
                logging.info(f"⚠️ Dimension {dim_id} non trouvée")
        
        # Si aucune dimension n'a été cliquée, essayer la méthode alternative
        if dimensions_clicked == 0:
            try:
                fieldsets = driver.find_elements(By.CSS_SELECTOR, "fieldset.ratingGridRow")
                logging.info(f"📊 Nombre de critères de satisfaction trouvés: {len(fieldsets)}")
                
                for fieldset in fieldsets:
                    radio_buttons = fieldset.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    if radio_buttons and len(radio_buttons) > 0:
                        radio_buttons[0].click()  # Sélectionner la première option (très satisfait)
                        logging.info("✅ Dimension trouvée par alternative - Option 1 sélectionnée")
                        time.sleep(0.5)
            except Exception as e:
                # Si la méthode alternative ne fonctionne pas non plus, essayer une méthode plus générale
                try:
                    all_radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    radio_groups = {}
                    
                    # Regrouper les boutons radio par leur attribut name
                    for button in all_radio_buttons:
                        name = button.get_attribute("name")
                        if name not in radio_groups:
                            radio_groups[name] = []
                        radio_groups[name].append(button)
                    
                    # Pour chaque groupe, sélectionner la première option
                    for name, buttons in radio_groups.items():
                        if len(buttons) > 0:
                            buttons[0].click()
                            logging.info(f"✅ Groupe {name}: Premier bouton sélectionné")
                            time.sleep(0.5)
                except Exception as e2:
                    logging.error(f"❌ Toutes les méthodes pour les dimensions ont échoué: {str(e2)}")
        
        return
        
    # Page "Est-ce que votre commande était exacte"
    elif "Est-ce que votre commande était exacte" in page_text:
        logging.info("✔️ Page: Exactitude de la commande")
        try:
            # Essayer de sélectionner par ID
            yes_option = driver.find_element(By.ID, "onf_q_feedback_m_was_your_order_accurate_1")
            yes_option.click()
            logging.info("✅ Commande exacte: Oui (par ID)")
            return
        except:
            # Méthode de secours
            radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if len(radio_buttons) >= 2:
                # Répondre "Oui" (première option)
                radio_buttons[0].click()
                logging.info("✅ Commande exacte: Oui")
                return
            
    # Page "Avez-vous rencontré un problème"
    elif "Avez-vous rencontré un problème" in page_text:
        logging.info("❓ Page: Problèmes rencontrés")
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        if len(radio_buttons) >= 2:
            # Répondre "Non" (deuxième option)
            radio_buttons[1].click()
            logging.info("✅ Problème rencontré: Non")
            return
            
    # Pour les autres pages, fallback vers le comportement standard
    try:
        radio_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        if radio_buttons:
            # Sélectionner une option positive (généralement au début de la liste pour les notes)
            option_index = 0  # Toujours sélectionner la première option (très satisfait/très bien/etc.)
            radio_buttons[option_index].click()
            logging.info(f"✅ Répondu à une question à choix unique standard - option {option_index+1}")
            return
    except:
        pass
    
    # Vérifier s'il y a des cases à cocher (checkboxes)
    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        if checkboxes:
            # Sélectionner de manière aléatoire 1 à 3 options
            num_to_select = min(random.randint(1, 3), len(checkboxes))
            selected_indices = random.sample(range(len(checkboxes)), num_to_select)
            
            for index in selected_indices:
                checkboxes[index].click()
            
            logging.info(f"✅ Répondu à une question à choix multiple - {num_to_select} options sélectionnées")
            return
    except:
        pass
    
    # Vérifier s'il y a des champs de texte à remplir
    try:
        text_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
        if text_fields:
            for field in text_fields:
                # Vérifier si le champ est visible et activé
                if field.is_displayed() and field.is_enabled():
                    # Répondre avec un texte générique positif
                    field.send_keys("Très bonne expérience. Service rapide et personnel sympathique.")
            
            logging.info("✅ Répondu à une ou plusieurs questions textuelles")
            return
    except:
        pass
    
    # Si aucune interaction n'a été effectuée, c'est peut-être une page d'information sans question
    logging.info("ℹ️ Page sans interaction détectée ou avec un format non reconnu")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automatisation du sondage McDonald's - Mode Standard - Version Render")
    parser.add_argument('--headless', action='store_true', help="Exécuter en mode headless (sans interface graphique)")
    parser.add_argument('--ticket', type=str, help="Code du ticket de caisse (si nécessaire)")
    
    args = parser.parse_args()
    
    automatiser_sondage_mcdo(
        headless=args.headless, 
        ticket_code=args.ticket
    )