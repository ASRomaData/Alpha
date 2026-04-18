"""
ASRomaData Bot — Data Fetching
=================================
Architettura a due fonti:

1. SOFASCORE  — Match data (curl_cffi impersonate per evitare 403)
2. FOOTBALL-DATA.CO.UK  — Serie A historical data

Richiede: pip install curl_cffi requests
"""

import csv
import io
import logging
import time
import random
from datetime import datetime
from typing import Dict, List, Optional

from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

ROMA_ID  = 2702
_SS_BASE = "https://api.sofascore.com/api/v1"

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
            r = curl_requests.get(url, headers=HEADERS_SS, impersonate="chrome110", timeout=20)

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


def parse_event(event: Dict, team_id: int = ROMA_ID) -> Dict:
    """
    Parse a SofaScore event dict.
    Works for any team_id — roma_score/opp_score are relative to team_id.
    """
    home_id    = event.get("homeTeam", {}).get("id")
    away_id    = event.get("awayTeam", {}).get("id")
    home_score = event.get("homeScore", {}).get("current", 0)
    away_score = event.get("awayScore", {}).get("current", 0)
    is_home    = home_id == team_id
    start_ts   = event.get("startTimestamp", 0)
    return {
        "match_id":      event.get("id"),
        "home_team":     event.get("homeTeam", {}).get("name", ""),
        "away_team":     event.get("awayTeam", {}).get("name", ""),
        "home_score":    home_score,
        "away_score":    away_score,
        "roma_score":    home_score if is_home else away_score,
        "opp_score":     away_score if is_home else home_score,
        "opponent":      event.get("awayTeam", {}).get("name", "") if is_home else event.get("homeTeam", {}).get("name", ""),
        "opponent_id":   away_id if is_home else home_id,
        "is_home":       is_home,
        "competition":   event.get("tournament", {}).get("name", ""),
        "tournament_id": event.get("tournament", {}).get("id"),
        "season_id":     event.get("season", {}).get("id"),
        "round":         event.get("roundInfo", {}).get("round", ""),
        "date":          datetime.utcfromtimestamp(start_ts).strftime("%d/%m/%Y") if start_ts else "",
        "start_ts":      start_ts,
        "status":        event.get("status", {}).get("type", ""),
        "venue":         (event.get("venue") or {}).get("name", ""),
    }


# ──────────────────────────────────────────────────────────────────────────────
# STATISTICHE
# ──────────────────────────────────────────────────────────────────────────────

def get_match_statistics(match_id: int) -> Optional[Dict]:
    return _ss_get(f"/event/{match_id}/statistics")


_STAT_MAP = {
    "Ball possession":  ("possession_roma",      "possession_opp"),
    "Total shots":      ("shots_roma",           "shots_opp"),
    "Shots on target":  ("shots_on_target_roma", "shots_on_target_opp"),
    "Passes":           ("passes_roma",          "passes_opp"),
    "Corner kicks":     ("corners_roma",         "corners_opp"),
    "Fouls":            ("fouls_roma",           "fouls_opp"),
    "Yellow cards":     ("yellow_roma",          "yellow_opp"),
    "Red cards":        ("red_roma",             "red_opp"),
    "Expected goals":   ("xg_roma",              "xg_opp"),
}


def parse_match_statistics(raw: Dict, is_home_roma: bool) -> Dict:
    result = {k: 0 for pair in _STAT_MAP.values() for k in pair}
    for period in raw.get("statistics", []):
        if period.get("period") != "ALL":
            continue
        for group in period.get("groups", []):
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


def split_shots(shotmap: List[Dict], is_home_roma: bool) -> Dict:
    """Split shotmap into Roma shots and opponent shots."""
    roma_shots = [s for s in shotmap if s.get("isHome") == is_home_roma]
    opp_shots  = [s for s in shotmap if s.get("isHome") != is_home_roma]
    return {"roma": roma_shots, "opp": opp_shots}


def xg_from_shots(shots: List[Dict]) -> Dict:
    """Sum xG values from a list of shots."""
    total = sum(float(s.get("xg", 0) or 0) for s in shots)
    return {"xg": round(total, 2)}


