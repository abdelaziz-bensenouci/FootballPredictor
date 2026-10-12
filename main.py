import json
import sys
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from data_sources.football_data import fetch_matches, fetch_historical_matches
from database import (
    initialize_database, get_matches, get_history, save_prediction,
    upsert_api_matches,
)
from models.team_stats import estimate_expected_goals
from models.poisson_model import predict_match, MODEL_VERSION

APP_STYLE = """
QMainWindow, QWidget { background-color: #0b1120; color: #e5eaf2; font-family: "Segoe UI"; font-size: 13px; }
QFrame#sidebar { background-color: #0f172a; border-right: 1px solid #1e293b; }
QLabel#brand { font-size: 22px; font-weight: 800; color: #34d399; }
QLabel#brandSub { color: #8493a8; font-size: 11px; }
QLabel#pageTitle { font-size: 27px; font-weight: 800; color: #f1f5f9; }
QLabel#pageSubtitle { color: #94a3b8; font-size: 12px; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; color: #e2e8f0; }
QLabel#muted { color: #94a3b8; }
QFrame#statCard { background-color: #111c30; border: 1px solid #23314a; border-radius: 13px; }
QLabel#statLabel { color: #94a3b8; font-size: 12px; }
QLabel#statValue { color: #f8fafc; font-size: 26px; font-weight: 800; }
QLabel#statHint { color: #34d399; font-size: 11px; }
QFrame#heroCard { background-color: #102b2b; border: 1px solid #1c5146; border-radius: 14px; }
QLabel#heroTitle { font-size: 21px; font-weight: 800; color: #ecfdf5; }
QLabel#heroText { color: #a7c9bd; font-size: 12px; }
QPushButton { background-color: #172338; color: #dbe5f1; border: 1px solid #2a3b54; border-radius: 8px; padding: 10px 13px; font-weight: 600; }
QPushButton:hover { background-color: #22334b; border-color: #34d399; }
QPushButton#primary { background-color: #059669; color: #ffffff; border: 1px solid #10b981; }
QPushButton#primary:hover { background-color: #047857; }
QPushButton#navButton { background-color: transparent; color: #aab8ca; text-align: left; padding: 12px; border: 1px solid transparent; border-radius: 8px; }
QPushButton#navButton:hover { background-color: #18263b; color: #ffffff; }
QPushButton#navButton:checked { background-color: #12352f; color: #6ee7b7; border: 1px solid #225b4b; }
QComboBox { background-color: #111c30; color: #e5eaf2; border: 1px solid #2a3b54; border-radius: 8px; padding: 9px 12px; min-width: 220px; }
QComboBox:hover { border-color: #34d399; }
QComboBox QAbstractItemView { background-color: #111c30; color: #e5eaf2; selection-background-color: #145344; selection-color: #ffffff; border: 1px solid #2a3b54; }
QTableWidget { background-color: #101a2b; alternate-background-color: #142137; color: #e5eaf2; gridline-color: #223149; border: 1px solid #23314a; border-radius: 10px; selection-background-color: #164e43; selection-color: #ffffff; }
QHeaderView::section { background-color: #172338; color: #aebdd0; padding: 12px 8px; border: none; border-bottom: 1px solid #2a3b54; font-weight: 700; }
QTableWidget::item { padding: 8px; border: none; }
QTableWidget QScrollBar:vertical { background: #101a2b; width: 10px; margin: 0; }
QTableWidget QScrollBar::handle:vertical { background: #34445d; border-radius: 5px; min-height: 25px; }
QMessageBox, QDialog { background-color: #0b1120; color: #e5eaf2; }
"""

ALL_COMPETITIONS = "Toutes les compétitions"


