
from data_sources.football_data import fetch_historical_matches
from database import (
    initialize_database,
    upsert_api_matches,
    get_connection,
)


def main():
    print("Initialisation de la base de données...")
    initialize_database()

    print("Récupération des matchs des 10 derniers jours...")
    matches = fetch_historical_matches(90)

    finished_api = [
        match for match in matches
        if match.get("status") == "FINISHED"
    ]

    print(f"Matchs récupérés depuis l'API : {len(matches)}")
    print(f"Matchs terminés dans la réponse API : {len(finished_api)}")

    print("Importation dans SQLite...")
    processed = upsert_api_matches(matches)

    with get_connection() as connection:
        total_finished = connection.execute("""
            SELECT COUNT(*)
            FROM matches
            WHERE is_demo = 0
              AND status = 'finished'
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
        """).fetchone()[0]

    print(f"Matchs traités pour l'importation : {processed}")
    print(f"Matchs terminés enregistrés en base : {total_finished}")
    print("Importation terminée.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Erreur : {exc}")