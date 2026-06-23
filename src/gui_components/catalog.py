import json
import threading
import tkinter as tk

import customtkinter as ctk


class CompetitionMixin:
    """Competition catalog, search, favorites, and API catalog refresh."""

    @staticmethod
    def region_for_group(group):
        group_lower = group.lower()
        if any(name in group_lower for name in ("aussie", "rugby league")):
            return "au"
        if any(name in group_lower for name in ("soccer", "rugby", "cricket")):
            return "eu"
        return "us"

    def build_competition_browser(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.browser_frame = ctk.CTkFrame(
            parent,
            fg_color=self.COLORS["panel"],
            corner_radius=14,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.browser_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.browser_frame.grid_rowconfigure(4, weight=1)
        self.browser_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.browser_frame, text="Browse competitions",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
        ctk.CTkLabel(
            self.browser_frame,
            text="Search by competition name:",
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 3))
        self.competition_search = ctk.CTkEntry(
            self.browser_frame,
            placeholder_text="Search competitions...",
            height=36,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
        )
        self.competition_search.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        self.competition_search.bind("<KeyRelease>", self.filter_competitions)
        self.search_result_count = ctk.CTkLabel(
            self.browser_frame,
            text="",
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        )
        self.search_result_count.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 5))
        self.competition_results = ctk.CTkScrollableFrame(
            self.browser_frame,
            label_text="",
            fg_color=self.COLORS["panel_soft"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.competition_results.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.competition_results.grid_columnconfigure(0, weight=1)
        self.populate_competition_browser()

    def on_sport_changed(self, selected_sport):
        competitions = self.sorted_competitions(selected_sport)
        self.competition_dropdown.configure(values=competitions)
        self.competition_dropdown.set(competitions[0] if competitions else "No competitions available")
        if hasattr(self, "competition_search"):
            if self.search_after_id is not None:
                self.after_cancel(self.search_after_id)
                self.search_after_id = None
            self.competition_search.delete(0, tk.END)
            self.populate_competition_browser()

    def filter_competitions(self, _event=None):
        if self.search_after_id is not None:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(160, self.apply_competition_filter)

    def apply_competition_filter(self):
        self.search_after_id = None
        self.populate_competition_browser(self.competition_search.get())

    def populate_competition_browser(self, query=""):
        for widget in self.competition_results.winfo_children():
            widget.destroy()
        sport = self.sport_dropdown.get()
        search_term = query.strip().casefold()
        matches = [
            name for name in self.sorted_competitions(sport)
            if search_term in name.casefold()
        ]
        self.search_result_count.configure(
            text=(
                f"{len(matches)} competition{'s' if len(matches) != 1 else ''}"
                "  •  ★ favorites stay first"
            )
        )
        if not matches:
            ctk.CTkLabel(
                self.competition_results, text="No competitions found",
                text_color=("gray45", "gray65"),
            ).grid(row=0, column=0, sticky="ew", padx=8, pady=16)
            return
        for row, competition in enumerate(matches):
            selected = competition == self.competition_dropdown.get()
            item = ctk.CTkFrame(
                self.competition_results,
                fg_color=self.COLORS["panel_alt"] if selected else "transparent",
                corner_radius=8,
            )
            item.grid(row=row, column=0, sticky="ew", padx=3, pady=3)
            item.grid_columnconfigure(1, weight=1)
            key = self.competition_catalog[sport][competition]["key"]
            favorite = key in self.favorite_competition_keys
            ctk.CTkButton(
                item, text="★" if favorite else "☆", width=34, fg_color="transparent",
                hover_color=self.COLORS["panel_alt"],
                text_color=self.COLORS["warning"] if favorite else self.COLORS["muted"],
                font=ctk.CTkFont(size=18),
                command=lambda name=competition: self.toggle_favorite(name),
            ).grid(row=0, column=0, padx=(0, 3))
            ctk.CTkButton(
                item, text=competition, anchor="w", fg_color="transparent",
                border_width=1, border_color=self.COLORS["border"],
                text_color=self.COLORS["text"], hover_color=self.COLORS["panel_alt"],
                command=lambda name=competition: self.select_competition(name),
            ).grid(row=0, column=1, sticky="ew")

    def select_competition(self, competition):
        self.competition_dropdown.set(competition)
        self.catalog_status.configure(text=f"Selected: {competition}")
        self.populate_competition_browser(self.competition_search.get())

    def sorted_competitions(self, sport):
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
        key = config["key"]
        if key in self.favorite_competition_keys:
            self.favorite_competition_keys.remove(key)
            action = "Removed from favorites"
        else:
            self.favorite_competition_keys.add(key)
            action = "Added to favorites"
        self.save_favorites()
        selected = self.competition_dropdown.get()
        ordered = self.sorted_competitions(sport)
        self.competition_dropdown.configure(values=ordered)
        if selected in ordered:
            self.competition_dropdown.set(selected)
        self.populate_competition_browser(self.competition_search.get())
        self.catalog_status.configure(text=f"{action}: {competition}")

    def load_favorites(self):
        try:
            data = json.loads(self.FAVORITES_FILE.read_text(encoding="utf-8"))
            keys = data.get("competition_keys", []) if isinstance(data, dict) else data
            return {str(key) for key in keys}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return set()

    def save_favorites(self):
        payload = {"competition_keys": sorted(self.favorite_competition_keys)}
        try:
            self.FAVORITES_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            self.write_to_terminal(f"[!] Could not save favorites: {exc}")

    def refresh_competition_catalog(self):
        threading.Thread(target=self._load_competition_catalog, daemon=True).start()

    def _load_competition_catalog(self):
        sports = self.client.get_available_sports(include_inactive=True)
        self.post_to_ui(self.refresh_quota_display)
        if not sports:
            self.post_to_ui(self._show_fallback_catalog_status)
            return
        catalog = {
            sport: {name: config.copy() for name, config in competitions.items()}
            for sport, competitions in self.FALLBACK_COMPETITIONS.items()
        }
        for item in sports:
            key, title = item.get("key"), item.get("title")
            group = item.get("group") or "Other"
            if not key or not title or item.get("has_outrights"):
                continue
            catalog.setdefault(group, {})[title] = {
                "key": key, "region": self.region_for_group(group),
                "active": item.get("active", False),
                "description": item.get("description", ""),
            }
        self.post_to_ui(self._apply_competition_catalog, catalog)

    def _apply_competition_catalog(self, catalog):
        self.competition_catalog = catalog
        sports = sorted(catalog)
        self.sport_dropdown.configure(values=sports)
        selected = "Soccer" if "Soccer" in catalog else sports[0]
        self.sport_dropdown.set(selected)
        self.on_sport_changed(selected)
        count = sum(len(items) for items in catalog.values())
        self.catalog_status.configure(text=f"{count} competitions loaded across {len(sports)} sports")

    def _show_fallback_catalog_status(self):
        self.catalog_status.configure(text="Using built-in competitions (online catalog unavailable)")
