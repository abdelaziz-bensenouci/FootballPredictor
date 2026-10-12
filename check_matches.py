
from database import get_connection

with get_connection() as connection:
    # Matchs terminés sans score complet
    missing = connection.execute("""
        SELECT COUNT(*)
        FROM matches
        WHERE is_demo = 0
          AND status = 'finished'
          AND (home_goals IS NULL OR away_goals IS NULL)
    """).fetchone()[0]

    print("Matchs terminés sans score :", missing)

    # Matchs actuellement en cours
    live_matches = connection.execute("""
        SELECT competition, home_team, away_team, kickoff,
               home_goals, away_goals
        FROM matches
        WHERE is_demo = 0 AND status = 'live'
    """).fetchall()

    print("\nMatchs en cours :")
    if not live_matches:
        print("Aucun")
    else:
        for match in live_matches:
            print(
                f"{match['competition']} | "
                f"{match['home_team']} - {match['away_team']} | "
                f"{match['kickoff']} | "
                f"Score : {match['home_goals']} - {match['away_goals']}"
            )