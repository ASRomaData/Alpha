"""
ASRomaData Bot — Data Fetching (FIXED Version)
=================================
Architettura a due fonti:

1. SOFASCORE  — Match data (Fix: curl_cffi impersonate per evitare 403)
2. FOOTBALL-DATA.CO.UK  — Serie A historical data

Nota: Richiede 'curl_cffi' installato (pip install curl_cffi)
"""

import csv
import io
import logging
import time
import random
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

# Gestione robusta import curl_cffi
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

ROMA_ID  = 2702
_SS_BASE = "https://api.sofascore.com/api/v1"

# Headers per SofaScore
HEADERS_SS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

# ──────────────────────────────────────────────────────────────────────────────
# SOFASCORE — base request
# ──────────────────────────────────────────────────────────────────────────────

def _ss_get(path: str, retries: int = 5, delay: float = 3.0) -> Optional[Dict]:
    url = f"{_SS_BASE}{path}"
    
    for attempt in range(retries):
        try:
            if CURL_AVAILABLE:
                # Usa impersonate per bypassare i blocchi come in bot.py
                r = curl_requests.get(url, headers=HEADERS_SS, impersonate="chrome110", timeout=20)
            else:
                r = requests.get(url, headers=HEADERS_SS, timeout=20)
            
            if r.status_code == 200:
                time.sleep(random.uniform(0.5, 1.5))
                return r.json()

            if r.status_code in (403, 429):
                wait = (delay * (2 ** attempt)) + random.uniform(2, 5)
                logger.warning(f"SofaScore Error {r.status_code} — Tentativo {attempt+1}. Attendo {wait:.1f}s...")
                time.sleep(wait)
                continue
                
            if r.status_code == 404:
                return None
                
            r.raise_for_status()
            
        except Exception as e:
            logger.warning(f"SofaScore {path} attempt {attempt+1}: {e}")
            time.sleep(delay * 2)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# PARTITE
# ──────────────────────────────────────────────────────────────────────────────

def get_last_match(team_id: int = ROMA_ID) -> Optional[Dict]:
    data = _ss_get(f"/team/{team_id}/events/last/0")
    if data:
        events = data.get("events", [])
        return events[-1] if events else None
    return None

def get_next_match(team_id: int = ROMA_ID) -> Optional[Dict]:
    data = _ss_get(f"/team/{team_id}/events/next/0")
    if data:
        events = data.get("events", [])
        return events[0] if events else None
    return None

def get_recent_matches(team_id: int = ROMA_ID, page: int = 0) -> List[Dict]:
    data = _ss_get(f"/team/{team_id}/events/last/{page}")
    return data.get("events", []) if data else []

def parse_event(event: Dict) -> Dict:
    home_id    = event.get("homeTeam", {}).get("id")
    away_id    = event.get("awayTeam", {}).get("id")
    home_score = event.get("homeScore", {}).get("current", 0)
    away_score = event.get("awayScore", {}).get("current", 0)
    is_home    = home_id == ROMA_ID
    start_ts   = event.get("startTimestamp", 0)
    return {
        "match_id":    event.get("id"),
        "home_team":   event.get("homeTeam", {}).get("name", ""),
        "away_team":   event.get("awayTeam", {}).get("name", ""),
        "home_score":  home_score,
        "away_score":  away_score,
        "roma_score":  home_score if is_home else away_score,
        "opp_score":   away_score if is_home else home_score,
        "opponent":    event.get("awayTeam", {}).get("name", "") if is_home else event.get("homeTeam", {}).get("name", ""),
        "opponent_id": away_id if is_home else home_id,
        "is_home":     is_home,
        "competition": event.get("tournament", {}).get("name", ""),
        "tournament_id": event.get("tournament", {}).get("id"),
        "season_id":   event.get("season", {}).get("id"),
        "round":       event.get("roundInfo", {}).get("round", ""),
        "date":        datetime.utcfromtimestamp(start_ts).strftime("%d/%m/%Y") if start_ts else "",
        "start_ts":    start_ts,
        "status":      event.get("status", {}).get("type", ""),
        "venue":       (event.get("venue") or {}).get("name", ""),
    }

# ──────────────────────────────────────────────────────────────────────────────
# STATISTICHE
# ──────────────────────────────────────────────────────────────────────────────

def get_match_statistics(match_id: int) -> Optional[Dict]:
    return _ss_get(f"/event/{match_id}/statistics")

_STAT_MAP = {
    "Ball possession":           ("possession_roma",       "possession_opp"),
    "Total shots":               ("shots_roma",            "shots_opp"),
    "Shots on target":           ("shots_on_target_roma",  "shots_on_target_opp"),
    "Passes":                    ("passes_roma",           "passes_opp"),
    "Corner kicks":              ("corners_roma",          "corners_opp"),
    "Fouls":                     ("fouls_roma",            "fouls_opp"),
    "Yellow cards":              ("yellow_roma",           "yellow_opp"),
    "Red cards":                 ("red_roma",              "red_opp"),
    "Expected goals":            ("xg_roma",               "xg_opp"),
}

def parse_match_statistics(raw: Dict, is_home_roma: bool) -> Dict:
    result = {k: 0 for pair in _STAT_MAP.values() for k in pair}
    for period in raw.get("statistics", []):
        if period.get("period") != "ALL":
            continue
        for group in period.get("groups", []):          # ← add this level
            for item in group.get("statisticsItems", []):
                name = item.get("name", "")
                if name in _STAT_MAP:
                    r_key, o_key = _STAT_MAP[name]
                    h_val = float(str(item.get("homeValue", "0")).replace("%", ""))
                    a_val = float(str(item.get("awayValue", "0")).replace("%", ""))
                    result[r_key] = h_val if is_home_roma else a_val
                    result[o_key] = a_val if is_home_roma else h_val
    return result

# ──────────────────────────────────────────────────────────────────────────────
# SHOT MAP & RATINGS
# ──────────────────────────────────────────────────────────────────────────────

def get_shot_map(match_id: int) -> Optional[List[Dict]]:
    data = _ss_get(f"/event/{match_id}/shotmap")
    return data.get("shotmap", []) if data else None

def get_player_ratings(match_id: int) -> Optional[List[Dict]]:
    data = _ss_get(f"/event/{match_id}/lineups")
    if not data: return None
    players = []
    for side in ("home", "away"):
        for p in data.get(side, {}).get("players", []):
            stats = p.get("statistics", {})
            if not stats.get("rating"): continue
            players.append({
                "name": p["player"]["name"],
                "rating": float(stats["rating"]),
                "side": side
            })
    return sorted(players, key=lambda x: x["rating"], reverse=True)

# ──────────────────────────────────────────────────────────────────────────────
# STORICO SERIE A (Usa requests standard)
# ──────────────────────────────────────────────────────────────────────────────

def download_season_csv(season_code: str) -> Optional[List[Dict]]:
    import requests as r_std
    url = f"https://www.football-data.co.uk/mmz4281/{season_code}/I1.csv"
    try:
        res = r_std.get(url, timeout=15)
        if res.status_code != 200: return None
        reader = csv.DictReader(io.StringIO(res.text))
        return list(reader)
    except: return None

def build_full_history(start_year: int = 2000, team: str = "Roma") -> List[Dict]:
    history = []
    # Logica per scaricare anni passati...
    return history

# Alias per compatibilità
fd_build_history = build_full_history
fd_download_season = download_season_csv
