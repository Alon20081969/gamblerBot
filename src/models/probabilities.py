import pandas as pd

class MarketAnalyzer:
    @staticmethod
    def flatten_odds_data(raw_event_data):
        """Converts raw nested JSON into a flat list of records, handling both 2-way and 3-way markets."""
        flat_records = []
        
        home_team = raw_event_data.get('home_team')
        away_team = raw_event_data.get('away_team')
        event_id = raw_event_data.get('id')
        
        for bookmaker in raw_event_data.get('bookmakers', []):
            bookie_name = bookmaker.get('title')
            
            for market in bookmaker.get('markets', []):
                if market.get('key') == 'h2h':
                    home_odds = None
                    away_odds = None
                    draw_odds = None
                    
                    # Track outcomes dynamically
                    for outcome in market.get('outcomes', []):
                        name = outcome.get('name')
                        price = outcome.get('price')
                        
                        if name == home_team:
                            home_odds = price
                        elif name == away_team:
                            away_odds = price
                        elif name.lower() == 'draw':
                            draw_odds = price
                    
                    if home_odds and away_odds:
                        # Compute market margin (juice/vig) dynamically
                        if draw_odds:
                            # 3-Way Market Formula (Soccer)
                            implied_margin = (1 / home_odds) + (1 / away_odds) + (1 / draw_odds)
                        else:
                            # 2-Way Market Formula (Baseball/Basketball)
                            implied_margin = (1 / home_odds) + (1 / away_odds)
                        
                        flat_records.append({
                            'event_id': event_id,
                            'home_team': home_team,
                            'away_team': away_team,
                            'bookmaker': bookie_name,
                            'home_odds': home_odds,
                            'away_odds': away_odds,
                            'draw_odds': draw_odds if draw_odds else None, # Keeps track of the draw if it exists
                            'margin_pct': round((implied_margin - 1) * 100, 2)
                        })
                        
        return pd.DataFrame(flat_records)

    @staticmethod
    def find_discrepancies(df):
        """Analyzes a flattened DataFrame using a robust Median baseline to prevent outlier skewing."""
        # Unused here, but kept for console compatibility
        pass