def parse_datetime(value):
    """Convertit une date en datetime UTC."""
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def predicted_winner(row):
    """Retourne l'issue ayant la probabilité la plus élevée."""
    p_home, p_draw, p_away = row["p_home"], row["p_draw"], row["p_away"]
    if p_home is None or p_draw is None or p_away is None:
        return "À calculer"
    outcomes = [(row["home_team"], p_home), ("Match nul", p_draw), (row["away_team"], p_away)]
    return max(outcomes, key=lambda item: item[1])[0]


def create_table(headers):
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(True)
    return table


def set_cell(table, row, column, value):
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if column in (3, 4):
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    table.setItem(row, column, item)


def make_stat_card(label, value="—", hint=""):
    card = QFrame()
    card.setObjectName("statCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(17, 15, 17, 15)
    layout.setSpacing(8)
    label_widget = QLabel(label)
    label_widget.setObjectName("statLabel")
    value_widget = QLabel(str(value))
    value_widget.setObjectName("statValue")
    hint_widget = QLabel(hint)
    hint_widget.setObjectName("statHint")
    layout.addWidget(label_widget)
    layout.addWidget(value_widget)
    layout.addWidget(hint_widget)
    layout.addStretch()
    return card, value_widget, hint_widget


class HistoryFetchWorker(QThread):
    """Télécharge les résultats historiques dans un thread séparé."""
    matches_ready = Signal(list)
    fetch_error = Signal(str)

    def run(self):
        try:
            matches = fetch_historical_matches(days_back=9)
            self.matches_ready.emit(list(matches or []))
        except Exception as error:
            self.fetch_error.emit(str(error))


class FootballPredictor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FootballPredictor")
        self.resize(1250, 790)
        self.setMinimumSize(950, 650)

        self.history_worker = None
        self.results_dialog = None
        self.results_table = None
        self.results_status = None

        self._build_interface()
        self.refresh_table()

    def _build_interface(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 25, 16, 20)
        side_layout.setSpacing(10)

        brand = QLabel("FootballPredictor")
        brand.setObjectName("brand")
        brand_sub = QLabel("FOOTBALL ANALYTICS")
        brand_sub.setObjectName("brandSub")
        side_layout.addWidget(brand)
        side_layout.addWidget(brand_sub)
        side_layout.addSpacing(28)

        nav_label = QLabel("ESPACE DE TRAVAIL")
        nav_label.setObjectName("muted")
        side_layout.addWidget(nav_label)
        side_layout.addSpacing(4)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.dashboard_nav = self._make_nav_button("▦   Tableau de bord")
        self.matches_nav = self._make_nav_button("⚽   Matchs à venir")
        self.nav_group.addButton(self.dashboard_nav, 0)
        self.nav_group.addButton(self.matches_nav, 1)
        side_layout.addWidget(self.dashboard_nav)
        side_layout.addWidget(self.matches_nav)

        results_nav = self._make_nav_button("◷   Résultats")
        results_nav.setCheckable(False)
        side_layout.addWidget(results_nav)

        self.dashboard_nav.clicked.connect(lambda: self.switch_page(0))
        self.matches_nav.clicked.connect(lambda: self.switch_page(1))
        results_nav.clicked.connect(self.show_results)

        side_layout.addStretch()
        model_label = QLabel(f"Modèle actif\n{MODEL_VERSION}")
        model_label.setObjectName("muted")
        model_label.setWordWrap(True)
        side_layout.addWidget(model_label)
        footer = QLabel("Version desktop")
        footer.setObjectName("brandSub")
        side_layout.addWidget(footer)
        root_layout.addWidget(sidebar)

        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)
        self.pages = QStackedWidget()
        self.dashboard_page = self._build_dashboard_page()
        self.matches_page = self._build_matches_page()
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.matches_page)
        main_layout.addWidget(self.pages)
        root_layout.addWidget(main_area, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLE)

        # Démarrage directement sur « Matchs à venir ».
        self.pages.setCurrentIndex(1)
        self.matches_nav.setChecked(True)

    def _make_nav_button(self, text):
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setMinimumHeight(43)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _build_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Tableau de bord")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Vue d'ensemble de vos matchs et pronostics")
        subtitle.setObjectName("pageSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        self.clock_label = QLabel(datetime.now().astimezone().strftime("%d/%m/%Y"))
        self.clock_label.setObjectName("muted")
        header.addWidget(self.clock_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        cards = QGridLayout()
        cards.setSpacing(14)
        card1, self.total_matches_value, _ = make_stat_card("MATCHS À VENIR", "0", "Matchs programmés")
        card2, self.predictions_value, _ = make_stat_card("PRONOSTICS DISPONIBLES", "0", "Déjà calculés")
        card3, self.competitions_value, _ = make_stat_card("COMPÉTITIONS", "0", "Avec des matchs à venir")
        card4, self.success_rate_value, self.success_rate_hint = make_stat_card(
            "TAUX DE RÉUSSITE", "—", "En attente de résultats"
        )
        cards.addWidget(card1, 0, 0)
        cards.addWidget(card2, 0, 1)
        cards.addWidget(card3, 0, 2)
        cards.addWidget(card4, 0, 3)
        layout.addLayout(cards)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(23, 22, 23, 22)
        hero_layout.setSpacing(10)
        hero_title = QLabel("Vos prochains pronostics")
        hero_title.setObjectName("heroTitle")
        hero_text = QLabel(
            "Actualisez les rencontres, puis calculez les pronostics qui manquent. "
            "Les prédictions reposent sur votre modèle statistique actuel."
        )
        hero_text.setObjectName("heroText")
        hero_text.setWordWrap(True)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_text)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.refresh_button = QPushButton("Actualiser les matchs")
        self.refresh_button.clicked.connect(self.refresh_matches_from_api)
        self.predict_button = QPushButton("Calculer les pronostics")
        self.predict_button.setObjectName("primary")
        self.predict_button.clicked.connect(self.calculate_predictions)
        open_matches_button = QPushButton("Consulter les matchs")
        open_matches_button.clicked.connect(lambda: self.switch_page(1))
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.predict_button)
        actions.addWidget(open_matches_button)
        actions.addStretch()
        hero_layout.addLayout(actions)
        layout.addWidget(hero)

        section_title = QLabel("État de l'application")
        section_title.setObjectName("sectionTitle")
        layout.addWidget(section_title)
        self.status_label = QLabel("Chargement des données locales...")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(45)
        layout.addWidget(self.status_label)
        note = QLabel(
            "Les données sont actualisées lorsque tu lances manuellement une actualisation. "
            "Les probabilités restent des estimations, pas des garanties de résultat."
        )
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _build_matches_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        title = QLabel("Matchs à venir")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Rencontres programmées et vainqueur estimé par le modèle")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        filter_label = QLabel("Compétition")
        self.competition_filter = QComboBox()
        self.competition_filter.addItem(ALL_COMPETITIONS)
        self.competition_filter.setToolTip("Filtrer les rencontres par compétition")
        self.competition_filter.currentTextChanged.connect(lambda _text: self.refresh_table())
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.competition_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.matches_table = create_table(["Date et heure", "Compétition", "Rencontre", "Vainqueur prédit"])
        self.matches_table.setMinimumHeight(300)
        layout.addWidget(self.matches_table, 1)
        table_note = QLabel(
            "Les matchs terminés et les données de démonstration ne sont pas affichés dans cette liste."
        )
        table_note.setObjectName("pageSubtitle")
        table_note.setWordWrap(True)
        layout.addWidget(table_note)
        return page

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        self.dashboard_nav.setChecked(index == 0)
        self.matches_nav.setChecked(index == 1)

    def refresh_table(self):
        """Met à jour les statistiques et la liste des matchs futurs."""
        now = datetime.now(timezone.utc)
        rows = get_matches()
        upcoming = []
        for row in rows:
            if row["is_demo"] or row["status"] != "scheduled":
                continue
            kickoff = parse_datetime(row["kickoff"])
            if kickoff is None or kickoff <= now or row["prediction_is_demo"]:
                continue
            upcoming.append((kickoff, row))
        upcoming.sort(key=lambda item: item[0])

        selected_competition = self.competition_filter.currentText()
        competitions = sorted(
            {row["competition"] for _, row in upcoming if row["competition"]},
            key=str.casefold,
        )
        options = [ALL_COMPETITIONS] + competitions
        self.competition_filter.blockSignals(True)
        try:
            self.competition_filter.clear()
            self.competition_filter.addItems(options)
            if selected_competition in options:
                self.competition_filter.setCurrentText(selected_competition)
            else:
                self.competition_filter.setCurrentIndex(0)
        finally:
            self.competition_filter.blockSignals(False)

        all_upcoming_count = len(upcoming)
        all_predictions_count = sum(
            1 for _, row in upcoming
            if row["p_home"] is not None and row["p_draw"] is not None and row["p_away"] is not None
        )
        all_competitions_count = len(competitions)
        self.total_matches_value.setText(str(all_upcoming_count))
        self.predictions_value.setText(str(all_predictions_count))
        self.competitions_value.setText(str(all_competitions_count))
        self.refresh_success_rate()

        selected_competition = self.competition_filter.currentText()
        if selected_competition != ALL_COMPETITIONS:
            upcoming = [(kickoff, row) for kickoff, row in upcoming if row["competition"] == selected_competition]

        table = self.matches_table
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(upcoming))
            for index, (kickoff, row) in enumerate(upcoming):
                values = [
                    kickoff.astimezone().strftime("%d/%m/%Y %H:%M"),
                    row["competition"],
                    f"{row['home_team']} - {row['away_team']}",
                    predicted_winner(row),
                ]
                for column, value in enumerate(values):
                    set_cell(table, index, column, value)
        finally:
            table.setUpdatesEnabled(True)
            table.viewport().update()

        self.status_label.setText(
            f"{all_upcoming_count} match(s) à venir • {all_predictions_count} pronostic(s) disponible(s) • "
            f"{all_competitions_count} compétition(s) • Modèle : {MODEL_VERSION}"
        )
        self.clock_label.setText(datetime.now().astimezone().strftime("%d/%m/%Y"))

    def refresh_success_rate(self):
        """Calcule le taux de réussite sur les matchs terminés ayant un pronostic réel."""
        try:
            evaluated = 0
            correct = 0

            for row in get_history():
                if row["is_demo"] or row["prediction_is_demo"]:
                    continue
                if row["status"] != "finished":
                    continue

                home_goals = row["home_goals"]
                away_goals = row["away_goals"]
                if home_goals is None or away_goals is None:
                    continue

                winner = predicted_winner(row)
                if winner == "À calculer":
                    continue

                if home_goals > away_goals:
                    actual = row["home_team"]
                elif home_goals == away_goals:
                    actual = "Match nul"
                else:
                    actual = row["away_team"]

                evaluated += 1
                if winner == actual:
                    correct += 1

            if evaluated:
                percentage = correct / evaluated * 100
                self.success_rate_value.setText(f"{percentage:.1f}%".replace(".", ","))
                self.success_rate_hint.setText(
                    f"{correct} bon(s) pronostic(s) sur {evaluated} match(s) évalué(s)"
                )
            else:
                self.success_rate_value.setText("—")
                self.success_rate_hint.setText("Aucun match terminé avec pronostic réel")
        except Exception as error:
            self.success_rate_value.setText("—")
            self.success_rate_hint.setText("Calcul indisponible")
            self.success_rate_value.setToolTip(str(error))

    def refresh_matches_from_api(self):
        """Importe les matchs à venir depuis l'API (fonction synchrone)."""
        self.refresh_button.setEnabled(False)
        try:
            matches = fetch_matches()
            saved = upsert_api_matches(matches)
            self.refresh_table()
            QMessageBox.information(
                self, "Actualisation terminée",
                f"Matchs reçus de l'API : {len(matches)}\n"
                f"Matchs enregistrés ou actualisés : {saved}\n\n"
                "Tu peux maintenant calculer les pronostics manquants.",
            )
        except Exception as error:
            QMessageBox.critical(self, "Erreur d'actualisation", f"Impossible d'actualiser les matchs :\n\n{error}")
        finally:
            self.refresh_button.setEnabled(True)

    def calculate_predictions(self):
        """Calcule les pronostics manquants pour les matchs futurs."""
        now = datetime.now(timezone.utc)
        rows = get_matches()
        created = 0
        already_present = 0
        skipped_invalid = 0
        errors = []
        self.predict_button.setEnabled(False)
        try:
            for row in rows:
                if row["is_demo"] or row["status"] != "scheduled":
                    continue
                kickoff = parse_datetime(row["kickoff"])
                if kickoff is None:
                    skipped_invalid += 1
                    continue
                if kickoff <= now or row["prediction_is_demo"]:
                    continue
                if row["model_version"] == MODEL_VERSION:
                    already_present += 1
                    continue
                try:
                    stats = estimate_expected_goals(row["id"])
                    prediction = predict_match(
                        home_expected_goals=stats["expected_goals_home"],
                        away_expected_goals=stats["expected_goals_away"],
                    )
                    snapshot = {
                        "competition": stats["competition"],
                        "historical_matches": stats["historical_matches"],
                        "home_matches_in_history": stats["home_matches_in_history"],
                        "away_matches_in_history": stats["away_matches_in_history"],
                        "expected_goals_home": stats["expected_goals_home"],
                        "expected_goals_away": stats["expected_goals_away"],
                    }
                    save_prediction(row["id"], prediction, source_snapshot=json.dumps(snapshot, ensure_ascii=False))
                    created += 1
                except (ValueError, KeyError) as error:
                    if len(errors) < 5:
                        errors.append(f"{row['home_team']} - {row['away_team']} : {error}")
            self.refresh_table()
            message = (
                f"Nouveaux pronostics : {created}\n"
                f"Pronostics déjà présents : {already_present}\n"
                f"Dates invalides : {skipped_invalid}\n"
                f"Exemples de matchs non calculés : {len(errors)}"
            )
            if errors:
                message += "\n\n" + "\n".join(errors)
            QMessageBox.information(self, "Calcul terminé", message)
        except Exception as error:
            QMessageBox.critical(self, "Erreur de calcul", str(error))
        finally:
            self.predict_button.setEnabled(True)

    def show_results(self):
        """Affiche d'abord les données locales, puis actualise en arrière-plan."""
        if self.results_dialog is not None:
            try:
                if self.results_dialog.isVisible():
                    self._populate_results_table()
                    self.results_dialog.raise_()
                    self.results_dialog.activateWindow()
                    self._start_history_update()
                    return
            except RuntimeError:
                self._clear_results_dialog()

        dialog = QDialog(self)
        dialog.setWindowTitle("Résultats des pronostics")
        dialog.resize(1050, 620)
        dialog.setStyleSheet(APP_STYLE)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(15)

        title = QLabel("Résultats des pronostics")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Comparaison entre le vainqueur prédit et le résultat réel")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        self.results_status = QLabel("Chargement des résultats locaux...")
        self.results_status.setObjectName("muted")
        self.results_status.setWordWrap(True)
        layout.addWidget(self.results_status)
        self.results_table = create_table(["Date", "Rencontre", "Pronostic", "Score final", "Verdict"])
        layout.addWidget(self.results_table, 1)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.results_dialog = dialog
        dialog.finished.connect(lambda _result, d=dialog: self._clear_results_dialog(d))
        self._populate_results_table()
        dialog.show()
        self._start_history_update()

    def _populate_results_table(self):
        """Remplit le tableau depuis la base locale."""
        table = self.results_table
        if table is None:
            return
        try:
            completed = []
            for row in get_history():
                if row["is_demo"] or row["prediction_is_demo"]:
                    continue
                if row["status"] != "finished":
                    continue
                if row["home_goals"] is None or row["away_goals"] is None:
                    continue
                completed.append(row)
            completed.sort(key=lambda row: row["kickoff"] or "", reverse=True)
            table.setUpdatesEnabled(False)
            try:
                table.setRowCount(len(completed))
                for index, row in enumerate(completed):
                    winner = predicted_winner(row)
                    home_goals, away_goals = row["home_goals"], row["away_goals"]
                    score = f"{home_goals} - {away_goals}"
                    if home_goals > away_goals:
                        actual = row["home_team"]
                    elif home_goals == away_goals:
                        actual = "Match nul"
                    else:
                        actual = row["away_team"]
                    if winner == "À calculer":
                        verdict = "Non évalué"
                    elif winner == actual:
                        verdict = "Correct"
                    else:
                        verdict = "Incorrect"
                    kickoff = parse_datetime(row["kickoff"])
                    date_text = kickoff.astimezone().strftime("%d/%m/%Y") if kickoff else str(row["kickoff"])
                    values = [date_text, f"{row['home_team']} - {row['away_team']}", winner, score, verdict]
                    for column, value in enumerate(values):
                        set_cell(table, index, column, value)
            finally:
                table.setUpdatesEnabled(True)
                table.viewport().update()
            if self.results_status is not None:
                if completed:
                    self.results_status.setText(f"{len(completed)} match(s) terminé(s) chargé(s) depuis la base locale.")
                else:
                    self.results_status.setText("Aucun résultat terminé disponible localement. Recherche des scores récents en arrière-plan...")
        except Exception as error:
            if self.results_status is not None:
                self.results_status.setText(f"Impossible de lire les résultats locaux : {error}")

    def _start_history_update(self):
        """Démarre le téléchargement historique sans bloquer l'interface."""
        if self.history_worker is not None and self.history_worker.isRunning():
            return
        if self.results_status is not None:
            self.results_status.setText("Actualisation des scores en arrière-plan. L'application reste utilisable.")
        worker = HistoryFetchWorker(self)
        self.history_worker = worker
        worker.matches_ready.connect(self._on_history_matches_ready)
        worker.fetch_error.connect(self._on_history_fetch_error)
        worker.finished.connect(self._on_history_worker_finished)
        worker.start()

    def _on_history_matches_ready(self, matches):
        """Enregistre les scores reçus et rafraîchit les vues."""
        try:
            if matches:
                upsert_api_matches(matches)
            self.refresh_table()
            self._populate_results_table()
            if self.results_status is not None:
                self.results_status.setText(
                    "Actualisation terminée : les données locales ont été mises à jour."
                    if matches else
                    "Actualisation terminée. Aucune donnée historique supplémentaire reçue."
                )
        except Exception as error:
            if self.results_status is not None:
                self.results_status.setText(f"Erreur pendant l'enregistrement des scores : {error}")
            self.status_label.setText(f"Erreur pendant l'actualisation des résultats : {error}")

    def _on_history_fetch_error(self, message):
        if self.results_status is not None:
            self.results_status.setText(
                "Impossible d'actualiser les scores. Les résultats locaux restent disponibles. "
                f"Détail : {message}"
            )
        self.status_label.setText("Actualisation des résultats indisponible ; les données locales restent consultables.")

    def _on_history_worker_finished(self):
        worker = self.sender()
        if worker is self.history_worker:
            self.history_worker = None
        if worker is not None:
            worker.deleteLater()

    def _clear_results_dialog(self, dialog=None):
        if dialog is not None and self.results_dialog is not dialog:
            return
        self.results_dialog = None
        self.results_table = None
        self.results_status = None


def main():
    initialize_database()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = FootballPredictor()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
