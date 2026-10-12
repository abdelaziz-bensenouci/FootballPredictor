
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "football_predictor.db"


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT,
                competition TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                kickoff TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                home_goals INTEGER,
                away_goals INTEGER,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(external_id, competition)
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                model_version TEXT NOT NULL,
                p_home REAL NOT NULL,
                p_draw REAL NOT NULL,
                p_away REAL NOT NULL,
                p_over25 REAL NOT NULL,
                p_under25 REAL NOT NULL,
                p_btts_yes REAL NOT NULL,
                p_btts_no REAL NOT NULL,
                source_snapshot TEXT,
                is_demo INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(match_id) REFERENCES matches(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_matches_kickoff
                ON matches(kickoff);

            CREATE INDEX IF NOT EXISTS idx_predictions_match
                ON predictions(match_id);
        """)


def get_matches():
    with get_connection() as connection:
        return connection.execute("""
            SELECT
                m.id,
                m.competition,
                m.home_team,
                m.away_team,
                m.kickoff,
                m.status,
                m.home_goals,
                m.away_goals,
                m.is_demo,
                p.id AS prediction_id,
                p.created_at AS prediction_date,
                p.model_version,
                p.p_home,
                p.p_draw,
                p.p_away,
                p.p_over25,
                p.p_under25,
                p.p_btts_yes,
                p.p_btts_no,
                p.is_demo AS prediction_is_demo
            FROM matches m
            LEFT JOIN predictions p
                ON p.id = (
                    SELECT p2.id
                    FROM predictions p2
                    WHERE p2.match_id = m.id
                    ORDER BY p2.created_at DESC, p2.id DESC
                    LIMIT 1
                )
            ORDER BY m.kickoff ASC
        """).fetchall()


def get_history():
    with get_connection() as connection:
        return connection.execute("""
            SELECT
                p.id AS prediction_id,
                p.created_at,
                p.model_version,
                p.p_home,
                p.p_draw,
                p.p_away,
                p.p_over25,
                p.p_under25,
                p.p_btts_yes,
                p.p_btts_no,
                m.competition,
                m.home_team,
                m.away_team,
                m.kickoff,
                m.status,
                m.home_goals,
                m.away_goals,
                m.is_demo,
                p.is_demo AS prediction_is_demo
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            ORDER BY p.created_at DESC, p.id DESC
        """).fetchall()


def add_demo_data():
    """Ajoute des exemples fictifs, uniquement pour tester l'interface."""
    with get_connection() as connection:
        already_exists = connection.execute(
            "SELECT COUNT(*) FROM matches WHERE is_demo = 1"
        ).fetchone()[0]

        if already_exists:
            return False

        examples = [
            {
                "competition": "Exemple fictif",
                "home": "Équipe Alpha",
                "away": "Équipe Bravo",
                "kickoff": "2026-10-01 20:00",
                "status": "finished",
                "home_goals": 2,
                "away_goals": 1,
                "probabilities": (0.55, 0.25, 0.20, 0.60, 0.40, 0.58, 0.42),
            },
            {
                "competition": "Exemple fictif",
                "home": "Équipe Charlie",
                "away": "Équipe Delta",
                "kickoff": "2026-10-02 18:00",
                "status": "finished",
                "home_goals": 0,
                "away_goals": 0,
                "probabilities": (0.35, 0.33, 0.32, 0.45, 0.55, 0.48, 0.52),
            },
            {
                "competition": "Exemple fictif",
                "home": "Équipe Echo",
                "away": "Équipe Foxtrot",
                "kickoff": "2026-10-20 20:00",
                "status": "scheduled",
                "home_goals": None,
                "away_goals": None,
                "probabilities": (0.48, 0.28, 0.24, 0.62, 0.38, 0.57, 0.43),
            },
        ]

        for item in examples:
            cursor = connection.execute("""
                INSERT INTO matches (
                    external_id, competition, home_team, away_team,
                    kickoff, status, home_goals, away_goals, is_demo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                "demo-" + item["home"],
                item["competition"],
                item["home"],
                item["away"],
                item["kickoff"],
                item["status"],
                item["home_goals"],
                item["away_goals"],
            ))

            probs = item["probabilities"]
            connection.execute("""
                INSERT INTO predictions (
                    match_id, model_version,
                    p_home, p_draw, p_away,
                    p_over25, p_under25,
                    p_btts_yes, p_btts_no,
                    source_snapshot, is_demo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                cursor.lastrowid,
                "demo-0.1",
                *probs,
                "Données fictives de démonstration",
            ))

        return True



def get_performance(model_version=None):
    """Évalue les pronostics 1N2 sur les matchs réels terminés.

    Si model_version est fourni, évalue uniquement cette version.
    Le score de Brier multiclasses varie de 0 à 2 ; plus bas est meilleur.
    """
    history = get_history()

    completed = [
        row for row in history
        if row["status"] == "finished"
        and row["home_goals"] is not None
        and row["away_goals"] is not None
        and not row["is_demo"]
        and not row["prediction_is_demo"]
        and (
            model_version is None
            or row["model_version"] == model_version
        )
    ]

    if not completed:
        return {
            "matches": 0,
            "accuracy": None,
            "brier": None,
            "demo_only": False,
            "model_version": model_version,
        }

    correct = 0
    total_brier = 0.0

    for row in completed:
        home_goals = row["home_goals"]
        away_goals = row["away_goals"]

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
            row["p_home"],
            row["p_draw"],
            row["p_away"],
        )

        predicted_label = (
            "home" if probabilities[0] >= probabilities[1]
            and probabilities[0] >= probabilities[2]
            else "draw" if probabilities[1] >= probabilities[2]
            else "away"
        )

        if predicted_label == actual_label:
            correct += 1

        total_brier += sum(
            (probability - outcome) ** 2
            for probability, outcome in zip(probabilities, actual)
        )

    return {
        "matches": len(completed),
        "accuracy": correct / len(completed),
        "brier": total_brier / len(completed),
        "demo_only": False,
        "model_version": model_version,
    }


