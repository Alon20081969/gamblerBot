import requests
import pandas as pd
from src.config import Config

class OddsAPIClient:
    def __init__(self):
        self.api_key = Config.ODDS_API_KEY
        self.base_url = "https://api.the-odds-api.com/v4/sports"
        self.usage = {"remaining": None, "used": None, "last": None}

    def _update_usage(self, response):
        """Capture request-credit information returned by The Odds API."""
        self.usage = {
            "remaining": response.headers.get("x-requests-remaining"),
            "used": response.headers.get("x-requests-used"),
            "last": response.headers.get("x-requests-last"),
        }

    def get_available_sports(self, include_inactive=True):
        """Return the provider's competition catalog.

        ``include_inactive`` keeps off-season competitions (for example the FIFA
        World Cup) visible in the UI even when they currently have no fixtures.
        """
        if not self.api_key:
            return []

        params = {'apiKey': self.api_key}
        if include_inactive:
            params['all'] = 'true'

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            self._update_usage(response)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"[!] Could not load competition catalog: {exc}")
            return []

    def get_upcoming_matches(self, sport="soccer_uefa_european_championship", region="eu", market="h2h"):
        """Fetches live head-to-head odds for a specified sport and region."""
        if not self.api_key:
            print("[!] Cannot fetch data: API key is missing.")
            return None
            
        url = f"{self.base_url}/{sport}/odds/"
        params = {
            'apiKey': self.api_key,
            'regions': region,
            'markets': market,
            'oddsFormat': 'decimal'
        }
        
        try:
            print(f"[*] Requesting live lines for sport: {sport}...")
            response = requests.get(url, params=params, timeout=20)
            self._update_usage(response)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[!] API Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"[!] Connection failed: {e}")
            return None

if __name__ == "__main__":
    # Test our fetcher with an active sport market like MLB
    client = OddsAPIClient()
    
    # We change the sport parameter here to target active lines
    raw_data = client.get_upcoming_matches(sport="baseball_mlb", region="us", market="h2h")
    
    if raw_data is not None:
        print(f"[+] Successfully pulled data for {len(raw_data)} upcoming events!")
        if len(raw_data) > 0:
            first_match = raw_data[0]
            print(f"Sample Event: {first_match.get('home_team')} vs {first_match.get('away_team')}")
            print(f"Raw data structure of first event:\n{first_match}")
        else:
            print("[-] Connected successfully, but the market returned 0 active games. Try changing the sport string!")
