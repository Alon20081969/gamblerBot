import threading
import tkinter

import customtkinter as ctk
import pandas as pd

from src.ingestion.winner_fetcher import WinnerOddsFetcher, match_winner_game
from src.models.probabilities import MarketAnalyzer


class AdvisorMixin:
    """Explain lower-risk market candidates and evaluate manual Winner prices."""

    def build_advisor_tab(self):
        self.advisor_tab.grid_rowconfigure(3, weight=1)
        self.advisor_tab.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.advisor_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Winner bet advisor",
            anchor="w",
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            header,
            text="Open Guide",
            command=lambda: self.show_page("Guide"),
            width=100,
            height=32,
            fg_color=self.COLORS["panel_alt"],
            hover_color=self.COLORS["border_light"],
        ).grid(row=0, column=1, padx=(8, 0))
        self.advisor_date_search = ctk.CTkEntry(
            header,
            placeholder_text="Search team or date...",
            width=190,
            height=32,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
        )
        self.advisor_date_search.grid(row=0, column=2, padx=(8, 0))
        self.advisor_date_search.bind(
            "<KeyRelease>", lambda _event: self.apply_advisor_filters()
        )
        self.advisor_date_sort = ctk.CTkComboBox(
            header,
            values=["Closest match first", "Furthest match first"],
            state="readonly",
            width=165,
            height=32,
            command=lambda _value: self.apply_advisor_filters(),
        )
        self.advisor_date_sort.set("Closest match first")
        self.advisor_date_sort.grid(row=0, column=3, padx=(8, 0))

        self.advisor_status = ctk.CTkLabel(
            self.advisor_tab,
            text=(
                "Scan a competition first. The advisor ranks the market's most likely "
                "outcome in each game. Enter the matching Winner odd to evaluate its price."
            ),
            anchor="w",
            justify="left",
            wraplength=1120,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        )
        self.advisor_status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        filters = ctk.CTkFrame(
            self.advisor_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        filters.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.advisor_matched_only = ctk.BooleanVar(value=True)
        self.advisor_favorable_only = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            filters,
            text="Matched Winner games only",
            variable=self.advisor_matched_only,
            command=self.apply_advisor_filters,
        ).pack(side="left", padx=(12, 10), pady=9)
        ctk.CTkSwitch(
            filters,
            text="Favorable Winner price only",
            variable=self.advisor_favorable_only,
            command=self.apply_advisor_filters,
        ).pack(side="left", padx=10, pady=9)
        self.advisor_confidence_filter = ctk.CTkComboBox(
            filters,
            values=["All confidence", "High only", "Medium + High"],
            state="readonly",
            width=145,
            command=lambda _value: self.apply_advisor_filters(),
        )
        self.advisor_confidence_filter.set("All confidence")
        self.advisor_confidence_filter.pack(side="left", padx=10, pady=9)
        self.advisor_risk_filter = ctk.CTkComboBox(
            filters,
            values=["All risk", "Lower only", "Lower + Moderate"],
            state="readonly",
            width=145,
            command=lambda _value: self.apply_advisor_filters(),
        )
        self.advisor_risk_filter.set("All risk")
        self.advisor_risk_filter.pack(side="left", padx=10, pady=9)
        self.advisor_filter_status = ctk.CTkLabel(
            filters,
            text="Waiting for scan",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.advisor_filter_status.pack(side="right", padx=12, pady=9)

        self.advisor_results = ctk.CTkScrollableFrame(
            self.advisor_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.advisor_results.grid(row=3, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.advisor_results.grid_columnconfigure(0, weight=1)
        self.advisor_controls = []
        self.winner_sync_generation = 0
        self.show_advisor_message("Scan a competition to generate suggestions.")

    def show_advisor_message(self, message):
        for widget in self.advisor_results.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.advisor_results,
            text=message,
            text_color=self.COLORS["muted"],
            wraplength=650,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=30)

    def render_advisor(self, df):
        if not hasattr(self, "advisor_results"):
            return
        self.winner_sync_generation += 1
        for widget in self.advisor_results.winfo_children():
            widget.destroy()

        candidates = MarketAnalyzer.advisor_candidates(df)
        if candidates.empty:
            self.advisor_controls = []
            self.show_advisor_message(
                "There is not enough complete bookmaker data for suggestions."
            )
            return

        self.advisor_status.configure(
            text=(
                f"{len(candidates)} games ranked by consensus chance. "
                "Lower risk does not mean safe. A recommendation is only made after "
                "you enter Winner's exact decimal odd."
            )
        )
        self.advisor_controls = []
        for position, (_, candidate) in enumerate(candidates.iterrows(), start=1):
            self.create_advisor_card(position, candidate)
        self.apply_advisor_filters()
        self.start_winner_auto_sync()

    def create_advisor_card(self, position, candidate):
        chance = float(candidate["consensus_probability_pct"])
        risk = str(candidate["risk_level"])
        confidence = str(candidate["consensus_confidence"])
        risk_color = {
            "Lower": self.COLORS["success"],
            "Moderate": self.COLORS["warning"],
            "High": self.COLORS["danger"],
        }.get(risk, self.COLORS["muted"])

        card = ctk.CTkFrame(
            self.advisor_results,
            fg_color=self.COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        card.grid(row=position - 1, column=0, sticky="ew", padx=8, pady=7)
        card.grid_columnconfigure(1, weight=1)

        rank_label = ctk.CTkLabel(
            card,
            text=f"#{position}",
            width=48,
            text_color=risk_color,
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        rank_label.grid(row=0, column=0, rowspan=3, padx=(12, 4), pady=12)

        ctk.CTkLabel(
            card,
            text=f"{candidate['match']}  •  Suggested outcome: {candidate['selection']}",
            anchor="w",
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=1, sticky="ew", padx=8, pady=(12, 2))

        ctk.CTkLabel(
            card,
            text=(
                f"Kickoff {self.format_jerusalem_time(candidate.get('commence_time'))}"
                f"  •  Consensus chance {chance:.2f}%  •  Fair odds "
                f"{float(candidate['consensus_fair_odds']):.2f}  •  "
                f"{confidence} confidence  •  "
                f"{int(candidate['consensus_bookmakers'])} bookmakers"
            ),
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=1, sticky="ew", padx=8, pady=2)

        ctk.CTkLabel(
            card,
            text=(
                f"{risk} relative risk: this is the market's most likely outcome "
                f"for this game, but it can still lose."
            ),
            anchor="w",
            text_color=risk_color,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=2, column=1, sticky="ew", padx=8, pady=(2, 12))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=0, column=2, rowspan=3, padx=12, pady=10)
        ctk.CTkLabel(
            controls,
            text="Winner odd:",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        ).grid(row=0, column=0, sticky="w", pady=(0, 3))
        odds_entry = ctk.CTkEntry(
            controls,
            width=105,
            placeholder_text="e.g. 1.80",
            fg_color=self.COLORS["panel_soft"],
            border_color=self.COLORS["border_light"],
        )
        odds_entry.grid(row=1, column=0, padx=(0, 6))
        verdict = ctk.CTkLabel(
            controls,
            text="Enter Winner's price",
            width=180,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        verdict.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        source_label = ctk.CTkLabel(
            controls,
            text="Waiting for Winner sync",
            width=180,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=9),
        )
        source_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        add_button = ctk.CTkButton(
            controls,
            text="Evaluate",
            width=82,
            command=lambda: self.evaluate_winner_candidate(
                candidate, odds_entry, verdict, add_button
            ),
        )
        add_button.grid(row=1, column=1)
        odds_entry.bind(
            "<Return>",
            lambda _event: self.evaluate_winner_candidate(
                candidate, odds_entry, verdict, add_button
            ),
        )
        odds_entry.bind(
            "<KeyRelease>",
            lambda _event: self.mark_winner_entry_edited(
                candidate,
                odds_entry,
                verdict,
                add_button,
                source_label,
            ),
        )
        self.advisor_controls.append(
            {
                "candidate": candidate.copy(),
                "entry": odds_entry,
                "verdict": verdict,
                "button": add_button,
                "source_label": source_label,
                "card": card,
                "rank_label": rank_label,
                "matched": None,
                "winner_value": None,
                "price_source": None,
            }
        )

    def start_winner_auto_sync(self):
        if self.sport_dropdown.get() != "Soccer":
            if hasattr(self, "winner_sync_label"):
                self.winner_sync_label.configure(
                    text=" • Winner sync: soccer only",
                    text_color=self.COLORS["muted"],
                )
            return
        self.winner_sync_generation += 1
        generation = self.winner_sync_generation
        controls = list(self.advisor_controls)
        if hasattr(self, "winner_sync_label"):
            self.winner_sync_label.configure(
                text=" • Auto-syncing Winner odds...",
                text_color=self.COLORS["warning"],
            )
        threading.Thread(
            target=self._winner_sync_worker,
            args=(generation, controls),
            daemon=True,
        ).start()

    def _winner_sync_worker(self, generation, controls):
        result = WinnerOddsFetcher().fetch()
        matches = []
        if not result.error:
            for control in controls:
                candidate = control["candidate"]
                match, score = match_winner_game(
                    candidate.get("home_team"),
                    candidate.get("away_team"),
                    result.matches,
                )
                winner_odd = (
                    match.odd_for(str(candidate.get("odds_column")))
                    if match
                    else None
                )
                matches.append((control, winner_odd, score, match))
        self.post_to_ui(
            self._apply_winner_sync,
            generation,
            result,
            matches,
        )

    def _apply_winner_sync(self, generation, result, matches):
        if generation != self.winner_sync_generation:
            return
        populated = 0
        for control in self.advisor_controls:
            if control.get("price_source") == "manual":
                continue
            control["matched"] = False
            control["winner_value"] = None
            control["source_label"].configure(
                text="No confident Winner match",
                text_color=self.COLORS["muted"],
            )
        for control, winner_odd, score, winner_match in matches:
            entry = control["entry"]
            try:
                if not entry.winfo_exists() or winner_odd is None:
                    continue
                if control.get("price_source") == "manual":
                    continue
                control["matched"] = True
                control["price_source"] = "auto"
                control["source_label"].configure(
                    text=(
                        f"Matched {winner_match.home_team} - "
                        f"{winner_match.away_team} ({score:.0%})"
                    ),
                    text_color=self.COLORS["success"],
                )
                entry.delete(0, "end")
                entry.insert(0, f"{float(winner_odd):.2f}")
                self.evaluate_winner_candidate(
                    control["candidate"],
                    entry,
                    control["verdict"],
                    control["button"],
                    source="auto",
                )
                populated += 1
            except (tkinter.TclError, ValueError, TypeError):
                continue

        if result.error:
            status = " • Winner sync unavailable"
            color = self.COLORS["danger"]
            self.advisor_status.configure(
                text=(
                    f"{result.error} Manual Winner entry remains available. "
                    "Set WINNER_ODDS_URL to a public JSON/HTML schedule endpoint "
                    "if Winner changes its listings."
                )
            )
        else:
            status = f" • Winner synced {populated}/{len(self.advisor_controls)}"
            color = self.COLORS["success"] if populated else self.COLORS["warning"]
            if populated:
                self.advisor_status.configure(
                    text=(
                        f"{populated} Winner games matched and evaluated. "
                        "Winner's lower prices often produce negative value, so "
                        "Favorable-only may correctly show few or zero games."
                    )
                )
            else:
                self.advisor_status.configure(
                    text=(
                        f"Winner returned {len(result.matches)} listings, but none "
                        "matched this scan confidently. Manual entry remains available."
                    )
                )
        if hasattr(self, "winner_sync_label"):
            self.winner_sync_label.configure(text=status, text_color=color)
        self.apply_advisor_filters()

    def mark_winner_entry_edited(
        self, candidate, odds_entry, verdict, button, source_label
    ):
        verdict.configure(
            text="Manual Winner price • press Evaluate",
            text_color=self.COLORS["muted"],
        )
        source_label.configure(
            text="Winner price edited manually",
            text_color=self.COLORS["warning"],
        )
        for control in self.advisor_controls:
            if control["entry"] is odds_entry:
                control["matched"] = True
                control["winner_value"] = None
                control["price_source"] = "manual"
                break
        button.configure(
            text="Evaluate",
            command=lambda: self.evaluate_winner_candidate(
                candidate,
                odds_entry,
                verdict,
                button,
                source="manual",
            ),
        )
        self.apply_advisor_filters()

    def evaluate_winner_candidate(
        self, candidate, odds_entry, verdict, button, source="manual"
    ):
        try:
            winner_odds = float(odds_entry.get().strip())
            if winner_odds <= 1:
                raise ValueError
        except ValueError:
            verdict.configure(
                text="Enter decimal odds above 1.00",
                text_color=self.COLORS["danger"],
            )
            return

        chance = float(candidate["consensus_probability_pct"]) / 100
        value = MarketAnalyzer.value_edge_pct(winner_odds, chance)
        if value >= 3:
            label = f"Favorable price • {value:+.2f}% value"
            color = self.COLORS["success"]
        elif value >= -3:
            label = f"Roughly fair price • {value:+.2f}% value"
            color = self.COLORS["warning"]
        else:
            label = f"Poor price • {value:+.2f}% value"
            color = self.COLORS["danger"]
        verdict.configure(text=label, text_color=color)
        for control in self.advisor_controls:
            if control["entry"] is odds_entry:
                control["winner_value"] = float(value)
                control["price_source"] = source
                if source == "manual":
                    control["matched"] = True
                    control["source_label"].configure(
                        text="Winner price entered manually",
                        text_color=self.COLORS["warning"],
                    )
                break
        button.configure(
            text="Add to slip",
            command=lambda: self.add_winner_candidate_to_slip(
                candidate, winner_odds, value, source
            ),
        )
        self.apply_advisor_filters()

    def apply_advisor_filters(self):
        if not hasattr(self, "advisor_controls"):
            return
        matched_only = self.advisor_matched_only.get()
        favorable_only = self.advisor_favorable_only.get()
        confidence_filter = self.advisor_confidence_filter.get()
        risk_filter = self.advisor_risk_filter.get()
        query = self.advisor_date_search.get().strip().casefold()
        visible_controls = []

        for control in self.advisor_controls:
            candidate = control["candidate"]
            matched = control.get("matched")
            value = control.get("winner_value")
            confidence = str(candidate.get("consensus_confidence") or "Low")
            risk = str(candidate.get("risk_level") or "High")

            visible = True
            if matched is not None and matched_only and not matched:
                visible = False
            if favorable_only and (value is None or value < 3):
                visible = False
            if confidence_filter == "High only" and confidence != "High":
                visible = False
            if (
                confidence_filter == "Medium + High"
                and confidence not in {"Medium", "High"}
            ):
                visible = False
            if risk_filter == "Lower only" and risk != "Lower":
                visible = False
            if (
                risk_filter == "Lower + Moderate"
                and risk not in {"Lower", "Moderate"}
            ):
                visible = False
            if query and query not in self.advisor_candidate_search_text(
                candidate
            ).casefold():
                visible = False

            if visible:
                visible_controls.append(control)
            else:
                control["card"].grid_remove()

        reverse = self.advisor_date_sort.get() == "Furthest match first"
        visible_controls.sort(
            key=lambda control: self.advisor_kickoff_sort_key(
                control["candidate"], reverse
            ),
            reverse=reverse,
        )
        for position, control in enumerate(visible_controls, start=1):
            control["rank_label"].configure(text=f"#{position}")
            control["card"].grid(
                row=position - 1,
                column=0,
                sticky="ew",
                padx=8,
                pady=7,
            )

        matched_count = sum(
            control.get("matched") is True for control in self.advisor_controls
        )
        self.advisor_filter_status.configure(
            text=(
                f"{len(visible_controls)} shown • {matched_count} Winner matched • "
                f"{len(self.advisor_controls)} scanned"
            )
        )

    def advisor_candidate_search_text(self, candidate):
        kickoff = pd.to_datetime(
            candidate.get("commence_time"), errors="coerce", utc=True
        )
        date_forms = ""
        if pd.notna(kickoff):
            local = kickoff.tz_convert("Asia/Jerusalem")
            date_forms = local.strftime(
                "%Y-%m-%d %d/%m/%Y %d/%m %d %b %B %H:%M"
            )
        return (
            f"{candidate.get('match', '')} {candidate.get('selection', '')} "
            f"{date_forms}"
        )

    @staticmethod
    def advisor_kickoff_sort_key(candidate, furthest_first=False):
        kickoff = pd.to_datetime(
            candidate.get("commence_time"), errors="coerce", utc=True
        )
        if pd.isna(kickoff):
            fallback = "1900-01-01" if furthest_first else "2200-01-01"
            return pd.Timestamp(fallback, tz="UTC")
        return kickoff

    def add_winner_candidate_to_slip(
        self, candidate, winner_odds, value, source="manual"
    ):
        event_id = candidate.get("event_id")
        event_key = (
            str(event_id)
            if pd.notna(event_id)
            else str(candidate["match"]).replace(" vs ", "|")
        )
        odds_column = str(candidate["odds_column"])
        bookmaker = "Winner (auto)" if source == "auto" else "Winner (manual)"
        identity = (event_key, bookmaker, odds_column)
        self.selected_bets[event_key] = {
            "identity": identity,
            "match": str(candidate["match"]),
            "selection": str(candidate["selection"]),
            "bookmaker": bookmaker,
            "odds": float(winner_odds),
            "fair_odds": float(candidate["consensus_fair_odds"]),
            "consensus_value": float(value),
            "confidence": str(candidate["consensus_confidence"]),
            "consensus_bookmakers": int(candidate["consensus_bookmakers"]),
            "outliers_excluded": int(candidate.get("outliers_excluded") or 0),
        }
        self.render_bet_slip()
        self.update_nav_slip_summary()
        self.saved_slip_status.configure(
            text=(
                f"Added Winner price: {candidate['selection']} @ "
                f"{float(winner_odds):.2f}"
            )
        )
        self.show_page("Bet Slip")
