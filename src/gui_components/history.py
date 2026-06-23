import csv
import tkinter as tk
from datetime import datetime
from zoneinfo import ZoneInfo

import customtkinter as ctk
import pandas as pd


class HistoryExportMixin:
    """In-session odds history charts and CSV export helpers."""

    def build_history_tab(self):
        self.history_tab.grid_rowconfigure(4, weight=1)
        self.history_tab.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.history_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            header,
            text="Odds history",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLORS["text"],
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Save all history to CSV", command=self.export_history_csv,
            width=165, height=34,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
        ).pack(side="right")
        ctk.CTkLabel(
            self.history_tab,
            text=(
                "How to use: scan the same competition more than once. Search for a team, "
                "outcome, or bookmaker, then choose a price line. Each dot is one scan. "
                "Higher decimal odds mean a larger potential payout. CSV saves all lines, "
                "not only the searched line."
            ),
            wraplength=650,
            justify="left",
            anchor="w",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=10),
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 7))
        history_filters = ctk.CTkFrame(
            self.history_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        history_filters.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        history_filters.grid_columnconfigure(1, weight=1)
        history_filters.grid_columnconfigure(3, weight=2)
        ctk.CTkLabel(history_filters, text="Search:").grid(
            row=0, column=0, sticky="w", padx=(12, 6), pady=10
        )
        self.history_search_entry = ctk.CTkEntry(
            history_filters,
            placeholder_text="Search team, outcome, or bookmaker...",
            width=220,
            height=34,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
        )
        self.history_search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=10)
        self.history_search_entry.bind("<KeyRelease>", self.filter_history_series)
        ctk.CTkLabel(history_filters, text="Price line:").grid(
            row=0, column=2, sticky="w", padx=(0, 6), pady=10
        )
        self.history_selector = ctk.CTkComboBox(
            history_filters,
            values=["No history yet"],
            state="readonly",
            height=34,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
            command=lambda _value: self.draw_history_chart(),
        )
        self.history_selector.set("No history yet")
        self.history_selector.grid(row=0, column=3, sticky="ew", padx=(0, 12), pady=10)
        self.history_selection_title = ctk.CTkLabel(
            self.history_tab,
            text="No price line selected",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.history_selection_title.grid(
            row=3, column=0, sticky="ew", padx=10, pady=(0, 6)
        )
        self.history_canvas = tk.Canvas(
            self.history_tab,
            background=self.COLORS["panel_soft"],
            highlightthickness=1,
            highlightbackground=self.COLORS["border"],
            height=340,
        )
        self.history_canvas.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.history_canvas.bind("<Configure>", lambda _event: self.draw_history_chart())
        self.history_status = ctk.CTkLabel(
            self.history_tab,
            text="Waiting for the first scan. Two or more scans are needed to show movement.",
            text_color=("gray45", "gray65"),
        )
        self.history_status.grid(row=5, column=0, sticky="w", padx=10, pady=(0, 8))

    def record_odds_history(self, current_odds, metadata):
        timestamp = datetime.now(ZoneInfo("Asia/Jerusalem"))
        for identity, odds in current_odds.items():
            info = metadata[identity]
            points = self.odds_history.setdefault(identity, [])
            points.append({"timestamp": timestamp, "odds": odds, **info})
            label = (
                f"{info['match']} | {info['selection']} | {info['bookmaker']}"
            )
            self.history_series_labels[label] = identity
        self.refresh_history_selector()

    def refresh_history_selector(self):
        self.filter_history_series()

    def filter_history_series(self, _event=None):
        query = self.history_search_entry.get().strip().casefold()
        labels = [
            label for label in sorted(self.history_series_labels)
            if query in label.casefold()
        ]
        if not labels:
            self.history_selector.configure(values=["No matching history"])
            self.history_selector.set("No matching history")
            self.draw_history_chart()
            return
        current = self.history_selector.get()
        self.history_selector.configure(values=labels)
        self.history_selector.set(current if current in labels else labels[0])
        self.draw_history_chart()

    def draw_history_chart(self):
        if not hasattr(self, "history_canvas"):
            return
        canvas = self.history_canvas
        canvas.delete("all")
        label = self.history_selector.get()
        identity = self.history_series_labels.get(label)
        points = self.odds_history.get(identity, []) if identity else []
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), 220)
        if not points:
            self.history_selection_title.configure(
                text="No matching price line. Change the search or run a scan."
            )
            self.history_status.configure(
                text="No chart is selected. Search less specifically or complete a scan."
            )
            canvas.create_text(
                width / 2, height / 2, text="No odds history yet", fill="#aaaaaa",
                font=("Segoe UI", 12),
            )
            return
        latest = points[-1]
        self.history_selection_title.configure(
            text=(
                f"Match: {latest['match']}\n"
                f"Outcome: {latest['selection']}   •   Bookmaker: {latest['bookmaker']}"
            )
        )
        left, right, top, bottom = 72, width - 22, 24, height - 55
        values = [point["odds"] for point in points]
        low, high = min(values), max(values)
        padding = max((high - low) * 0.15, 0.05)
        low, high = low - padding, high + padding
        canvas.create_line(left, top, left, bottom, fill="#777777")
        canvas.create_line(left, bottom, right, bottom, fill="#777777")
        canvas.create_text(
            18, (top + bottom) / 2, text="Decimal odds", fill="#aaaaaa", angle=90
        )
        canvas.create_text(
            (left + right) / 2, height - 12, text="Scan time", fill="#aaaaaa"
        )
        canvas.create_text(left - 8, top, text=f"{high:.2f}", fill="#aaaaaa", anchor="e")
        canvas.create_text(left - 8, bottom, text=f"{low:.2f}", fill="#aaaaaa", anchor="e")
        coordinates = []
        for index, point in enumerate(points):
            x = left if len(points) == 1 else left + index * (right - left) / (len(points) - 1)
            y = bottom - (point["odds"] - low) * (bottom - top) / (high - low)
            coordinates.extend((x, y))
        if len(points) > 1:
            difference = values[-1] - values[0]
            line_color = "#62d48b" if difference > 0 else "#ef8585" if difference < 0 else "#aaaaaa"
            canvas.create_line(*coordinates, fill=line_color, width=3, smooth=True)
        else:
            line_color = "#77c4ff"
        for index in range(0, len(coordinates), 2):
            canvas.create_oval(
                coordinates[index] - 4, coordinates[index + 1] - 4,
                coordinates[index] + 4, coordinates[index + 1] + 4,
                fill=line_color, outline="",
            )
        canvas.create_text(
            left, bottom + 18,
            text=points[0]["timestamp"].strftime("%d %b %H:%M:%S"),
            fill="#aaaaaa", anchor="w",
        )
        canvas.create_text(
            right, bottom + 18,
            text=points[-1]["timestamp"].strftime("%d %b %H:%M:%S"),
            fill="#aaaaaa", anchor="e",
        )
        if len(points) == 1:
            status = (
                f"Baseline recorded at {values[0]:.2f}. Scan this competition again "
                "to see whether the odds rise or fall."
            )
        else:
            difference = values[-1] - values[0]
            percent = (difference / values[0]) * 100
            direction = "increased" if difference > 0 else "decreased" if difference < 0 else "did not change"
            status = (
                f"Across {len(points)} scans, odds {direction} from {values[0]:.2f} "
                f"to {values[-1]:.2f} ({difference:+.2f}, {percent:+.1f}%)."
            )
        self.history_status.configure(text=status)

    def create_export_path(self, prefix):
        """Return a timestamped path inside the project's exports directory."""
        self.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self.EXPORT_DIR / f"{prefix}_{timestamp}.csv"

    def display_export_path(self, path):
        try:
            return str(path.relative_to(self.EXPORT_DIR.parent))
        except ValueError:
            return str(path)

    @staticmethod
    def write_csv(path, fieldnames, rows):
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_results_csv(self):
        if self.latest_results_df is None or self.latest_results_df.empty:
            self.write_to_terminal("[-] No scan results are available to export.")
            return
        rows = []
        for _, row in self.latest_results_df.iterrows():
            event_key = str(row['event_id']) if pd.notna(row['event_id']) else (
                f"{row['home_team']}|{row['away_team']}"
            )
            for column, selection in (
                ('home_odds', row['home_team']), ('draw_odds', 'Draw'),
                ('away_odds', row['away_team']),
            ):
                if pd.isna(row.get(column)):
                    continue
                identity = (event_key, str(row['bookmaker']), column)
                movement = self.odds_movements.get(identity)
                rows.append({
                    "event_id": row['event_id'], "home_team": row['home_team'],
                    "away_team": row['away_team'], "commence_time": row.get('commence_time'),
                    "country": row.get('country'), "stadium": row.get('stadium'),
                    "bookmaker": row['bookmaker'], "selection": selection,
                    "odds": row[column], "movement": movement,
                })
        try:
            path = self.create_export_path("scan_results")
            self.write_csv(path, list(rows[0]), rows)
            location = self.display_export_path(path)
            self.results_export_status.configure(text=f"Saved current scan to {location}")
            self.write_to_terminal(f"[+] Results exported to {path}")
        except OSError as exc:
            self.results_export_status.configure(text=f"Results export failed: {exc}")
            self.write_to_terminal(f"[!] Results export failed: {exc}")

    def export_history_csv(self):
        rows = []
        for identity, points in self.odds_history.items():
            for point in points:
                rows.append({
                    "event_id": identity[0], "bookmaker": point['bookmaker'],
                    "selection": point['selection'], "match": point['match'],
                    "timestamp_jerusalem": point['timestamp'].isoformat(),
                    "odds": point['odds'],
                })
        if not rows:
            self.history_status.configure(text="No history is available to export.")
            return
        try:
            path = self.create_export_path("odds_history")
            self.write_csv(path, list(rows[0]), rows)
            self.history_status.configure(
                text=f"Saved all session history to {self.display_export_path(path)}"
            )
        except OSError as exc:
            self.history_status.configure(text=f"History export failed: {exc}")

    def export_gamble_slip_csv(self):
        if not self.selected_bets:
            self.saved_slip_status.configure(text="No Gamble-slip selections to export.")
            return
        rows = [
            {
                "event_id": event_key, "match": bet['match'],
                "selection": bet['selection'], "bookmaker": bet['bookmaker'],
                "odds": bet['odds'], "stake": self.stake_entry.get().strip(),
            }
            for event_key, bet in self.selected_bets.items()
        ]
        try:
            path = self.create_export_path("gamble_slip")
            self.write_csv(path, list(rows[0]), rows)
            self.saved_slip_status.configure(
                text=f"Saved current slip to {self.display_export_path(path)}"
            )
        except OSError as exc:
            self.saved_slip_status.configure(text=f"Slip export failed: {exc}")
