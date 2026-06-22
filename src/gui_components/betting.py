import json
import re
import tkinter as tk

import customtkinter as ctk


class BettingMixin:
    """Gamble slip, custom odds, and standalone calculator behavior."""

    def build_betting_tabs(self):
        self.gamble_tab.grid_rowconfigure(2, weight=1)
        self.gamble_tab.grid_columnconfigure(0, weight=1)
        slip_header = ctk.CTkFrame(self.gamble_tab, fg_color="transparent")
        slip_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        self.slip_title = ctk.CTkLabel(
            slip_header, text="Gamble slip", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.slip_title.pack(side="left")
        ctk.CTkButton(
            slip_header, text="Clear slip", command=self.clear_bet_slip,
            width=80, height=28, fg_color=("gray70", "gray28"),
            hover_color=("gray60", "gray35"),
        ).pack(side="right")
        ctk.CTkButton(
            slip_header, text="Export slip CSV", command=self.export_gamble_slip_csv,
            width=105, height=28,
        ).pack(side="right", padx=(0, 6))

        saved_controls = ctk.CTkFrame(self.gamble_tab, fg_color="transparent")
        saved_controls.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        saved_controls.grid_columnconfigure(0, weight=1)
        saved_controls.grid_columnconfigure(2, weight=1)
        self.slip_name_entry = ctk.CTkEntry(
            saved_controls, placeholder_text="Name this slip..."
        )
        self.slip_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.slip_name_entry.bind("<Return>", lambda _event: self.save_named_slip())
        ctk.CTkButton(
            saved_controls, text="Save", command=self.save_named_slip, width=58
        ).grid(row=0, column=1, padx=(0, 10))
        saved_names = sorted(self.saved_slips) or ["No saved slips"]
        self.saved_slips_dropdown = ctk.CTkComboBox(
            saved_controls, values=saved_names, state="readonly", width=145
        )
        self.saved_slips_dropdown.set(saved_names[0])
        self.saved_slips_dropdown.grid(row=0, column=2, sticky="ew", padx=(0, 5))
        ctk.CTkButton(
            saved_controls, text="Load", command=self.load_named_slip, width=55
        ).grid(row=0, column=3, padx=(0, 5))
        ctk.CTkButton(
            saved_controls, text="Delete", command=self.delete_named_slip,
            width=58, fg_color=("#b65d5d", "#8f3333"),
            hover_color=("#9f4646", "#a94444"),
        ).grid(row=0, column=4)
        self.saved_slip_status = ctk.CTkLabel(
            saved_controls,
            text="Export slip CSV saves only the selections and stake currently in this slip.",
            anchor="w",
            text_color=("gray45", "gray65"), font=ctk.CTkFont(size=10),
        )
        self.saved_slip_status.grid(
            row=1, column=0, columnspan=5, sticky="ew", pady=(3, 0)
        )

        self.bet_slip_results = ctk.CTkScrollableFrame(
            self.gamble_tab, fg_color=("gray90", "gray14")
        )
        self.bet_slip_results.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self.bet_slip_results.grid_columnconfigure(0, weight=1)

        totals = ctk.CTkFrame(self.gamble_tab)
        totals.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 4))
        totals.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(totals, text="Stake amount:").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 5)
        )
        self.stake_entry = ctk.CTkEntry(totals, placeholder_text="0.00")
        self.stake_entry.grid(row=0, column=1, sticky="ew", padx=(5, 12), pady=(10, 5))
        self.stake_entry.bind("<KeyRelease>", lambda _event: self.update_bet_totals())
        self.combined_odds_label = ctk.CTkLabel(totals, text="Combined odds: —", anchor="w")
        self.return_label = ctk.CTkLabel(totals, text="Potential return: 0.00", anchor="w")
        self.profit_label = ctk.CTkLabel(totals, text="Estimated profit: 0.00", anchor="w")
        self.combined_odds_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=2)
        self.return_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=2)
        self.profit_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=2)
        ctk.CTkLabel(
            totals, text="Estimates use decimal odds. This does not place a real bet.",
            text_color=("gray45", "gray65"), font=ctk.CTkFont(size=10),
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(3, 10))
        self.render_bet_slip()
        self._build_calculator_tab()

    def load_saved_slips(self):
        """Load and validate named Gamble slips from local storage."""
        try:
            data = json.loads(self.SAVED_SLIPS_FILE.read_text(encoding="utf-8"))
            raw_slips = data.get("slips", {}) if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}

        slips = {}
        for name, payload in raw_slips.items():
            if not isinstance(name, str) or not isinstance(payload, dict):
                continue
            valid_bets = []
            for bet in payload.get("bets", []):
                if (
                    not isinstance(bet, dict)
                    or not isinstance(bet.get("identity"), list)
                    or len(bet["identity"]) != 3
                ):
                    continue
                try:
                    odds = float(bet["odds"])
                    if odds <= 1.0:
                        continue
                    valid_bets.append({
                        "identity": tuple(str(part) for part in bet["identity"]),
                        "match": str(bet["match"]),
                        "selection": str(bet["selection"]),
                        "bookmaker": str(bet["bookmaker"]),
                        "odds": odds,
                    })
                except (KeyError, TypeError, ValueError):
                    continue
            if valid_bets:
                slips[name] = {
                    "stake": str(payload.get("stake", "")),
                    "bets": valid_bets,
                }
        return slips

    def persist_saved_slips(self):
        payload = {
            "slips": {
                name: {
                    "stake": slip.get("stake", ""),
                    "bets": [
                        {**bet, "identity": list(bet["identity"])}
                        for bet in slip.get("bets", [])
                    ],
                }
                for name, slip in sorted(self.saved_slips.items())
            }
        }
        try:
            self.SAVED_SLIPS_FILE.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            self.write_to_terminal(f"[!] Could not save Gamble slips: {exc}")
            return False

    def refresh_saved_slips_dropdown(self, selected_name=None):
        names = sorted(self.saved_slips) or ["No saved slips"]
        self.saved_slips_dropdown.configure(values=names)
        self.saved_slips_dropdown.set(
            selected_name if selected_name in self.saved_slips else names[0]
        )

    def save_named_slip(self):
        name = self.slip_name_entry.get().strip()
        if not name:
            self.saved_slip_status.configure(text="Enter a name for the slip.")
            return
        if not self.selected_bets:
            self.saved_slip_status.configure(text="Add at least one selection before saving.")
            return
        bets = [
            {**bet, "identity": tuple(bet["identity"])}
            for bet in self.selected_bets.values()
        ]
        existed = name in self.saved_slips
        self.saved_slips[name] = {"stake": self.stake_entry.get().strip(), "bets": bets}
        if self.persist_saved_slips():
            self.refresh_saved_slips_dropdown(name)
            self.saved_slip_status.configure(
                text=f"{'Updated' if existed else 'Saved'}: {name}"
            )

    def load_named_slip(self):
        name = self.saved_slips_dropdown.get()
        slip = self.saved_slips.get(name)
        if not slip:
            self.saved_slip_status.configure(text="Choose a saved slip to load.")
            return
        restored = {}
        for bet in slip["bets"]:
            copied = {**bet, "identity": tuple(bet["identity"]), "odds": float(bet["odds"])}
            restored[copied["identity"][0]] = copied
        self.selected_bets = restored
        self.stake_entry.delete(0, tk.END)
        if slip.get("stake"):
            self.stake_entry.insert(0, slip["stake"])
        self.update_odds_button_styles()
        for event_key in list(self.custom_odd_controls):
            bet = self.selected_bets.get(event_key)
            self.set_custom_odd_status(
                event_key, bool(bet and bet.get("bookmaker") == "Custom odd")
            )
        self.render_bet_slip()
        self.saved_slip_status.configure(text=f"Loaded: {name}")

    def delete_named_slip(self):
        name = self.saved_slips_dropdown.get()
        if name not in self.saved_slips:
            self.saved_slip_status.configure(text="Choose a saved slip to delete.")
            return
        del self.saved_slips[name]
        if self.persist_saved_slips():
            self.refresh_saved_slips_dropdown()
            self.saved_slip_status.configure(text=f"Deleted: {name}")

    def _build_calculator_tab(self):
        self.calculator_tab.grid_columnconfigure(0, weight=1)
        calculator = ctk.CTkFrame(self.calculator_tab)
        calculator.grid(row=0, column=0, sticky="new", padx=18, pady=18)
        calculator.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            calculator, text="Decimal odds calculator",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 12))
        ctk.CTkLabel(calculator, text="Odds:").grid(row=1, column=0, sticky="w", padx=16, pady=6)
        self.calculator_odds_entry = ctk.CTkEntry(
            calculator, placeholder_text="Example: 1.80, 2.10, 1.55"
        )
        self.calculator_odds_entry.grid(row=1, column=1, sticky="ew", padx=(6, 16), pady=6)
        ctk.CTkLabel(calculator, text="Stake:").grid(row=2, column=0, sticky="w", padx=16, pady=6)
        self.calculator_stake_entry = ctk.CTkEntry(calculator, placeholder_text="100")
        self.calculator_stake_entry.grid(row=2, column=1, sticky="ew", padx=(6, 16), pady=6)
        self.calculator_combined_label = ctk.CTkLabel(calculator, text="Combined odds: —", anchor="w")
        self.calculator_return_label = ctk.CTkLabel(calculator, text="Potential return: 0.00", anchor="w")
        self.calculator_profit_label = ctk.CTkLabel(calculator, text="Estimated profit: 0.00", anchor="w")
        self.calculator_combined_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 3))
        self.calculator_return_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=3)
        self.calculator_profit_label.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(3, 16))
        self.calculator_odds_entry.bind("<KeyRelease>", self.update_odds_calculator)
        self.calculator_stake_entry.bind("<KeyRelease>", self.update_odds_calculator)

    def build_custom_odd_controls(self, card, event_key, home, away, has_draw):
        frame = ctk.CTkFrame(card, fg_color=("gray88", "gray19"))
        frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 9))
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text="Custom odd:", font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=0, column=0, padx=(10, 5), pady=8
        )
        options = [f"Home — {home}"] + (["Draw"] if has_draw else []) + [f"Away — {away}"]
        selection = ctk.CTkComboBox(frame, values=options, state="readonly", width=170)
        selection.set(options[0])
        selection.grid(row=0, column=1, sticky="ew", padx=5, pady=8)
        odds_entry = ctk.CTkEntry(frame, placeholder_text="Decimal odd", width=95)
        odds_entry.grid(row=0, column=2, padx=5, pady=8)
        feedback = ctk.CTkLabel(frame, text="", width=18, text_color=("#a13a3a", "#ef8585"))
        feedback.grid(row=0, column=4, padx=(3, 8), pady=8)
        ctk.CTkButton(
            frame, text="Add to slip", width=82,
            command=lambda: self.add_custom_odd(
                event_key, home, away, selection.get(), odds_entry.get(), feedback
            ),
        ).grid(row=0, column=3, padx=5, pady=8)
        self.custom_odd_controls[event_key] = {
            "feedback": feedback, "entry": odds_entry, "selection": selection
        }
        existing = self.selected_bets.get(event_key)
        if existing and existing.get("bookmaker") == "Custom odd":
            if existing["selection"] in options:
                selection.set(existing["selection"])
            odds_entry.insert(0, f"{existing['odds']:g}")
            self.set_custom_odd_status(event_key, True)

    def add_custom_odd(self, event_key, home, away, selection, odds_text, feedback):
        try:
            odds = float(odds_text.strip())
            if odds <= 1.0:
                raise ValueError
        except (ValueError, AttributeError):
            feedback.configure(text="Enter an odd above 1.00")
            return
        identity = (event_key, "Custom odd", f"{selection}:{odds:.8g}")
        self.selected_bets[event_key] = {
            "identity": identity, "match": f"{home} vs {away}",
            "selection": selection, "bookmaker": "Custom odd", "odds": odds,
        }
        self.update_odds_button_styles(event_key)
        self.render_bet_slip()
        self.set_custom_odd_status(event_key, True)

    def set_custom_odd_status(self, event_key, added):
        controls = self.custom_odd_controls.get(event_key)
        if not controls:
            return
        try:
            controls["feedback"].configure(
                text="Added ✓" if added else "",
                text_color=("#147a3d", "#62d48b") if added else ("gray40", "gray65"),
            )
        except tk.TclError:
            self.custom_odd_controls.pop(event_key, None)

    @staticmethod
    def parse_decimal_odds(odds_text):
        tokens = [token for token in re.split(r"[,;\s]+", odds_text.strip()) if token]
        if not tokens:
            return []
        odds = [float(token) for token in tokens]
        if any(value <= 1.0 for value in odds):
            raise ValueError("Decimal odds must be above 1.00")
        return odds

    def update_odds_calculator(self, _event=None):
        try:
            values = self.parse_decimal_odds(self.calculator_odds_entry.get())
            stake_text = self.calculator_stake_entry.get().strip()
            stake = float(stake_text) if stake_text else 0.0
            if stake < 0:
                raise ValueError
        except ValueError:
            self.calculator_combined_label.configure(text="Combined odds: enter valid decimal odds above 1.00")
            self.calculator_return_label.configure(text="Potential return: —")
            self.calculator_profit_label.configure(text="Estimated profit: —")
            return
        if not values:
            self.calculator_combined_label.configure(text="Combined odds: —")
            self.calculator_return_label.configure(text="Potential return: 0.00")
            self.calculator_profit_label.configure(text="Estimated profit: 0.00")
            return
        combined = 1.0
        for odds in values:
            combined *= odds
        self.calculator_combined_label.configure(text=f"Combined odds: {combined:.2f}")
        self.calculator_return_label.configure(text=f"Potential return: {stake * combined:,.2f}")
        self.calculator_profit_label.configure(text=f"Estimated profit: {stake * (combined - 1):,.2f}")

    def create_selectable_odd(self, parent, text, event_key, match, selection,
                              bookmaker, odds, odds_column):
        identity = (event_key, bookmaker, odds_column)
        movement = self.odds_movements.get(identity)
        if movement is not None and movement > 0:
            display_text = f"{text}  ↑ +{movement:.2f}"
        elif movement is not None and movement < 0:
            display_text = f"{text}  ↓ {movement:.2f}"
        else:
            display_text = text
        button = ctk.CTkButton(
            parent, text=display_text, anchor="center", height=28, border_width=1,
            corner_radius=6, fg_color="transparent", hover_color="#287fd1",
            border_color=("gray65", "gray35"), text_color=("gray10", "gray92"),
            command=lambda: self.toggle_bet(
                identity, event_key, match, selection, bookmaker, odds
            ),
        )
        self.odds_buttons.setdefault(identity, []).append((button, display_text, movement))
        self.update_odds_button_style(identity)
        return button

    def toggle_bet(self, identity, event_key, match, selection, bookmaker, odds):
        current = self.selected_bets.get(event_key)
        if current and current["identity"] == identity:
            del self.selected_bets[event_key]
        else:
            self.selected_bets[event_key] = {
                "identity": identity, "match": match, "selection": selection,
                "bookmaker": bookmaker, "odds": odds,
            }
        self.set_custom_odd_status(event_key, False)
        self.update_odds_button_styles(event_key)
        self.render_bet_slip()

    def update_odds_button_style(self, identity):
        selected = any(bet["identity"] == identity for bet in self.selected_bets.values())
        for button, base_text, movement in self.odds_buttons.get(identity, []):
            try:
                if not button.winfo_exists():
                    continue
                button.configure(
                    text=f"✓  {base_text}" if selected else base_text,
                    fg_color="#1769aa" if selected else "transparent",
                    hover_color="#3b9cff" if selected else "#287fd1",
                    border_color="#77c4ff" if selected else ("gray65", "gray35"),
                    border_width=2 if selected else 1,
                    text_color=(
                        "white" if selected
                        else ("#147a3d", "#62d48b") if movement and movement > 0
                        else ("#a13a3a", "#ef8585") if movement and movement < 0
                        else ("gray10", "gray92")
                    ),
                )
            except tk.TclError:
                continue

    def update_odds_button_styles(self, event_key=None):
        for identity in self.odds_buttons:
            if event_key is None or identity[0] == event_key:
                self.update_odds_button_style(identity)

    def render_bet_slip(self):
        for widget in self.bet_slip_results.winfo_children():
            widget.destroy()
        count = len(self.selected_bets)
        self.slip_title.configure(text=f"Gamble slip  •  {count} selection{'s' if count != 1 else ''}")
        if not self.selected_bets:
            ctk.CTkLabel(
                self.bet_slip_results, text="Click any odds button to add a selection.",
                text_color=("gray40", "gray65"),
            ).grid(row=0, column=0, sticky="ew", padx=20, pady=30)
            self.update_bet_totals()
            return
        for row, (event_key, bet) in enumerate(self.selected_bets.items()):
            card = ctk.CTkFrame(self.bet_slip_results, corner_radius=8)
            card.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card, text=(f"{bet['match']}\nPick: {bet['selection']}  •  "
                            f"{bet['bookmaker']}  @  {bet['odds']:.2f}"),
                anchor="w", justify="left",
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=9)
            ctk.CTkButton(
                card, text="×", width=30, height=28, fg_color="transparent",
                hover_color=("#d98b8b", "#8f3333"),
                text_color=("#a13a3a", "#ef8585"),
                command=lambda key=event_key: self.remove_bet(key),
            ).grid(row=0, column=1, padx=(3, 8), pady=8)
        self.update_bet_totals()

    def remove_bet(self, event_key):
        if event_key in self.selected_bets:
            del self.selected_bets[event_key]
            self.set_custom_odd_status(event_key, False)
            self.update_odds_button_styles(event_key)
            self.render_bet_slip()

    def clear_bet_slip(self):
        self.selected_bets.clear()
        for event_key in list(self.custom_odd_controls):
            self.set_custom_odd_status(event_key, False)
        self.update_odds_button_styles()
        self.render_bet_slip()

    def update_bet_totals(self):
        if not self.selected_bets:
            self.combined_odds_label.configure(text="Combined odds: —")
            self.return_label.configure(text="Potential return: 0.00")
            self.profit_label.configure(text="Estimated profit: 0.00")
            return
        combined = 1.0
        for bet in self.selected_bets.values():
            combined *= bet["odds"]
        self.combined_odds_label.configure(text=f"Combined odds: {combined:.2f}")
        try:
            stake_text = self.stake_entry.get().strip()
            stake = float(stake_text) if stake_text else 0.0
            if stake < 0:
                raise ValueError
        except ValueError:
            self.return_label.configure(text="Potential return: enter a valid stake")
            self.profit_label.configure(text="Estimated profit: —")
            return
        self.return_label.configure(text=f"Potential return: {stake * combined:,.2f}")
        self.profit_label.configure(text=f"Estimated profit: {stake * (combined - 1):,.2f}")
