# 
import json
from pathlib import Path

def load_json(path: str) -> dict:
    try:
        with open(Path(path).expanduser(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"⚠️ Failed to load state from {path}: {e}")
        return {}

def save_json(path: str, data: dict):
    try:
        with open(Path(path).expanduser(), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to write state to {path}: {e}")
