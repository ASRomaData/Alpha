"""
ASRomaData Bot — Data Fetching
═══════════════════════════════════════════════════════════════════
FONTI (tutte gratuite, nessun abbonamento):

1. FOTMOB          → xG, xGoT, shot map Opta, stats match, fixtures
2. SOFASCORE       → rating giocatori, formazioni
3. FOOTBALL-DATA   → storico Serie A risultati dal 2000 (CSV diretto)
4. TRANSFERMARKT   → valori di mercato, trasferimenti

FBref e Understat RIMOSSI — dati Serie A inaffidabili/incompleti.
═══════════════════════════════════════════════════════════════════
"""

import csv
import io
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ROMA_SOFASCORE_ID = 2702
ROMA_FOTMOB_ID    = 8404   # fotmob.com/teams/8404/as-roma
SERIE_A_FOTMOB_ID = 55     # fotmob.com/leagues/55/serie-a

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
})


# ══════════════════════════════════════════════════════════════════
# FOTMOB  — fonte primaria xG, shot map, stats match
# Dati Opta-powered, nessuna auth richiesta
# ══════════════════════════════════════════════════════════════════

FOTMOB_BASE = "https://www.fotmob.com/api"

def _fotmob_get(path: str, params: dict = None) -> Optional[dict]:
    url = f"{FOTMOB_BASE}/{path}"
    for attempt in range(3):
        try:
            r = _SESSION.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            if code == 403:
                _SESSION.headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                time.sleep(8)
            elif code == 429:
                time.sleep(30 * (attempt + 1))
            else:
                logger.error(f"Fotmob HTTP {code} — {path}")
                return None
        except Exception as e:
            logger.warning(f"Fotmob attempt {attempt+1} ({path}): {e}")
            time.sleep(5)
    return None


def fotmob_get_team_fixtures(team_id: int = ROMA_FOTMOB_ID) -> Optional[dict]:
    """Fixtures + info squadra. Endpoint: /api/teams?id=8404"""
    return _fotmob_get("teams", params={"id": team_id})


def fotmob_get_last_match_id(team_id: int = ROMA_FOTMOB_ID) -> Optional[int]:
    """Match ID Fotmob dell'ultima partita completata."""
    data = fotmob_get_team_fixtures(team_id)
    if not data:
        return None
    fixtures = data.get("fixtures", {}).get("allMatches", [])
    completed = [m for m in fixtures if m.get("status", {}).get("finished", False)]
    if not completed:
        return None
    completed.sort(key=lambda m: m.get("status", {}).get("utcTime", ""), reverse=True)
    return completed[0].get("id")


def fotmob_get_match_details(match_id: int) -> Optional[dict]:
    """
    Dettagli completi partita. Endpoint: /api/matchDetails?matchId=XXX
    Contiene: stats, xG, shot map con expectedGoals per tiro, lineups.
    """
    return _fotmob_get("matchDetails", params={"matchId": match_id})


def fotmob_parse_match(data: dict) -> dict:
    """Normalizza risposta Fotmob in formato standard bot."""
    if not data:
        return {}

    general = data.get("general", {})
    teams   = data.get("header", {}).get("teams", [{}, {}])

    home = teams[0] if len(teams) > 0 else {}
    away = teams[1] if len(teams) > 1 else {}

    home_id    = int(home.get("id", 0) or 0)
    home_name  = home.get("name", "")
    away_name  = away.get("name", "")
    home_score = home.get("score", 0)
    away_score = away.get("score", 0)
    is_home    = (home_id == ROMA_FOTMOB_ID)

    roma_score = home_score if is_home else away_score
    opp_score  = away_score if is_home else home_score
    opponent   = away_name  if is_home else home_name

    utc_str = general.get("matchTimeUTCDate", "")
    try:
        dt         = datetime.strptime(utc_str[:10], "%Y-%m-%d")
        match_date = dt.strftime("%d/%m/%Y")
        start_ts   = int(dt.timestamp())
    except Exception:
        match_date = utc_str[:10]
        start_ts   = 0

    stats = _fotmob_parse_stats(data, is_home)
    shots = _fotmob_parse_shots(data)

    xg_roma = round(sum(s.get("xg", 0) for s in shots["roma"]), 3)
    xg_opp  = round(sum(s.get("xg", 0) for s in shots["opp"]),  3)
    if xg_roma == 0 and xg_opp == 0:
        xg_roma = stats.pop("xg_roma", 0)
        xg_opp  = stats.pop("xg_opp",  0)
    else:
        stats.pop("xg_roma", None)
        stats.pop("xg_opp",  None)

    finished = data.get("header", {}).get("status", {}).get("finished", False)

    return {
        "source":      "fotmob",
        "match_id":    general.get("matchId", 0),
        "fotmob_id":   general.get("matchId", 0),
        "home_team":   home_name,
        "away_team":   away_name,
        "home_score":  home_score,
        "away_score":  away_score,
        "roma_score":  roma_score,
        "opp_score":   opp_score,
        "opponent":    opponent,
        "is_home":     is_home,
        "competition": general.get("leagueName", ""),
        "round":       general.get("leagueRoundName", ""),
        "date":        match_date,
        "start_ts":    start_ts,
        "venue":       general.get("venueName", ""),
        "status":      "finished" if finished else "live",
        "xg_roma":     xg_roma,
        "xg_opp":      xg_opp,
        "shots_roma":  shots["roma"],
        "shots_opp":   shots["opp"],
        **stats,
    }


