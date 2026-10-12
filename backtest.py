
from collections import Counter

from database import get_connection
from models.team_stats import estimate_expected_goals
from models.poisson_model import predict_match, MODEL_VERSION


def run_backtest():
    with get_connection() as connection:
        matches = connection.execute("""
            SELECT id, competition, home_team, away_team,
                   kickoff, home_goals, away_goals
            FROM matches
            WHERE status = 'finished'
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
              AND is_demo = 0
            ORDER BY kickoff ASC
        """).fetchall()

    evaluated = 0
    correct = 0
    total_brier = 0.0
    skipped = Counter()
    examples = []

    for match in matches:
        try:
            # Les statistiques doivent être calculées uniquement
            # à partir de données antérieures au match cible.
            stats = estimate_expected_goals(match["id"])

            prediction = predict_match(
                home_expected_goals=stats["expected_goals_home"],
                away_expected_goals=stats["expected_goals_away"],
            )

            home_goals = match["home_goals"]
            away_goals = match["away_goals"]

            if home_goals > away_goals:
                actual = (1, 0, 0)
                actual_label = "home"
            elif home_goals == away_goals:
                actual = (0, 1, 0)
                actual_label = "draw"
            else:
                actual = (0, 0, 1)
                actual_label = "away"

            probabilities = (
                prediction["p_home"],
                prediction["p_draw"],
                prediction["p_away"],
            )

            predicted_label = max(
                zip(probabilities, ("home", "draw", "away"))
            )[1]

            if predicted_label == actual_label:
                correct += 1

            total_brier += sum(
                (p - outcome) ** 2
                for p, outcome in zip(probabilities, actual)
            )

            evaluated += 1

            if len(examples) < 5:
                examples.append(
                    f"{match['competition']} | "
                    f"{match['home_team']} - {match['away_team']} | "
                    f"Score réel : {home_goals}-{away_goals} | "
                    f"Pronostic : {predicted_label}"
                )

        except ValueError as error:
            skipped[str(error)] += 1
        except (KeyError, TypeError) as error:
            skipped[f"Erreur de données : {error}"] += 1

    print("\n========== BACKTEST FOOTBALLPREDICTOR ==========")
    print(f"Version du modèle : {MODEL_VERSION}")
    print(f"Matchs terminés disponibles : {len(matches)}")
    print(f"Matchs évalués : {evaluated}")
    print(f"Matchs ignorés : {len(matches) - evaluated}")

    if evaluated:
        print(f"Taux de réussite 1N2 : {correct / evaluated:.2%}")
        print(f"Score de Brier : {total_brier / evaluated:.4f}")
    else:
        print("Pas assez de données pour évaluer le modèle.")

    if skipped:
        print("\nPrincipales raisons des exclusions :")
        for reason, count in skipped.most_common(5):
            print(f"- {count} match(s) : {reason}")

    if examples:
        print("\nExemples de prédictions évaluées :")
        for example in examples:
            print("-", example)

    print("\nAucune donnée de la base n'a été modifiée.")


if __name__ == "__main__":
    run_backtest()