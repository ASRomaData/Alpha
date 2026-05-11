"""
ASRomaData Bot — Historical Data Manager
==========================================
Mantiene data/history.json aggiornato dopo ogni partita.
Fonte storica: football-data.co.uk (build_full_history).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_HISTORY = Path("data/history.json")
_HISTORY.parent.mkdir(exist_ok=True)


def _empty() -> Dict:
    return {
        "team":         "AS Roma",
        "last_updated": "",
        "current_season": {
            "season": _season_label(), "games": 0, "wins": 0, "draws": 0, "losses": 0,
            "goals_for": 0, "goals_against": 0, "points": 0,
            "xg_total": 0.0, "xga_total": 0.0, "ppg": 0.0,
            "xg_per_game": 0.0, "xga_per_game": 0.0,
        },
        "season_summary": {},
        "matches":       [],
        "records":       {"most_points_season": 0, "consecutive_wins": 0,
                          "consecutive_unbeaten": 0},
        "streaks":       {"current_wins": 0, "current_draws": 0,
                          "current_losses": 0, "current_unbeaten": 0},
    }


def _season_label() -> str:
    now = datetime.utcnow()
    y   = now.year if now.month >= 7 else now.year - 1
    return f"{y}/{str(y+1)[-2:]}"


def load_history() -> Dict:
    if _HISTORY.exists():
        try:
            return json.loads(_HISTORY.read_text())
        except Exception as e:
            logger.error(f"History load: {e}")
    return _empty()


def save_history(data: Dict) -> bool:
    try:
        data["last_updated"] = datetime.utcnow().isoformat()
        _HISTORY.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        logger.error(f"History save: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# AGGIORNAMENTO POST-PARTITA
# ══════════════════════════════════════════════════════════════════════════════

def update_match_history(
    match: Dict, stats: Dict,
    xg_data: Optional[Dict], history: Dict,
) -> Dict:
    mid = str(match.get("match_id", ""))
    existing = {str(m.get("match_id")) for m in history.get("matches", [])}
    if mid in existing:
        logger.info(f"Match {mid} già in history, skip")
        return history

    rs = match.get("roma_score", 0)
    os_ = match.get("opp_score", 0)
    result = "W" if rs > os_ else "D" if rs == os_ else "L"

    record = {
        "match_id":    mid,
        "date":        match.get("date", ""),
        "opponent":    match.get("opponent", ""),
        "is_home":     match.get("is_home", True),
        "competition": match.get("competition", ""),
        "roma_score":  rs,
        "opp_score":   os_,
        "result":      result,
        "xg_roma":     stats.get("xg_roma", 0),
        "xg_opp":      stats.get("xg_opp", 0),
        "possession":  stats.get("possession_roma", 0),
        "shots":       stats.get("shots_roma", 0),
        "season":      _season_label(),
    }
    history.setdefault("matches", []).append(record)

    # Streaks
    streaks = history.setdefault("streaks", {
        "current_wins": 0, "current_draws": 0,
        "current_losses": 0, "current_unbeaten": 0,
    })
    if result == "W":
        streaks["current_wins"] += 1
        streaks["current_unbeaten"] += 1
        streaks["current_draws"] = streaks["current_losses"] = 0
    elif result == "D":
        streaks["current_draws"] += 1
        streaks["current_unbeaten"] += 1
        streaks["current_wins"] = streaks["current_losses"] = 0
    else:
        streaks["current_losses"] += 1
        streaks["current_wins"] = streaks["current_draws"] = streaks["current_unbeaten"] = 0

    recs = history.setdefault("records", {})
    recs["consecutive_wins"]     = max(recs.get("consecutive_wins", 0), streaks["current_wins"])
    recs["consecutive_unbeaten"] = max(recs.get("consecutive_unbeaten", 0), streaks["current_unbeaten"])

    # Stagione corrente
    cs = history.setdefault("current_season", _empty()["current_season"])
    cs["games"]          += 1
    cs["goals_for"]      += rs
    cs["goals_against"]  += os_
    if result == "W":   cs["wins"] += 1;  cs["points"] += 3
    elif result == "D": cs["draws"] += 1; cs["points"] += 1
    else:               cs["losses"] += 1
    xg_r = stats.get("xg_roma", 0) or 0
    xg_o = stats.get("xg_opp", 0) or 0
    cs["xg_total"]    += xg_r
    cs["xga_total"]   += xg_o
    cs["ppg"]          = round(cs["points"] / cs["games"], 3)
    cs["xg_per_game"]  = round(cs["xg_total"] / cs["games"], 3)
    cs["xga_per_game"] = round(cs["xga_total"] / cs["games"], 3)

    save_history(history)
    logger.info(f"History: {_season_label()} → {cs['games']}G {cs['points']}pt")
    return history


# ══════════════════════════════════════════════════════════════════════════════
# RECORD DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def check_records(
    match: Dict, stats: Dict,
    xg_data: Optional[Dict], history: Dict,
) -> List[Dict]:
    found   = []
    streaks = history.get("streaks", {})
    recs    = history.get("records", {})

    cw = streaks.get("current_wins", 0)
    if cw >= 3 and cw > recs.get("consecutive_wins", 0):
        found.append({"type": "consecutive_wins", "value": cw,
                      "description": f"{cw} vittorie consecutive"})

    cu = streaks.get("current_unbeaten", 0)
    if cu >= 5 and cu > recs.get("consecutive_unbeaten", 0):
        found.append({"type": "consecutive_unbeaten", "value": cu,
                      "description": f"{cu} partite senza sconfitta"})

    xg_r = stats.get("xg_roma", 0) or 0
    if xg_r >= 3.0:
        found.append({"type": "high_xg_match", "value": xg_r,
                      "description": f"xG {xg_r:.2f} — tra i più alti della stagione"})
    return found


# ══════════════════════════════════════════════════════════════════════════════
# BUILD STORICO (una tantum)
# ══════════════════════════════════════════════════════════════════════════════

def build_historical_database(start_year: int = 2000) -> Dict:
    """
    Scarica storico Serie A da football-data.co.uk e salva in history.json.
    Fonte unica: football-data.co.uk (CSV pubblici, User-Agent browser).
    """
    from bot.fetch_data import build_full_history

    logger.info(f"Building history from football-data.co.uk ({start_year}→oggi)...")
    history = _empty()

    records = build_full_history(start_year=start_year, team="Roma")
    logger.info(f"Stagioni trovate: {len(records)}")

    history["season_summary"] = {r["season_label"]: r for r in records}
    if records:
        best = max(records, key=lambda r: r["points"])
        history["records"]["most_points_season"] = best["points"]
        history["records"]["best_season_label"]  = best.get("season_label", "")

    save_history(history)
    logger.info(f"History salvata: {_HISTORY}")
    return history


# ══════════════════════════════════════════════════════════════════════════════
# ANNIVERSARY DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def find_anniversaries(history: Dict) -> List[Dict]:
    """Trova partite storiche che cadono oggi (±2 giorni)."""
    today = datetime.utcnow()
    out   = []
    for m in history.get("matches", []):
        try:
            d, mo, y = m["date"].split("/")
            if abs(int(mo) - today.month) <= 1 and abs(int(d) - today.day) <= 2:
                years_ago = today.year - int(y)
                if years_ago >= 1:
                    out.append({**m, "years_ago": years_ago})
        except Exception:
            continue
    out.sort(key=lambda m: (
        m.get("result") == "W",
        (m.get("roma_score", 0) or 0) + (m.get("opp_score", 0) or 0),
    ), reverse=True)
    return out[:3]


# Alias usato da weekly_review
_current_season_label = _season_label