def _fotmob_parse_stats(data: dict, is_home_roma: bool) -> dict:
    result = {
        "possession_roma": 0, "possession_opp": 0,
        "shots_total_roma": 0, "shots_total_opp": 0,
        "shots_on_target_roma": 0, "shots_on_target_opp": 0,
        "big_chances_roma": 0, "big_chances_opp": 0,
        "passes_roma": 0, "passes_opp": 0,
        "accurate_passes_pct_roma": 0, "accurate_passes_pct_opp": 0,
        "corners_roma": 0, "corners_opp": 0,
        "fouls_roma": 0, "fouls_opp": 0,
        "yellow_roma": 0, "yellow_opp": 0,
        "red_roma": 0, "red_opp": 0,
        "xg_roma": 0, "xg_opp": 0,
        "xgot_roma": 0, "xgot_opp": 0,
    }
    name_map = {
        "possession":          ("possession_roma",          "possession_opp"),
        "total shots":         ("shots_total_roma",         "shots_total_opp"),
        "shots on target":     ("shots_on_target_roma",     "shots_on_target_opp"),
        "big chances":         ("big_chances_roma",         "big_chances_opp"),
        "passes":              ("passes_roma",              "passes_opp"),
        "accurate passes %":   ("accurate_passes_pct_roma", "accurate_passes_pct_opp"),
        "corner kicks":        ("corners_roma",             "corners_opp"),
        "fouls":               ("fouls_roma",               "fouls_opp"),
        "yellow cards":        ("yellow_roma",              "yellow_opp"),
        "red cards":           ("red_roma",                 "red_opp"),
        "expected goals (xg)": ("xg_roma",                  "xg_opp"),
        "xg":                  ("xg_roma",                  "xg_opp"),
        "xgot":                ("xgot_roma",                "xgot_opp"),
    }
    try:
        groups = data.get("content", {}).get("stats", {}).get("stats", [])
        for group in groups:
            for stat in group.get("stats", []):
                title = stat.get("title", "").lower().strip()
                vals  = stat.get("stats", [])
                if isinstance(vals, list) and len(vals) >= 2:
                    h_val, a_val = vals[0], vals[1]
                else:
                    h_val = stat.get("homeValue", "0")
                    a_val = stat.get("awayValue", "0")
                if title in name_map:
                    r_key, o_key = name_map[title]
                    try:
                        hv = float(str(h_val).replace("%", "").replace(",", ".") or 0)
                        av = float(str(a_val).replace("%", "").replace(",", ".") or 0)
                        result[r_key] = hv if is_home_roma else av
                        result[o_key] = av if is_home_roma else hv
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Stats parse error: {e}")
    return result


