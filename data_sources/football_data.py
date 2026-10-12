import time
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.football-data.org/v4"
MAX_PERIOD_DAYS = 10


def _get_token():
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        raise RuntimeError(
            "Token API manquant. Vérifie FOOTBALL_DATA_TOKEN dans le fichier .env."
        )
    return token


def _fetch_period(date_from, date_to):
    """Récupère les matchs d'une période autorisée par l'API."""
    time.sleep(6)

    response = requests.get(
    f"{API_URL}/matches",
    headers={
        "X-Auth-Token": _get_token(),
        "User-Agent": "FootballPredictor/1.0",
    },
    params={
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
    },
    timeout=30,
)

    if response.status_code == 401:
        raise RuntimeError("Token API invalide (HTTP 401).")
    if response.status_code == 403:
        raise RuntimeError(
            "Accès refusé (HTTP 403). Vérifie les compétitions autorisées par ton offre."
        )
    if response.status_code == 429:
        raise RuntimeError(
            "Limite de requêtes API atteinte (HTTP 429). Réessaie plus tard."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Erreur API HTTP {response.status_code} : {response.text[:500]}"
        ) from exc

    data = response.json()
    matches = data.get("matches")

    if not isinstance(matches, list):
        raise RuntimeError("Réponse API invalide : liste de matchs absente.")

    return matches


def fetch_matches():
    """Récupère les matchs d'aujourd'hui et des neuf jours suivants."""
    today = datetime.now(timezone.utc).date()
    return _fetch_period(today, today + timedelta(days=9))


def fetch_historical_matches(days_back=90):
    """
    Récupère les matchs des derniers jours par périodes de dix jours maximum.

    Attention : la disponibilité des compétitions et des résultats dépend
    des droits associés au token football-data.org.
    """
    if not isinstance(days_back, int) or not 1 <= days_back <= 365:
        raise ValueError("days_back doit être compris entre 1 et 365.")

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days_back)
    all_matches = []
    current_date = start_date

    while current_date <= today:
        end_date = min(
            current_date + timedelta(days=MAX_PERIOD_DAYS - 1),
            today,
        )
        all_matches.extend(_fetch_period(current_date, end_date))
        current_date = end_date + timedelta(days=1)

    # Supprime les doublons éventuels en conservant un exemplaire par ID.
    unique_matches = {}
    for match in all_matches:
        match_id = match.get("id")
        if match_id is not None:
            unique_matches[match_id] = match

    return list(unique_matches.values())