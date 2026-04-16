"""
ASRomaData Bot — Data Fetching
=================================
Architettura a due fonti:

1. SOFASCORE  — tutto ciò che riguarda le partite:
   - Risultati, statistiche, xG (Opta), shot map con xG per tiro,
     player ratings, standings, forma squadra, prossima partita

2. FOOTBALL-DATA.CO.UK  — serie storiche Serie A dal 2000:
   - CSV scaricabile direttamente, zero login, zero API key

Niente FBref. Niente Understat. Una sola fonte live, una per lo storico.
"""

import csv
import io
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ROMA_ID  = 2702
_SS_BASE = "https://api.sofascore.com/api/v1"
_SS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
}


# ──────────────────────────────────────────────────────────────────────────────
# SOFASCORE — base request
# ──────────────────────────────────────────────────────────────────────────────

def _ss_get(path: str, retries: int = 3, delay: float = 4.0) -> Optional[Dict]:
    url = f"{_SS_BASE}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_SS_HEADERS, timeout=20)
            if r.status_code == 429:
                wait = delay * (attempt + 1) * 4
                logger.warning(f"SofaScore 429 — attendo {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(delay)
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
# STATISTICHE PARTITA (incluso xG Opta)
# ──────────────────────────────────────────────────────────────────────────────

def get_match_statistics(match_id: int) -> Optional[Dict]:
    """Statistiche complete incluse Expected Goals (xG Opta)."""
    return _ss_get(f"/event/{match_id}/statistics")


# Mappa nomi statistica SofaScore → chiavi del dict risultato
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
# SHOT MAP (xG per tiro + coordinate)
# ──────────────────────────────────────────────────────────────────────────────

def get_shot_map(match_id: int) -> Optional[List[Dict]]:
    """
    Shot map da SofaScore: tutti i tiri con xG (Opta) e coordinate (0-100).
    Ogni tiro: {isHome, shotType, xg, xgot, playerCoordinates, time, player, bodyPart, situation}
    shotType: 'goal' | 'save' | 'miss' | 'block' | 'post'
    """
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

# Serie A su SofaScore: tournament_id = 23
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
    """Forma W/D/L ultime N partite completate."""
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


def get_xg_form(team_id: int = ROMA_ID, last_n: int = 5) -> List[float]:
    """
    xG Roma nelle ultime N partite completate.
    Attenzione: fa N chiamate API — usa con rate limiting.
    """
    matches   = get_recent_matches(team_id, page=0)
    completed = [
        e for e in matches
        if e.get("status", {}).get("type", "") in ("finished", "ended", "afterpenalties", "aet")
    ][-last_n:]

    xg_list = []
    for event in completed:
        mid     = event.get("id")
        is_home = event.get("homeTeam", {}).get("id") == team_id
        raw     = get_match_statistics(mid)
        if raw:
            s = parse_match_statistics(raw, is_home)
            if s.get("xg_roma", 0) > 0:
                xg_list.append(s["xg_roma"])
    return xg_list


# ──────────────────────────────────────────────────────────────────────────────
# FOOTBALL-DATA.CO.UK — storico Serie A
# ──────────────────────────────────────────────────────────────────────────────

_FD_BASE = "https://www.football-data.co.uk/mmz4281"
_FD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Referer":         "https://www.football-data.co.uk/italy.php",
}