def _fotmob_parse_shots(data: dict) -> dict:
    """
    Estrae i tiri dal shot map Fotmob.
    Ogni tiro include expectedGoals (xG) e expectedGoalsOnTarget (xGoT).
    """
    roma_shots, opp_shots = [], []
    try:
        raw = data.get("content", {}).get("shotmap", {}).get("shots", [])
    except Exception:
        return {"roma": [], "opp": []}

    for s in raw:
        team_id  = int(s.get("teamId", 0) or 0)
        is_roma  = (team_id == ROMA_FOTMOB_ID)
        shot = {
            "x":          float(s.get("x", 50) or 50),
            "y":          float(s.get("y", 50) or 50),
            "xg":         float(s.get("expectedGoals", 0) or 0),
            "xgot":       float(s.get("expectedGoalsOnTarget", 0) or 0),
            "player":     s.get("playerName", ""),
            "minute":     int(s.get("min", 0) or 0),
            "result":     s.get("eventType", ""),
            "is_goal":    s.get("eventType", "") == "Goal",
            "is_blocked": s.get("isBlocked", False),
            "on_target":  s.get("isOnTarget", False),
            "situation":  s.get("situation", ""),
            "shot_type":  s.get("shotType", ""),
            "period":     s.get("period", ""),
        }
        if is_roma:
            roma_shots.append(shot)
        else:
            opp_shots.append(shot)

    return {"roma": roma_shots, "opp": opp_shots}


def fotmob_get_season_matches(team_id: int = ROMA_FOTMOB_ID) -> List[dict]:
    """Tutte le partite completate della stagione corrente."""
    data = fotmob_get_team_fixtures(team_id)
    if not data:
        return []
    result = []
    for m in data.get("fixtures", {}).get("allMatches", []):
        if not m.get("status", {}).get("finished", False):
            continue
        home = m.get("home", {})
        away = m.get("away", {})
        is_h = int(home.get("id", 0) or 0) == team_id
        ss   = m.get("status", {}).get("scoreStr", "0-0")
        try:
            hs, as_ = [int(x) for x in ss.split("-")]
        except Exception:
            hs = as_ = 0
        result.append({
            "fotmob_id": m.get("id"),
            "date":      m.get("status", {}).get("utcTime", "")[:10],
            "home_team": home.get("name", ""),
            "away_team": away.get("name", ""),
            "home_score": hs,
            "away_score": as_,
            "is_home":   is_h,
            "opponent":  away.get("name","") if is_h else home.get("name",""),
        })
    return result


def fotmob_get_form(team_id: int = ROMA_FOTMOB_ID, n: int = 5) -> List[str]:
    """Ultimi N risultati come lista ['W','D','L',...]."""
    matches = fotmob_get_season_matches(team_id)
    if not matches:
        return []
    matches.sort(key=lambda m: m.get("date", ""), reverse=True)
    form = []
    for m in matches[:n]:
        is_h = m.get("is_home", True)
        rs   = m["home_score"] if is_h else m["away_score"]
        os   = m["away_score"] if is_h else m["home_score"]
        if rs > os:   form.append("W")
        elif rs == os: form.append("D")
        else:          form.append("L")
    return list(reversed(form))


def fotmob_get_next_match(team_id: int = ROMA_FOTMOB_ID) -> Optional[dict]:
    """Prossima partita non giocata."""
    data = fotmob_get_team_fixtures(team_id)
    if not data:
        return None
    upcoming = [
        m for m in data.get("fixtures", {}).get("allMatches", [])
        if not m.get("status", {}).get("finished", False)
           and not m.get("status", {}).get("cancelled", False)
    ]
    if not upcoming:
        return None
    upcoming.sort(key=lambda m: m.get("status", {}).get("utcTime", ""))
    m    = upcoming[0]
    home = m.get("home", {})
    away = m.get("away", {})
    is_h = int(home.get("id", 0) or 0) == team_id
    utc  = m.get("status", {}).get("utcTime", "")
    try:
        dt         = datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S")
        match_date = dt.strftime("%d/%m/%Y")
        start_ts   = int(dt.timestamp())
    except Exception:
        match_date = utc[:10]
        start_ts   = 0
    return {
        "fotmob_id":   m.get("id"),
        "home_team":   home.get("name", ""),
        "away_team":   away.get("name", ""),
        "is_home":     is_h,
        "opponent":    away.get("name","") if is_h else home.get("name",""),
        "competition": m.get("leagueName", ""),
        "date":        match_date,
        "start_ts":    start_ts,
    }


