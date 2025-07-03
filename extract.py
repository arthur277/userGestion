import requests
from bs4 import BeautifulSoup
import mysql.connector
import urllib3

# --- Désactiver les avertissements SSL (à éviter en production) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Paramètres pfSense ---
PFSENSE_URL = 'https://192.168.1.1'
USERNAME = 'admin'
PASSWORD = 'arthur123456'
CAPTIVE_PORTAL_STATUS_URL = f'{PFSENSE_URL}/status_captiveportal.php'

# --- Paramètres MySQL ---
DB_HOST = '98.66.152.100'
DB_USER = 'root'
DB_PASSWORD = 'rootpass'
DB_NAME = 'mydb'

try:
    # Connexion à la base de données
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()

    # Création de la table si elle n'existe pas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pfsense_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            ip VARCHAR(45),
            mac VARCHAR(20),
            date_insert DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_user_mac (username, mac)
        )
    """)
    conn.commit()

    # --- Connexion à pfSense ---
    session = requests.Session()
    session.verify = False  # Désactive la vérification SSL (ne pas utiliser en prod)

    # Récupérer le token CSRF
    login_page = session.get(f'{PFSENSE_URL}/index.php')
    login_page.raise_for_status()
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_input = soup.find('input', {'name': '__csrf_magic'})

    if not csrf_input:
        raise Exception("Token CSRF non trouvé dans le formulaire de login.")

    csrf_token = csrf_input.get('value')

    # Préparer et envoyer la requête de connexion
    login_data = {
        '__csrf_magic': csrf_token,
        'usernamefld': USERNAME,
        'passwordfld': PASSWORD,
        'login': 'Login'
    }

    login_response = session.post(f'{PFSENSE_URL}/index.php', data=login_data)
    login_response.raise_for_status()

    if 'Dashboard' not in login_response.text and 'status_captiveportal' not in login_response.text:
        raise Exception("Connexion échouée : vérifiez les identifiants.")

    # --- Récupération des données du portail captif ---
    response = session.get(CAPTIVE_PORTAL_STATUS_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Parcours des lignes du tableau (en ignorant l'en-tête)
    for row in soup.find_all('tr')[1:]:
        cols = row.find_all('td')
        if len(cols) >= 4:
            ip = cols[0].text.strip()
            mac = cols[1].text.strip()
            user = cols[2].text.strip()

            print(f"Utilisateur: {user}, IP: {ip}, MAC: {mac}")

            try:
                cursor.execute("""
                    INSERT INTO pfsense_users (username, ip, mac)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE ip = VALUES(ip), date_insert = CURRENT_TIMESTAMP
                """, (user, ip, mac))
            except mysql.connector.Error as err:
                print(f"Erreur d'insertion MySQL : {err}")

    conn.commit()

except requests.RequestException as e:
    print(f"Erreur réseau ou HTTP : {e}")
except mysql.connector.Error as err:
    print(f"Erreur base de données : {err}")
except Exception as ex:
    print(f"Erreur inattendue : {ex}")
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals() and conn.is_connected():
        conn.close()
