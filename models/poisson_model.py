
from math import exp, factorial


MODEL_VERSION = "poisson-0.1"


def poisson_probability(goals: int, expected_goals: float) -> float:
    """Probabilité de marquer exactement un nombre de buts donné."""
    if goals < 0:
        return 0.0

    if expected_goals < 0:
        raise ValueError("Les buts attendus ne peuvent pas être négatifs.")

    return (
        exp(-expected_goals)
        * expected_goals**goals
        / factorial(goals)
    )


def predict_match(
    home_expected_goals: float,
    away_expected_goals: float,
    max_goals: int = 10,
) -> dict:
    """
    Calcule les probabilités 1N2, over/under 2.5 et BTTS.

    Les deux valeurs d'entrée sont des estimations de buts attendus.
    Elles ne sont pas encore calculées à partir de données réelles.
    """
    if home_expected_goals < 0 or away_expected_goals < 0:
        raise ValueError("Les buts attendus doivent être positifs ou nuls.")

    if max_goals < 5:
        raise ValueError("max_goals doit être au moins égal à 5.")

    home_probs = [
        poisson_probability(g, home_expected_goals)
        for g in range(max_goals + 1)
    ]
    away_probs = [
        poisson_probability(g, away_expected_goals)
        for g in range(max_goals + 1)
    ]

    # Matrice des scores : lignes = buts domicile,
    # colonnes = buts extérieur.
    matrix = [
        [ph * pa for pa in away_probs]
        for ph in home_probs
    ]

    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    p_over25 = 0.0
    p_btts_yes = 0.0

    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                p_home += probability
            elif home_goals == away_goals:
                p_draw += probability
            else:
                p_away += probability

            if home_goals + away_goals >= 3:
                p_over25 += probability

            if home_goals > 0 and away_goals > 0:
                p_btts_yes += probability

    # La plage de scores est tronquée à max_goals.
    # On normalise la matrice pour que les probabilités
    # soient cohérentes sur cette plage.
    total = sum(sum(row) for row in matrix)

    if total <= 0:
        raise ValueError("Impossible de calculer les probabilités.")

    p_home /= total
    p_draw /= total
    p_away /= total
    p_over25 /= total
    p_btts_yes /= total

    return {
        "model_version": MODEL_VERSION,
        "expected_goals_home": home_expected_goals,
        "expected_goals_away": away_expected_goals,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_over25": p_over25,
        "p_under25": 1.0 - p_over25,
        "p_btts_yes": p_btts_yes,
        "p_btts_no": 1.0 - p_btts_yes,
        "most_likely_score": max(
            (
                (home_goals, away_goals, probability)
                for home_goals, row in enumerate(matrix)
                for away_goals, probability in enumerate(row)
            ),
            key=lambda item: item[2],
        )[:2],
    }


def format_prediction(prediction: dict) -> str:
    """Présente les résultats sous forme lisible."""
    percent = lambda value: f"{value * 100:.1f}%"
    score = prediction["most_likely_score"]

    return "\n".join([
        f"Version du modèle : {prediction['model_version']}",
        (
            "Buts attendus : "
            f"{prediction['expected_goals_home']:.2f} - "
            f"{prediction['expected_goals_away']:.2f}"
        ),
        "",
        f"Victoire domicile (1) : {percent(prediction['p_home'])}",
        f"Match nul (N) : {percent(prediction['p_draw'])}",
        f"Victoire extérieur (2) : {percent(prediction['p_away'])}",
        "",
        f"Plus de 2,5 buts : {percent(prediction['p_over25'])}",
        f"Moins de 2,5 buts : {percent(prediction['p_under25'])}",
        f"Les deux équipes marquent : {percent(prediction['p_btts_yes'])}",
        f"Au moins une équipe ne marque pas : {percent(prediction['p_btts_no'])}",
        f"Score modal estimé : {score[0]} - {score[1]}",
    ])


if __name__ == "__main__":
    # Exemple purement illustratif, pas un vrai pronostic.
    result = predict_match(
        home_expected_goals=1.65,
        away_expected_goals=1.10,
    )

    print(format_prediction(result))