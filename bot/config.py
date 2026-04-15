"""
ASRomaData Bot — Configuration
Tutte le variabili di configurazione vengono lette da variabili d'ambiente (GitHub Secrets).
"""

import os

# ─────────────────────────────────────────────
# SQUADRA
# ─────────────────────────────────────────────
TEAM_NAME       = "Roma"
TEAM_ID_SOFASCORE = 2702          # AS Roma su SofaScore
TEAM_ID_UNDERSTAT = "Roma"        # Nome AS Roma su Understat (Serie A)
TEAM_FBREF_URL  = "https://fbref.com/en/squads/cf74a709/AS-Roma-Stats"
LEAGUE_FBREF    = "ITA"           # codice paese FBref
LEAGUE_UNDERSTAT = "Serie_A"      # nome lega Understat

# ─────────────────────────────────────────────
# SOCIAL — letti da environment
# ─────────────────────────────────────────────
# Instagram Graph API
IG_USER_ID      = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# X / Twitter (v2 API — Free tier supporta tweet creation)
X_API_KEY          = os.getenv("X_API_KEY", "")
X_API_SECRET       = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN     = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET    = os.getenv("X_ACCESS_SECRET", "")
X_BEARER_TOKEN     = os.getenv("X_BEARER_TOKEN", "")

# Bluesky (AT Protocol)
BSKY_HANDLE     = os.getenv("BSKY_HANDLE", "")
BSKY_PASSWORD   = os.getenv("BSKY_PASSWORD", "")

# Threads — usa stessa app Instagram se abilitato
THREADS_ENABLED = os.getenv("THREADS_ENABLED", "false").lower() == "true"

# ─────────────────────────────────────────────
# AI — Groq (gratuito, 14.400 req/day)
# ─────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"   # best quality gratuito
GROQ_MODEL_FAST = "llama-3.1-8b-instant"       # fallback rapido

# ─────────────────────────────────────────────
# GITHUB — per aggiornare dati storici nel repo
# ─────────────────────────────────────────────
GITHUB_TOKEN    = os.getenv("GH_TOKEN", "")
GITHUB_OWNER    = os.getenv("GH_OWNER", "")
GITHUB_REPO     = os.getenv("GH_REPO", "asromadata-history")  # repo storico dedicato

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
DATA_DIR        = "data"
HISTORY_FILE    = f"{DATA_DIR}/history.json"
LAST_MATCH_FILE = f"{DATA_DIR}/last_match.json"
VISUALS_DIR     = "visuals"

# ─────────────────────────────────────────────
# FINESTRA TEMPORALE BOT (minuti)
# ─────────────────────────────────────────────
WINDOW_BEFORE   = 60    # pubblica a partire da -60min dall'inizio
WINDOW_AFTER    = 180   # pubblica fino a +180min dall'inizio

# ─────────────────────────────────────────────
# TONO EDITORIALE (usato nei prompt AI)
# ─────────────────────────────────────────────
EDITORIAL_VOICE = """
Sei il redattore di @ASRomaData, account di football analytics dedicato all'AS Roma.
Stile: analitico, appassionato, conciso. Usi il gergo tecnico corretto (xG non "expected goals",
xGA, xPTS, PPDA). Non usi emoji eccessive. Citi sempre la fonte del dato.
Scrivi in italiano. Non usi frasi banali come "bella partita" o "grande prestazione".
Ogni testo deve avere almeno un dato statistico concreto che supporta l'analisi.
"""
