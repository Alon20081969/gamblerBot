import customtkinter as ctk


class GuideMixin:
    """Plain-language reference for the market metrics shown in the app."""

    GUIDE_TERMS = (
        {
            "title": "Decimal odds",
            "summary": "The total return for every 1 unit staked, including your stake.",
            "example": (
                "Example: odds of 3.00 with a 10 stake return 30 if the bet wins. "
                "That is 20 profit plus the original 10 stake."
            ),
        },
        {
            "title": "Implied chance",
            "summary": "The probability suggested directly by one bookmaker's odds.",
            "formula": "Formula: 100 / decimal odds",
            "example": (
                "Example: odds of 4.00 imply a 25% chance. This number still includes "
                "the bookmaker's margin."
            ),
        },
        {
            "title": "Bookmaker margin (vig)",
            "summary": (
                "The bookmaker's built-in pricing advantage. The raw implied chances "
                "of all outcomes normally add up to more than 100%."
            ),
            "example": (
                "Example: Home 50% + Draw 30% + Away 25% = 105%. "
                "The extra 5% is the market margin."
            ),
        },
        {
            "title": "Consensus chance",
            "summary": (
                "The market's estimated probability after removing each bookmaker's "
                "margin and combining the complete bookmaker markets."
            ),
            "example": (
                "Example: after margin removal, bookmakers estimate a team around "
                "24%, 25%, and 26%. The consensus is approximately 25%."
            ),
        },
        {
            "title": "Fair odds",
            "summary": "The decimal odds that exactly match the consensus chance.",
            "formula": "Formula: 1 / consensus probability",
            "example": (
                "Example: a 25% consensus chance produces fair odds of 4.00. "
                "A price above 4.00 may offer value; a price below it may not."
            ),
        },
        {
            "title": "Consensus value",
            "summary": (
                "How much better or worse the best available price is compared with "
                "the margin-free consensus estimate."
            ),
            "formula": "Formula: (best odds x consensus probability - 1) x 100",
            "example": (
                "Example: best odds 5.00 and consensus chance 25% give "
                "(5.00 x 0.25 - 1) x 100 = +25% value."
            ),
        },
        {
            "title": "Positive and negative value",
            "summary": (
                "Positive value means the offered payout is better than the consensus "
                "estimate. Negative value means it is worse."
            ),
            "example": (
                "Example: +12% is attractively priced relative to the market. "
                "-8% is priced below the market estimate. Neither predicts one result."
            ),
        },
        {
            "title": "Best and lowest odds",
            "summary": (
                "The highest and lowest prices currently offered for the same outcome "
                "by the scanned bookmakers."
            ),
            "example": (
                "Example: one bookmaker offers 2.40 while another offers 2.10. "
                "For the same winning bet, 2.40 pays more."
            ),
        },
        {
            "title": "Bookmaker spread",
            "summary": (
                "The percentage gap between the highest and lowest odds for an outcome."
            ),
            "formula": "Formula: (highest odds - lowest odds) / lowest odds x 100",
            "example": (
                "Example: highest 2.40 and lowest 2.00 produce a 20% bookmaker spread."
            ),
        },
        {
            "title": "Price disagreement",
            "summary": (
                "The older opportunity score that measures how far the best price sits "
                "above the market's lowest and median prices."
            ),
            "example": (
                "Example: a high score means bookmakers disagree strongly about price. "
                "It can reveal a good price, but disagreement alone is not evidence "
                "that the selection will win."
            ),
        },
        {
            "title": "Median odds",
            "summary": (
                "The middle bookmaker price after all available odds are ordered. "
                "It is less affected by one unusually high or low bookmaker."
            ),
            "example": "Example: odds 2.00, 2.20, and 3.50 have a median of 2.20.",
        },
        {
            "title": "Bookmaker count",
            "summary": (
                "How many bookmakers supplied a complete market used in the consensus."
            ),
            "example": (
                "Example: a consensus based on 10 complete bookmakers is generally "
                "more informative than one based on only 2."
            ),
        },
        {
            "title": "Confidence rating",
            "summary": (
                "A High, Medium, or Low label describing how stable the consensus "
                "estimate is. It measures data support, not the chance of winning."
            ),
            "example": (
                "High: at least 6 complete bookmakers and no more than a 5 percentage-"
                "point estimate range. Medium: at least 3 bookmakers and no more than "
                "10 points. All other cases are Low."
            ),
        },
        {
            "title": "Probability estimate range",
            "summary": (
                "The distance between the highest and lowest margin-free probability "
                "estimates supplied by bookmakers for the same outcome."
            ),
            "example": (
                "Example: bookmaker estimates of 22%, 24%, and 27% have a 5 "
                "percentage-point range. A smaller range means stronger agreement."
            ),
        },
        {
            "title": "Why this opportunity?",
            "summary": (
                "The explanation below each Best card connecting its offered odds, "
                "fair odds, value, bookmaker count, and confidence rating."
            ),
            "example": (
                "Example: '5.00 is 25% above fair odds 4.00; Medium confidence from "
                "4 bookmakers whose estimates span 6 percentage points.'"
            ),
        },
        {
            "title": "Value-aware bet slip",
            "summary": (
                "A bet-slip selection that keeps its fair odds, consensus value, "
                "confidence rating, and bookmaker count beside the offered price."
            ),
            "example": (
                "Example: the slip can show offered odds 5.00, fair odds 4.00, "
                "+25% consensus value, and Medium confidence. This preserves the "
                "reason the selection was added."
            ),
        },
        {
            "title": "Outlier protection",
            "summary": (
                "A safety rule that stops one unusually high bookmaker price from "
                "creating a misleading value recommendation."
            ),
            "example": (
                "Example: if most prices are near 4.00 but one feed reports 15.00, "
                "the 15.00 remains visible in bookmaker details but is excluded from "
                "the recommended best price when it exceeds the robust limit."
            ),
        },
        {
            "title": "Suspicious price",
            "summary": (
                "A price at least 15% above the median and also beyond a robust "
                "median-deviation limit when three or more prices are available."
            ),
            "example": (
                "This may be a genuine temporary price or a feed error. The app does "
                "not delete it; it simply avoids using it to calculate recommended value."
            ),
        },
        {
            "title": "Odds freshness",
            "summary": (
                "The time of the latest successful market scan used to verify prices "
                "in the Results page and Bet Slip."
            ),
            "example": (
                "Example: 'Odds updated 20:14:32' means the displayed verification "
                "uses market data received at that Jerusalem time."
            ),
        },
        {
            "title": "Changed odds",
            "summary": (
                "A warning that the currently available bookmaker price differs from "
                "the price originally added to your slip."
            ),
            "example": (
                "Example: 2.20 → 2.05 means your stored selection still shows 2.20, "
                "but the latest scan found 2.05. The app does not silently replace it."
            ),
        },
        {
            "title": "Unavailable selection",
            "summary": (
                "The bookmaker and outcome combination from the slip was not returned "
                "by the latest scan."
            ),
            "example": (
                "It may have been removed, suspended, renamed, or temporarily omitted. "
                "Treat the stored price as stale until a later scan verifies it."
            ),
        },
        {
            "title": "Market favorite",
            "summary": (
                "The outcome with the highest margin-free consensus probability "
                "in one game."
            ),
            "example": (
                "Example: Home 68%, Draw 20%, Away 12% makes Home the market favorite. "
                "It remains possible for Home to lose."
            ),
        },
        {
            "title": "Relative risk",
            "summary": (
                "A simple comparison based on consensus chance: Lower at 65% or more, "
                "Moderate from 50% to below 65%, and High below 50%."
            ),
            "example": (
                "Lower risk means more likely according to the market—not safe, certain, "
                "or automatically worth betting."
            ),
        },
        {
            "title": "Winner price evaluation",
            "summary": (
                "A comparison between the manually entered Winner odd and the general "
                "bookmaker consensus probability."
            ),
            "example": (
                "The advisor calls +3% or more Favorable, -3% to +3% Roughly fair, "
                "and below -3% a Poor price."
            ),
        },
        {
            "title": "Winner auto-sync",
            "summary": (
                "A background request to Winner's public full-time 1/X/2 line that "
                "fills matched Advisor prices without blocking the interface."
            ),
            "example": (
                "The status beside the odds timestamp reports syncing, the number "
                "matched, or that manual entry is required."
            ),
        },
        {
            "title": "Fuzzy team matching",
            "summary": (
                "A similarity check used to align international English team names "
                "with Winner's Hebrew names and minor spelling variations."
            ),
            "example": (
                "Example: Netherlands can match הולנד through the alias map. "
                "A price is inserted only when both teams pass the confidence threshold."
            ),
        },
        {
            "title": "Reference bookmaker odds",
            "summary": (
                "Global bookmaker prices shown in Results and Best to estimate the "
                "market. They cannot be added to the actionable slip."
            ),
            "example": (
                "A global price of 1.90 can help calculate fair value, but the slip "
                "must use the actual Winner price you can place in Israel."
            ),
        },
        {
            "title": "Winner-only shortlist",
            "summary": (
                "The actionable Advisor list containing Winner-synced or manually "
                "entered prices, with filters for matching, value, confidence, and risk."
            ),
            "example": (
                "Matched-only is enabled by default. Favorable-only may show zero "
                "games when Winner's lower prices do not compensate for the risk."
            ),
        },
        {
            "title": "Kickoff time",
            "summary": (
                "The scheduled match date and hour converted from the provider's UTC "
                "timestamp into Jerusalem local time."
            ),
            "example": (
                "Example: 'Thu, 25 Jun 2026 at 22:00' is the local Israeli kickoff "
                "time shown consistently in Results, Best, and Advisor."
            ),
        },
        {
            "title": "Closest and furthest match",
            "summary": (
                "Chronological sorting by kickoff. Closest puts the next scheduled "
                "game first; furthest puts the latest scheduled game first."
            ),
            "example": (
                "Games with missing kickoff data are kept after games with valid dates "
                "instead of being mixed into the chronological list."
            ),
        },
        {
            "title": "Date search",
            "summary": (
                "A team-or-date filter available in Results, Best, and Advisor."
            ),
            "example": (
                "Search using formats such as 2026-06-25, 25/06, 25 Jun, June, "
                "22:00, or a team name."
            ),
        },
        {
            "title": "Opening Winner odds",
            "summary": (
                "The first Winner price supplied for an outcome in the current "
                "365Scores market record."
            ),
            "example": (
                "Open 1.35 and current 1.25 means Winner shortened the price since "
                "the market was first recorded."
            ),
        },
        {
            "title": "Previous Winner odds",
            "summary": (
                "The Winner price immediately before the current price update."
            ),
            "example": (
                "Prev 1.30 and current 1.25 produces a downward arrow because the "
                "available payout decreased."
            ),
        },
        {
            "title": "Winner price trend",
            "summary": (
                "A quick comparison between the current and previous Winner prices."
            ),
            "example": (
                "↑ means the payout increased, ↓ means it decreased, and → means "
                "no detected change."
            ),
        },
        {
            "title": "Local Winner history",
            "summary": (
                "A SQLite time series stored locally whenever a Winner outcome price "
                "changes between app scans."
            ),
            "example": (
                "Repeated unchanged scans add no duplicates. A changed home, draw, "
                "or away price creates one timestamped history point."
            ),
        },
        {
            "title": "Winner price chart",
            "summary": (
                "An expandable graph inside an Advisor card showing each changed "
                "Winner price stored for that exact match and outcome."
            ),
            "example": (
                "Open Price chart to see whether the selected Winner odd has risen "
                "or fallen across your scans. One dot means only one change is stored."
            ),
        },
        {
            "title": "Fixture identity matching",
            "summary": (
                "The Winner sync checks both teams and kickoff time so repeated "
                "fixtures are less likely to receive odds from the wrong game."
            ),
            "example": (
                "If the same teams play again next week, a listing more than 18 hours "
                "from the scanned kickoff is rejected even when the names match."
            ),
        },
        {
            "title": "Stale Winner odds",
            "summary": (
                "An automatically synced Winner price older than five minutes. "
                "It may no longer be available at the bookmaker."
            ),
            "example": (
                "The Advisor keeps a stale price visible for context but disables "
                "Add to slip until a new scan refreshes it."
            ),
        },
        {
            "title": "Upcoming-only fixture filter",
            "summary": (
                "A kickoff-time check that removes games once their scheduled start "
                "time has passed, even if the odds provider still returns the market."
            ),
            "example": (
                "If Qatar vs Bosnia kicked off at 20:00, a scan after 20:00 will hide "
                "it from Results, Best, Advisor, and new history records."
            ),
        },
        {
            "title": "Team Form Score",
            "summary": (
                "Points earned across a team's five most recent completed matches: "
                "3 for a win, 1 for a draw, and 0 for a loss."
            ),
            "formula": "Maximum: 5 wins x 3 points = 15",
            "example": (
                "Results W-W-D-L-W produce 3 + 3 + 1 + 0 + 3 = 10/15."
            ),
        },
        {
            "title": "Form Differential",
            "summary": (
                "The suggested team's Form Score minus its opponent's Form Score."
            ),
            "formula": "Suggested team score - opponent score",
            "example": (
                "Suggested team 4/15 and opponent 11/15 gives -7. "
                "A result below -5 triggers the form penalty."
            ),
        },
        {
            "title": "Adjusted safety chance",
            "summary": (
                "An Advisor-only risk check derived from consensus chance and recent "
                "form. It does not replace or rewrite the bookmaker consensus."
            ),
            "example": (
                "A 68% consensus chance with a -7 Form Differential receives a "
                "5-point penalty, becoming 63% for the relative-risk label."
            ),
        },
        {
            "title": "Form Alert",
            "summary": (
                "A warning shown when poor recent form pushes a selection from Lower "
                "relative risk below the 65% threshold."
            ),
            "example": (
                "The card is demoted to Moderate risk while its original consensus "
                "chance remains visible for transparency."
            ),
        },
        {
            "title": "Elo rating",
            "summary": (
                "A running team-strength rating updated after historical results. "
                "Beating stronger opponents raises a rating more than beating weaker ones."
            ),
            "example": (
                "The Advisor starts unseen teams at 1500, includes home advantage, "
                "and replays the recent scored games supplied by 365Scores."
            ),
        },
        {
            "title": "Experimental Elo probability",
            "summary": (
                "The home, draw, or away chance derived from the provisional Elo "
                "ratings. It is shown separately because it is not yet calibrated."
            ),
            "example": (
                "Elo 61% means the recent-result rating model assigns 61%, not that "
                "the outcome is guaranteed or that Winner offers a good price."
            ),
        },
        {
            "title": "Blended model chance",
            "summary": (
                "A conservative estimate using 80% bookmaker consensus and 20% "
                "experimental Elo before any poor-form penalty."
            ),
            "formula": "0.80 x market chance + 0.20 x Elo chance",
            "example": (
                "Market 70% and Elo 60% produce a 68% blended chance. The heavier "
                "market weight limits the effect of an immature Elo model."
            ),
        },
        {
            "title": "Prediction ledger",
            "summary": (
                "A local SQLite record of each pre-match Advisor estimate, its Winner "
                "price, and the eventual result."
            ),
            "example": (
                "Predictions are keyed by the exact 365Scores fixture and outcome so "
                "later scans can settle them without confusing repeated fixtures."
            ),
        },
        {
            "title": "Brier score",
            "summary": (
                "A probability-calibration error where lower is better. It penalizes "
                "confident predictions that are wrong."
            ),
            "formula": "Average of (predicted probability - actual result)^2",
            "example": (
                "Predicting 80% for an outcome that loses creates 0.64 error; "
                "predicting 55% creates 0.3025. Use many settled games before judging."
            ),
        },
        {
            "title": "Flat-stake model P/L",
            "summary": (
                "The hypothetical profit or loss from staking one unit on every "
                "tracked selection at its recorded Winner price."
            ),
            "example": (
                "It is a backtest diagnostic, not a promise. A small sample can be "
                "strongly distorted by luck and high odds."
            ),
        },
    )

    def build_guide_tab(self):
        self.guide_tab.grid_rowconfigure(1, weight=1)
        self.guide_tab.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.guide_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Odds & market guide",
            anchor="w",
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=(
                "A plain-language reference for the terms used in Results and Best."
            ),
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.guide_search_entry = ctk.CTkEntry(
            header,
            placeholder_text="Search terms, formulas, or examples...",
            width=310,
            height=34,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
        )
        self.guide_search_entry.grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
            padx=(12, 8),
        )
        self.guide_search_entry.bind(
            "<KeyRelease>",
            lambda _event: self.filter_guide_terms(),
        )
        self.guide_search_status = ctk.CTkLabel(
            header,
            text=f"{len(self.GUIDE_TERMS)} terms",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.guide_search_status.grid(
            row=0,
            column=2,
            rowspan=2,
            sticky="e",
        )

        self.guide_scroll = ctk.CTkScrollableFrame(
            self.guide_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.guide_scroll.grid(
            row=1, column=0, sticky="nsew", padx=4, pady=(0, 4)
        )
        self.guide_scroll.grid_columnconfigure(
            (0, 1), weight=1, uniform="guide"
        )

        self.guide_warning = ctk.CTkFrame(
            self.guide_scroll,
            fg_color=self.COLORS["panel_alt"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["warning"],
        )
        self.guide_warning.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(8, 10),
        )
        self.guide_warning.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.guide_warning,
            text="Important: value measures price, not certainty",
            anchor="w",
            text_color=self.COLORS["warning"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            self.guide_warning,
            text=(
                "A +25% value selection can still lose. The number says the available "
                "payout is favorable relative to the market estimate, not that the "
                "event has a 25% guaranteed profit."
            ),
            anchor="w",
            justify="left",
            wraplength=1050,
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 10))

        self.guide_cards = []
        for index, term in enumerate(self.GUIDE_TERMS):
            row = (index // 2) + 1
            column = index % 2
            card = self._create_guide_card(
                self.guide_scroll, row, column, term
            )
            self.guide_cards.append((card, term))

        self.guide_no_results = ctk.CTkLabel(
            self.guide_scroll,
            text="No guide terms match that search.",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )

    def filter_guide_terms(self):
        query = self.guide_search_entry.get().strip().casefold()
        visible = []
        for card, term in self.guide_cards:
            searchable = " ".join(
                str(term.get(field, ""))
                for field in ("title", "summary", "formula", "example")
            ).casefold()
            if not query or query in searchable:
                visible.append((card, term))
            else:
                card.grid_remove()

        for index, (card, _term) in enumerate(visible):
            card.grid(
                row=(index // 2) + 1,
                column=index % 2,
                sticky="nsew",
                padx=8,
                pady=7,
            )

        self.guide_search_status.configure(
            text=f"{len(visible)} of {len(self.GUIDE_TERMS)} terms"
        )
        if visible:
            self.guide_no_results.grid_remove()
        else:
            self.guide_no_results.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=20,
                pady=35,
            )

    def _create_guide_card(self, parent, row, column, term):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        card.grid(row=row, column=column, sticky="nsew", padx=8, pady=7)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=term["title"],
            anchor="w",
            text_color=self.COLORS["accent_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 5))
        ctk.CTkLabel(
            card,
            text=term["summary"],
            anchor="w",
            justify="left",
            wraplength=500,
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 5))

        content_row = 2
        formula = term.get("formula")
        if formula:
            ctk.CTkLabel(
                card,
                text=formula,
                anchor="w",
                justify="left",
                wraplength=500,
                text_color=self.COLORS["warning"],
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=content_row, column=0, sticky="ew", padx=14, pady=(1, 5))
            content_row += 1

        ctk.CTkLabel(
            card,
            text=term["example"],
            anchor="w",
            justify="left",
            wraplength=500,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(
            row=content_row,
            column=0,
            sticky="ew",
            padx=14,
            pady=(2, 12),
        )
        return card