def get_player_ratings(match_id: int) -> Optional[List[Dict]]:
    data = _ss_get(f"/event/{match_id}/lineups")
    if not data:
        return None
    players = []
    for side in ("home", "away"):
        for p in data.get(side, {}).get("players", []):
            stats = p.get("statistics", {})
            if not stats.get("rating"):
                continue
            players.append({
                "name":   p["player"]["name"],
                "rating": float(stats["rating"]),
                "side":   side,
            })
    return sorted(players, key=lambda x: x["rating"], reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# FORM + STATS AGGREGATE  (usato da pre_match.py)
# ──────────────────────────────────────────────────────────────────────────────

FINISHED_STATUSES = ("finished", "ended", "afterpenalties", "aet")


def get_team_form_stats(team_id: int, n: int = 5) -> Dict:
    """
    Returns form, avg xG, avg xGA, avg shots for/against
    for any team over last N finished matches from SofaScore.
    """
    matches = get_recent_matches(team_id, page=0)
    form = []
    xg_vals, xga_vals, shots_for, shots_against = [], [], [], []

    for event in matches:
        parsed = parse_event(event, team_id=team_id)
        if parsed["status"] not in FINISHED_STATUSES:
            continue

        rs, os_ = parsed["roma_score"], parsed["opp_score"]
        if rs > os_:    form.append("W")
        elif rs == os_: form.append("D")
        else:           form.append("L")

        raw = get_match_statistics(parsed["match_id"])
        if raw:
            stats = parse_match_statistics(raw, parsed["is_home"])
            if stats.get("xg_roma"):    xg_vals.append(float(stats["xg_roma"]))
            if stats.get("xg_opp"):     xga_vals.append(float(stats["xg_opp"]))
            if stats.get("shots_roma"): shots_for.append(float(stats["shots_roma"]))
            if stats.get("shots_opp"):  shots_against.append(float(stats["shots_opp"]))

        if len(form) >= n:
            break
        time.sleep(random.uniform(0.5, 1.0))

    def avg(lst): return round(sum(lst) / len(lst), 2) if lst else 0.0

    return {
        "form":               form[-n:],
        "avg_xg":             avg(xg_vals),
        "avg_xga":            avg(xga_vals),
        "avg_shots_for":      avg(shots_for),
        "avg_shots_against":  avg(shots_against),
    }


def get_form(team_id: int = ROMA_ID, n: int = 5) -> List[str]:
    """Shortcut — returns only form list."""
    return get_team_form_stats(team_id, n)["form"]


def get_avg_xg(team_id: int = ROMA_ID, n: int = 5) -> float:
    """Shortcut — returns only avg xG."""
    return get_team_form_stats(team_id, n)["avg_xg"]


# ──────────────────────────────────────────────────────────────────────────────
# STORICO SERIE A — football-data.co.uk
# ──────────────────────────────────────────────────────────────────────────────

def download_season_csv(season_code: str) -> Optional[List[Dict]]:
    import requests as r_std
    url = f"https://www.football-data.co.uk/mmz4281/{season_code}/I1.csv"
    try:
        res = r_std.get(url, timeout=15)
        if res.status_code != 200:
            return None
        reader = csv.DictReader(io.StringIO(res.text))
        return list(reader)
    except Exception:
        return None


def build_full_history(start_year: int = 2000, team: str = "Roma") -> List[Dict]:
    history = []
    current_year = datetime.utcnow().year
    for y in range(start_year, current_year):
        code = f"{str(y)[-2:]}{str(y + 1)[-2:]}"
        rows = download_season_csv(code)
        if not rows:
            continue
        for row in rows:
            home = row.get("HomeTeam", "")
            away = row.get("AwayTeam", "")
            if team not in (home, away):
                continue
            ftr = row.get("FTR", "")
            is_home = home == team
            if ftr == "H":   result = "W" if is_home else "L"
            elif ftr == "A": result = "L" if is_home else "W"
            elif ftr == "D": result = "D"
            else: continue
            try:
                history.append({
                    "season":     f"{y}/{y+1}",
                    "date":       row.get("Date", ""),
                    "home_team":  home,
                    "away_team":  away,
                    "home_score": int(row.get("FTHG", 0)),
                    "away_score": int(row.get("FTAG", 0)),
                    "result":     result,
                    "is_home":    is_home,
                })
            except Exception:
                continue
    return history


def fd_h2h(opponent: str, last_n: int = 5) -> Dict:
    """Head-to-head record Roma vs opponent from football-data.co.uk."""
    roma_wins = draws = opp_wins = 0
    matched = 0
    opponent_lower = opponent.lower()

    current_year = datetime.utcnow().year
    for y in range(current_year - 1, current_year - 7, -1):
        if matched >= last_n:
            break
        code = f"{str(y)[-2:]}{str(y + 1)[-2:]}"
        rows = download_season_csv(code)
        if not rows:
            continue
        for row in rows:
            home = row.get("HomeTeam", "").lower()
            away = row.get("AwayTeam", "").lower()
            if "roma" not in (home, away):
                continue
            if opponent_lower not in (home, away):
                continue
            ftr = row.get("FTR", "")
            is_home_roma = "roma" in home
            if ftr == "H":
                if is_home_roma: roma_wins += 1
                else: opp_wins += 1
            elif ftr == "A":
                if is_home_roma: opp_wins += 1
                else: roma_wins += 1
            elif ftr == "D":
                draws += 1
            matched += 1
            if matched >= last_n:
                break

    return {"roma_wins": roma_wins, "draws": draws, "opp_wins": opp_wins, "total": matched}


# Alias per compatibilità
fd_build_history   = build_full_history
fd_download_season = download_season_csv
