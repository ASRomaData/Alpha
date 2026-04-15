"""
ASRomaData Bot — Post-Match Orchestrator
Pipeline: Fotmob (xG+stats) → SofaScore (ratings) → Visual → AI → Pubblica → Storico
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.fetch_data import (
    fotmob_get_last_match_id, fotmob_get_match_details, fotmob_parse_match,
    sofascore_last_match, sofascore_player_ratings,
    ROMA_SOFASCORE_ID, ROMA_FOTMOB_ID,
)
from bot.generate_visuals import generate_match_card, generate_shot_map
from bot.ai_narrative import (
    generate_post_match_thread, generate_instagram_caption,
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


def in_window(start_ts: int) -> bool:
    now = datetime.utcnow().timestamp()
    return (start_ts - WINDOW_BEFORE_MIN * 60) <= now <= (start_ts + WINDOW_AFTER_MIN * 60)


def run_post_match(force: bool = False):
    logger.info("═══ ASRomaData Bot — Post-Match ═══")

    # ── 1. Fotmob: ultima partita completata ──────────────────────
    logger.info("Fotmob: cerca ultima partita Roma...")
    fotmob_id = fotmob_get_last_match_id(ROMA_FOTMOB_ID)
    if not fotmob_id:
        logger.error("Nessuna partita trovata su Fotmob")
        sys.exit(1)

    raw = fotmob_get_match_details(fotmob_id)
    if not raw:
        logger.error(f"Fotmob matchDetails vuoto per id={fotmob_id}")
        sys.exit(1)

    match = fotmob_parse_match(raw)
    logger.info(
        f"Partita: {match['home_team']} {match['home_score']}-"
        f"{match['away_score']} {match['away_team']} [{match['status']}]"
    )

    # Controllo stato + finestra temporale
    if not force:
        if match.get("status") not in ("finished",):
            logger.info("Partita non terminata. Usa --force per override.")
            sys.exit(0)
        if not in_window(match.get("start_ts", 0)):
            logger.info("Fuori finestra temporale (-1h/+3h). Usa --force.")
            sys.exit(0)

    # Controlla se abbiamo già pubblicato questa partita
    state_file = DATA_DIR / "last_match.json"
    if state_file.exists() and not force:
        with open(state_file) as f:
            prev = json.load(f)
        if str(prev.get("last_fotmob_id")) == str(fotmob_id):
            logger.info("Partita già pubblicata. Skip.")
            sys.exit(0)

    # ── 2. SofaScore: rating giocatori ───────────────────────────
    logger.info("SofaScore: rating giocatori...")
    top_players = []
    try:
        ss_event = sofascore_last_match(ROMA_SOFASCORE_ID)
        if ss_event:
            ss_id   = ss_event.get("id")
            top_players = sofascore_player_ratings(ss_id)
            logger.info(f"Ratings: {len(top_players)} giocatori")
    except Exception as e:
        logger.warning(f"SofaScore ratings failed (non critico): {e}")

    # ── 3. Costruisce stats dict compatibile con generate_visuals ─
    stats = {
        "possession_roma":      match.get("possession_roma", 0),
        "possession_opp":       match.get("possession_opp",  0),
        "shots_roma":           match.get("shots_total_roma", 0),
        "shots_opp":            match.get("shots_total_opp",  0),
        "shots_on_target_roma": match.get("shots_on_target_roma", 0),
        "shots_on_target_opp":  match.get("shots_on_target_opp",  0),
        "passes_roma":          match.get("passes_roma", 0),
        "passes_opp":           match.get("passes_opp",  0),
        "corners_roma":         match.get("corners_roma", 0),
        "corners_opp":          match.get("corners_opp",  0),
        "fouls_roma":           match.get("fouls_roma", 0),
        "fouls_opp":            match.get("fouls_opp",  0),
        "yellow_roma":          match.get("yellow_roma", 0),
        "yellow_opp":           match.get("yellow_opp",  0),
    }
    xg_data = {
        "xg_roma": match.get("xg_roma", 0),
        "xg_opp":  match.get("xg_opp",  0),
    }

    logger.info(
        f"xG Roma: {xg_data['xg_roma']:.2f} | "
        f"xG Opp: {xg_data['xg_opp']:.2f} | "
        f"Possesso: {stats['possession_roma']:.0f}%"
    )

    # ── 4. Genera visual ─────────────────────────────────────────
    logger.info("Generazione visual...")
    card_path     = None
    shot_map_path = None
    mid_str       = str(fotmob_id)

    try:
        card_path = generate_match_card(
            match=match, stats=stats, xg_data=xg_data,
            top_players=top_players,
            filename=f"match_card_{mid_str}.png",
        )
        logger.info(f"Match card: {card_path}")
    except Exception as e:
        logger.warning(f"Match card failed: {e}")

    # Shot map solo se abbiamo tiri con coordinate
    roma_shots = match.get("shots_roma", [])
    opp_shots  = match.get("shots_opp",  [])
    if roma_shots or opp_shots:
        try:
            shot_map_path = generate_shot_map(
                shots_data={"roma": roma_shots, "opp": opp_shots},
                home_team=match["home_team"],
                away_team=match["away_team"],
                is_home_roma=match.get("is_home", True),
                match_label=(
                    f"{match['home_team']} {match['home_score']}"
                    f"-{match['away_score']} {match['away_team']}"
                ),
                filename=f"shot_map_{mid_str}.png",
            )
            logger.info(f"Shot map: {shot_map_path}")
        except Exception as e:
            logger.warning(f"Shot map failed: {e}")

    # ── 5. Controlla record storici ───────────────────────────────
    history = load_history()
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

    # ── 6. AI narrative (Groq) ────────────────────────────────────
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

    # ── 7. Pubblica ───────────────────────────────────────────────
    logger.info("Pubblicazione...")
    results = publish_to_all_platforms(
        image_path=card_path,
        x_thread=x_thread,
        ig_caption=ig_caption,
        bsky_text=bsky_text,
    )
    logger.info(f"Risultati: {results}")

    # ── 8. Aggiorna serie storica ─────────────────────────────────
    try:
        update_match_history(match, stats, xg_data, history)
        logger.info("History aggiornata")
    except Exception as e:
        logger.warning(f"History update: {e}")

    # ── 9. Salva stato ────────────────────────────────────────────
    state = {
        "last_fotmob_id":   fotmob_id,
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Ignora finestra temporale e stato")
    args = ap.parse_args()
    run_post_match(force=args.force)
