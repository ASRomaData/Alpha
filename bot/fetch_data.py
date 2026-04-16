"""
ASRomaData Bot — Data Fetching
=================================
Architettura a due fonti:

1. FOOTBALL-DATA.ORG  — match discovery (ultima/prossima partita, forma):
   - Unico endpoint affidabile da GitHub Actions (SofaScore blocca gli IP datacenter)
   - Free tier: 10 req/min, nessuna carta di credito
   - API key gratuita: https://www.football-data.org/client/register
   - Configurare FD_API_KEY come GitHub Secret

2. SOFASCORE  — statistiche avanzate (xG, shot map, ratings):
   - Usato per l'arricchimento dei dati post-partita
   - Se bloccato (403), il bot pubblica comunque con i dati base
   - Endpoint: www.sofascore.com/api/v1 (non api.sofascore.com)

3. OPENFOOTBALL / FOOTBALL-DATA.ORG — serie storiche Serie A dal 2000:
   - Zero login, openfootball su GitHub raw
"""

import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ── Costanti squadra ──────────────────────────────────────────────────────────
ROMA_ID     = 2702    # ID SofaScore (per statistiche avanzate)
ROMA_FDO_ID = 100     # ID football-data.org — verifica su:
                      # https://api.football-data.org/v4/teams/100
                      # Se 404, cerca l'ID corretto con:
                      # https://api.football-data.org/v4/competitions/SA/teams

_SERIE_A_ID = 23      # SofaScore tournament_id


# ──────────────────────────────────────────────────────────────────────────────
# FOOTBALL-DATA.ORG — fonte primaria per match discovery
# Funziona da GitHub Actions (nessun blocco IP datacenter)
# Free tier: 10 req/min · registrazione: https://www.football-data.org/client/register
# ──────────────────────────────────────────────────────────────────────────────

_FDO_BASE    = "https://api.football-data.org/v4"
_FDO_API_KEY = os.getenv("FD_API_KEY", "")
_FDO_LEAGUE  = "SA"   # Serie A
_FDO_DELAY   = 6.5    # secondi tra richieste (stare sotto i 10/min)


def _fdo_get(path: str) -> Optional[Dict]:
    """GET su football-data.org. Richiede FD_API_KEY in ambiente."""
    if not _FDO_API_KEY:
        logger.warning("FD_API_KEY non impostata — football-data.org non disponibile")
        return None
    url     = f"{_FDO_BASE}{path}"
    headers = {"X-Auth-Token": _FDO_API_KEY}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 429:
                logger.warning("football-data.org 429 — attendo 65s")
                time.sleep(65)
                continue
            if r.status_code in (401, 403):
                logger.error(f"football-data.org {r.status_code}: controlla FD_API_KEY")
                return None
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(_FDO_DELAY)
            return r.json()
        except requests.RequestException as e:
            logger.warning(f"football-data.org {path} attempt {attempt + 1}: {e}")
            if attempt < 2:
                time.sleep(10)
    return None


def _fdo_parse_match(m: Dict) -> Dict:
    """
    Converte un match football-data.org nel formato interno (stesso di parse_event).
    Roma può essere homeTeam o awayTeam.
    """
    home_id  = m.get("homeTeam", {}).get("id")
    away_id  = m.get("awayTeam", {}).get("id")
    is_home  = home_id == ROMA_FDO_ID
    score    = m.get("score", {}).get("fullTime", {})
    h_score  = score.get("home") or 0
    a_score  = score.get("away") or 0

    # utcDate → timestamp Unix + stringa dd/mm/yyyy
    utc_str  = m.get("utcDate", "")
    start_ts = 0
    date_str = ""
    if utc_str:
        try:
            dt       = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
            start_ts = int(dt.timestamp())
            date_str = dt.strftime("%d/%m/%Y")
        except ValueError:
            pass

    status_map = {
        "FINISHED":   "finished",
        "IN_PLAY":    "inprogress",
        "PAUSED":     "paused",
        "SCHEDULED":  "notstarted",
        "TIMED":      "notstarted",
        "POSTPONED":  "postponed",
        "CANCELLED":  "cancelled",
        "SUSPENDED":  "suspended",
    }
    status = status_map.get(m.get("status", ""), m.get("status", "").lower())

    return {
        # match_id è l'ID football-data.org.
        # Se usato per _ss_get (stats/shotmap) → SofaScore restituirà 404 → None
        # gestito gracefully in post_match.py con "if raw_stats:"
        "match_id":      m.get("id"),
        "home_team":     m.get("homeTeam", {}).get("name", ""),
        "away_team":     m.get("awayTeam", {}).get("name", ""),
        "home_score":    h_score,
        "away_score":    a_score,
        "roma_score":    h_score if is_home else a_score,
        "opp_score":     a_score if is_home else h_score,
        "opponent":      m.get("awayTeam", {}).get("name", "") if is_home
                         else m.get("homeTeam", {}).get("name", ""),
        "opponent_id":   away_id if is_home else home_id,
        "is_home":       is_home,
        "competition":   m.get("competition", {}).get("name", ""),
        "tournament_id": None,
        "season_id":     None,
        "round":         str(m.get("matchday", "")),
        "date":          date_str,
        "start_ts":      start_ts,
        "status":        status,
        "venue":         m.get("venue", ""),
        "_source":       "fdo",
    }


