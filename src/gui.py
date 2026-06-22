import threading
import tkinter as tk
import customtkinter as ctk
import pandas as pd
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GamblerBotGUI(ctk.CTk):
    # Used immediately at startup and whenever the catalog endpoint is unavailable.
    # The live API catalog is merged into this data after the window opens.
    FALLBACK_COMPETITIONS = {
        "Baseball": {
            "MLB": {"key": "baseball_mlb", "region": "us"},
        },
        "Basketball": {
            "NBA": {"key": "basketball_nba", "region": "us"},
        },
        "American Football": {
            "NFL": {"key": "americanfootball_nfl", "region": "us"},
        },
        "Soccer": {
            "English Premier League": {"key": "soccer_epl", "region": "eu"},
            "UEFA Champions League": {"key": "soccer_uefa_champs_league", "region": "eu"},
            "FIFA World Cup": {"key": "soccer_fifa_world_cup", "region": "eu"},
        },
    }

    def __init__(self):
        super().__init__()

        self.title("GamblerBot - Live Market Scanner")
        self.geometry("1040x650")
        self.minsize(900, 560)

        self.client = OddsAPIClient()

        self.competition_catalog = {
            sport: {name: config.copy() for name, config in competitions.items()}
            for sport, competitions in self.FALLBACK_COMPETITIONS.items()
        }

        self.create_widgets()
        self.refresh_competition_catalog()

    def create_widgets(self):
        # --- Top Control Bar ---
        self.top_frame = ctk.CTkFrame(self, corner_radius=10)
        self.top_frame.pack(side="top", fill="x", padx=10, pady=10)
        self.top_frame.grid_columnconfigure(3, weight=1)

        self.title_label = ctk.CTkLabel(
            self.top_frame, 
            text="GamblerBot Dashboard", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(12, 5))

        self.quota_label = ctk.CTkLabel(
            self.top_frame,
            text="API credits: loading...",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.quota_label.grid(
            row=0, column=3, columnspan=2, sticky="e", padx=20, pady=(12, 5)
        )

        # --- Sport Selector Dropdown ---
        self.sport_label = ctk.CTkLabel(self.top_frame, text="Sport:", font=ctk.CTkFont(size=12))
        self.sport_label.grid(row=1, column=0, sticky="w", padx=(20, 5), pady=(5, 14))

        self.sport_dropdown = ctk.CTkComboBox(
            self.top_frame,
            values=sorted(self.competition_catalog),
            command=self.on_sport_changed,
            width=170,
            state="readonly",
        )
        self.sport_dropdown.set("Soccer")
        self.sport_dropdown.grid(row=1, column=1, sticky="w", padx=5, pady=(5, 14))

        self.competition_label = ctk.CTkLabel(
            self.top_frame, text="Competition:", font=ctk.CTkFont(size=12)
        )
        self.competition_label.grid(row=1, column=2, sticky="w", padx=(18, 5), pady=(5, 14))

        self.competition_dropdown = ctk.CTkComboBox(
            self.top_frame,
            values=[],
            width=260,
            state="readonly",
        )
        self.competition_dropdown.grid(row=1, column=3, sticky="w", padx=5, pady=(5, 14))
        self.on_sport_changed("Soccer")

        # --- Action Button ---
        self.scan_button = ctk.CTkButton(
            self.top_frame, 
            text="Scan Market", 
            command=self.start_async_scan, 
            width=120
        )
        self.scan_button.grid(row=1, column=4, sticky="e", padx=20, pady=(5, 14))

        self.catalog_status = ctk.CTkLabel(
            self.top_frame,
            text="Loading competitions...",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
        )
        self.catalog_status.grid(row=2, column=0, columnspan=5, sticky="w", padx=20, pady=(0, 9))

        # --- Main Content Area ---
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # --- Console Feed Text Pane ---
        self.log_frame = ctk.CTkFrame(self.content_frame)
        self.log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.log_header.pack(fill="x", padx=15, pady=(10, 5))

        self.log_label = ctk.CTkLabel(
            self.log_header,
            text="Console Feed", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.log_label.pack(side="left")

        self.clear_button = ctk.CTkButton(
            self.log_header,
            text="Clear",
            command=self.clear_terminal,
            width=74,
            height=28,
            fg_color=("gray70", "gray28"),
            hover_color=("gray60", "gray35"),
        )
        self.clear_button.pack(side="right")

        self.terminal_box = ctk.CTkTextbox(
            self.log_frame, 
            font=("Consolas", 12), 
            state="disabled", 
            wrap="word"
        )
        self.terminal_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # --- Searchable Competition Browser ---
        self.browser_frame = ctk.CTkFrame(self.content_frame, width=300)
        self.browser_frame.grid(row=0, column=1, sticky="ns")
        self.browser_frame.grid_propagate(False)
        self.browser_frame.grid_rowconfigure(3, weight=1)
        self.browser_frame.grid_columnconfigure(0, weight=1)

        self.browser_title = ctk.CTkLabel(
            self.browser_frame,
            text="Browse competitions",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.browser_title.grid(row=0, column=0, sticky="w", padx=15, pady=(14, 8))

        self.competition_search = ctk.CTkEntry(
            self.browser_frame,
            placeholder_text="Search competitions...",
        )
        self.competition_search.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 6))
        self.competition_search.bind("<KeyRelease>", self.filter_competitions)

        self.search_result_count = ctk.CTkLabel(
            self.browser_frame,
            text="",
            anchor="w",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
        )
        self.search_result_count.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 5))

        # CTkScrollableFrame supplies the vertical bar on its right edge.
        self.competition_results = ctk.CTkScrollableFrame(
            self.browser_frame,
            label_text="",
            fg_color=("gray88", "gray17"),
        )
        self.competition_results.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.competition_results.grid_columnconfigure(0, weight=1)
        self.populate_competition_browser()
        
        self.write_to_terminal("System Ready. Select a sport and competition, then click 'Scan Market'...\n")

    @staticmethod
    def region_for_group(group):
        """Choose the bookmaker region most likely to cover a sport group."""
        group_lower = group.lower()
        if any(name in group_lower for name in ("aussie", "rugby league")):
            return "au"
        if any(name in group_lower for name in ("soccer", "rugby", "cricket")):
            return "eu"
        return "us"

    def on_sport_changed(self, selected_sport):
        competitions = sorted(self.competition_catalog.get(selected_sport, {}))
        self.competition_dropdown.configure(values=competitions)
        self.competition_dropdown.set(competitions[0] if competitions else "No competitions available")
        if hasattr(self, "competition_search"):
            self.competition_search.delete(0, tk.END)
            self.populate_competition_browser()

    def filter_competitions(self, _event=None):
        self.populate_competition_browser(self.competition_search.get())

    def populate_competition_browser(self, query=""):
        """Render filtered competition buttons inside the scrollable sidebar."""
        for widget in self.competition_results.winfo_children():
            widget.destroy()

        selected_sport = self.sport_dropdown.get()
        competitions = sorted(self.competition_catalog.get(selected_sport, {}))
        search_term = query.strip().casefold()
        matches = [name for name in competitions if search_term in name.casefold()]

        self.search_result_count.configure(
            text=f"{len(matches)} competition{'s' if len(matches) != 1 else ''}"
        )

        if not matches:
            empty_label = ctk.CTkLabel(
                self.competition_results,
                text="No competitions found",
                text_color=("gray45", "gray65"),
            )
            empty_label.grid(row=0, column=0, sticky="ew", padx=8, pady=16)
            return

        for row, competition in enumerate(matches):
            button = ctk.CTkButton(
                self.competition_results,
                text=competition,
                anchor="w",
                fg_color="transparent",
                border_width=1,
                border_color=("gray70", "gray30"),
                text_color=("gray10", "gray90"),
                hover_color=("gray78", "gray25"),
                command=lambda name=competition: self.select_competition(name),
            )
            button.grid(row=row, column=0, sticky="ew", padx=3, pady=3)

    def select_competition(self, competition):
        self.competition_dropdown.set(competition)
        self.catalog_status.configure(text=f"Selected: {competition}")

    def refresh_competition_catalog(self):
        """Load every competition exposed by the odds provider without freezing the UI."""
        threading.Thread(target=self._load_competition_catalog, daemon=True).start()

    def _load_competition_catalog(self):
        sports = self.client.get_available_sports(include_inactive=True)
        self.after(0, self.refresh_quota_display)
        if not sports:
            self.after(0, self._show_fallback_catalog_status)
            return

        # Merge the server response into the fallback so marquee competitions
        # such as the World Cup remain selectable while they are off-season.
        catalog = {
            sport: {name: config.copy() for name, config in competitions.items()}
            for sport, competitions in self.FALLBACK_COMPETITIONS.items()
        }
        for item in sports:
            key = item.get("key")
            title = item.get("title")
            group = item.get("group") or "Other"
            if not key or not title or item.get("has_outrights"):
                continue
            catalog.setdefault(group, {})[title] = {
                "key": key,
                "region": self.region_for_group(group),
                "active": item.get("active", False),
                "description": item.get("description", ""),
            }

        if catalog:
            self.after(0, lambda: self._apply_competition_catalog(catalog))
        else:
            self.after(0, self._show_fallback_catalog_status)

    def _apply_competition_catalog(self, catalog):
        self.competition_catalog = catalog
        sports = sorted(catalog)
        self.sport_dropdown.configure(values=sports)
        selected_sport = "Soccer" if "Soccer" in catalog else sports[0]
        self.sport_dropdown.set(selected_sport)
        self.on_sport_changed(selected_sport)
        competition_count = sum(len(items) for items in catalog.values())
        self.catalog_status.configure(
            text=f"{competition_count} competitions loaded across {len(sports)} sports"
        )

    def _show_fallback_catalog_status(self):
        self.catalog_status.configure(text="Using built-in competitions (online catalog unavailable)")

    def refresh_quota_display(self):
        """Show API request-credit usage from the most recent server response."""
        usage = self.client.usage
        remaining = usage.get("remaining")
        used = usage.get("used")
        last = usage.get("last")
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
        """Thread-safe injection of text to terminal box interface."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, lambda: self.write_to_terminal(text))
            return
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert(tk.END, text + "\n")
        self.terminal_box.see(tk.END)
        self.terminal_box.configure(state="disabled")

    def clear_terminal(self):
        """Remove all messages from the console feed."""
        self.terminal_box.configure(state="normal")
        self.terminal_box.delete("1.0", tk.END)
        self.terminal_box.configure(state="disabled")

    def start_async_scan(self):
        """Fires the scanning function in a background thread to keep UI alive."""
        selected_sport = self.sport_dropdown.get()
        selected_competition = self.competition_dropdown.get()
        sport_config = self.competition_catalog.get(selected_sport, {}).get(selected_competition)
        if not sport_config:
            self.write_to_terminal("[-] Choose a valid competition before scanning.")
            return
        self.scan_button.configure(state="disabled", text="Scanning...")
        threading.Thread(
            target=self.run_market_scan_pipeline,
            args=(selected_competition, sport_config),
            daemon=True,
        ).start()

    def run_market_scan_pipeline(self, selected_competition, sport_config):
        try:
            api_sport_key = sport_config["key"]
            api_region = sport_config["region"]

            self.write_to_terminal(f"[*] Target adjusted to: {selected_competition}")
            self.write_to_terminal(f"[*] Contacting odds servers for key: '{api_sport_key}'...")
            
            raw_events = self.client.get_upcoming_matches(
                sport=api_sport_key, 
                region=api_region, 
                market="h2h"
            )
            
            if not raw_events:
                self.write_to_terminal("[-] API returned 0 upcoming matches or league is off-season.")
                return

            self.write_to_terminal(f"[+] Ingested {len(raw_events)} active game objects. Evaluating lines...")
            
            all_market_dfs = []
            for event in raw_events:
                event_df = MarketAnalyzer.flatten_odds_data(event)
                if not event_df.empty:
                    all_market_dfs.append(event_df)

            if all_market_dfs:
                master_df = pd.concat(all_market_dfs, ignore_index=True)
                self.write_to_terminal(f"[+] Operational data matrix compiled ({len(master_df)} rows parsed).")
                self.evaluate_gui_discrepancies(master_df)
            else:
                self.write_to_terminal("[-] Parsing failure: Could not construct structured arrays.")

        except Exception as e:
            self.write_to_terminal(f"[!] Critical structural failure: {str(e)}")
        finally:
            self.after(0, self.refresh_quota_display)
            self.after(0, lambda: self.scan_button.configure(state="normal", text="Scan Market"))

    def evaluate_gui_discrepancies(self, df):
        """Processes flattened datasets inside class scope, utilizing Implied Probability Edges."""
        self.write_to_terminal("\n=== SCAN RESULTS ===")
        self.write_to_terminal(
            "How to read these results:\n"
            "  Typical market odds = the middle price across all bookmakers.\n"
            "  Price advantage = how much better this offer looks than that typical price.\n"
            "  This is a market comparison, not a guarantee that the bet will win.\n"
        )
        found_any = False
        
        # Define the minimum theoretical edge we care about (e.g., 2% absolute probability edge)
        MIN_PROBABILITY_EDGE = 0.02 
        
        for (home, away), game_df in df.groupby(['home_team', 'away_team']):
            median_home = game_df['home_odds'].median()
            median_away = game_df['away_odds'].median()
            
            # Convert market consensus medians to baseline probabilities
            prob_market_home = 1 / median_home
            prob_market_away = 1 / median_away
            
            has_draws = 'draw_odds' in game_df.columns and not game_df['draw_odds'].isna().all()
            median_draw = game_df['draw_odds'].median() if has_draws else None
            prob_market_draw = (1 / median_draw) if has_draws else None
            
            for _, row in game_df.iterrows():
                # 1. Evaluate Home Team Probability Edge
                prob_bookie_home = 1 / row['home_odds']
                edge_home = prob_market_home - prob_bookie_home
                if edge_home >= MIN_PROBABILITY_EDGE:
                    self.write_value_result(
                        home, away, row['home_team'], row['bookmaker'],
                        row['home_odds'], median_home, edge_home,
                    )
                    found_any = True
                    
                # 2. Evaluate Away Team Probability Edge
                prob_bookie_away = 1 / row['away_odds']
                edge_away = prob_market_away - prob_bookie_away
                if edge_away >= MIN_PROBABILITY_EDGE:
                    self.write_value_result(
                        home, away, row['away_team'], row['bookmaker'],
                        row['away_odds'], median_away, edge_away,
                    )
                    found_any = True
                    
                # 3. Evaluate Draw Probability Edge
                if has_draws and pd.notna(row['draw_odds']) and row['draw_odds'] > 0:
                    prob_bookie_draw = 1 / row['draw_odds']
                    edge_draw = prob_market_draw - prob_bookie_draw
                    if edge_draw >= MIN_PROBABILITY_EDGE:
                        self.write_value_result(
                            home, away, "Draw", row['bookmaker'],
                            row['draw_odds'], median_draw, edge_draw,
                        )
                        found_any = True
                        
        if not found_any:
            self.write_to_terminal(
                "[+] No offers were at least 2 percentage points better than the typical market price."
            )

    def write_value_result(self, home, away, selection, bookmaker, offered_odds,
                           typical_odds, advantage):
        """Write one value result using beginner-friendly labels."""
        self.write_to_terminal(
            "----------------------------------------\n"
            "VALUE OPPORTUNITY FOUND\n"
            f"Match: {home} vs {away}\n"
            f"Your selection: {selection}\n"
            f"Bookmaker: {bookmaker}\n"
            f"Odds offered: {offered_odds:.2f}\n"
            f"Typical market odds: {typical_odds:.2f}\n"
            f"Price advantage: +{advantage * 100:.1f} percentage points\n"
            "Why it was flagged: this bookmaker is offering a better price than most of the market.\n"
        )

if __name__ == "__main__":
    app = GamblerBotGUI()
    app.mainloop()
