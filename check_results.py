
from database import get_connection

with get_connection() as connection:
    rows = connection.execute("""
        SELECT status, COUNT(*) AS total
        FROM matches
        WHERE is_demo = 0
        GROUP BY status
        ORDER BY status
    """).fetchall()

    print("=== STATUTS DES MATCHS ===")
    for row in rows:
        print(f"{row['status']} : {row['total']}")

    finished = connection.execute("""
        SELECT COUNT(*)
        FROM matches
        WHERE is_demo = 0
          AND status = 'finished'
          AND home_goals IS NOT NULL
          AND away_goals IS NOT NULL
    """).fetchone()[0]

    print(f"\nMatchs terminés avec un score final : {finished}")

    evaluated = connection.execute("""
        SELECT COUNT(*)
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        WHERE m.is_demo = 0
          AND p.is_demo = 0
          AND m.status = 'finished'
          AND m.home_goals IS NOT NULL
          AND m.away_goals IS NOT NULL
    """).fetchone()[0]

    print(f"Pronostics évaluables : {evaluated}")