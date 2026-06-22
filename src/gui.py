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
        self.title_label.grid(row=0, column=0, columnspan=5, sticky="w", padx=20, pady=(12, 5))

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

        # --- Console Feed Text Pane ---
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_label = ctk.CTkLabel(
            self.log_frame, 
            text="Console Feed", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.log_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.terminal_box = ctk.CTkTextbox(
            self.log_frame, 
            font=("Consolas", 12), 
            state="disabled", 
            wrap="word"
        )
        self.terminal_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
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

    def refresh_competition_catalog(self):
        """Load every competition exposed by the odds provider without freezing the UI."""
        threading.Thread(target=self._load_competition_catalog, daemon=True).start()

    def _load_competition_catalog(self):
        sports = self.client.get_available_sports(include_inactive=True)
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

    def write_to_terminal(self, text):
        """Thread-safe injection of text to terminal box interface."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, lambda: self.write_to_terminal(text))
            return
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert(tk.END, text + "\n")
        self.terminal_box.see(tk.END)
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
            self.after(0, lambda: self.scan_button.configure(state="normal", text="Scan Market"))

    def evaluate_gui_discrepancies(self, df):
        """Processes flattened datasets inside class scope, utilizing Implied Probability Edges."""
        self.write_to_terminal("\n=== SCAN RESULTS ===")
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
                    self.write_to_terminal(f"[!] VALUE ALERT | {row['home_team']} vs {row['away_team']}\n"
                                           f"    Bookie: {row['bookmaker']} @ {row['home_odds']} (Consensus Median: {median_home:.2f}) -> Edge: {edge_home*100:.1f}%\n")
                    found_any = True
                    
                # 2. Evaluate Away Team Probability Edge
                prob_bookie_away = 1 / row['away_odds']
                edge_away = prob_market_away - prob_bookie_away
                if edge_away >= MIN_PROBABILITY_EDGE:
                    self.write_to_terminal(f"[!] VALUE ALERT | {row['away_team']} @ {row['home_team']}\n"
                                           f"    Bookie: {row['bookmaker']} @ {row['away_odds']} (Consensus Median: {median_away:.2f}) -> Edge: {edge_away*100:.1f}%\n")
                    found_any = True
                    
                # 3. Evaluate Draw Probability Edge
                if has_draws and row['draw_odds']:
                    prob_bookie_draw = 1 / row['draw_odds']
                    edge_draw = prob_market_draw - prob_bookie_draw
                    if edge_draw >= MIN_PROBABILITY_EDGE:
                        self.write_to_terminal(f"[!] VALUE ALERT | DRAW - {row['home_team']} vs {row['away_team']}\n"
                                               f"    Bookie: {row['bookmaker']} @ {row['draw_odds']} (Consensus Median: {median_draw:.2f}) -> Edge: {edge_draw*100:.1f}%\n")
                        found_any = True
                        
        if not found_any:
            self.write_to_terminal("[+] Complete efficiency observed. No math-backed outliers found.")

if __name__ == "__main__":
    app = GamblerBotGUI()
    app.mainloop()
