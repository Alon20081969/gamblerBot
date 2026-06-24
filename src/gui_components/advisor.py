import threading
import tkinter
from datetime import datetime, timezone

import customtkinter as ctk
import pandas as pd

from src.ingestion.winner_fetcher import (
    WinnerHistoryStore,
    WinnerOddsFetcher,
    match_winner_game,
    team_similarity,
)
from src.models.form_analyzer import FormAnalyzer
from src.models.probabilities import MarketAnalyzer


class AdvisorMixin:
    """Explain lower-risk market candidates and evaluate manual Winner prices."""

    WINNER_STALE_AFTER_SECONDS = 300

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
        rank_label.grid(row=0, column=0, rowspan=4, padx=(12, 4), pady=12)

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

        risk_label = ctk.CTkLabel(
            card,
            text=(
                f"{risk} relative risk: this is the market's most likely outcome "
                f"for this game, but it can still lose."
            ),
            anchor="w",
            text_color=risk_color,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        risk_label.grid(row=2, column=1, sticky="ew", padx=8, pady=(2, 2))

        form_label = ctk.CTkLabel(
            card,
            text="Recent form: waiting for a matched 365Scores fixture...",
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        )
        form_label.grid(row=3, column=1, sticky="ew", padx=8, pady=(2, 12))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=0, column=2, rowspan=4, padx=12, pady=10)
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
        trend_label = ctk.CTkLabel(
            controls,
            text="",
            width=24,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        trend_label.grid(row=1, column=1, padx=(0, 4))
        verdict = ctk.CTkLabel(
            controls,
            text="Enter Winner's price",
            width=180,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        verdict.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        history_label = ctk.CTkLabel(
            controls,
            text="Open: —  •  Prev: —",
            width=190,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=9),
        )
        history_label.grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )
        source_label = ctk.CTkLabel(
            controls,
            text="Waiting for Winner sync",
            width=180,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=9),
        )
        source_label.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        freshness_label = ctk.CTkLabel(
            controls,
            text="Freshness: waiting",
            width=180,
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=9, weight="bold"),
        )
        freshness_label.grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(2, 0)
        )
        history_button = ctk.CTkButton(
            controls,
            text="Price chart",
            width=82,
            height=24,
            state="disabled",
            fg_color=self.COLORS["panel_alt"],
            hover_color=self.COLORS["border_light"],
        )
        history_button.grid(row=5, column=2, sticky="e", pady=(4, 0))
        add_button = ctk.CTkButton(
            controls,
            text="Evaluate",
            width=82,
            command=lambda: self.evaluate_winner_candidate(
                candidate, odds_entry, verdict, add_button
            ),
        )
        add_button.grid(row=1, column=2)
        history_frame = ctk.CTkFrame(
            card,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=9,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        history_frame.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(0, 12),
        )
        history_frame.grid_columnconfigure(0, weight=1)
        history_canvas = tkinter.Canvas(
            history_frame,
            height=155,
            background=self.COLORS["panel_soft"],
            highlightthickness=0,
        )
        history_canvas.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        history_frame.grid_remove()
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
        control = {
            "candidate": candidate.copy(),
            "entry": odds_entry,
            "verdict": verdict,
            "button": add_button,
            "source_label": source_label,
            "trend_label": trend_label,
            "history_label": history_label,
            "freshness_label": freshness_label,
            "history_button": history_button,
            "history_frame": history_frame,
            "history_canvas": history_canvas,
            "card": card,
            "rank_label": rank_label,
            "risk_label": risk_label,
            "form_label": form_label,
            "matched": None,
            "winner_value": None,
            "price_source": None,
            "is_stale": False,
            "winner_fetched_at": None,
            "winner_match_id": None,
            "winner_outcome": None,
            "adjusted_risk": risk,
            "adjusted_safety_chance": chance,
            "form_differential": None,
        }
        history_button.configure(
            command=lambda selected=control: self.toggle_winner_history(selected)
        )
        self.advisor_controls.append(control)

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
                    expected_start_time=candidate.get("commence_time"),
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
        if result.warning:
            self.write_to_terminal(f"[!] {result.warning}")
        if result.error:
            self.write_to_terminal(f"[!] Winner sync failed: {result.error}")
        populated = 0
        age_seconds = self.winner_data_age_seconds(result.fetched_at)
        is_stale = (
            age_seconds is None
            or age_seconds > self.WINNER_STALE_AFTER_SECONDS
        )
        for control in self.advisor_controls:
            if control.get("price_source") == "manual":
                continue
            control["matched"] = False
            control["winner_value"] = None
            control["is_stale"] = False
            control["winner_fetched_at"] = None
            control["winner_match_id"] = None
            control["winner_outcome"] = None
            control["history_button"].configure(state="disabled")
            control["freshness_label"].configure(
                text="Freshness: no matched price",
                text_color=self.COLORS["muted"],
            )
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
                control["is_stale"] = is_stale
                control["winner_fetched_at"] = result.fetched_at
                control["winner_match_id"] = winner_match.match_id
                odds_column = str(control["candidate"].get("odds_column"))
                control["winner_outcome"] = {
                    "home_odds": "home",
                    "draw_odds": "draw",
                    "away_odds": "away",
                }.get(odds_column)
                previous = winner_match.previous_for(odds_column)
                opening = winner_match.opening_for(odds_column)
                trend = winner_match.trend_for(odds_column)
                arrow, trend_color = self.winner_trend_display(
                    winner_odd, previous, trend
                )
                control["trend_label"].configure(
                    text=arrow,
                    text_color=trend_color,
                )
                control["history_label"].configure(
                    text=(
                        f"Open: {self.winner_price_text(opening)}  •  "
                        f"Prev: {self.winner_price_text(previous)}"
                    )
                )
                control["source_label"].configure(
                    text=(
                        f"{winner_match.source} • "
                        f"{winner_match.home_team} - "
                        f"{winner_match.away_team} ({score:.0%})"
                    ),
                    text_color=self.COLORS["success"],
                )
                freshness_text, freshness_color = self.winner_freshness_display(
                    age_seconds, is_stale
                )
                control["freshness_label"].configure(
                    text=freshness_text,
                    text_color=freshness_color,
                )
                if control["winner_match_id"] and control["winner_outcome"]:
                    control["history_button"].configure(state="normal")
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
                if control["history_frame"].winfo_ismapped():
                    self.draw_winner_history(control)
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
            source_name = (
                "365Scores"
                if "365scores" in result.source_url.casefold()
                else "Winner fallback"
            )
            cache_note = " cached" if result.from_cache else ""
            status = (
                f" • {source_name}{cache_note} "
                f"{populated}/{len(self.advisor_controls)}"
            )
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
            if populated and is_stale:
                status = " â€¢ Winner prices stale - rescan required"
                color = self.COLORS["danger"]
                self.advisor_status.configure(
                    text=(
                        "Matched Winner prices are older than 5 minutes. "
                        "They are visible for comparison, but Add to slip is disabled "
                        "until a fresh sync completes."
                    )
                )
        if hasattr(self, "winner_sync_label"):
            self.winner_sync_label.configure(text=status, text_color=color)
        self.apply_advisor_filters()
        self.start_team_form_sync(generation, matches)
        self.after(
            30_000,
            lambda current_generation=generation: (
                self.refresh_winner_freshness(current_generation)
            ),
        )

    def start_team_form_sync(self, generation, matches):
        eligible = []
        for control, _winner_odd, _score, winner_match in matches:
            if (
                winner_match is None
                or winner_match.source != "365Scores"
                or not winner_match.match_id
            ):
                continue
            control["form_label"].configure(
                text="Recent form: syncing last 5 matches...",
                text_color=self.COLORS["warning"],
            )
            eligible.append((control, winner_match))
        if not eligible:
            return
        threading.Thread(
            target=self._team_form_worker,
            args=(generation, eligible),
            daemon=True,
        ).start()

    def _team_form_worker(self, generation, eligible):
        analyzer = FormAnalyzer()
        for control, winner_match in eligible:
            if generation != self.winner_sync_generation:
                return
            result = analyzer.fetch_match(winner_match.match_id)
            self.post_to_ui(
                self._apply_team_form,
                generation,
                control,
                result,
            )

    def _apply_team_form(self, generation, control, result):
        if generation != self.winner_sync_generation:
            return
        try:
            if not control["card"].winfo_exists():
                return
        except tkinter.TclError:
            return

        candidate = control["candidate"]
        baseline = float(candidate["consensus_probability_pct"])
        odds_column = str(candidate.get("odds_column"))
        if result.error or result.home is None or result.away is None:
            control["form_label"].configure(
                text="Recent form unavailable - no safety adjustment applied",
                text_color=self.COLORS["muted"],
            )
            return

        home_form, away_form = self.align_team_forms(candidate, result)
        form_summary = (
            f"{home_form.team_name} {home_form.score}/15 "
            f"({''.join(home_form.results)})  •  "
            f"{away_form.team_name} {away_form.score}/15 "
            f"({''.join(away_form.results)})"
        )
        if odds_column == "draw_odds":
            control["form_label"].configure(
                text=f"Recent form: {form_summary} • draw receives no form penalty",
                text_color=self.COLORS["muted"],
            )
            return

        if odds_column == "home_odds":
            suggested_form, opponent_form = home_form, away_form
        else:
            suggested_form, opponent_form = away_form, home_form
        adjusted, differential, penalty, has_alert = (
            FormAnalyzer.adjusted_safety(
                baseline,
                suggested_form,
                opponent_form,
            )
        )
        adjusted_risk = self.advisor_risk_from_chance(adjusted)
        control["adjusted_safety_chance"] = adjusted
        control["adjusted_risk"] = adjusted_risk
        control["form_differential"] = differential
        control["candidate"]["adjusted_safety_chance"] = adjusted
        control["candidate"]["adjusted_risk"] = adjusted_risk
        risk_color = self.advisor_risk_color(adjusted_risk)
        demoted = (
            str(candidate["risk_level"]) == "Lower"
            and adjusted_risk != "Lower"
        )
        warning = (
            " ⚠ Form Alert: Suggested team has poor recent form."
            if demoted
            else ""
        )
        penalty_text = (
            f" • safety chance {baseline:.2f}% → {adjusted:.2f}%"
            if penalty
            else f" • safety chance stays {adjusted:.2f}%"
        )
        control["form_label"].configure(
            text=(
                f"Recent form: {form_summary} • differential "
                f"{differential:+d}{penalty_text}{warning}"
            ),
            text_color=(
                self.COLORS["danger"] if has_alert else self.COLORS["muted"]
            ),
        )
        control["risk_label"].configure(
            text=(
                f"{adjusted_risk} relative risk after form review: "
                "this outcome can still lose."
                f"{warning}"
            ),
            text_color=risk_color,
        )
        control["rank_label"].configure(text_color=risk_color)
        self.apply_advisor_filters()

    def align_team_forms(self, candidate, result):
        expected_home = str(candidate.get("home_team") or "")
        direct = (
            team_similarity(expected_home, result.home.team_name)
            >= team_similarity(expected_home, result.away.team_name)
        )
        return (
            (result.home, result.away)
            if direct
            else (result.away, result.home)
        )

    @staticmethod
    def advisor_risk_from_chance(chance):
        chance = float(chance)
        if chance >= 65:
            return "Lower"
        if chance >= 50:
            return "Moderate"
        return "High"

    def advisor_risk_color(self, risk):
        return {
            "Lower": self.COLORS["success"],
            "Moderate": self.COLORS["warning"],
            "High": self.COLORS["danger"],
        }.get(str(risk), self.COLORS["muted"])

    def winner_trend_display(self, current, previous, trend):
        try:
            current_value = float(current)
            previous_value = float(previous)
            if current_value > previous_value:
                return "↑", self.COLORS["success"]
            if current_value < previous_value:
                return "↓", self.COLORS["danger"]
            return "→", self.COLORS["muted"]
        except (TypeError, ValueError):
            if trend == 3:
                return "↑", self.COLORS["success"]
            if trend == 1:
                return "↓", self.COLORS["danger"]
            return "→", self.COLORS["muted"]

    @staticmethod
    def winner_price_text(value):
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def winner_data_age_seconds(fetched_at):
        if not fetched_at:
            return None
        try:
            fetched = datetime.fromisoformat(
                str(fetched_at).replace("Z", "+00:00")
            )
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (
                    datetime.now(timezone.utc)
                    - fetched.astimezone(timezone.utc)
                ).total_seconds(),
            )
        except (TypeError, ValueError):
            return None

    def winner_freshness_display(self, age_seconds, is_stale):
        if age_seconds is None:
            return (
                "Freshness unknown - rescan before betting",
                self.COLORS["danger"],
            )
        if age_seconds < 60:
            age_text = f"{int(age_seconds)} sec ago"
        else:
            age_text = f"{int(age_seconds // 60)} min ago"
        if is_stale:
            return (
                f"Stale - synced {age_text} - rescan required",
                self.COLORS["danger"],
            )
        return f"Live sync - {age_text}", self.COLORS["success"]

    def refresh_winner_freshness(self, generation):
        if generation != self.winner_sync_generation:
            return
        stale_count = 0
        for control in self.advisor_controls:
            if (
                control.get("price_source") != "auto"
                or not control.get("matched")
            ):
                continue
            age_seconds = self.winner_data_age_seconds(
                control.get("winner_fetched_at")
            )
            is_stale = (
                age_seconds is None
                or age_seconds > self.WINNER_STALE_AFTER_SECONDS
            )
            control["is_stale"] = is_stale
            text, color = self.winner_freshness_display(age_seconds, is_stale)
            try:
                control["freshness_label"].configure(
                    text=text,
                    text_color=color,
                )
                if is_stale:
                    stale_count += 1
                    control["button"].configure(
                        text="Stale - rescan",
                        state="disabled",
                    )
                elif control.get("winner_value") is not None:
                    control["button"].configure(
                        text="Add to slip",
                        state="normal",
                    )
            except tkinter.TclError:
                continue
        if stale_count and hasattr(self, "winner_sync_label"):
            self.winner_sync_label.configure(
                text=f" â€¢ {stale_count} Winner prices stale - scan again",
                text_color=self.COLORS["danger"],
            )
        self.after(
            30_000,
            lambda current_generation=generation: (
                self.refresh_winner_freshness(current_generation)
            ),
        )

    def toggle_winner_history(self, control):
        frame = control["history_frame"]
        if frame.winfo_ismapped():
            frame.grid_remove()
            control["history_button"].configure(text="Price chart")
            return
        frame.grid()
        control["history_button"].configure(text="Hide chart")
        self.after_idle(lambda: self.draw_winner_history(control))

    def draw_winner_history(self, control):
        canvas = control["history_canvas"]
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 155)
        points = WinnerHistoryStore().get_history(
            control.get("winner_match_id"),
            control.get("winner_outcome"),
        )
        muted = self.COLORS["muted"]
        if not points:
            canvas.create_text(
                width / 2,
                height / 2,
                text=(
                    "No stored price changes yet. "
                    "Future scans will build this chart."
                ),
                fill=muted,
                font=("Segoe UI", 10),
            )
            return

        left, right, top, bottom = 54, width - 18, 18, height - 32
        values = [float(point["current_odds"]) for point in points]
        low, high = min(values), max(values)
        padding = max((high - low) * 0.15, 0.05)
        low -= padding
        high += padding
        canvas.create_line(
            left, top, left, bottom, fill=self.COLORS["border_light"]
        )
        canvas.create_line(
            left, bottom, right, bottom, fill=self.COLORS["border_light"]
        )
        canvas.create_text(
            left - 8,
            top,
            text=f"{high:.2f}",
            anchor="e",
            fill=muted,
            font=("Segoe UI", 8),
        )
        canvas.create_text(
            left - 8,
            bottom,
            text=f"{low:.2f}",
            anchor="e",
            fill=muted,
            font=("Segoe UI", 8),
        )

        coordinates = []
        count = len(points)
        for index, value in enumerate(values):
            x = (
                left
                if count == 1
                else left + (right - left) * index / (count - 1)
            )
            y = bottom - ((value - low) / (high - low)) * (bottom - top)
            coordinates.extend((x, y))
        if len(coordinates) >= 4:
            canvas.create_line(
                *coordinates,
                fill=self.COLORS["accent"],
                width=2,
            )
        for index in range(0, len(coordinates), 2):
            x, y = coordinates[index], coordinates[index + 1]
            canvas.create_oval(
                x - 3,
                y - 3,
                x + 3,
                y + 3,
                fill=self.COLORS["accent"],
                outline=self.COLORS["accent"],
            )
        canvas.create_text(
            left,
            bottom + 15,
            text=self.winner_history_time_text(points[0]["recorded_at"]),
            anchor="w",
            fill=muted,
            font=("Segoe UI", 8),
        )
        canvas.create_text(
            right,
            bottom + 15,
            text=self.winner_history_time_text(points[-1]["recorded_at"]),
            anchor="e",
            fill=muted,
            font=("Segoe UI", 8),
        )
        change_word = "change" if len(points) == 1 else "changes"
        canvas.create_text(
            right,
            top,
            text=(
                f"{len(points)} stored {change_word} - "
                f"current {values[-1]:.2f}"
            ),
            anchor="e",
            fill=self.COLORS["text"],
            font=("Segoe UI", 9, "bold"),
        )

    @staticmethod
    def winner_history_time_text(value):
        try:
            timestamp = pd.to_datetime(value, utc=True).tz_convert(
                "Asia/Jerusalem"
            )
            return timestamp.strftime("%d %b %H:%M")
        except (TypeError, ValueError):
            return "Unknown"

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
                control["is_stale"] = False
                control["winner_fetched_at"] = None
                control["trend_label"].configure(
                    text="",
                    text_color=self.COLORS["muted"],
                )
                control["history_label"].configure(
                    text="Open: —  •  Prev: —"
                )
                control["freshness_label"].configure(
                    text="Manual price - verify it in Winner",
                    text_color=self.COLORS["warning"],
                )
                break
        button.configure(
            text="Evaluate",
            state="normal",
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
        matched_control = None
        for control in self.advisor_controls:
            if control["entry"] is odds_entry:
                matched_control = control
                control["winner_value"] = float(value)
                control["price_source"] = source
                if source == "manual":
                    control["matched"] = True
                    control["source_label"].configure(
                        text="Winner price entered manually",
                        text_color=self.COLORS["warning"],
                    )
                break
        if (
            source == "auto"
            and matched_control is not None
            and matched_control.get("is_stale")
        ):
            button.configure(
                text="Stale - rescan",
                state="disabled",
            )
        else:
            button.configure(
                text="Add to slip",
                state="normal",
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
            risk = str(
                control.get("adjusted_risk")
                or candidate.get("risk_level")
                or "High"
            )

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
