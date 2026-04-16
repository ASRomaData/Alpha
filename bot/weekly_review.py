"""
ASRomaData Bot — Weekly Review
Trigger: ogni lunedì 09:00 UTC.
Aggrega dati della settimana dal database storico locale.
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from bot.update_history import load_history, _current_season_label
from bot.generate_visuals import generate_weekly_card, generate_points_history
from bot.ai_narrative import generate_weekly_narrative
from bot.publishers import publish_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")


def _week_matches(history: dict, days: int = 7) -> list:
    cutoff = datetime.utcnow() - timedelta(days=days)
    out = []
    for m in history.get("matches", []):
        ds = m.get("date", "")
        try:
            parts = ds.split("/")
            dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            if dt >= cutoff:
                out.append(m)
        except Exception:
            pass
    return sorted(out, key=lambda m: m.get("date", ""))


def run_weekly_review():
    logger.info("═══ ASRomaData Bot — Weekly Review ═══")

    history = load_history()
    week    = _week_matches(history, days=7)

    if not week:
        logger.info("Nessuna partita questa settimana. Skip.")
        sys.exit(0)

    logger.info(f"Partite settimana: {len(week)}")

    pts = gf = ga = 0
    total_xg = total_xga = shots = 0.0
    for m in week:
        r = m.get("result", "")
        if r == "W": pts += 3
        elif r == "D": pts += 1
        gf   += m.get("roma_score", 0) or 0
        ga   += m.get("opp_score",  0) or 0
        total_xg  += m.get("xg_roma", 0) or 0
        total_xga += m.get("xg_opp",  0) or 0
        shots += m.get("shots", 0) or 0

    now   = datetime.utcnow()
    label = f"{(now-timedelta(days=7)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}"

    week_data = {
        "week_label":      f"Settimana {label}",
        "games_played":    len(week),
        "points_won":      pts,
        "goals_for":       gf,
        "goals_against":   ga,
        "total_xg":        round(total_xg,  2),
        "total_xga":       round(total_xga, 2),
        "total_shots":     int(shots),
        "top_player":      {"name": "N/A", "rating": 0},
        "league_position": history.get("current_season", {}).get("league_position", "N/A"),
        "season":          _current_season_label(),
    }

    # Visual: weekly card
    card_path = None
    try:
        card_path = generate_weekly_card(week_data, filename="weekly_review.png")
        logger.info(f"Weekly card: {card_path}")
    except Exception as e:
        logger.warning(f"Weekly card failed: {e}")

    # Visual opzionale: punti storici
    try:
        ss = history.get("season_summary", {})
        seasons = sorted(ss.values(), key=lambda s: s.get("season_start", 0))
        pt_seasons = [s for s in seasons if "points" in s]
        if len(pt_seasons) >= 3:
            generate_points_history(
                pt_seasons,
                filename="points_weekly.png",
            )
    except Exception as e:
        logger.warning(f"Points chart: {e}")

    # AI narrative
    logger.info("Groq: narrative settimanale...")
    content    = generate_weekly_narrative(week_data)
    x_thread   = content.get("thread", [])
    ig_caption = content.get("caption", "")
    bsky_text  = x_thread[0] if x_thread else week_data["week_label"]

    # Pubblica
    logger.info("Pubblicazione weekly review...")
    results = publish_to_all_platforms(
        image_path=card_path,
        x_thread=x_thread,
        ig_caption=ig_caption,
        bsky_text=bsky_text,
    )
    logger.info(f"Risultati: {results}")


if __name__ == "__main__":
    run_weekly_review()
