#!/usr/bin/env python3
"""
Configuration module for OSINT Kanban Pipeline.
Loads environment variables and provides centralized configuration access.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the script directory (absolute path)
_env_path = Path(__file__).parent / '.env'
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


class Config:
    """Main configuration class for API keys and settings"""
    
    # Search Engine APIs
    SERPER_KEY = os.getenv("SERPER_API_KEY")
    SCRAPEANT_API_KEY = os.getenv("SCRAPEANT_API_KEY")
    
    # Social Media APIs (Optional)
    TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    LINKEDIN_OAUTH_TOKEN = os.getenv("LINKEDIN_OAUTH_TOKEN")
    
    # OSINT/Breach APIs
    LEAK_LOOKUP_API_KEY = os.getenv("LEAK_LOOKUP_API_KEY")
    SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")
    
    # Pipeline Settings
    MAX_CONCURRENT_SEARCHES = int(os.getenv("MAX_CONCURRENT_SEARCHES", "5"))
    MAX_RETRIES_PER_TICKET = int(os.getenv("MAX_RETRIES_PER_TICKET", "5"))
    CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
    RECOVERY_TIME_AFTER_FAILURE = float(os.getenv("RECOVERY_TIME_AFTER_FAILURE", "60"))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "./logs/pipeline.log")


class DatabaseConfig:
    """Database configuration settings"""
    
    DB_PATH = os.getenv("OSINT_DB_PATH", "osint.db")
    CONNECTION_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    CONNECTION_TIMEOUT = float(os.getenv("DB_CONNECTION_TIMEOUT", "30.0"))


class ReportConfig:
    """Report generation configuration"""
    
    PDF_WATERMARK_TEXT = os.getenv("PDF_WATERMARK_TEXT", "CONFIDENTIAL")
    DEFAULT_REPORT_TITLE = os.getenv("DEFAULT_REPORT_TITLE", "MythWorx OSINT Intelligence Report")
    REPORT_CLASSIFICATION = os.getenv("REPORT_CLASSIFICATION", "INTERNAL_USE_ONLY")


# Export all config classes for easy importing
__all__ = ['Config', 'DatabaseConfig', 'ReportConfig']
