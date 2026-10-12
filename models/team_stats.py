
from database import get_connection


MODEL_PRIOR_MATCHES = 5
MIN_EXPECTED_GOALS = 0.2
MAX_EXPECTED_GOALS = 4.5

# Marge de sécurité entre un match historique et le match cible.
HISTORY_CUTOFF_HOURS = 4


def estimate_expected_goals(match_id: int) -> dict:
    """
    Estime les buts attendus à partir des matchs terminés de la même
    compétition, commencés au moins 4 heures avant le match cible.

    Les matchs fictifs et les matchs sans score complet sont exclus.

    Attention : la marge de 4 heures est une approximation.
    Sans heure réelle de fin, elle ne garantit pas une absence totale
    de fuite temporelle dans un backtest.
    """

    with get_connection() as connection:
        target = connection.execute("""
            SELECT id, competition, home_team, away_team, kickoff, is_demo
            FROM matches
            WHERE id = ?
        """, (match_id,)).fetchone()

        if target is None:
            raise ValueError(f"Match introuvable : {match_id}")

        if target["is_demo"]:
            raise ValueError(
                "Impossible de calculer un pronostic réel pour un match fictif."
            )

        if not target["kickoff"]:
            raise ValueError(
                f"Date de coup d'envoi manquante pour "
                f"{target['home_team']} - {target['away_team']}."
            )

        # On exclut les matchs commencés moins de 4 heures avant
        # le match cible, afin de limiter le risque de fuite temporelle.
        history = connection.execute("""
            SELECT home_team, away_team, home_goals, away_goals
            FROM matches
            WHERE competition = ?
              AND status = 'finished'
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
              AND is_demo = 0
              AND datetime(kickoff) <
                  datetime(?, ?)
            ORDER BY kickoff DESC
        """, (
            target["competition"],
            target["kickoff"],
            f"-{HISTORY_CUTOFF_HOURS} hours",
        )).fetchall()

    if len(history) < MODEL_PRIOR_MATCHES:
        raise ValueError(
            f"Historique insuffisant pour {target['competition']} : "
            f"{len(history)} matchs terminés disponibles avec une marge "
            f"de {HISTORY_CUTOFF_HOURS} h avant le coup d'envoi "
            f"(minimum requis : {MODEL_PRIOR_MATCHES})."
        )

    # Moyennes de buts à domicile et à l'extérieur dans la compétition.
    league_home_avg = (
        sum(row["home_goals"] for row in history) / len(history)
    )
    league_away_avg = (
        sum(row["away_goals"] for row in history) / len(history)
    )

    if league_home_avg <= 0 or league_away_avg <= 0:
        raise ValueError(
            "Impossible de calculer les moyennes de buts de cette compétition."
        )

    home_scored = []
    home_conceded = []
    away_scored = []
    away_conceded = []

    # Performances de l'équipe à domicile chez elle,
    # et de l'équipe extérieure lorsqu'elle joue à l'extérieur.
    for row in history:
        if row["home_team"] == target["home_team"]:
            home_scored.append(row["home_goals"])
            home_conceded.append(row["away_goals"])

        if row["away_team"] == target["away_team"]:
            away_scored.append(row["away_goals"])
            away_conceded.append(row["home_goals"])

    # Lissage : les équipes avec peu de matchs restent proches
    # des moyennes générales de leur compétition.
    prior = MODEL_PRIOR_MATCHES

    home_attack_avg = (
        sum(home_scored) + prior * league_home_avg
    ) / (len(home_scored) + prior)

    home_defense_conceded_avg = (
        sum(home_conceded) + prior * league_away_avg
    ) / (len(home_conceded) + prior)

    away_attack_avg = (
        sum(away_scored) + prior * league_away_avg
    ) / (len(away_scored) + prior)

    away_defense_conceded_avg = (
        sum(away_conceded) + prior * league_home_avg
    ) / (len(away_conceded) + prior)

    # Forces offensives et défensives relatives aux moyennes de la ligue.
    home_attack = home_attack_avg / league_home_avg
    away_defense = away_defense_conceded_avg / league_home_avg

    away_attack = away_attack_avg / league_away_avg
    home_defense = home_defense_conceded_avg / league_away_avg

    expected_home = league_home_avg * home_attack * away_defense
    expected_away = league_away_avg * away_attack * home_defense

    # Protection contre les estimations extrêmes.
    expected_home = max(
        MIN_EXPECTED_GOALS,
        min(MAX_EXPECTED_GOALS, expected_home),
    )
    expected_away = max(
        MIN_EXPECTED_GOALS,
        min(MAX_EXPECTED_GOALS, expected_away),
    )

    return {
        "match_id": match_id,
        "competition": target["competition"],
        "home_team": target["home_team"],
        "away_team": target["away_team"],
        "historical_matches": len(history),
        "home_matches_in_history": len(home_scored),
        "away_matches_in_history": len(away_scored),
        "expected_goals_home": expected_home,
        "expected_goals_away": expected_away,
    }