def fotmob_avg_xg_last_n(team_id: int = ROMA_FOTMOB_ID, n: int = 5) -> float:
    """
    xG medio delle ultime N partite (richiede N chiamate matchDetails).
    Usa con parsimonia nel pre-match workflow.
    """
    matches = fotmob_get_season_matches(team_id)
    matches.sort(key=lambda m: m.get("date",""), reverse=True)
    vals = []
    for m in matches[:n]:
        mid = m.get("fotmob_id")
        if not mid:
            continue
        raw = fotmob_get_match_details(mid)
        if not raw:
            continue
        parsed = fotmob_parse_match(raw)
        xg = parsed.get("xg_roma", 0)
        if xg > 0:
            vals.append(xg)
        time.sleep(2)
    return round(sum(vals) / len(vals), 3) if vals else 0.0


# ══════════════════════════════════════════════════════════════════
# SOFASCORE  — player ratings, formazioni
# ══════════════════════════════════════════════════════════════════

SS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}


def sofascore_last_match(team_id: int = ROMA_SOFASCORE_ID) -> Optional[dict]:
    """Ultimo evento da SofaScore (per recuperare il SS match ID)."""
    url = f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0"
    try:
        r = requests.get(url, headers=SS_HEADERS, timeout=15)
        r.raise_for_status()
        events = r.json().get("events", [])
        return events[-1] if events else None
    except Exception as e:
        logger.error(f"SofaScore last match: {e}")
    return None


def sofascore_player_ratings(ss_match_id: int) -> List[dict]:
    """
    Rating giocatori da SofaScore.
    Lista ordinata per rating decrescente.
    """
    url = f"https://api.sofascore.com/api/v1/event/{ss_match_id}/lineups"
    try:
        r = requests.get(url, headers=SS_HEADERS, timeout=15)
        r.raise_for_status()
        players = []
        for side in ("home", "away"):
            for p in r.json().get(side, {}).get("players", []):
                pd_ = p.get("player", {})
                st  = p.get("statistics", {})
                rtg = st.get("rating")
                if rtg:
                    players.append({
                        "name":      pd_.get("name", ""),
                        "shortName": pd_.get("shortName", pd_.get("name", "")),
                        "team":      side,
                        "rating":    float(rtg),
                        "position":  p.get("position", ""),
                        "minutes":   st.get("minutesPlayed", 90),
                    })
        return sorted(players, key=lambda x: x["rating"], reverse=True)
    except Exception as e:
        logger.error(f"SofaScore ratings: {e}")
    return []


def sofascore_next_match(team_id: int = ROMA_SOFASCORE_ID) -> Optional[dict]:
    """Prossima partita da SofaScore (fallback se Fotmob non disponibile)."""
    url = f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0"
    try:
        r = requests.get(url, headers=SS_HEADERS, timeout=15)
        r.raise_for_status()
        events = r.json().get("events", [])
        if not events:
            return None
        e    = events[0]
        home = e.get("homeTeam", {})
        away = e.get("awayTeam", {})
        ts   = e.get("startTimestamp", 0)
        is_h = home.get("id") == team_id
        return {
            "sofascore_id": e.get("id"),
            "home_team":    home.get("name", ""),
            "away_team":    away.get("name", ""),
            "is_home":      is_h,
            "opponent":     away.get("name","") if is_h else home.get("name",""),
            "competition":  e.get("tournament", {}).get("name", ""),
            "date":         datetime.utcfromtimestamp(ts).strftime("%d/%m/%Y") if ts else "",
            "start_ts":     ts,
        }
    except Exception as e:
        logger.error(f"SofaScore next: {e}")
    return None


# ══════════════════════════════════════════════════════════════════
# FOOTBALL-DATA.CO.UK  — storico Serie A 2000→oggi (CSV)
# ══════════════════════════════════════════════════════════════════

FD_BASE = "https://www.football-data.co.uk/mmz4281"


def fd_season_csv(season_code: str) -> List[dict]:
    """
    CSV stagione Serie A.
    Codice: '2425'=2024/25, '2324'=2023/24, '0001'=2000/01, ecc.
    Colonne: HomeTeam, AwayTeam, FTHG, FTAG, FTR, HS, AS, HST, AST
    """
    url = f"{FD_BASE}/{season_code}/I1.csv"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return [row for row in csv.DictReader(io.StringIO(r.text)) if row.get("HomeTeam")]
    except Exception as e:
        logger.error(f"football-data {season_code}: {e}")
    return []


