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

        guide = ctk.CTkScrollableFrame(
            self.guide_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        guide.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        guide.grid_columnconfigure((0, 1), weight=1, uniform="guide")

        warning = ctk.CTkFrame(
            guide,
            fg_color=self.COLORS["panel_alt"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["warning"],
        )
        warning.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 10))
        warning.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            warning,
            text="Important: value measures price, not certainty",
            anchor="w",
            text_color=self.COLORS["warning"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            warning,
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

        for index, term in enumerate(self.GUIDE_TERMS):
            row = (index // 2) + 1
            column = index % 2
            self._create_guide_card(guide, row, column, term)

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
