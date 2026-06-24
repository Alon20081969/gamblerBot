import queue
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import pandas as pd

from src.gui_components import (
    AdvisorMixin,
    BettingMixin,
    CompetitionMixin,
    GuideMixin,
    HistoryExportMixin,
    ResultsMixin,
)
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PageRouter:
    """Small adapter so older component code can still call self.view_tabs.set(...)."""

    def __init__(self, app):
        self.app = app

    def set(self, page_name):
        self.app.show_page(page_name)


class GamblerBotGUI(
    CompetitionMixin, ResultsMixin, BettingMixin, HistoryExportMixin,
    GuideMixin, AdvisorMixin, ctk.CTk
):
    """Application shell coordinating the API, worker threads, and UI components."""

    COLORS = {
        "bg": "#0f1724",
        "panel": "#172131",
        "panel_alt": "#202c3f",
        "panel_soft": "#111b2a",
        "border": "#2d3b50",
        "border_light": "#41536c",
        "text": "#f4f7fb",
        "muted": "#9aa8ba",
        "accent": "#2f80ed",
        "accent_hover": "#4d96f4",
        "success": "#39c47f",
        "danger": "#d65f5f",
        "warning": "#f2b632",
    }

    FAVORITES_FILE = Path(__file__).resolve().parents[1] / ".gamblerbot_favorites.json"
    SAVED_SLIPS_FILE = Path(__file__).resolve().parents[1] / ".gamblerbot_saved_slips.json"
    EXPORT_DIR = Path(__file__).resolve().parents[1] / "exports"
    FALLBACK_COMPETITIONS = {
        "Baseball": {"MLB": {"key": "baseball_mlb", "region": "us"}},
        "Basketball": {"NBA": {"key": "basketball_nba", "region": "us"}},
        "American Football": {
            "NFL": {"key": "americanfootball_nfl", "region": "us"}
        },
        "Soccer": {
            "English Premier League": {"key": "soccer_epl", "region": "eu"},
            "UEFA Champions League": {
                "key": "soccer_uefa_champs_league", "region": "eu"
            },
            "FIFA World Cup": {"key": "soccer_fifa_world_cup", "region": "eu"},
        },
    }

    def __init__(self):
        super().__init__()
        self.title("GamblerBot - Live Market Scanner")
        self.geometry("1280x760")
        self.minsize(1060, 650)
        self.configure(fg_color=self.COLORS["bg"])

        self.client = OddsAPIClient()
        self.favorite_competition_keys = self.load_favorites()
        self.saved_slips = self.load_saved_slips()
        self.selected_bets = {}
        self.odds_buttons = {}
        self.custom_odd_controls = {}
        self.previous_odds_snapshot = {}
        self.odds_movements = {}
        self.latest_market_snapshot = {}
        self.suspicious_odds_identities = set()
        self.latest_market_scan_at = None
        self.odds_history = {}
        self.history_series_labels = {}
        self.ui_queue = queue.Queue()
        self.is_closing = False
        self.results_generation = 0
        self.search_after_id = None
        self.result_search_after_id = None
        self.latest_results_df = None
        self.scan_in_progress = False
        self.auto_refresh_enabled = False
        self.auto_refresh_started = False
        self.auto_refresh_after_id = None
        self.auto_refresh_remaining = 5 * 60
        self.auto_refresh_quota_paused = False
        self.competition_catalog = {
            sport: {name: config.copy() for name, config in competitions.items()}
            for sport, competitions in self.FALLBACK_COMPETITIONS.items()
        }

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        self.after(50, self.process_ui_queue)
        self.refresh_competition_catalog()

    def create_widgets(self):
        self.page_names = [
            "Competitions", "Results", "Best", "Advisor", "Bet Slip", "Calculator",
            "History", "Console", "Guide", "Settings",
        ]
        self._build_top_controls()
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.log_frame = ctk.CTkFrame(
            self.content_frame,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
            corner_radius=14,
        )
        self.log_frame.grid(row=0, column=0, sticky="nsew")
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.view_tabs = PageRouter(self)
        self.pages = {}
        for page_name in self.page_names:
            page = ctk.CTkFrame(self.log_frame, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            self.pages[page_name] = page
        self.competitions_tab = self.pages["Competitions"]
        self.results_tab = self.pages["Results"]
        self.best_tab = self.pages["Best"]
        self.advisor_tab = self.pages["Advisor"]
        self.gamble_tab = self.pages["Bet Slip"]
        self.calculator_tab = self.pages["Calculator"]
        self.history_tab = self.pages["History"]
        self.console_tab = self.pages["Console"]
        self.guide_tab = self.pages["Guide"]
        self.settings_tab = self.pages["Settings"]

        self.build_competition_browser(self.competitions_tab)
        self.build_results_tab()
        self.build_advisor_tab()
        self.build_betting_tabs()
        self.build_history_tab()
        self._build_console_tab()
        self.build_guide_tab()
        self._build_settings_tab()
        self.show_page("Results")
        self.write_to_terminal(
            "System Ready. Select a sport and competition, then click 'Scan Market'...\n"
        )

    def show_page(self, page_name):
        if not hasattr(self, "pages") or page_name not in self.pages:
            return
        self.pages[page_name].tkraise()
        self.update_nav_button_styles(page_name)

    def update_nav_button_styles(self, active_page=None):
        if not hasattr(self, "nav_buttons"):
            return
        active_page = active_page or getattr(self, "current_page", "Results")
        self.current_page = active_page
        for page_name, button in self.nav_buttons.items():
            selected = page_name == active_page
            button.configure(
                fg_color=self.COLORS["accent"] if selected else "transparent",
                hover_color=self.COLORS["panel_alt"],
                text_color="white" if selected else self.COLORS["muted"],
                border_width=1 if selected else 0,
                border_color=self.COLORS["accent_hover"],
            )

    def _build_top_controls(self):
        self.top_frame = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.top_frame.pack(side="top", fill="x")
        self.top_frame.grid_columnconfigure(1, weight=1)
        self.top_frame.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            self.top_frame,
            text="GamblerBot",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=(18, 18), pady=(9, 6))

        nav_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        nav_frame.grid(row=0, column=1, columnspan=5, sticky="w", pady=(9, 6))
        self.nav_buttons = {}
        nav_labels = {
            "Competitions": "Leagues",
            "Results": "Results",
            "Best": "Best",
            "Advisor": "Advisor",
            "Bet Slip": "Slip",
            "Calculator": "Calc",
            "History": "History",
            "Console": "Console",
            "Guide": "Guide",
            "Settings": "Settings",
        }
        for page_name in self.page_names:
            button = ctk.CTkButton(
                nav_frame,
                text=nav_labels[page_name],
                command=lambda name=page_name: self.show_page(name),
                width=66,
                height=30,
                corner_radius=8,
                fg_color="transparent",
                hover_color=self.COLORS["panel_alt"],
                text_color=self.COLORS["muted"],
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            button.pack(side="left", padx=(0, 5))
            self.nav_buttons[page_name] = button

        self.sport_dropdown = ctk.CTkComboBox(
            self.top_frame,
            values=sorted(self.competition_catalog),
            command=self.on_sport_changed,
            width=190,
            height=34,
            state="readonly",
            fg_color=self.COLORS["panel_alt"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
            border_color=self.COLORS["border_light"],
            dropdown_fg_color=self.COLORS["panel_alt"],
        )
        self.sport_dropdown.set("Soccer")
        self.sport_dropdown.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 8))

        self.competition_dropdown = ctk.CTkComboBox(
            self.top_frame,
            values=[],
            width=300,
            height=34,
            state="readonly",
            fg_color=self.COLORS["panel_alt"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
            border_color=self.COLORS["border_light"],
            dropdown_fg_color=self.COLORS["panel_alt"],
        )
        self.competition_dropdown.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))
        self.on_sport_changed("Soccer")

        self.scan_button = ctk.CTkButton(
            self.top_frame,
            text="Scan",
            command=self.start_async_scan,
            width=94,
            height=34,
            corner_radius=10,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.scan_button.grid(row=1, column=2, sticky="w", padx=(0, 10), pady=(0, 8))

        sync_status_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        sync_status_frame.grid(
            row=1, column=3, sticky="w", padx=(0, 10), pady=(0, 8)
        )
        self.scan_freshness_label = ctk.CTkLabel(
            sync_status_frame,
            text="Odds: not scanned",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        )
        self.scan_freshness_label.pack(side="left")
        self.winner_sync_label = ctk.CTkLabel(
            sync_status_frame,
            text=" • Winner: waiting",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        )
        self.winner_sync_label.pack(side="left")

        self.slip_summary_button = ctk.CTkButton(
            self.top_frame,
            text="Slip: empty",
            command=lambda: self.show_page("Bet Slip"),
            width=170,
            height=34,
            corner_radius=10,
            fg_color=self.COLORS["panel_alt"],
            hover_color=self.COLORS["border_light"],
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.slip_summary_button.grid(row=1, column=4, sticky="e", padx=(0, 8), pady=(0, 8))

        self.quota_label = ctk.CTkLabel(
            self.top_frame,
            text="Credits: loading...",
            fg_color=self.COLORS["panel_alt"],
            corner_radius=10,
            padx=10,
            pady=6,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.quota_label.grid(row=1, column=5, sticky="e", padx=(0, 18), pady=(0, 8))

        self.catalog_status = ctk.CTkLabel(
            self.top_frame,
            text="Loading competitions...",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        )
        self.update_nav_slip_summary()
        self.update_nav_button_styles("Results")

    def update_nav_slip_summary(self):
        if not hasattr(self, "slip_summary_button"):
            return
        count = len(self.selected_bets)
        if not count:
            self.slip_summary_button.configure(
                text="Slip: empty",
                fg_color=self.COLORS["panel_alt"],
                hover_color=self.COLORS["border_light"],
                text_color=self.COLORS["muted"],
            )
            return

        combined = 1.0
        for bet in self.selected_bets.values():
            combined *= float(bet["odds"])

        text = f"Slip: {count} pick{'s' if count != 1 else ''} | {combined:.2f}"
        try:
            if hasattr(self, "stake_entry"):
                stake_text = self.stake_entry.get().strip()
                stake = float(stake_text) if stake_text else 0.0
                if stake > 0:
                    text += f" | Return {stake * combined:,.2f}"
        except ValueError:
            text += " | check stake"

        self.slip_summary_button.configure(
            text=text,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
            text_color="white",
        )

    def _build_settings_tab(self):
        self.settings_tab.grid_rowconfigure(1, weight=1)
        self.settings_tab.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.settings_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        ctk.CTkLabel(
            header,
            text="Settings",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.COLORS["text"],
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Control scanning, API safety, and local project data.",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=14)

        settings_grid = ctk.CTkFrame(self.settings_tab, fg_color="transparent")
        settings_grid.grid(row=1, column=0, sticky="nsew", padx=18, pady=(2, 18))
        settings_grid.grid_columnconfigure((0, 1), weight=1, uniform="settings")
        settings_grid.grid_rowconfigure(2, weight=1)

        auto_card = self._settings_card(
            settings_grid,
            row=0,
            column=0,
            title="Auto-refresh",
            description="Automatically scan the selected competition on a timer.",
        )
        self._build_auto_refresh_controls(auto_card)

        safety_card = self._settings_card(
            settings_grid,
            row=0,
            column=1,
            title="API credit safety",
            description="Pause automatic scans before your API credits run too low.",
        )
        self._build_credit_safety_controls(safety_card)

        data_card = self._settings_card(
            settings_grid,
            row=1,
            column=0,
            title="Local data",
            description="Exports and saved app data stay inside this project.",
        )
        self._build_data_settings_card(data_card)

        tips_card = self._settings_card(
            settings_grid,
            row=1,
            column=1,
            title="Quick guide",
            description="Short reminders for using the scanner clearly.",
        )
        self._build_settings_tips_card(tips_card)

    def _settings_card(self, parent, row, column, title, description):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.COLORS["panel_soft"],
            border_width=1,
            border_color=self.COLORS["border"],
            corner_radius=14,
        )
        card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 3))
        ctk.CTkLabel(
            card,
            text=description,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        return card

    def _build_auto_refresh_controls(self, parent):
        controls = ctk.CTkFrame(
            parent,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
            corner_radius=12,
        )
        controls.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        controls.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(
            controls,
            text="Scan every",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(14, 8), pady=14, sticky="w")
        self.refresh_interval = ctk.CTkComboBox(
            controls,
            values=["1", "2", "5", "10", "15", "30"],
            width=68,
            height=32,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
            command=lambda _value: self.change_auto_refresh_interval(),
        )
        self.refresh_interval.set("5")
        self.refresh_interval.grid(row=0, column=1, padx=(0, 8), pady=14)
        self.refresh_interval.bind("<Return>", lambda _event: self.change_auto_refresh_interval())
        self.refresh_interval.bind("<FocusOut>", lambda _event: self.change_auto_refresh_interval())
        ctk.CTkLabel(
            controls,
            text="minutes",
            text_color=self.COLORS["muted"],
        ).grid(row=0, column=2, padx=(0, 14), pady=14)
        self.auto_refresh_button = ctk.CTkButton(
            controls,
            text="Start",
            command=self.toggle_auto_refresh,
            width=86,
            height=32,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
        )
        self.auto_refresh_button.grid(row=0, column=3, padx=(0, 14), pady=14)
        self.auto_refresh_label = ctk.CTkLabel(
            controls,
            text="Ready • 05:00",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.auto_refresh_label.grid(row=0, column=4, padx=(0, 14), pady=14, sticky="w")

    def _build_credit_safety_controls(self, parent):
        quota_controls = ctk.CTkFrame(
            parent,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
            corner_radius=12,
        )
        quota_controls.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        quota_controls.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            quota_controls,
            text="Pause at",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(14, 8), pady=(14, 6), sticky="w")
        self.credit_floor = ctk.CTkComboBox(
            quota_controls,
            values=["5", "10", "25", "50", "100"],
            width=68,
            height=32,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
        )
        self.credit_floor.set("10")
        self.credit_floor.grid(row=0, column=1, padx=(0, 8), pady=(14, 6))
        ctk.CTkLabel(
            quota_controls,
            text="credits remaining",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=2, padx=(0, 14), pady=(14, 6), sticky="w")
        ctk.CTkLabel(
            quota_controls,
            text="Auto-refresh pauses before crossing this credit level.",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 14))

    def _build_data_settings_card(self, parent):
        ctk.CTkLabel(
            parent,
            text=f"Exports folder: {self.EXPORT_DIR.name}/",
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(2, 5))
        ctk.CTkLabel(
            parent,
            text=(
                "Scan CSVs, bet-slip CSVs, and history exports are saved in "
                "the project exports folder. Favorites and saved slips are "
                "stored as hidden JSON files in the project root."
            ),
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=520,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))

    def _build_settings_tips_card(self, parent):
        tips = (
            "• Favorite leagues in Competitions.\n"
            "• Results shows highest and lowest bookmaker odds.\n"
            "• Click an odd to add or remove it from Bet Slip.\n"
            "• History is useful after scanning the same competition twice."
        )
        ctk.CTkLabel(
            parent,
            text=tips,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(2, 16))

    def _build_console_tab(self):
        header = ctk.CTkFrame(self.console_tab, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(
            header, text="Console Feed", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Clear", command=self.clear_terminal, width=74, height=28,
            fg_color=("gray70", "gray28"), hover_color=("gray60", "gray35"),
        ).pack(side="right")
        self.terminal_box = ctk.CTkTextbox(
            self.console_tab,
            font=("Consolas", 12),
            state="disabled",
            wrap="word",
            fg_color=self.COLORS["panel_soft"],
            border_width=1,
            border_color=self.COLORS["border"],
            corner_radius=10,
        )
        self.terminal_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def post_to_ui(self, callback, *args, **kwargs):
        if not self.is_closing:
            self.ui_queue.put((callback, args, kwargs))

    def process_ui_queue(self):
        if self.is_closing:
            return
        for _ in range(100):
            try:
                callback, args, kwargs = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                if not self.is_closing:
                    print(f"[!] UI update failed safely ({type(exc).__name__}): {exc}")
        if not self.is_closing:
            self.after(50, self.process_ui_queue)

    def close_application(self):
        self.is_closing = True
        if self.auto_refresh_after_id is not None:
            try:
                self.after_cancel(self.auto_refresh_after_id)
            except tk.TclError:
                pass
        self.destroy()

    @staticmethod
    def format_countdown(seconds):
        minutes, remaining_seconds = divmod(max(0, int(seconds)), 60)
        return f"{minutes:02d}:{remaining_seconds:02d}"

    def get_refresh_interval_seconds(self):
        try:
            minutes = float(self.refresh_interval.get().strip())
            if minutes <= 0 or minutes > 1440:
                raise ValueError
            return max(1, round(minutes * 60))
        except ValueError:
            return None

    def get_credit_floor(self):
        try:
            floor = int(self.credit_floor.get().strip())
            return floor if floor >= 0 else None
        except ValueError:
            return None

    def remaining_credit_count(self):
        try:
            remaining = self.client.usage.get("remaining")
            return int(remaining) if remaining is not None else None
        except (TypeError, ValueError):
            return None

    def auto_refresh_has_credits(self):
        remaining = self.remaining_credit_count()
        floor = self.get_credit_floor()
        return remaining is None or floor is None or remaining > floor

    def pause_auto_refresh_for_quota(self):
        remaining = self.remaining_credit_count()
        floor = self.get_credit_floor()
        if remaining is None or floor is None or remaining > floor:
            return False
        if not self.auto_refresh_enabled:
            return False
        self.auto_refresh_enabled = False
        self.auto_refresh_quota_paused = True
        self.cancel_auto_refresh_tick()
        self.auto_refresh_button.configure(text="Resume")
        self.auto_refresh_label.configure(
            text=f"Credit protection paused auto-refresh • {remaining} remaining"
        )
        return True

    def change_auto_refresh_interval(self):
        seconds = self.get_refresh_interval_seconds()
        if seconds is None:
            self.auto_refresh_label.configure(text="Enter 0.01–1440 minutes")
            return
        if self.auto_refresh_enabled and not self.auto_refresh_has_credits():
            self.pause_auto_refresh_for_quota()
            return
        self.auto_refresh_remaining = seconds
        state = "Next scan" if self.auto_refresh_enabled else (
            "Paused" if self.auto_refresh_started else "Ready"
        )
        self.auto_refresh_label.configure(
            text=f"{state} • {self.format_countdown(seconds)}"
        )
        if self.auto_refresh_enabled:
            self.schedule_auto_refresh_tick()

    def toggle_auto_refresh(self):
        if self.auto_refresh_enabled:
            self.auto_refresh_enabled = False
            self.cancel_auto_refresh_tick()
            self.auto_refresh_button.configure(text="Resume")
            self.auto_refresh_label.configure(
                text=f"Paused • {self.format_countdown(self.auto_refresh_remaining)}"
            )
            return

        seconds = self.get_refresh_interval_seconds()
        if seconds is None:
            self.auto_refresh_label.configure(text="Enter 0.01–1440 minutes")
            return
        if not self.auto_refresh_has_credits():
            remaining = self.remaining_credit_count()
            self.auto_refresh_started = True
            self.auto_refresh_quota_paused = True
            self.auto_refresh_button.configure(text="Resume")
            self.auto_refresh_label.configure(
                text=f"Credit protection paused auto-refresh • {remaining} remaining"
            )
            return
        if not self.auto_refresh_started or self.auto_refresh_remaining <= 0:
            self.auto_refresh_remaining = seconds
        self.auto_refresh_started = True
        self.auto_refresh_enabled = True
        self.auto_refresh_quota_paused = False
        self.auto_refresh_button.configure(text="Pause")
        self.auto_refresh_label.configure(
            text=f"Next scan • {self.format_countdown(self.auto_refresh_remaining)}"
        )
        self.schedule_auto_refresh_tick()

    def cancel_auto_refresh_tick(self):
        if self.auto_refresh_after_id is not None:
            try:
                self.after_cancel(self.auto_refresh_after_id)
            except tk.TclError:
                pass
            self.auto_refresh_after_id = None

    def schedule_auto_refresh_tick(self):
        self.cancel_auto_refresh_tick()
        if self.auto_refresh_enabled and not self.is_closing:
            self.auto_refresh_after_id = self.after(1000, self.auto_refresh_tick)

    def auto_refresh_tick(self):
        self.auto_refresh_after_id = None
        if not self.auto_refresh_enabled or self.is_closing:
            return
        if self.scan_in_progress:
            self.auto_refresh_label.configure(text="Scan running…")
            return
        if not self.auto_refresh_has_credits():
            self.pause_auto_refresh_for_quota()
            return
        self.auto_refresh_remaining -= 1
        if self.auto_refresh_remaining <= 0:
            if self.start_async_scan():
                self.auto_refresh_label.configure(text="Auto-refresh scanning…")
                return
            self.auto_refresh_remaining = self.get_refresh_interval_seconds() or 300
        self.auto_refresh_label.configure(
            text=f"Next scan • {self.format_countdown(self.auto_refresh_remaining)}"
        )
        self.schedule_auto_refresh_tick()

    def refresh_quota_display(self):
        usage = self.client.usage
        remaining, used, last = (
            usage.get("remaining"), usage.get("used"), usage.get("last")
        )
        if remaining is None:
            self.quota_label.configure(text="Credits: n/a")
            return
        text = f"Credits: {remaining}"
        if last is not None:
            text += f"  |  scan {last}"
        elif used is not None:
            text += f"  |  used {used}"
        self.quota_label.configure(text=text)
        self.pause_auto_refresh_for_quota()

    def write_to_terminal(self, text):
        if threading.current_thread() is not threading.main_thread():
            self.post_to_ui(self.write_to_terminal, text)
            return
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert(tk.END, text + "\n")
        self.terminal_box.see(tk.END)
        self.terminal_box.configure(state="disabled")

    def clear_terminal(self):
        self.terminal_box.configure(state="normal")
        self.terminal_box.delete("1.0", tk.END)
        self.terminal_box.configure(state="disabled")

    def start_async_scan(self):
        if self.scan_in_progress:
            return False
        sport = self.sport_dropdown.get()
        competition = self.competition_dropdown.get()
        config = self.competition_catalog.get(sport, {}).get(competition)
        if not config:
            self.write_to_terminal("[-] Choose a valid competition before scanning.")
            return False
        self.scan_in_progress = True
        if self.auto_refresh_enabled:
            self.cancel_auto_refresh_tick()
        self.show_results_message(f"Scanning {competition}...")
        self.scan_button.configure(state="disabled", text="Scanning...")
        threading.Thread(
            target=self.run_market_scan_pipeline,
            args=(competition, config), daemon=True,
        ).start()
        return True

    def finish_scan(self):
        self.scan_in_progress = False
        self.scan_button.configure(state="normal", text="Scan")
        if self.auto_refresh_enabled:
            self.auto_refresh_remaining = self.get_refresh_interval_seconds() or 300
            self.auto_refresh_label.configure(
                text=f"Next scan • {self.format_countdown(self.auto_refresh_remaining)}"
            )
            self.schedule_auto_refresh_tick()
        elif self.auto_refresh_started and not self.auto_refresh_quota_paused:
            self.auto_refresh_label.configure(
                text=f"Paused • {self.format_countdown(self.auto_refresh_remaining)}"
            )

    def run_market_scan_pipeline(self, competition, config):
        try:
            sport_key, region = config["key"], config["region"]
            self.write_to_terminal(f"[*] Target adjusted to: {competition}")
            self.write_to_terminal(f"[*] Contacting odds servers for key: '{sport_key}'...")
            raw_events = self.client.get_upcoming_matches(
                sport=sport_key, region=region, market="h2h"
            )
            if not raw_events:
                self.write_to_terminal("[-] API returned 0 upcoming matches or league is off-season.")
                self.post_to_ui(
                    self.show_results_message,
                    "No upcoming games were returned. This competition may be off-season.",
                )
                return
            self.write_to_terminal(
                f"[+] Ingested {len(raw_events)} active game objects. Evaluating lines..."
            )
            frames = [MarketAnalyzer.flatten_odds_data(event) for event in raw_events]
            frames = [frame for frame in frames if not frame.empty]
            if not frames:
                self.write_to_terminal("[-] Parsing failure: Could not construct structured arrays.")
                self.post_to_ui(
                    self.show_results_message,
                    "Games were returned, but their odds could not be displayed.",
                )
                return
            parsed_df = pd.concat(frames, ignore_index=True)
            parsed_games = parsed_df["event_id"].nunique(dropna=False)
            upcoming_df = MarketAnalyzer.upcoming_only(parsed_df)
            upcoming_games = upcoming_df["event_id"].nunique(dropna=False)
            removed_games = max(0, parsed_games - upcoming_games)
            if removed_games:
                self.write_to_terminal(
                    f"[-] Hidden {removed_games} fixture(s) that already started "
                    "or had no valid kickoff time."
                )
            if upcoming_df.empty:
                self.write_to_terminal(
                    "[-] No not-yet-started fixtures remain after kickoff filtering."
                )
                self.post_to_ui(
                    self.show_results_message,
                    "All returned fixtures have already started. "
                    "Scan again when upcoming games are listed.",
                )
                return
            master_df = MarketAnalyzer.enrich_market_dataframe(upcoming_df)
            self.write_to_terminal(
                f"[+] Operational data matrix compiled ({len(master_df)} rows parsed)."
            )
            self.post_to_ui(self.display_game_results, master_df.copy())
        except Exception as exc:
            self.write_to_terminal(f"[!] Critical structural failure: {exc}")
        finally:
            self.post_to_ui(self.refresh_quota_display)
            self.post_to_ui(self.finish_scan)


if __name__ == "__main__":
    app = GamblerBotGUI()
    app.mainloop()
