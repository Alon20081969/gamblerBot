import threading
import tkinter as tk
import customtkinter as ctk
import pandas as pd
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GamblerBotGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GamblerBot - Live Market Scanner")
        self.geometry("800x550")
        self.resizable(False, False)

        self.client = OddsAPIClient()

        # Friendly display names mapped directly to API keys and regions
        self.SPORT_MARKETS = {
            "MLB Baseball": {"key": "baseball_mlb", "region": "us"},
            "NBA Basketball": {"key": "basketball_nba", "region": "us"},
            "NFL Football": {"key": "football_nfl", "region": "us"},
            "UEFA Champions League": {"key": "soccer_uefa_champions_league", "region": "eu"},
            "English Premier League": {"key": "soccer_epl", "region": "eu"}
        }

        self.create_widgets()

    def create_widgets(self):
        # --- Top Control Bar ---
        self.top_frame = ctk.CTkFrame(self, height=70, corner_radius=0)
        self.top_frame.pack(side="top", fill="x", padx=10, pady=10)

        self.title_label = ctk.CTkLabel(
            self.top_frame, 
            text="GamblerBot Dashboard", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.pack(side="left", padx=20)

        # --- Sport Selector Dropdown ---
        self.sport_label = ctk.CTkLabel(self.top_frame, text="Sport:", font=ctk.CTkFont(size=12))
        self.sport_label.pack(side="left", padx=(20, 5))

        self.sport_dropdown = ctk.CTkComboBox(
            self.top_frame,
            values=list(self.SPORT_MARKETS.keys()),
            width=180
        )
        self.sport_dropdown.set("MLB Baseball")
        self.sport_dropdown.pack(side="left", padx=5)

        # --- Action Button ---
        self.scan_button = ctk.CTkButton(
            self.top_frame, 
            text="Scan Market", 
            command=self.start_async_scan, 
            width=120
        )
        self.scan_button.pack(side="right", padx=20)

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
        
        self.write_to_terminal("System Ready. Select a sport and click 'Scan Market'...\n")

    def write_to_terminal(self, text):
        """Thread-safe injection of text to terminal box interface."""
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert(tk.END, text + "\n")
        self.terminal_box.see(tk.END)
        self.terminal_box.configure(state="disabled")

    def start_async_scan(self):
        """Fires the scanning function in a background thread to keep UI alive."""
        self.scan_button.configure(state="disabled", text="Scanning...")
        threading.Thread(target=self.run_market_scan_pipeline, daemon=True).start()

    def run_market_scan_pipeline(self):
        try:
            selected_display_name = self.sport_dropdown.get()
            sport_config = self.SPORT_MARKETS[selected_display_name]
            
            api_sport_key = sport_config["key"]
            api_region = sport_config["region"]

            self.write_to_terminal(f"[*] Target adjusted to: {selected_display_name}")
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
            self.scan_button.configure(state="normal", text="Scan Market")

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
