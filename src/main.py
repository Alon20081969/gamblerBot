import pandas as pd
from src.ingestion.api_client import OddsAPIClient
from src.models.probabilities import MarketAnalyzer

def run_pipeline():
    print("==================================================")
    print("      LAUNCHING LIVE MARKET SCANNER CORE          ")
    print("==================================================\n")
    
    # Initialize the data engine
    client = OddsAPIClient()
    
    # Pull fresh live lines from active MLB markets
    raw_events = client.get_upcoming_matches(sport="baseball_mlb", region="us", market="h2h")
    
    if not raw_events:
        print("[-] Market scanning halted: No live events returned.")
        return

    print(f"\n[*] Ingested {len(raw_events)} live events. Parsing options...")
    
    all_market_dfs = []
    
    # Process each match payload independently
    for event in raw_events:
        event_df = MarketAnalyzer.flatten_odds_data(event)
        if not event_df.empty:
            all_market_dfs.append(event_df)
            
    if all_market_dfs:
        # Stitch all game dataframes together into one giant master spreadsheet
        master_df = pd.concat(all_market_dfs, ignore_index=True)
        
        # Display sample overview metrics of the current boards
        print(f"[+] Operational data matrix compiled successfully ({len(master_df)} odds rows).")
        
        # Unleash the mathematical anomaly detector across all live games
        MarketAnalyzer.find_discrepancies(master_df)
    else:
        print("[-] Failed to construct active data matrices.")

if __name__ == "__main__":
    run_pipeline()