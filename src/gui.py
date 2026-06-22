import queue
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import pandas as pd

from src.gui_components import BettingMixin, CompetitionMixin, ResultsMixin
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GamblerBotGUI(CompetitionMixin, ResultsMixin, BettingMixin, ctk.CTk):
    """Application shell coordinating the API, worker threads, and UI components."""

    FAVORITES_FILE = Path(__file__).resolve().parents[1] / ".gamblerbot_favorites.json"
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
        self.geometry("1040x650")
        self.minsize(900, 560)

        self.client = OddsAPIClient()
        self.favorite_competition_keys = self.load_favorites()
        self.selected_bets = {}
        self.odds_buttons = {}
        self.custom_odd_controls = {}
        self.previous_odds_snapshot = {}
        self.odds_movements = {}
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
        self.competition_catalog = {
            sport: {name: config.copy() for name, config in competitions.items()}
            for sport, competitions in self.FALLBACK_COMPETITIONS.items()
        }

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        self.after(50, self.process_ui_queue)
        self.refresh_competition_catalog()

    def create_widgets(self):
        self._build_top_controls()
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.log_frame = ctk.CTkFrame(self.content_frame)
        self.log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.view_tabs = ctk.CTkTabview(self.log_frame)
        self.view_tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.results_tab = self.view_tabs.add("Results")
        self.gamble_tab = self.view_tabs.add("Gamble")
        self.calculator_tab = self.view_tabs.add("Calculator")
        self.console_tab = self.view_tabs.add("Console")

        self.build_results_tab()
        self.build_betting_tabs()
        self._build_console_tab()
        self.view_tabs.set("Results")
        self.build_competition_browser(self.content_frame)
        self.write_to_terminal(
            "System Ready. Select a sport and competition, then click 'Scan Market'...\n"
        )

    def _build_top_controls(self):
        self.top_frame = ctk.CTkFrame(self, corner_radius=10)
        self.top_frame.pack(side="top", fill="x", padx=10, pady=10)
        self.top_frame.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            self.top_frame, text="GamblerBot Dashboard",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(12, 5))
        self.quota_label = ctk.CTkLabel(
            self.top_frame, text="API credits: loading...",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.quota_label.grid(row=0, column=3, columnspan=2, sticky="e", padx=20, pady=(12, 5))
        ctk.CTkLabel(self.top_frame, text="Sport:").grid(
            row=1, column=0, sticky="w", padx=(20, 5), pady=(5, 14)
        )
        self.sport_dropdown = ctk.CTkComboBox(
            self.top_frame, values=sorted(self.competition_catalog),
            command=self.on_sport_changed, width=170, state="readonly",
        )
        self.sport_dropdown.set("Soccer")
        self.sport_dropdown.grid(row=1, column=1, sticky="w", padx=5, pady=(5, 14))
        ctk.CTkLabel(self.top_frame, text="Competition:").grid(
            row=1, column=2, sticky="w", padx=(18, 5), pady=(5, 14)
        )
        self.competition_dropdown = ctk.CTkComboBox(
            self.top_frame, values=[], width=260, state="readonly"
        )
        self.competition_dropdown.grid(row=1, column=3, sticky="w", padx=5, pady=(5, 14))
        self.on_sport_changed("Soccer")
        self.scan_button = ctk.CTkButton(
            self.top_frame, text="Scan Market", command=self.start_async_scan, width=120
        )
        self.scan_button.grid(row=1, column=4, sticky="e", padx=20, pady=(5, 14))
        self.catalog_status = ctk.CTkLabel(
            self.top_frame, text="Loading competitions...",
            text_color=("gray45", "gray65"), font=ctk.CTkFont(size=11),
        )
        self.catalog_status.grid(row=2, column=0, columnspan=5, sticky="w", padx=20, pady=(0, 9))
        self._build_auto_refresh_controls()

    def _build_auto_refresh_controls(self):
        controls = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        controls.grid(row=3, column=0, columnspan=5, sticky="ew", padx=20, pady=(0, 10))
        ctk.CTkLabel(controls, text="Auto-refresh every").pack(side="left")
        self.refresh_interval = ctk.CTkComboBox(
            controls,
            values=["1", "2", "5", "10", "15", "30"],
            width=68,
            command=lambda _value: self.change_auto_refresh_interval(),
        )
        self.refresh_interval.set("5")
        self.refresh_interval.pack(side="left", padx=(7, 4))
        self.refresh_interval.bind("<Return>", lambda _event: self.change_auto_refresh_interval())
        self.refresh_interval.bind("<FocusOut>", lambda _event: self.change_auto_refresh_interval())
        ctk.CTkLabel(controls, text="minutes").pack(side="left", padx=(0, 10))
        self.auto_refresh_button = ctk.CTkButton(
            controls,
            text="Start",
            command=self.toggle_auto_refresh,
            width=76,
            height=28,
        )
        self.auto_refresh_button.pack(side="left")
        self.auto_refresh_label = ctk.CTkLabel(
            controls,
            text="Ready • 05:00",
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.auto_refresh_label.pack(side="left", padx=12)
        ctk.CTkLabel(
            controls,
            text="Automatic scans use API credits",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=10),
        ).pack(side="right")

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
            self.console_tab, font=("Consolas", 12), state="disabled", wrap="word"
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

    def change_auto_refresh_interval(self):
        seconds = self.get_refresh_interval_seconds()
        if seconds is None:
            self.auto_refresh_label.configure(text="Enter 0.01–1440 minutes")
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
        if not self.auto_refresh_started or self.auto_refresh_remaining <= 0:
            self.auto_refresh_remaining = seconds
        self.auto_refresh_started = True
        self.auto_refresh_enabled = True
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
            self.quota_label.configure(text="API credits: unavailable")
            return
        text = f"API credits: {remaining} remaining"
        if used is not None:
            text += f"  |  {used} used"
        if last is not None:
            text += f"  |  last scan cost {last}"
        self.quota_label.configure(text=text)

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
        self.scan_button.configure(state="normal", text="Scan Market")
        if self.auto_refresh_enabled:
            self.auto_refresh_remaining = self.get_refresh_interval_seconds() or 300
            self.auto_refresh_label.configure(
                text=f"Next scan • {self.format_countdown(self.auto_refresh_remaining)}"
            )
            self.schedule_auto_refresh_tick()
        elif self.auto_refresh_started:
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
            master_df = pd.concat(frames, ignore_index=True)
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
