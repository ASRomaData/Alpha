"""
ASRomaData Bot — Data Fetching (FIXED Version)
=================================
Architettura a due fonti:

1. SOFASCORE  — tutto ciò che riguarda le partite
2. FOOTBALL-DATA.CO.UK  — serie storiche Serie A dal 2000

Fix: Migliorata gestione 403 tramite Session, Jitter e Modern Headers.
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

import requests

logger = logging.getLogger(__name__)

ROMA_ID  = 2702
_SS_BASE = "https://api.sofascore.com/api/v1"

# Inizializziamo una sessione per mantenere i cookie (aiuta a evitare i 403)
session = requests.Session()

def get_ss_headers():
    """Genera header dinamici per simulare un browser reale."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Cache-Control": "no-cache",
    }

# ──────────────────────────────────────────────────────────────────────────────
# SOFASCORE — base request
# ──────────────────────────────────────────────────────────────────────────────

def _ss_get(path: str, retries: int = 5, delay: float = 3.0) -> Optional[Dict]:
    url = f"{_SS_BASE}{path}"
    
    for attempt in range(retries):
        try:
            # Usiamo la sessione e aggiorniamo gli header ogni tentativo
            r = session.get(url, headers=get_ss_headers(), timeout=20)
            
            if r.status_code == 403:
                # Se riceviamo 403, aumentiamo drasticamente il tempo di attesa (backoff esponenziale)
                wait = (delay * (2 ** attempt)) + random.uniform(2, 5)
                logger.warning(f"SofaScore 403 Forbidden — Tentativo {attempt+1}. Attendo {wait:.1f}s...")
                time.sleep(wait)
                continue
                
            if r.status_code == 429:
                wait = (delay * 10) + random.uniform(5, 10)
                logger.warning(f"SofaScore 429 Too Many Requests — Attendo {wait:.1f}s")
                time.sleep(wait)
                continue
                
            if r.status_code == 404:
                return None
                
            r.raise_for_status()
            
            # Aggiungiamo un piccolo ritardo casuale dopo ogni successo per non sembrare un bot
            time.sleep(delay + random.uniform(0.5, 1.5))
            return r.json()
            
        except requests.RequestException as e:
            logger.warning(f"SofaScore {path} attempt {attempt+1}: {e}")
            if attempt < retries - 1:
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
# STATISTICHE PARTITA
# ──────────────────────────────────────────────────────────────────────────────

def get_match_statistics(match_id: int) -> Optional[Dict]:
    return _ss_get(f"/event/{match_id}/statistics")

_STAT_MAP = {
    "Ball possession":           ("possession_roma",       "possession_opp"),
    "Total shots":               ("shots_roma",            "shots_opp"),
    "Shots on target":           ("shots_on_target_roma",  "shots_on_target_opp"),
    "Passes":                    ("passes_roma",           "passes_opp"),
    "Accurate passes":           ("passes_roma",           "passes_opp"),
    "Corner kicks":              ("corners_roma",          "corners_opp"),
    "Fouls":                     ("fouls_roma",            "fouls_opp"),
    "Yellow cards":              ("yellow_roma",           "yellow_opp"),
    "Red cards":                 ("red_roma",              "red_opp"),
    "Expected goals":            ("xg_roma",               "xg_opp"),
    "Expected Goals":            ("xg_roma",               "xg_opp"),
    "xG":                        ("xg_roma",               "xg_opp"),
    "Expected Goals on Target":  ("xgot_roma",             "xgot_opp"),
    "Big chances":               ("big_chances_roma",      "big_chances_opp"),
    "Big chances missed":        ("big_chances_missed_roma","big_chances_missed_opp"),
    "Goalkeeper saves":          ("saves_roma",            "saves_opp"),
    "Tackles":                   ("tackles_roma",          "tackles_opp"),
    "Attacks":                   ("attacks_roma",          "attacks_opp"),
    "Dangerous attacks":         ("dangerous_attacks_roma","dangerous_attacks_opp"),
}

def parse_match_statistics(raw: Dict, is_home_roma: bool) -> Dict:
    result = {k: 0 for pair in _STAT_MAP.values() for k in pair}
    result["possession_roma"] = 50
    result["possession_opp"]  = 50

    for period in raw.get("statistics", []):
        for item in period.get("statisticsItems", []):
            name = item.get("name", "")
            if name not in _STAT_MAP:
                continue
            r_key, o_key = _STAT_MAP[name]
            try:
                h_raw = str(item.get("homeValue", "0") or "0").replace("%", "").strip()
                a_raw = str(item.get("awayValue", "0") or "0").replace("%", "").strip()
                h_val = float(h_raw) if h_raw else 0.0
                a_val = float(a_raw) if a_raw else 0.0
                result[r_key] = h_val if is_home_roma else a_val
                result[o_key] = a_val if is_home_roma else h_val
            except (ValueError, TypeError):
                pass
    return result


