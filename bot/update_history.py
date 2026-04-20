"""
ASRomaData Bot — Historical Data Manager
Mantiene le serie storiche in data/history.json e data/season_YYYY.json
Rilevatore automatico di record e milestone.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

DATA_DIR     = Path("data")
HISTORY_FILE = DATA_DIR / "history.json"

DATA_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# LOAD / SAVE
# ──────────────────────────────────────────────────────────────────

def load_history() -> Dict:
    """Carica il file storia. Se non esiste, restituisce struttura vuota."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"History load error: {e}")
    return _empty_history()


def save_history(data: Dict) -> bool:
    """Salva il file storia."""
    try:
        data["last_updated"] = datetime.utcnow().isoformat()
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"History save error: {e}")
        return False


def _empty_history() -> Dict:
    return {
        "team": "AS Roma",
        "last_updated": "",
        "current_season": {},
        "season_summary": {},    # chiave: "2024/25", valore: {...}
        "matches": [],           # lista di tutte le partite registrate
        "records": {
            "most_points_season": 0,
            "most_xg_season":     0,
            "consecutive_wins":   0,
            "consecutive_unbeaten": 0,
        },
        "streaks": {
            "current_wins":      0,
            "current_draws":     0,
            "current_losses":    0,
            "current_unbeaten":  0,
        },
    }


# ──────────────────────────────────────────────────────────────────
# AGGIORNAMENTO DOPO OGNI PARTITA
# ──────────────────────────────────────────────────────────────────

def update_match_history(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict],
    history: Dict,
) -> Dict:
    """
    Aggiunge la partita appena giocata al database storico.
    Aggiorna streak, stagione corrente, etc.
    """
    match_id = str(match.get("match_id", ""))

    # Evita duplicati
    existing_ids = {str(m.get("match_id")) for m in history.get("matches", [])}
    if match_id in existing_ids:
        logger.info(f"Partita {match_id} già presente in history, skip.")
        return history

    # Determina risultato Roma
    roma_score = match.get("roma_score", 0)
    opp_score  = match.get("opp_score", 0)
    if roma_score > opp_score:
        result = "W"
    elif roma_score == opp_score:
        result = "D"
    else:
        result = "L"

    # Costruisce record partita
    record = {
        "match_id":    match_id,
        "date":        match.get("date", ""),
        "opponent":    match.get("opponent", ""),
        "is_home":     match.get("is_home", True),
        "competition": match.get("competition", ""),
        "roma_score":  roma_score,
        "opp_score":   opp_score,
        "result":      result,
        "xg_roma":     xg_data.get("xg_roma", 0) if xg_data else None,
        "xg_opp":      xg_data.get("xg_opp", 0)  if xg_data else None,
        "possession":  stats.get("possession_roma", 0),
        "shots":       stats.get("shots_roma", 0),
        "shots_opp":   stats.get("shots_opp", 0),
        "season":      _current_season_label(),
    }

    history.setdefault("matches", []).append(record)

    # ─── Aggiorna streak ─────────────────────────────────────────
    streaks = history.setdefault("streaks", {
        "current_wins": 0, "current_draws": 0,
        "current_losses": 0, "current_unbeaten": 0,
    })
    if result == "W":
        streaks["current_wins"] += 1
        streaks["current_losses"] = 0
        streaks["current_unbeaten"] += 1
        streaks["current_draws"] = 0
    elif result == "D":
        streaks["current_wins"] = 0
        streaks["current_draws"] += 1
        streaks["current_unbeaten"] += 1
        streaks["current_losses"] = 0
    else:
        streaks["current_wins"] = 0
        streaks["current_draws"] = 0
        streaks["current_losses"] += 1
        streaks["current_unbeaten"] = 0

    # Aggiorna record streak
    records = history.setdefault("records", {})
    records["consecutive_wins"]     = max(records.get("consecutive_wins", 0),
                                          streaks["current_wins"])
    records["consecutive_unbeaten"] = max(records.get("consecutive_unbeaten", 0),
                                          streaks["current_unbeaten"])

    # ─── Aggiorna riepilogo stagione corrente ─────────────────────
    season_label = _current_season_label()
    _cs_default = {
        "season": season_label,
        "games": 0, "wins": 0, "draws": 0, "losses": 0,
        "goals_for": 0, "goals_against": 0, "points": 0,
        "xg_total": 0.0, "xga_total": 0.0,
    }
    cs = history.get("current_season") or {}
    # Merge defaults for any missing keys (handles empty {} from init)
    for k, v in _cs_default.items():
        cs.setdefault(k, v)
    history["current_season"] = cs
    cs["games"] += 1
    cs["goals_for"]     += roma_score
    cs["goals_against"] += opp_score
    if result == "W":
        cs["wins"] += 1; cs["points"] += 3
    elif result == "D":
        cs["draws"] += 1; cs["points"] += 1
    else:
        cs["losses"] += 1
    if xg_data:
        cs["xg_total"]  += xg_data.get("xg_roma", 0) or 0
        cs["xga_total"] += xg_data.get("xg_opp", 0) or 0
    cs["ppg"]       = round(cs["points"] / cs["games"], 3)
    cs["xg_per_game"]  = round(cs["xg_total"] / cs["games"], 3) if cs.get("xg_total") else 0
    cs["xga_per_game"] = round(cs["xga_total"] / cs["games"], 3) if cs.get("xga_total") else 0

    save_history(history)
    logger.info(f"History aggiornata: {season_label} → {cs['games']} partite, {cs['points']} pt")
    return history


