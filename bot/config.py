"""ASRomaData Bot — Configurazione centralizzata."""
import os

ROMA_ID         = 2702          # AS Roma su SofaScore
SERIE_A_TOURN   = 23            # Serie A tournament_id su SofaScore

# Social
IG_USER_ID        = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN   = os.getenv("IG_ACCESS_TOKEN", "")
X_API_KEY         = os.getenv("X_API_KEY", "")
X_API_SECRET      = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN    = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET   = os.getenv("X_ACCESS_SECRET", "")
X_BEARER_TOKEN    = os.getenv("X_BEARER_TOKEN", "")
BSKY_HANDLE       = os.getenv("BSKY_HANDLE", "")
BSKY_PASSWORD     = os.getenv("BSKY_PASSWORD", "")
THREADS_ENABLED   = os.getenv("THREADS_ENABLED", "false").lower() == "true"
THREADS_USER_ID   = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", ""))
THREADS_TOKEN     = os.getenv("THREADS_ACCESS_TOKEN", os.getenv("IG_ACCESS_TOKEN", ""))

# AI
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"
GROQ_MODEL_FAST = "llama-3.1-8b-instant"

# Paths
DATA_DIR        = "data"
VISUALS_DIR     = "visuals"
HISTORY_FILE    = f"{DATA_DIR}/history.json"
LAST_MATCH_FILE = f"{DATA_DIR}/last_match.json"

# Match window (minuti)
WINDOW_BEFORE   = 60
WINDOW_AFTER    = 180
