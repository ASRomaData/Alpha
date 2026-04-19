"""
ASRomaData Bot — Post-Match Orchestrator
Pipeline: SofaScore (stats + xG + shotmap + ratings) → Visual → AI → Pubblica → Storico
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.fetch_data import (
    ROMA_ID,
    get_last_match,
    parse_event,
    get_match_statistics,
    parse_match_statistics,
    get_shot_map,
    split_shots,
    xg_from_shots,
    get_player_ratings,
)
from bot.generate_visuals import generate_match_card, generate_shot_map
from bot.ai_narrative import (
    generate_post_match_thread,
    generate_instagram_caption,
    detect_and_narrate_record,
)
from bot.publishers import publish_to_all_platforms
from bot.update_history import load_history, update_match_history, check_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DATA_DIR    = Path("data")
VISUALS_DIR = Path("visuals")
DATA_DIR.mkdir(exist_ok=True)
VISUALS_DIR.mkdir(exist_ok=True)

WINDOW_BEFORE_MIN = 60
WINDOW_AFTER_MIN  = 180

FINISHED_STATUSES = ("finished", "ended", "afterpenalties", "aet")


def in_window(start_ts: int) -> bool:
    now = datetime.utcnow().timestamp()
    return (start_ts - WINDOW_BEFORE_MIN * 60) <= now <= (start_ts + WINDOW_AFTER_MIN * 60)


def run_post_match(force: bool = False):
    logger.info("═══ ASRomaData Bot — Post-Match ═══")

    # ── 1. Ultima partita Roma da SofaScore ───────────────────────
    logger.info("SofaScore: cerca ultima partita Roma...")
    event = get_last_match(ROMA_ID)
    if not event:
        logger.error("Nessuna partita trovata su SofaScore")
        sys.exit(1)

    match    = parse_event(event)
    match_id = match["match_id"]
    is_home  = match["is_home"]

    logger.info(
        f"Partita: {match['home_team']} {match['home_score']}-"
        f"{match['away_score']} {match['away_team']} "
        f"[{match['status']}] id={match_id}"
    )

    # ── Controllo stato + finestra temporale ──────────────────────
    if not force:
        if match.get("status") not in FINISHED_STATUSES:
            logger.info("Partita non terminata. Usa --force per override.")
            sys.exit(0)
        if not in_window(match.get("start_ts", 0)):
            logger.info("Fuori finestra temporale (-1h/+3h). Usa --force.")
            sys.exit(0)

    state_file = DATA_DIR / "last_match.json"
    if state_file.exists() and not force:
        with open(state_file) as f:
            prev = json.load(f)
        if str(prev.get("last_match_id")) == str(match_id):
            logger.info("Partita già pubblicata. Skip.")
            sys.exit(0)

    # ── 2. Statistiche + xG ───────────────────────────────────────
    logger.info(f"SofaScore: statistiche match {match_id}...")
    stats = {}
    xg_data = {"xg_roma": 0.0, "xg_opp": 0.0}

    raw_stats = get_match_statistics(match_id)
    if raw_stats:
        parsed = parse_match_statistics(raw_stats, is_home)
        stats = {
            "possession_roma":       parsed.get("possession_roma", 50),
            "possession_opp":        parsed.get("possession_opp",  50),
            "shots_roma":            parsed.get("shots_roma", 0),
            "shots_opp":             parsed.get("shots_opp",  0),
            "shots_on_target_roma":  parsed.get("shots_on_target_roma", 0),
            "shots_on_target_opp":   parsed.get("shots_on_target_opp",  0),
            "passes_roma":           parsed.get("passes_roma", 0),
            "passes_opp":            parsed.get("passes_opp",  0),
            "corners_roma":          parsed.get("corners_roma", 0),
            "corners_opp":           parsed.get("corners_opp",  0),
            "fouls_roma":            parsed.get("fouls_roma", 0),
            "fouls_opp":             parsed.get("fouls_opp",  0),
            "yellow_roma":           parsed.get("yellow_roma", 0),
            "yellow_opp":            parsed.get("yellow_opp",  0),
        }
        xg_data = {
            "xg_roma": parsed.get("xg_roma", 0.0),
            "xg_opp":  parsed.get("xg_opp",  0.0),
        }
        logger.info(
            f"xG Roma: {xg_data['xg_roma']:.2f} | "
            f"xG Opp: {xg_data['xg_opp']:.2f} | "
            f"Possesso: {stats.get('possession_roma', 50):.0f}%"
        )
    else:
        logger.warning("Statistiche non disponibili su SofaScore")

    # ── 3. Shot map ───────────────────────────────────────────────
    logger.info(f"SofaScore: shot map match {match_id}...")
    roma_shots: list = []
    opp_shots:  list = []

    raw_shots = get_shot_map(match_id)
    if raw_shots:
        split      = split_shots(raw_shots, is_home)
        roma_shots = split["roma"]
        opp_shots  = split["opp"]

        # Se xG da statistics è 0, prova a calcolarlo dalla shotmap
        if xg_data["xg_roma"] == 0:
            xg_data["xg_roma"] = xg_from_shots(roma_shots)["xg"]
        if xg_data["xg_opp"] == 0:
            xg_data["xg_opp"] = xg_from_shots(opp_shots)["xg"]

        logger.info(f"Tiri Roma: {len(roma_shots)} | Tiri Opp: {len(opp_shots)}")
    else:
        logger.warning("Shot map non disponibile")

    # Merge shots nel dict match per compatibilità con generate_visuals
    match["shots_roma"] = roma_shots
    match["shots_opp"]  = opp_shots

    # ── 4. Player ratings ─────────────────────────────────────────
    logger.info(f"SofaScore: rating giocatori match {match_id}...")
    top_players = []
    try:
        players = get_player_ratings(match_id)
        if players:
            # Filtra solo giocatori Roma (side corretto)
            roma_side  = "home" if is_home else "away"
            top_players = [p for p in players if p.get("side") == roma_side][:5]
            logger.info(f"Ratings Roma: {len(top_players)} giocatori")
    except Exception as e:
        logger.warning(f"Player ratings failed (non critico): {e}")

    # ── 5. Genera visual ─────────────────────────────────────────
    logger.info("Generazione visual...")
    mid_str       = str(match_id)
    card_path     = None
    shot_map_path = None

    try:
        card_path = generate_match_card(
            match=match, stats=stats, xg_data=xg_data,
            top_players=top_players,
            filename=f"match_card_{mid_str}.png",
        )
        logger.info(f"Match card: {card_path}")
    except Exception as e:
        logger.warning(f"Match card failed: {e}")

    if roma_shots or opp_shots:
        try:
            shot_map_path = generate_shot_map(
                shots_data={"roma": roma_shots, "opp": opp_shots},
                home_team=match["home_team"],
                away_team=match["away_team"],
                is_home_roma=is_home,
                match_label=(
                    f"{match['home_team']} {match['home_score']}"
                    f"-{match['away_score']} {match['away_team']}"
                ),
                filename=f"shot_map_{mid_str}.png",
            )
            logger.info(f"Shot map: {shot_map_path}")
        except Exception as e:
            logger.warning(f"Shot map failed: {e}")

    # ── 6. Record storici ─────────────────────────────────────────
    history      = load_history()
    record_tweet = None
    try:
        records = check_records(match, stats, xg_data, history)
        if records:
            record_tweet = detect_and_narrate_record(
                event_type=records[0]["type"],
                value=records[0]["value"],
                historical_data=history.get("season_summary", {}),
            )
            if record_tweet:
                logger.info(f"Record: {record_tweet[:70]}...")
    except Exception as e:
        logger.warning(f"Record check: {e}")

    # ── 7. AI narrative (Groq) ────────────────────────────────────
    logger.info("Groq: generazione narrative...")
    x_thread = generate_post_match_thread(
        match=match, stats=stats, xg_data=xg_data,
        top_players=top_players,
        history_context=record_tweet,
    )
    ig_caption = generate_instagram_caption(
        match=match, stats=stats, xg_data=xg_data,
    )
    if record_tweet:
        x_thread.append(record_tweet)

    bsky_text = x_thread[0] if x_thread else (
        f"{match['home_team']} {match['home_score']}-"
        f"{match['away_score']} {match['away_team']} | "
        f"xG {xg_data['xg_roma']:.2f}–{xg_data['xg_opp']:.2f}"
    )
    logger.info(f"Thread X: {len(x_thread)} tweet")

    # ── 8. Pubblica ───────────────────────────────────────────────
    logger.info("Pubblicazione...")
    results = publish_to_all_platforms(
        image_path=card_path,
        x_thread=x_thread,
        ig_caption=ig_caption,
        bsky_text=bsky_text,
    )
    logger.info(f"Risultati: {results}")

    # ── 9. Aggiorna serie storica ─────────────────────────────────
    try:
        update_match_history(match, stats, xg_data, history)
        logger.info("History aggiornata")
    except Exception as e:
        logger.warning(f"History update: {e}")

    # ── 10. Salva stato ───────────────────────────────────────────
    state = {
        "last_match_id":    match_id,
        "last_match_date":  match.get("date", ""),
        "last_match_label": (
            f"{match['home_team']} {match['home_score']}-"
            f"{match['away_score']} {match['away_team']}"
        ),
        "published_at": datetime.utcnow().isoformat(),
        "results":      results,
    }
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    logger.info("═══ Pipeline completata ═══")
    return results


# Alias called by main.py CLI
def run(force: bool = False, half_time: bool = False):
    run_post_match(force=force)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force",     action="store_true", help="Ignora finestra temporale e stato")
    ap.add_argument("--half-time", action="store_true", help="Pubblica stats primo tempo")
    args = ap.parse_args()
    run_post_match(force=args.force)