def download_season_csv(season_code: str) -> Optional[List[Dict]]:
    """
    Scarica CSV stagione Serie A.
    season_code: '2425' per 2024/25, '2324' per 2023/24, '0001' per 2000/01
    
    football-data.co.uk richiede un browser User-Agent o risponde 403.
    Serie A = I1.csv (prima divisione italiana).
    """
    url = f"{_FD_BASE}/{season_code}/I1.csv"
    try:
        r = requests.get(url, headers=_FD_HEADERS, timeout=20)
        r.raise_for_status()
        text   = r.content.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        rows   = [row for row in reader if row.get("HomeTeam", "").strip()]
        logger.info(f"football-data {season_code}: {len(rows)} partite")
        return rows
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            logger.debug(f"football-data {season_code}: non trovato (stagione non ancora disponibile)")
        else:
            logger.warning(f"football-data.co.uk {season_code}: HTTP {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"football-data.co.uk {season_code}: {e}")
        return None


def season_record(rows: List[Dict], team: str = "Roma") -> Optional[Dict]:
    """Calcola record stagionale da CSV."""
    wins = draws = losses = gf = ga = 0
    for row in rows:
        home = row.get("HomeTeam", "").strip()
        away = row.get("AwayTeam", "").strip()
        ftr  = row.get("FTR", "").strip()
        try:
            hg, ag = int(row.get("FTHG", 0) or 0), int(row.get("FTAG", 0) or 0)
        except ValueError:
            continue
        if home == team:
            gf += hg; ga += ag
            if ftr == "H": wins += 1
            elif ftr == "D": draws += 1
            elif ftr == "A": losses += 1
        elif away == team:
            gf += ag; ga += hg
            if ftr == "A": wins += 1
            elif ftr == "D": draws += 1
            elif ftr == "H": losses += 1

    games = wins + draws + losses
    if not games:
        return None
    return {
        "games": games, "wins": wins, "draws": draws, "losses": losses,
        "goals_for": gf, "goals_against": ga,
        "goal_diff": gf - ga,
        "points": wins * 3 + draws,
        "ppg": round((wins * 3 + draws) / games, 3),
    }


def build_full_history(start_year: int = 2000, team: str = "Roma") -> List[Dict]:
    """Scarica storico completo Serie A dal start_year ad oggi."""
    now      = datetime.utcnow()
    end_year = now.year if now.month >= 7 else now.year - 1
    history  = []

    for year in range(start_year, end_year + 1):
        code = f"{str(year)[-2:]}{str(year + 1)[-2:]}"
        rows = download_season_csv(code)
        if not rows:
            time.sleep(1)
            continue
        rec = season_record(rows, team)
        if rec:
            rec.update({
                "season_code":  code,
                "season_label": f"{year}/{str(year + 1)[-2:]}",
                "season_start": year,
            })
            history.append(rec)
        time.sleep(1.5)

    return history


def get_h2h(rows: List[Dict], team_a: str = "Roma", team_b: str = "") -> Dict:
    """H2H tra due squadre da CSV stagione."""
    a_wins = draws = b_wins = 0
    for row in rows:
        home = row.get("HomeTeam", "").strip()
        away = row.get("AwayTeam", "").strip()
        ftr  = row.get("FTR", "").strip()
        if {home, away} != {team_a, team_b}:
            continue
        if (home == team_a and ftr == "H") or (away == team_a and ftr == "A"):
            a_wins += 1
        elif ftr == "D":
            draws += 1
        else:
            b_wins += 1
    return {"a_wins": a_wins, "draws": draws, "b_wins": b_wins}


def current_season_code() -> str:
    now = datetime.utcnow()
    y   = now.year if now.month >= 7 else now.year - 1
    return f"{str(y)[-2:]}{str(y + 1)[-2:]}"


# ──────────────────────────────────────────────────────────────────────────────
# TRANSFERMARKT — valore rosa (opzionale)
# ──────────────────────────────────────────────────────────────────────────────

_TM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.transfermarkt.com/",
}


def get_squad_value() -> Optional[Dict]:
    try:
        from bs4 import BeautifulSoup
        r = requests.get(
            "https://www.transfermarkt.com/as-rom/kader/verein/12/plus/1",
            headers=_TM_HEADERS, timeout=20
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        total_el  = soup.select_one(".right.dark")
        top_row   = soup.select_one(".items tbody tr")
        top_player = {}
        if top_row:
            n = top_row.select_one(".hauptlink a")
            v = top_row.select_one(".rechts.hauptlink")
            if n: top_player["name"]  = n.get_text(strip=True)
            if v: top_player["value"] = v.get_text(strip=True)
        return {
            "total_value": total_el.get_text(strip=True) if total_el else "N/A",
            "top_player":  top_player,
            "fetched_at":  datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.warning(f"Transfermarkt: {e}")
        return None