# ──────────────────────────────────────────────────────────────────────────────
# SHOT MAP
# ──────────────────────────────────────────────────────────────────────────────

def get_shot_map(match_id: int) -> Optional[List[Dict]]:
    data = _ss_get(f"/event/{match_id}/shotmap")
    return data.get("shotmap", []) if data else None

def split_shots(shots: List[Dict], is_home_roma: bool) -> Dict[str, List[Dict]]:
    roma = [s for s in shots if s.get("isHome") == is_home_roma]
    opp  = [s for s in shots if s.get("isHome") != is_home_roma]
    return {"roma": roma, "opp": opp}

def xg_from_shots(shots: List[Dict]) -> Dict:
    return {
        "xg":        round(sum(float(s.get("xg", 0) or 0) for s in shots), 3),
        "xgot":      round(sum(float(s.get("xgot", 0) or 0) for s in shots), 3),
        "shots":     len(shots),
        "goals":     sum(1 for s in shots if s.get("shotType") == "goal"),
        "on_target": sum(1 for s in shots if s.get("shotType") in ("goal", "save")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# PLAYER RATINGS
# ──────────────────────────────────────────────────────────────────────────────

def get_player_ratings(match_id: int) -> Optional[List[Dict]]:
    data = _ss_get(f"/event/{match_id}/lineups")
    if not data:
        return None

    players = []
    for side in ("home", "away"):
        for p in data.get(side, {}).get("players", []):
            stats  = p.get("statistics", {})
            rating = stats.get("rating")
            if not rating:
                continue
            info = p.get("player", {})
            players.append({
                "id":        info.get("id"),
                "name":      info.get("name", ""),
                "shortName": info.get("shortName", info.get("name", "")),
                "side":      side,
                "position":  p.get("position", ""),
                "rating":    float(rating),
                "goals":     stats.get("goals", 0) or 0,
                "assists":   stats.get("goalAssist", 0) or 0,
                "minutes":   stats.get("minutesPlayed", 0) or 0,
                "shots":     stats.get("totalShots", 0) or 0,
                "key_passes":stats.get("keyPass", 0) or 0,
            })
    return sorted(players, key=lambda x: x["rating"], reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# STANDINGS
# ──────────────────────────────────────────────────────────────────────────────

_SERIE_A_ID = 23

def get_current_season_id(tournament_id: int = _SERIE_A_ID) -> Optional[int]:
    data = _ss_get(f"/tournament/{tournament_id}/seasons")
    if data:
        seasons = data.get("seasons", [])
        return seasons[0].get("id") if seasons else None
    return None

def get_standings(tournament_id: int = _SERIE_A_ID, season_id: int = None) -> Optional[List[Dict]]:
    if not season_id:
        season_id = get_current_season_id(tournament_id)
    if not season_id:
        return None

    data = _ss_get(f"/tournament/{tournament_id}/season/{season_id}/standings/total")
    if not data:
        return None

    rows = data.get("standings", [{}])[0].get("rows", [])
    return [{
        "position":      row.get("position"),
        "team_id":       row.get("team", {}).get("id"),
        "team_name":     row.get("team", {}).get("name", ""),
        "played":        row.get("matches", 0),
        "wins":          row.get("wins", 0),
        "draws":         row.get("draws", 0),
        "losses":        row.get("losses", 0),
        "goals_for":     row.get("scoresFor", 0),
        "goals_against": row.get("scoresAgainst", 0),
        "points":        row.get("points", 0),
    } for row in rows]

def get_roma_position(standings: List[Dict]) -> Optional[int]:
    for row in standings:
        if row.get("team_id") == ROMA_ID:
            return row.get("position")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# FORMA SQUADRA
# ──────────────────────────────────────────────────────────────────────────────

def get_team_form(team_id: int = ROMA_ID, last_n: int = 5) -> List[str]:
    matches   = get_recent_matches(team_id, page=0)
    completed = [
        e for e in matches
        if e.get("status", {}).get("type", "") in ("finished", "ended", "afterpenalties", "aet")
    ]
    form = []
    for event in completed:
        home_id    = event.get("homeTeam", {}).get("id")
        is_home    = home_id == team_id
        h_score    = event.get("homeScore", {}).get("current", 0)
        a_score    = event.get("awayScore", {}).get("current", 0)
        r_score    = h_score if is_home else a_score
        o_score    = a_score if is_home else h_score
        form.append("W" if r_score > o_score else "D" if r_score == o_score else "L")
    return form[-last_n:]


# ──────────────────────────────────────────────────────────────────────────────
# STORICO SERIE A
# ──────────────────────────────────────────────────────────────────────────────

_FDO_BASE    = "https://api.football-data.org/v4"
_FDO_API_KEY = os.getenv("FD_API_KEY", "")
_FDO_HEADERS = {"X-Auth-Token": _FDO_API_KEY}
_FDO_LEAGUE  = "SA"

def _fdo_get(path: str) -> Optional[Dict]:
    if not _FDO_API_KEY:
        return None
    url = f"{_FDO_BASE}{path}"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=_FDO_HEADERS, timeout=20)
            if r.status_code == 429:
                time.sleep(60)
                continue
            r.raise_for_status()
            time.sleep(6)
            return r.json()
        except requests.RequestException:
            time.sleep(10)
    return None

def _fdo_season_matches(year: int) -> Optional[List[Dict]]:
    data = _fdo_get(f"/competitions/{_FDO_LEAGUE}/matches?season={year}")
    if not data: return None
    rows = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED": continue
        hg = m.get("score", {}).get("fullTime", {}).get("home")
        ag = m.get("score", {}).get("fullTime", {}).get("away")
        if hg is None or ag is None: continue
        rows.append({
            "HomeTeam": m.get("homeTeam", {}).get("name", ""),
            "AwayTeam": m.get("awayTeam", {}).get("name", ""),
            "FTHG": str(hg), "FTAG": str(ag),
            "FTR": "H" if hg > ag else ("A" if ag > hg else "D"),
        })
    return rows

_OFB_RAW = "https://raw.githubusercontent.com/openfootball/italy/master"
_OFB_MATCH_RE = re.compile(r"^\s{2,}(.+?)\s{2,}(\d+)-(\d+)\s{2,}(.+?)\s*$")

def _ofb_season_matches(year: int) -> Optional[List[Dict]]:
    folder = f"{year}-{str(year + 1)[-2:]}"
    url = f"{_OFB_RAW}/{folder}/it.1.txt"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 404: return None
        r.raise_for_status()
        rows = []
        for line in r.text.splitlines():
            m = _OFB_MATCH_RE.match(line)
            if m:
                hg, ag = int(m.group(2)), int(m.group(3))
                rows.append({
                    "HomeTeam": m.group(1).strip(), "AwayTeam": m.group(4).strip(),
                    "FTHG": str(hg), "FTAG": str(ag),
                    "FTR": "H" if hg > ag else ("A" if ag > hg else "D"),
                })
        return rows
    except: return None

def download_season_csv(season_code: str) -> Optional[List[Dict]]:
    year = 2000 + int(season_code[:2])
    if year >= 2011:
        rows = _ofb_season_matches(year)
        if rows: return rows
    return _fdo_season_matches(year)

def season_record(rows: List[Dict], team: str = "Roma") -> Optional[Dict]:
    wins = draws = losses = gf = ga = 0
    for row in rows:
        home, away, ftr = row.get("HomeTeam", ""), row.get("AwayTeam", ""), row.get("FTR", "")
        hg, ag = int(row.get("FTHG", 0)), int(row.get("FTAG", 0))
        if team in home:
            gf += hg; ga += ag
            if ftr == "H": wins += 1
            elif ftr == "D": draws += 1
            else: losses += 1
        elif team in away:
            gf += ag; ga += hg
            if ftr == "A": wins += 1
            elif ftr == "D": draws += 1
            else: losses += 1
    games = wins + draws + losses
    if not games: return None
    return {
        "games": games, "wins": wins, "draws": draws, "losses": losses,
        "goals_for": gf, "goals_against": ga, "points": wins * 3 + draws,
        "ppg": round((wins * 3 + draws) / games, 3)
    }

def build_full_history(start_year: int = 2000, team: str = "Roma") -> List[Dict]:
    now = datetime.utcnow()
    end_year = now.year if now.month >= 7 else now.year - 1
    history = []
    for year in range(start_year, end_year + 1):
        code = f"{str(year)[-2:]}{str(year + 1)[-2:]}"
        rows = download_season_csv(code)
        if rows:
            rec = season_record(rows, team)
            if rec:
                rec.update({"season_label": f"{year}/{str(year+1)[-2:]}", "season_code": code})
                history.append(rec)
        time.sleep(1)
    return history

# ──────────────────────────────────────────────────────────────────────────────
# TRANSFERMARKT (Richiede BeautifulSoup)
# ──────────────────────────────────────────────────────────────────────────────

_TM_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def get_squad_value() -> Optional[Dict]:
    try:
        from bs4 import BeautifulSoup
        r = requests.get("https://www.transfermarkt.com/as-rom/kader/verein/12/plus/1", headers=_TM_HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        total_el = soup.select_one(".right.dark")
        return {
            "total_value": total_el.get_text(strip=True) if total_el else "N/A",
            "fetched_at":  datetime.utcnow().isoformat(),
        }
    except: return None

# Alias compatibilità
fd_build_history = build_full_history
fd_season_record = season_record
fd_download_season = download_season_csv
