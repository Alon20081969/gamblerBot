import tkinter as tk

import customtkinter as ctk
import pandas as pd

from src.models.probabilities import MarketAnalyzer


class AdvisorMixin:
    """Explain lower-risk market candidates and evaluate manual Winner prices."""

    def build_advisor_tab(self):
        self.advisor_tab.grid_rowconfigure(2, weight=1)
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

        self.advisor_results = ctk.CTkScrollableFrame(
            self.advisor_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.advisor_results.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.advisor_results.grid_columnconfigure(0, weight=1)
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
        for widget in self.advisor_results.winfo_children():
            widget.destroy()

        candidates = MarketAnalyzer.advisor_candidates(df)
        if candidates.empty:
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
        for position, (_, candidate) in enumerate(candidates.iterrows(), start=1):
            self.create_advisor_card(position, candidate)

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

        ctk.CTkLabel(
            card,
            text=f"#{position}",
            width=48,
            text_color=risk_color,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, rowspan=3, padx=(12, 4), pady=12)

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
                f"Consensus chance {chance:.2f}%  •  Fair odds "
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

    def evaluate_winner_candidate(self, candidate, odds_entry, verdict, button):
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
        button.configure(
            text="Add to slip",
            command=lambda: self.add_winner_candidate_to_slip(
                candidate, winner_odds, value
            ),
        )

    def add_winner_candidate_to_slip(self, candidate, winner_odds, value):
        event_id = candidate.get("event_id")
        event_key = (
            str(event_id)
            if pd.notna(event_id)
            else str(candidate["match"]).replace(" vs ", "|")
        )
        odds_column = str(candidate["odds_column"])
        identity = (event_key, "Winner (manual)", odds_column)
        self.selected_bets[event_key] = {
            "identity": identity,
            "match": str(candidate["match"]),
            "selection": str(candidate["selection"]),
            "bookmaker": "Winner (manual)",
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
