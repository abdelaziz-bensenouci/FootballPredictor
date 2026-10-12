
from database import get_connection
from models.team_stats import estimate_expected_goals
from models.poisson_model import predict_match, format_prediction


with get_connection() as connection:
    match = connection.execute("""
        SELECT id, competition, home_team, away_team, kickoff
        FROM matches
        WHERE is_demo = 0
          AND status = 'scheduled'
        ORDER BY kickoff ASC
        LIMIT 1
    """).fetchone()

if match is None:
    print("Aucun match programmé trouvé dans la base.")
else:
    print(
        f"Match testé : {match['home_team']} - {match['away_team']}"
    )
    print(f"Compétition : {match['competition']}")
    print(f"Coup d'envoi : {match['kickoff']}")

    try:
        stats = estimate_expected_goals(match["id"])

        print("\nStatistiques utilisées :")
        print(f"Matchs historiques : {stats['historical_matches']}")
        print(
            "Matchs à domicile de l'équipe : "
            f"{stats['home_matches_in_history']}"
        )
        print(
            "Matchs à l'extérieur de l'équipe : "
            f"{stats['away_matches_in_history']}"
        )

        prediction = predict_match(
            home_expected_goals=stats["expected_goals_home"],
            away_expected_goals=stats["expected_goals_away"],
        )

        print("\nPronostic expérimental :")
        print(format_prediction(prediction))

    except ValueError as exc:
        print(f"Pronostic non calculé : {exc}")