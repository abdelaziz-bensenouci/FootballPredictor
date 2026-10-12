
import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("FOOTBALL_DATA_TOKEN")

if not token or token == "COLLE_TON_TOKEN_ICI":
    raise SystemExit(
        "Token absent : vérifie le fichier .env."
    )

url = "https://api.football-data.org/v4/competitions"

try:
    response = requests.get(
        url,
        headers={"X-Auth-Token": token},
        timeout=20,
    )

    if response.status_code == 200:
        data = response.json()
        competitions = data.get("competitions", [])

        print("Connexion réussie !")
        print(f"Compétitions accessibles : {len(competitions)}")

        for competition in competitions[:10]:
            print(
                f"- {competition.get('name')} "
                f"({competition.get('code')})"
            )

    elif response.status_code == 401:
        print("Token invalide ou non reconnu.")

    elif response.status_code == 403:
        print(
            "Accès refusé : cette ressource peut ne pas "
            "être incluse dans ton forfait."
        )

    elif response.status_code == 429:
        print("Limite de requêtes atteinte. Réessaie plus tard.")

    else:
        print(f"Erreur HTTP {response.status_code}")
        print(response.text[:500])

except requests.RequestException as error:
    print(f"Erreur réseau : {error}")