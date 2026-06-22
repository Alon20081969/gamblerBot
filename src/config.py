import os
from pathlib import Path
from dotenv import load_dotenv

# Define the root folder of your project (gamblerBot/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from your hidden .env file
load_dotenv(BASE_DIR / '.env')

class Config:
    # Read the API key from the environment variables
    ODDS_API_KEY = os.getenv('ODDS_API_KEY')
    
    # Establish centralized directories for logging and saving data
    DATA_DIR = BASE_DIR / 'data'
    LOGS_DIR = BASE_DIR / 'logs'
    
    # Universal strategy configurations
    MIN_VALUE_THRESHOLD = 1.05  # Look for a minimum 5% statistical advantage
    
    @classmethod
    def validate_config(cls):
        """Ensures the project won't run without essential keys."""
        if not cls.ODDS_API_KEY:
            print("[!] WARNING: ODDS_API_KEY is missing from your .env file!")
            return False
        return True

if __name__ == "__main__":
    # Test file execution to ensure paths map out correctly
    print(f"Project Base Directory: {BASE_DIR}")
    print(f"Checking configuration validation...")
    Config.validate_config()