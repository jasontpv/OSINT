import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    SCRAPEANT_API_KEY = os.getenv("SCRAPINGANT_API_KEY")
    LEAKLOOKUP_API_KEY = os.getenv("LEAKLOOKUP_API_KEY")

class DatabaseConfig:
    DB_PATH = "osint.db"