def _fdo_get_last_match() -> Optional[Dict]:
    """Ultima partita Roma conclusa — football-data.org."""
    data = _fdo_get(f"/teams/{ROMA_FDO_ID}/matches?status=FINISHED&limit=5")
    if not data:
        return None
    matches = data.get("matches", [])
    if not matches:
        return None
    return _fdo_parse_match(matches[-1])


def _fdo_get_next_match() -> Optional[Dict]:
    """Prossima partita Roma — football-data.org."""
    # Prova prima SCHEDULED, poi TIMED
    for status in ("SCHEDULED", "TIMED"):
        data = _fdo_get(f"/teams/{ROMA_FDO_ID}/matches?status={status}&limit=5")
        if data and data.get("matches"):
            return _fdo_parse_match(data["matches"][0])
    return None


def _fdo_get_recent_matches(last_n: int = 10) -> List[Dict]:
    """Ultime N partite Roma finite — football-data.org."""
    data = _fdo_get(f"/teams/{ROMA_FDO_ID}/matches?status=FINISHED&limit={last_n}")
    if not data:
        return []
    return [_fdo_parse_match(m) for m in data.get("matches", [])]


def _fdo_season_matches(year: int) -> Optional[List[Dict]]:
    """Partite Serie A di una stagione per lo storico — football-data.org."""
    data = _fdo_get(f"/competitions/{_FDO_LEAGUE}/matches?season={year}")
    if not data:
        return None
    rows = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        home  = m.get("homeTeam", {}).get("name", "")
        away  = m.get("awayTeam", {}).get("name", "")
        score = m.get("score", {}).get("fullTime", {})
        hg    = score.get("home")
        ag    = score.get("away")
        if hg is None or ag is None:
            continue
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        rows.append({
            "HomeTeam": home, "AwayTeam": away,
            "FTHG": str(hg), "FTAG": str(ag), "FTR": ftr,
        })
    return rows or None


# ──────────────────────────────────────────────────────────────────────────────
# SOFASCORE — statistiche avanzate (best-effort)
# GitHub Actions IP → 403 invariabile; queste funzioni restituiscono None.
# I caller usano già "if raw_stats:" quindi nessun crash.
# ──────────────────────────────────────────────────────────────────────────────

_SS_BASE    = "https://www.sofascore.com/api/v1"
_SS_SESSION: Optional[requests.Session] = None


