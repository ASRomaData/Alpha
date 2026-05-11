"""ASRomaData Bot — Weekly Review (ogni lunedì)"""
import logging, sys
from datetime import datetime, timedelta
from pathlib import Path
from bot.update_history import load_history, _current_season_label
from bot.generate_visuals import generate_weekly_card, generate_points_history
from bot.ai_narrative import generate_weekly_narrative
from bot.publishers import publish_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def _week_matches(history, days_back=7):
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    out = []
    for m in history.get("matches", []):
        try:
            d, mo, y = m["date"].split("/")
            if datetime(int(y), int(mo), int(d)) >= cutoff:
                out.append(m)
        except Exception:
            continue
    return sorted(out, key=lambda m: m.get("date", ""))

def run_weekly_review():
    logger.info("=== Weekly Review ===")
    history = load_history()
    matches = _week_matches(history)
    if not matches:
        logger.info("Nessuna partita questa settimana — skip"); sys.exit(0)

    pts = gf = ga = xg = xga = shots = 0
    for m in matches:
        r = m.get("result", "")
        if r == "W": pts += 3
        elif r == "D": pts += 1
        gf    += m.get("roma_score", 0) or 0
        ga    += m.get("opp_score", 0)  or 0
        xg    += m.get("xg_roma", 0)    or 0
        xga   += m.get("xg_opp", 0)     or 0
        shots += m.get("shots", 0)      or 0

    cs  = history.get("current_season", {})
    now = datetime.utcnow()
    week_data = {
        "week_label":      f"Settimana {(now-timedelta(7)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}",
        "games_played":    len(matches),
        "points_won":      pts,
        "goals_for":       gf,
        "goals_against":   ga,
        "total_xg":        round(xg, 2),
        "total_xga":       round(xga, 2),
        "total_shots":     shots,
        "league_position": cs.get("league_position", "N/A"),
        "season":          _current_season_label(),
    }

    card_path = None
    try:
        card_path = generate_weekly_card(week_data, filename="weekly_review.png")
    except Exception as e:
        logger.warning(f"Weekly card: {e}")

    # Grafico storico punti (se abbastanza dati)
    try:
        ss = history.get("season_summary", {})
        seasons = sorted(ss.values(), key=lambda s: s.get("season_start", 0))
        pt_seasons = [s for s in seasons if s.get("points", 0) > 0]
        if len(pt_seasons) >= 3:
            generate_points_history(pt_seasons, filename="points_weekly.png")
    except Exception as e:
        logger.warning(f"Points chart: {e}")

    content    = generate_weekly_narrative(week_data)
    x_thread   = content.get("thread", [])
    ig_caption = content.get("caption", "")
    bsky_text  = x_thread[0] if x_thread else week_data["week_label"]

    results = publish_to_all_platforms(image_path=card_path, x_thread=x_thread,
                                       ig_caption=ig_caption, bsky_text=bsky_text)
    logger.info(f"Weekly review: {results}")

if __name__ == "__main__":
    run_weekly_review()