# ──────────────────────────────────────────────────────────────────
# RECORD DETECTOR
# ──────────────────────────────────────────────────────────────────

def check_records(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict],
    history: Dict,
) -> List[Dict]:
    """
    Controlla se l'ultima partita ha generato record o milestone.
    Returns lista di record trovati: [{type, value, description}]
    """
    found = []
    streaks = history.get("streaks", {})
    records = history.get("records", {})
    cs      = history.get("current_season", {})

    # Streak vittorie
    cw = streaks.get("current_wins", 0)
    if cw >= 3 and cw > records.get("consecutive_wins", 0):
        found.append({
            "type": "consecutive_wins",
            "value": cw,
            "description": f"{cw} vittorie consecutive"
        })

    # Streak imbattibilità
    cu = streaks.get("current_unbeaten", 0)
    if cu >= 5 and cu > records.get("consecutive_unbeaten", 0):
        found.append({
            "type": "consecutive_unbeaten",
            "value": cu,
            "description": f"{cu} partite senza sconfitta"
        })

    # xG alto in una singola partita
    if xg_data:
        xg_r = xg_data.get("xg_roma", 0) or 0
        if xg_r >= 3.0:
            found.append({
                "type": "high_xg_match",
                "value": xg_r,
                "description": f"xG {xg_r:.2f} — tra i più alti della stagione"
            })

    # Prima vittoria dopo una serie negativa
    losses_before = streaks.get("current_losses", 0)
    if match.get("result") == "W" and losses_before == 0:
        prev_matches = history.get("matches", [])[-6:-1]
        recent_losses = sum(1 for m in prev_matches if m.get("result") == "L")
        if recent_losses >= 3:
            found.append({
                "type": "win_after_losing_run",
                "value": recent_losses,
                "description": f"Prima vittoria dopo {recent_losses} sconfitte consecutive"
            })

    return found


# ──────────────────────────────────────────────────────────────────
# BULK LOAD: carica storico da football-data.co.uk (setup iniziale)
# ──────────────────────────────────────────────────────────────────

def build_historical_database(start_year: int = 2000):
    """
    Costruisce il database storico completo da zero.
    Fonte: football-data.co.uk (risultati Serie A dal 2000, CSV diretto).
    Eseguire UNA SOLA VOLTA per inizializzare le serie storiche.
    """
    from bot.fetch_data import fd_build_history

    logger.info(f"Building historical database from {start_year} (football-data.co.uk)...")

    history = _empty_history()

    records = fd_build_history(start_year=start_year)
    logger.info(f"Trovate {len(records)} stagioni")

    history["season_summary"] = {
        rec["season_label"]: rec for rec in records
    }

    if records:
        best_pts = max(records, key=lambda r: r["points"])
        history["records"]["most_points_season"] = best_pts["points"]
        history["records"]["best_season_label"]  = best_pts.get("season_label", "")
        best_gd  = max(records, key=lambda r: r["goal_diff"])
        history["records"]["best_goal_diff"]     = best_gd["goal_diff"]

    save_history(history)
    logger.info(f"Database storico salvato in {HISTORY_FILE}")
    return history


# ──────────────────────────────────────────────────────────────────
# ANNIVERSARY DETECTOR (per contenuto "on this day")
# ──────────────────────────────────────────────────────────────────

def find_anniversary_matches(history: Dict, days_tolerance: int = 2) -> List[Dict]:
    """
    Trova partite storiche che ricorrono oggi (±2 giorni).
    Utile per generare contenuto "X anni fa..."
    """
    today = datetime.utcnow()
    today_md = (today.month, today.day)

    anniversaries = []
    for match in history.get("matches", []):
        date_str = match.get("date", "")
        if not date_str:
            continue
        try:
            # Formato dd/mm/yyyy
            parts = date_str.split("/")
            if len(parts) == 3:
                md = int(parts[1]), int(parts[0])  # month, day
                if abs(md[0] - today_md[0]) <= 1 and abs(md[1] - today_md[1]) <= days_tolerance:
                    match_year = int(parts[2])
                    years_ago  = today.year - match_year
                    if years_ago >= 1:
                        anniversaries.append({**match, "years_ago": years_ago})
        except:
            continue

    # Ordina per partite più interessanti (vittorie, gol alti)
    anniversaries.sort(key=lambda m: (
        m.get("result") == "W",
        (m.get("roma_score", 0) or 0) + (m.get("opp_score", 0) or 0),
    ), reverse=True)

    return anniversaries[:3]


def _current_season_label() -> str:
    """Es.: 2024/25"""
    now = datetime.utcnow()
    year = now.year if now.month >= 7 else now.year - 1
    return f"{year}/{str(year+1)[-2:]}"