def upsert_api_matches(api_matches):
    """
    Insère ou actualise les matchs provenant de l'API.
    Les prédictions déjà enregistrées ne sont pas modifiées.
    """
    saved = 0

    with get_connection() as connection:
        for match in api_matches:
            competition = match.get("competition") or {}
            home_team = match.get("homeTeam") or {}
            away_team = match.get("awayTeam") or {}
            score = match.get("score") or {}
            full_time = score.get("fullTime") or {}

            match_id = match.get("id")
            competition_name = competition.get("name")
            kickoff = match.get("utcDate")
            home_name = home_team.get("name")
            away_name = away_team.get("name")

            # Ignorer une entrée incomplète plutôt que d'inventer
            # des informations.
            if not all([
                match_id,
                competition_name,
                kickoff,
                home_name,
                away_name,
            ]):
                continue

            api_status = match.get("status", "SCHEDULED")

            if api_status == "FINISHED":
                status = "finished"
            elif api_status in ("IN_PLAY", "LIVE", "PAUSED"):
                status = "live"
            elif api_status in ("POSTPONED", "SUSPENDED", "CANCELLED"):
                status = api_status.lower()
            else:
                status = "scheduled"

            home_goals = full_time.get("home")
            away_goals = full_time.get("away")

            if (
                not isinstance(home_goals, int)
                or not isinstance(away_goals, int)
            ):
                home_goals = None
                away_goals = None

            connection.execute("""
                INSERT INTO matches (
                    external_id,
                    competition,
                    home_team,
                    away_team,
                    kickoff,
                    status,
                    home_goals,
                    away_goals,
                    is_demo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(external_id, competition)
                DO UPDATE SET
                    home_team = excluded.home_team,
                    away_team = excluded.away_team,
                    kickoff = excluded.kickoff,
                    status = excluded.status,
                    home_goals = excluded.home_goals,
                    away_goals = excluded.away_goals
            """, (
                str(match_id),
                competition_name,
                home_name,
                away_name,
                kickoff,
                status,
                home_goals,
                away_goals,
            ))

            saved += 1

    return saved

def save_prediction(match_id, prediction, source_snapshot=None):
    """Enregistre un nouveau pronostic sans modifier l'historique."""
    with get_connection() as connection:
        match = connection.execute(
            "SELECT is_demo FROM matches WHERE id = ?",
            (match_id,),
        ).fetchone()

        if match is None:
            raise ValueError(f"Match introuvable : {match_id}")

        cursor = connection.execute("""
            INSERT INTO predictions (
                match_id,
                model_version,
                p_home,
                p_draw,
                p_away,
                p_over25,
                p_under25,
                p_btts_yes,
                p_btts_no,
                source_snapshot,
                is_demo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            match_id,
            prediction["model_version"],
            prediction["p_home"],
            prediction["p_draw"],
            prediction["p_away"],
            prediction["p_over25"],
            prediction["p_under25"],
            prediction["p_btts_yes"],
            prediction["p_btts_no"],
            source_snapshot,
            match["is_demo"],
        ))

        return cursor.lastrowid
    
def save_prediction(match_id, prediction, source_snapshot=None):
    """Ajoute un pronostic sans modifier les pronostics précédents."""
    with get_connection() as connection:
        match = connection.execute(
            "SELECT is_demo FROM matches WHERE id = ?",
            (match_id,),
        ).fetchone()

        if match is None:
            raise ValueError(f"Match introuvable : {match_id}")

        if match["is_demo"]:
            raise ValueError("Un match fictif ne peut pas recevoir un pronostic réel.")

        cursor = connection.execute("""
            INSERT INTO predictions (
                match_id, model_version,
                p_home, p_draw, p_away,
                p_over25, p_under25,
                p_btts_yes, p_btts_no,
                source_snapshot, is_demo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            match_id,
            prediction["model_version"],
            prediction["p_home"],
            prediction["p_draw"],
            prediction["p_away"],
            prediction["p_over25"],
            prediction["p_under25"],
            prediction["p_btts_yes"],
            prediction["p_btts_no"],
            source_snapshot,
        ))

        return cursor.lastrowid