def _get_ss_session() -> requests.Session:
    global _SS_SESSION
    if _SS_SESSION is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":             "application/json, text/plain, */*",
            "Accept-Language":    "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding":    "gzip, deflate, br",
            "Referer":            "https://www.sofascore.com/",
            "Origin":             "https://www.sofascore.com",
            "sec-ch-ua":          '"Chromium";v="124","Google Chrome";v="124","Not-A.Brand";v="99"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest":     "empty",
            "sec-fetch-mode":     "cors",
            "sec-fetch-site":     "same-origin",
            "Cache-Control":      "no-cache",
            "Pragma":             "no-cache",
        })
        try:
            s.get("https://www.sofascore.com/", timeout=15)
        except Exception:
            pass
        _SS_SESSION = s
    return _SS_SESSION


def _ss_get(path: str, retries: int = 2, delay: float = 3.0) -> Optional[Dict]:
    """
    GET www.sofascore.com/api/v1.
    403 → None immediato (IP datacenter bloccato — non ritentare).
    """
    url     = f"{_SS_BASE}{path}"
    session = _get_ss_session()
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 429:
                wait = delay * (attempt + 1) * 5
                logger.warning(f"SofaScore 429 — attendo {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code == 403:
                logger.warning(
                    f"SofaScore 403 ({path}) — IP datacenter bloccato, "
                    "stats avanzate non disponibili"
                )
                return None   # Non ritentare: è un blocco IP, non un errore temporaneo
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(delay)
            return r.json()
        except requests.RequestException as e:
            logger.warning(f"SofaScore {path} attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                time.sleep(delay * 2)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# PARTITE — interfaccia pubblica
# ──────────────────────────────────────────────────────────────────────────────

def get_last_match(team_id: int = ROMA_ID) -> Optional[Dict]:
    """
    Ultima partita Roma conclusa.
    Primario: football-data.org (affidabile da GitHub Actions)
    Fallback: SofaScore (per dati ricchi se l'IP non è bloccato)
    """
    match = _fdo_get_last_match()
    if match:
        logger.info(
            f"Match trovato su football-data.org: "
            f"{match['home_team']} {match['home_score']}-"
            f"{match['away_score']} {match['away_team']} [{match['status']}]"
        )
        return match

    # Fallback SofaScore
    logger.info("football-data.org non disponibile — provo SofaScore...")
    data = _ss_get(f"/team/{team_id}/events/last/0")
    if data:
        events = data.get("events", [])
        return events[-1] if events else None

    logger.error(
        "Nessuna fonte disponibile per get_last_match. "
        "Verifica FD_API_KEY (football-data.org) nelle GitHub Secrets."
    )
    return None


def get_next_match(team_id: int = ROMA_ID) -> Optional[Dict]:
    """Prossima partita Roma. Primario: football-data.org, fallback: SofaScore."""
    match = _fdo_get_next_match()
    if match:
        return match
    data = _ss_get(f"/team/{team_id}/events/next/0")
    if data:
        events = data.get("events", [])
        return events[0] if events else None
    return None


def get_recent_matches(team_id: int = ROMA_ID, page: int = 0) -> List[Dict]:
    """Ultime partite Roma. Primario: football-data.org, fallback: SofaScore."""
    matches = _fdo_get_recent_matches(last_n=10)
    if matches:
        return matches
    data = _ss_get(f"/team/{team_id}/events/last/{page}")
    return data.get("events", []) if data else []


def parse_event(event: Dict) -> Dict:
    """
    Normalizza un evento nel formato interno.
    Gli eventi da football-data.org (_source='fdo') sono già normalizzati.
    """
    if event.get("_source") == "fdo":
        return event

    # Formato SofaScore raw
    home_id    = event.get("homeTeam", {}).get("id")
    away_id    = event.get("awayTeam", {}).get("id")
    home_score = event.get("homeScore", {}).get("current", 0)
    away_score = event.get("awayScore", {}).get("current", 0)
    is_home    = home_id == ROMA_ID
    start_ts   = event.get("startTimestamp", 0)
    return {
        "match_id":      event.get("id"),
        "home_team":     event.get("homeTeam", {}).get("name", ""),
        "away_team":     event.get("awayTeam", {}).get("name", ""),
        "home_score":    home_score,
        "away_score":    away_score,
        "roma_score":    home_score if is_home else away_score,
        "opp_score":     away_score if is_home else home_score,
        "opponent":      event.get("awayTeam", {}).get("name", "") if is_home
                         else event.get("homeTeam", {}).get("name", ""),
        "opponent_id":   away_id if is_home else home_id,
        "is_home":       is_home,
        "competition":   event.get("tournament", {}).get("name", ""),
        "tournament_id": event.get("tournament", {}).get("id"),
        "season_id":     event.get("season", {}).get("id"),
        "round":         event.get("roundInfo", {}).get("round", ""),
        "date":          datetime.utcfromtimestamp(start_ts).strftime("%d/%m/%Y")
                         if start_ts else "",
        "start_ts":      start_ts,
        "status":        event.get("status", {}).get("type", ""),
        "venue":         (event.get("venue") or {}).get("name", ""),
    }


# ──────────────────────────────────────────────────────────────────────────────
# STATISTICHE PARTITA — SofaScore (best-effort, None se bloccato)
# ──────────────────────────────────────────────────────────────────────────────

def get_match_statistics(match_id: int) -> Optional[Dict]:
    return _ss_get(f"/event/{match_id}/statistics")


_STAT_MAP = {
    "Ball possession":           ("possession_roma",          "possession_opp"),
    "Total shots":               ("shots_roma",               "shots_opp"),
    "Shots on target":           ("shots_on_target_roma",     "shots_on_target_opp"),
    "Passes":                    ("passes_roma",              "passes_opp"),
    "Accurate passes":           ("passes_roma",              "passes_opp"),
    "Corner kicks":              ("corners_roma",             "corners_opp"),
    "Fouls":                     ("fouls_roma",               "fouls_opp"),
    "Yellow cards":              ("yellow_roma",              "yellow_opp"),
    "Red cards":                 ("red_roma",                 "red_opp"),
    "Expected goals":            ("xg_roma",                  "xg_opp"),
    "Expected Goals":            ("xg_roma",                  "xg_opp"),
    "xG":                        ("xg_roma",                  "xg_opp"),
    "Expected Goals on Target":  ("xgot_roma",                "xgot_opp"),
    "Big chances":               ("big_chances_roma",         "big_chances_opp"),
    "Big chances missed":        ("big_chances_missed_roma",  "big_chances_missed_opp"),
    "Goalkeeper saves":          ("saves_roma",               "saves_opp"),
    "Tackles":                   ("tackles_roma",             "tackles_opp"),
    "Attacks":                   ("attacks_roma",             "attacks_opp"),
    "Dangerous attacks":         ("dangerous_attacks_roma",   "dangerous_attacks_opp"),
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
# SHOT MAP — SofaScore (best-effort)
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
# PLAYER RATINGS — SofaScore (best-effort)
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
                "id":         info.get("id"),
                "name":       info.get("name", ""),
                "shortName":  info.get("shortName", info.get("name", "")),
                "side":       side,
                "position":   p.get("position", ""),
                "rating":     float(rating),
                "goals":      stats.get("goals", 0) or 0,
                "assists":    stats.get("goalAssist", 0) or 0,
                "minutes":    stats.get("minutesPlayed", 0) or 0,
                "shots":      stats.get("totalShots", 0) or 0,
                "key_passes": stats.get("keyPass", 0) or 0,
            })
    return sorted(players, key=lambda x: x["rating"], reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# STANDINGS — SofaScore (best-effort)
# ──────────────────────────────────────────────────────────────────────────────

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
# FORMA SQUADRA — primario football-data.org, fallback SofaScore
# ──────────────────────────────────────────────────────────────────────────────

def get_team_form(team_id: int = ROMA_ID, last_n: int = 5) -> List[str]:
    """Forma W/D/L ultime N partite concluse."""
    recent = _fdo_get_recent_matches(last_n=last_n)
    if recent:
        form = []
        for m in recent:
            r = m.get("roma_score", 0)
            o = m.get("opp_score", 0)
            form.append("W" if r > o else "D" if r == o else "L")
        return form[-last_n:]

    # Fallback SofaScore
    matches   = get_recent_matches(team_id, page=0)
    completed = [
        e for e in matches
        if e.get("status", {}).get("type", "") in ("finished", "ended", "afterpenalties", "aet")
        or e.get("status") == "finished"
    ]
    form = []
    for event in completed:
        is_home = event.get("is_home", event.get("homeTeam", {}).get("id") == team_id)
        if "roma_score" in event:
            r, o = event["roma_score"], event["opp_score"]
        else:
            h = event.get("homeScore", {}).get("current", 0)
            a = event.get("awayScore", {}).get("current", 0)
            r, o = (h, a) if is_home else (a, h)
        form.append("W" if r > o else "D" if r == o else "L")
    return form[-last_n:]


def get_xg_form(team_id: int = ROMA_ID, last_n: int = 5) -> List[float]:
    """xG Roma nelle ultime N partite — SofaScore (best-effort)."""
    matches   = get_recent_matches(team_id, page=0)
    completed = [
        e for e in matches
        if e.get("status", {}).get("type", "") in ("finished", "ended", "afterpenalties", "aet")
        or e.get("status") == "finished"
    ][-last_n:]

    xg_list = []
    for event in completed:
        mid     = event.get("id") or event.get("match_id")
        is_home = event.get("is_home", True)
        raw     = get_match_statistics(mid)
        if raw:
            s = parse_match_statistics(raw, is_home)
            if s.get("xg_roma", 0) > 0:
                xg_list.append(s["xg_roma"])
    return xg_list


# ──────────────────────────────────────────────────────────────────────────────
# H2H — da storico openfootball
# ──────────────────────────────────────────────────────────────────────────────

def fd_h2h(opponent: str, last_n: int = 5) -> Dict:
    """
    H2H Roma vs avversario nelle ultime last_n stagioni (openfootball).
    Restituisce {roma_wins, draws, opp_wins}.
    """
    now      = datetime.utcnow()
    end_year = now.year if now.month >= 7 else now.year - 1
    all_rows: List[Dict] = []

    for year in range(max(end_year - last_n, 2011), end_year + 1):
        code = f"{str(year)[-2:]}{str(year + 1)[-2:]}"
        rows = download_season_csv(code)
        if rows:
            all_rows.extend(rows)
        time.sleep(0.5)

    h2h = get_h2h(all_rows, "Roma", opponent)
    return {
        "roma_wins": h2h["a_wins"],
        "draws":     h2h["draws"],
        "opp_wins":  h2h["b_wins"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# STORICO SERIE A
# Fonte primaria  : openfootball su GitHub (raw.githubusercontent.com)
# Fonte secondaria: football-data.org
# ──────────────────────────────────────────────────────────────────────────────

_OFB_RAW = "https://raw.githubusercontent.com/openfootball/italy/master"

_OFB_NAME_MAP = {
    "Inter":          "Inter",
    "Internazionale": "Inter",
    "AC Milan":       "AC Milan",
    "Milan":          "AC Milan",
    "Juventus":       "Juventus",
    "Roma":           "Roma",
    "Napoli":         "Napoli",
    "Lazio":          "Lazio",
    "Fiorentina":     "Fiorentina",
    "Atalanta":       "Atalanta",
    "Torino":         "Torino",
    "Sampdoria":      "Sampdoria",
    "Bologna":        "Bologna",
    "Udinese":        "Udinese",
    "Genoa":          "Genoa",
    "Cagliari":       "Cagliari",
    "Verona":         "Verona",
    "Hellas Verona":  "Verona",
    "Parma":          "Parma",
    "Sassuolo":       "Sassuolo",
    "Empoli":         "Empoli",
    "Spezia":         "Spezia",
    "Venezia":        "Venezia",
    "Salernitana":    "Salernitana",
    "Cremonese":      "Cremonese",
    "Lecce":          "Lecce",
    "Monza":          "Monza",
    "Frosinone":      "Frosinone",
    "Como":           "Como",
}

_OFB_MATCH_RE = re.compile(r"^\s{2,}(.+?)\s{2,}(\d+)-(\d+)\s{2,}(.+?)\s*$")


def _ofb_season_matches(year: int) -> Optional[List[Dict]]:
    folder = f"{year}-{str(year + 1)[-2:]}"
    url    = f"{_OFB_RAW}/{folder}/it.1.txt"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 404:
            return None
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"openfootball {folder}: {e}")
        return None

    rows = []
    for line in r.text.splitlines():
        m = _OFB_MATCH_RE.match(line)
        if not m:
            continue
        home_raw, hg_s, ag_s, away_raw = m.group(1), m.group(2), m.group(3), m.group(4)
        home = _OFB_NAME_MAP.get(home_raw.strip(), home_raw.strip())
        away = _OFB_NAME_MAP.get(away_raw.strip(), away_raw.strip())
        hg, ag = int(hg_s), int(ag_s)
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        rows.append({
            "HomeTeam": home, "AwayTeam": away,
            "FTHG": str(hg), "FTAG": str(ag), "FTR": ftr,
        })

    logger.info(f"openfootball {folder}: {len(rows)} partite")
    return rows or None


def download_season_csv(season_code: str) -> Optional[List[Dict]]:
    """
    Partite Serie A stagione. season_code: '2425' → 2024/25.
    Primario: openfootball (GitHub raw). Fallback: football-data.org.
    """
    year = 2000 + int(season_code[:2])
    if year >= 2011:
        rows = _ofb_season_matches(year)
        if rows:
            return rows
    rows = _fdo_season_matches(year)
    if rows:
        return rows
    logger.warning(f"download_season_csv: nessuna fonte per {season_code}")
    return None


def season_record(rows: List[Dict], team: str = "Roma") -> Optional[Dict]:
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
            if ftr == "H":   wins += 1
            elif ftr == "D": draws += 1
            elif ftr == "A": losses += 1
        elif away == team:
            gf += ag; ga += hg
            if ftr == "A":   wins += 1
            elif ftr == "D": draws += 1
            elif ftr == "H": losses += 1

    games = wins + draws + losses
    if not games:
        return None
    return {
        "games": games, "wins": wins, "draws": draws, "losses": losses,
        "goals_for": gf, "goals_against": ga,
        "goal_diff": gf - ga,
        "points":    wins * 3 + draws,
        "ppg":       round((wins * 3 + draws) / games, 3),
    }


def build_full_history(start_year: int = 2000, team: str = "Roma") -> List[Dict]:
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
    "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.transfermarkt.com/",
}


def get_squad_value() -> Optional[Dict]:
    try:
        from bs4 import BeautifulSoup
        r = requests.get(
            "https://www.transfermarkt.com/as-rom/kader/verein/12/plus/1",
            headers=_TM_HEADERS, timeout=20
        )
        r.raise_for_status()
        soup      = BeautifulSoup(r.text, "html.parser")
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


# ── Alias di compatibilità ────────────────────────────────────────────────────
fd_build_history   = build_full_history
fd_season_record   = season_record
fd_download_season = download_season_csv
fd_h2h_record      = fd_h2h
