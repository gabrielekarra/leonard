"""Configuration settings for Leonard Core."""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
INDEX_DIR = DATA_DIR / "index"

# Server
HOST = "127.0.0.1"
PORT = 7878

# API
API_PREFIX = "/api"
API_VERSION = "0.1.0"
