import json
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import customtkinter as ctk
import pandas as pd
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GamblerBotGUI(ctk.CTk):
    FAVORITES_FILE = Path(__file__).resolve().parents[1] / ".gamblerbot_favorites.json"

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
        self.favorite_competition_keys = self.load_favorites()

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

        self.view_tabs = ctk.CTkTabview(self.log_frame)
        self.view_tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.results_tab = self.view_tabs.add("Results")
        self.console_tab = self.view_tabs.add("Console")
        self.view_tabs.set("Results")

        self.results_tab.grid_rowconfigure(1, weight=1)
        self.results_tab.grid_columnconfigure(0, weight=1)
        self.results_title = ctk.CTkLabel(
            self.results_tab,
            text="Game odds overview",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.results_title.grid(row=0, column=0, sticky="w", padx=8, pady=(6, 8))

        self.game_results = ctk.CTkScrollableFrame(
            self.results_tab,
            fg_color=("gray90", "gray14"),
        )
        self.game_results.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.game_results.grid_columnconfigure(0, weight=1)
        self.show_results_message("Scan a competition to see its games here.")

        self.log_header = ctk.CTkFrame(self.console_tab, fg_color="transparent")
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
            self.console_tab,
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
        competitions = self.sorted_competitions(selected_sport)
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
        competitions = self.sorted_competitions(selected_sport)
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
            competition_row = ctk.CTkFrame(self.competition_results, fg_color="transparent")
            competition_row.grid(row=row, column=0, sticky="ew", padx=3, pady=3)
            competition_row.grid_columnconfigure(1, weight=1)

            competition_key = self.competition_catalog[selected_sport][competition]["key"]
            is_favorite = competition_key in self.favorite_competition_keys
            star_button = ctk.CTkButton(
                competition_row,
                text="★" if is_favorite else "☆",
                width=34,
                fg_color="transparent",
                hover_color=("gray78", "gray25"),
                text_color="#f2b632" if is_favorite else ("gray35", "gray70"),
                font=ctk.CTkFont(size=18),
                command=lambda name=competition: self.toggle_favorite(name),
            )
            star_button.grid(row=0, column=0, padx=(0, 3))

            button = ctk.CTkButton(
                competition_row,
                text=competition,
                anchor="w",
                fg_color="transparent",
                border_width=1,
                border_color=("gray70", "gray30"),
                text_color=("gray10", "gray90"),
                hover_color=("gray78", "gray25"),
                command=lambda name=competition: self.select_competition(name),
            )
            button.grid(row=0, column=1, sticky="ew")

    def select_competition(self, competition):
        self.competition_dropdown.set(competition)
        self.catalog_status.configure(text=f"Selected: {competition}")

    def sorted_competitions(self, sport):
        """Return favorites first, followed by all other competitions alphabetically."""
        competitions = self.competition_catalog.get(sport, {})
        return sorted(
            competitions,
            key=lambda name: (
                competitions[name].get("key") not in self.favorite_competition_keys,
                name.casefold(),
            ),
        )

    def toggle_favorite(self, competition):
        sport = self.sport_dropdown.get()
        config = self.competition_catalog.get(sport, {}).get(competition)
        if not config:
            return

        competition_key = config["key"]
        if competition_key in self.favorite_competition_keys:
            self.favorite_competition_keys.remove(competition_key)
            action = "Removed from favorites"
        else:
            self.favorite_competition_keys.add(competition_key)
            action = "Added to favorites"

        self.save_favorites()
        current_selection = self.competition_dropdown.get()
        ordered = self.sorted_competitions(sport)
        self.competition_dropdown.configure(values=ordered)
        if current_selection in ordered:
            self.competition_dropdown.set(current_selection)
        self.populate_competition_browser(self.competition_search.get())
        self.catalog_status.configure(text=f"{action}: {competition}")

    def load_favorites(self):
        """Load favorite API competition keys from the local settings file."""
        try:
            data = json.loads(self.FAVORITES_FILE.read_text(encoding="utf-8"))
            keys = data.get("competition_keys", []) if isinstance(data, dict) else data
            return {str(key) for key in keys}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return set()

    def save_favorites(self):
        """Persist favorites so they survive application restarts."""
        payload = {"competition_keys": sorted(self.favorite_competition_keys)}
        try:
            self.FAVORITES_FILE.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            self.write_to_terminal(f"[!] Could not save favorites: {exc}")

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
        self.show_results_message(f"Scanning {selected_competition}...")
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
                self.after(0, lambda: self.show_results_message(
                    "No upcoming games were returned. This competition may be off-season."
                ))
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
                self.after(0, lambda data=master_df.copy(): self.display_game_results(data))
            else:
                self.write_to_terminal("[-] Parsing failure: Could not construct structured arrays.")
                self.after(0, lambda: self.show_results_message(
                    "Games were returned, but their odds could not be displayed."
                ))

        except Exception as e:
            self.write_to_terminal(f"[!] Critical structural failure: {str(e)}")
        finally:
            self.after(0, self.refresh_quota_display)
            self.after(0, lambda: self.scan_button.configure(state="normal", text="Scan Market"))

    def show_results_message(self, message):
        """Clear the result list and show a single status message."""
        for widget in self.game_results.winfo_children():
            widget.destroy()
        label = ctk.CTkLabel(
            self.game_results,
            text=message,
            text_color=("gray40", "gray65"),
            wraplength=500,
        )
        label.grid(row=0, column=0, sticky="ew", padx=20, pady=30)

    def display_game_results(self, df):
        """Display one collapsed summary card per game."""
        for widget in self.game_results.winfo_children():
            widget.destroy()

        self.view_tabs.set("Results")
        grouped = df.groupby(
            ['event_id', 'home_team', 'away_team'],
            dropna=False,
            sort=False,
        )
        for row, ((_, home, away), game_df) in enumerate(grouped):
            self.create_game_card(row, home, away, game_df)

        self.results_title.configure(text=f"Game odds overview  •  {grouped.ngroups} games")

    def create_game_card(self, row, home, away, game_df):
        """Create a best/worst summary that expands into all bookmaker odds."""
        card = ctk.CTkFrame(self.game_results, corner_radius=9)
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=5)
        card.grid_columnconfigure(0, weight=1)

        details = ctk.CTkFrame(card, fg_color=("gray87", "gray18"))
        state = {"expanded": False}

        def toggle_details():
            state["expanded"] = not state["expanded"]
            if state["expanded"]:
                details.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
                arrow_button.configure(text=f"▼  {home} vs {away}")
            else:
                details.grid_remove()
                arrow_button.configure(text=f"▶  {home} vs {away}")

        arrow_button = ctk.CTkButton(
            card,
            text=f"▶  {home} vs {away}",
            command=toggle_details,
            anchor="w",
            fg_color="transparent",
            hover_color=("gray78", "gray25"),
            text_color=("gray10", "gray95"),
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        arrow_button.grid(row=0, column=0, sticky="ew", padx=8, pady=(7, 3))

        first_row = game_df.iloc[0]
        kickoff = self.format_jerusalem_time(first_row.get('commence_time'))
        country = self.metadata_value(first_row.get('country'))
        stadium = self.metadata_value(first_row.get('stadium'))
        metadata = ctk.CTkLabel(
            card,
            text=(
                f"Jerusalem time: {kickoff}\n"
                f"Country: {country}   •   Stadium: {stadium}"
            ),
            anchor="w",
            justify="left",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11),
        )
        metadata.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 5))

        summary = ctk.CTkFrame(card, fg_color="transparent")
        summary.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 9))
        summary.grid_columnconfigure(1, weight=1)
        summary.grid_columnconfigure(2, weight=1)

        selections = [(home, 'home_odds')]
        if 'draw_odds' in game_df and game_df['draw_odds'].notna().any():
            selections.append(("Draw", 'draw_odds'))
        selections.append((away, 'away_odds'))

        for selection_row, (selection, column) in enumerate(selections):
            valid = game_df.dropna(subset=[column])
            if valid.empty:
                continue
            highest = valid.loc[valid[column].idxmax()]
            lowest = valid.loc[valid[column].idxmin()]
            ctk.CTkLabel(
                summary, text=selection, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=selection_row, column=0, sticky="w", padx=(0, 12), pady=2)
            ctk.CTkLabel(
                summary,
                text=f"Highest: {highest[column]:.2f}  ({highest['bookmaker']})",
                anchor="w",
                text_color=("#147a3d", "#62d48b"),
            ).grid(row=selection_row, column=1, sticky="w", padx=6, pady=2)
            ctk.CTkLabel(
                summary,
                text=f"Lowest: {lowest[column]:.2f}  ({lowest['bookmaker']})",
                anchor="w",
                text_color=("#a13a3a", "#ef8585"),
            ).grid(row=selection_row, column=2, sticky="w", padx=6, pady=2)

        self.populate_bookmaker_details(details, home, away, game_df)

    @staticmethod
    def metadata_value(value):
        """Return a readable venue value without exposing pandas NaN values."""
        if value is None:
            return "Not provided by odds API"
        text = str(value).strip()
        if not text or text.casefold() in {"none", "nan", "nat", "<na>"}:
            return "Not provided by odds API"
        return text

    @staticmethod
    def format_jerusalem_time(value):
        """Convert an ISO-8601 API kickoff timestamp to Jerusalem local time."""
        if pd.isna(value) or not str(value).strip():
            return "Time not provided"
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            jerusalem = parsed.astimezone(ZoneInfo("Asia/Jerusalem"))
            return jerusalem.strftime("%a, %d %b %Y at %H:%M")
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            return "Invalid kickoff time"

    def populate_bookmaker_details(self, details, home, away, game_df):
        """Build the full odds table hidden beneath an expandable game card."""
        has_draw = 'draw_odds' in game_df and game_df['draw_odds'].notna().any()
        columns = [("Bookmaker", None), (home, 'home_odds')]
        if has_draw:
            columns.append(("Draw", 'draw_odds'))
        columns.append((away, 'away_odds'))

        for column_index, (heading, _) in enumerate(columns):
            details.grid_columnconfigure(column_index, weight=1)
            ctk.CTkLabel(
                details,
                text=heading,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=0, column=column_index, sticky="ew", padx=7, pady=(7, 4))

        bookmaker_rows = game_df.drop_duplicates(subset=['bookmaker']).sort_values('bookmaker')
        for table_row, (_, odds_row) in enumerate(bookmaker_rows.iterrows(), start=1):
            for column_index, (_, odds_column) in enumerate(columns):
                if odds_column is None:
                    value = str(odds_row['bookmaker'])
                else:
                    odds = odds_row[odds_column]
                    value = f"{odds:.2f}" if pd.notna(odds) else "—"
                ctk.CTkLabel(details, text=value).grid(
                    row=table_row, column=column_index, sticky="ew", padx=7, pady=3
                )

if __name__ == "__main__":
    app = GamblerBotGUI()
    app.mainloop()