def fd_roma_record(season_code: str, team: str = "Roma") -> Optional[dict]:
    """Record stagionale Roma da football-data.co.uk."""
    rows = fd_season_csv(season_code)
    if not rows:
        return None
    w = d = l = gf = ga = sf = sa = stf = sta = 0
    for row in rows:
        ht, at = row.get("HomeTeam",""), row.get("AwayTeam","")
        ftr = row.get("FTR","")
        try:
            hg, ag  = int(row["FTHG"]), int(row["FTAG"])
            hs, as_ = int(row.get("HS",0) or 0), int(row.get("AS",0) or 0)
            hst,ast = int(row.get("HST",0) or 0), int(row.get("AST",0) or 0)
        except Exception:
            continue
        if ht == team:
            gf+=hg; ga+=ag; sf+=hs; sa+=as_; stf+=hst; sta+=ast
            if ftr=="H": w+=1
            elif ftr=="D": d+=1
            else: l+=1
        elif at == team:
            gf+=ag; ga+=hg; sf+=as_; sa+=hs; stf+=ast; sta+=hst
            if ftr=="A": w+=1
            elif ftr=="D": d+=1
            else: l+=1
    games = w+d+l
    if not games:
        return None
    return {
        "season": season_code, "games": games,
        "wins": w, "draws": d, "losses": l,
        "goals_for": gf, "goals_against": ga, "goal_diff": gf-ga,
        "points": w*3+d, "ppg": round((w*3+d)/games, 3),
        "shots_for": sf, "shots_against": sa,
        "sot_for": stf, "sot_against": sta,
        "shot_accuracy": round(stf/sf*100, 1) if sf else 0,
    }


def fd_build_history(start_year: int = 2000) -> List[dict]:
    """Serie storica completa Roma in Serie A dal start_year."""
    end_year = datetime.utcnow().year
    records  = []
    for yr in range(start_year, end_year):
        code = f"{str(yr)[-2:]}{str(yr+1)[-2:]}"
        rec  = fd_roma_record(code)
        if rec:
            rec["season_label"] = f"{yr}/{str(yr+1)[-2:]}"
            rec["season_start"] = yr
            records.append(rec)
        time.sleep(0.8)
    logger.info(f"History: {len(records)} stagioni")
    return records


def fd_h2h(opponent: str, last_n: int = 5) -> dict:
    """Record H2H Roma vs avversario nelle ultime N stagioni."""
    now = datetime.utcnow()
    cur = now.year if now.month >= 7 else now.year - 1
    w = d = l = 0
    for yr in range(cur, cur - last_n, -1):
        code = f"{str(yr)[-2:]}{str(yr+1)[-2:]}"
        for row in fd_season_csv(code):
            ht, at = row.get("HomeTeam",""), row.get("AwayTeam","")
            ftr    = row.get("FTR","")
            if not ((ht=="Roma" and at==opponent) or (ht==opponent and at=="Roma")):
                continue
            if (ht=="Roma" and ftr=="H") or (at=="Roma" and ftr=="A"): w+=1
            elif ftr=="D": d+=1
            else: l+=1
        time.sleep(0.5)
    return {"opponent": opponent, "roma_wins": w, "draws": d, "opp_wins": l, "total": w+d+l}


# ══════════════════════════════════════════════════════════════════
# TRANSFERMARKT  — valori di mercato rosa
# ══════════════════════════════════════════════════════════════════

TM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.transfermarkt.com/",
}


def tm_squad_value(season_id: int = 2024) -> dict:
    """Valore rosa Roma da Transfermarkt (web scraping)."""
    url = (
        f"https://www.transfermarkt.com/as-rom/kader/verein/12"
        f"/saison_id/{season_id}/plus/1"
    )
    result = {"total_value": "N/A", "players": [], "fetched_at": ""}
    try:
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=TM_HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        total_el = (
            soup.select_one(".transfer-record__total") or
            soup.select_one("[data-market-value]")
        )
        if total_el:
            result["total_value"] = total_el.get_text(strip=True)

        players = []
        for row in soup.select(".items tbody tr")[:25]:
            name_el  = row.select_one(".hauptlink a")
            value_el = row.select_one(".rechts.hauptlink")
            if name_el and value_el:
                players.append({
                    "name":  name_el.get_text(strip=True),
                    "value": value_el.get_text(strip=True),
                })
        result["players"]    = players
        result["fetched_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        logger.error(f"Transfermarkt: {e}")
    return result
