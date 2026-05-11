"""
ASRomaData Bot — Post-Match Pipeline
======================================
Fonte unica: SofaScore (risultato + stats + xG + shot map + ratings).
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.fetch_data import (
    get_last_match, get_match_statistics, get_player_ratings,
    get_shot_map, get_standings, get_roma_position,
    parse_event, parse_match_statistics, split_shots, xg_from_shots,
    ROMA_ID,
)
from bot.generate_visuals import generate_match_card, generate_shot_map
from bot.ai_narrative import (
    generate_post_match_thread, generate_instagram_caption,
    detect_and_narrate_record,
)
from bot.publishers import publish_to_all_platforms
from bot.update_history import load_history, update_match_history, check_records

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

Path("data").mkdir(exist_ok=True)
Path("visuals").mkdir(exist_ok=True)


def _in_window(start_ts: int, before: int = 60, after: int = 180) -> bool:
    now = datetime.utcnow().timestamp()
    return (start_ts - before * 60) <= now <= (start_ts + after * 60)


def run(force: bool = False, half_time: bool = False):
    logger.info("=== Post-Match Bot ===")

    # 1. Ultima partita
    event = get_last_match()
    if not event:
        logger.error("Nessuna partita da SofaScore"); sys.exit(1)
    match  = parse_event(event)
    logger.info(f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}")

    if not force:
        status = match.get("status", "")
        if status not in ("finished", "ended", "afterpenalties", "aet"):
            if not half_time:
                logger.info(f"Status={status} — skip (usa --force)"); sys.exit(0)
        if not _in_window(match["start_ts"]):
            logger.info("Fuori finestra — usa --force"); sys.exit(0)

    mid     = match["match_id"]
    is_home = match["is_home"]

    # 2. Statistiche + xG
    stats_raw = get_match_statistics(mid)
    stats     = parse_match_statistics(stats_raw, is_home) if stats_raw else {}
    logger.info(f"xG Roma: {stats.get('xg_roma',0):.2f} | xG Opp: {stats.get('xg_opp',0):.2f}")

    # 3. Shot map
    all_shots   = get_shot_map(mid)
    shots_split = None
    if all_shots:
        shots_split = split_shots(all_shots, is_home)
        sm_r = xg_from_shots(shots_split["roma"])
        sm_o = xg_from_shots(shots_split["opp"])
        logger.info(f"Shots: Roma {sm_r['shots']} (xG {sm_r['xg']:.2f}) | Opp {sm_o['shots']} (xG {sm_o['xg']:.2f})")
        # shot map xG è più granulare — sovrascrivi se disponibile
        if sm_r["xg"] > 0:
            stats["xg_roma"] = sm_r["xg"]
            stats["xg_opp"]  = sm_o["xg"]

    # 4. Player ratings
    top_players = get_player_ratings(mid)
    if top_players:
        logger.info(f"Ratings: {len(top_players)} giocatori")

    # 5. Classifica
    standings = get_standings()
    position  = get_roma_position(standings) if standings else None
    if position:
        logger.info(f"Roma: {position}° in classifica")

    # 6. Visual
    match_label = f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}"
    card_path     = None
    shot_map_path = None
    try:
        card_path = generate_match_card(match=match, stats=stats,
                                        top_players=top_players,
                                        filename=f"match_card_{mid}.png")
    except Exception as e:
        logger.warning(f"Match card: {e}")

    if shots_split:
        try:
            shot_map_path = generate_shot_map(
                shots_roma=shots_split["roma"], shots_opp=shots_split["opp"],
                match_label=match_label, filename=f"shot_map_{mid}.png")
        except Exception as e:
            logger.warning(f"Shot map: {e}")

    # 7. Record check
    history      = load_history()
    record_tweet = None
    try:
        found = check_records(match, stats, None, history)
        if found:
            record_tweet = detect_and_narrate_record(
                found[0]["type"], found[0]["value"],
                history.get("season_summary", {}))
    except Exception as e:
        logger.warning(f"Record check: {e}")

    # 8. AI narrative
    x_thread   = generate_post_match_thread(
        match=match, stats=stats,
        xg_data={"xg_roma": stats.get("xg_roma", 0), "xg_opp": stats.get("xg_opp", 0)},
        top_players=top_players, history_context=record_tweet)
    ig_caption = generate_instagram_caption(
        match=match, stats=stats,
        xg_data={"xg_roma": stats.get("xg_roma", 0), "xg_opp": stats.get("xg_opp", 0)})
    if record_tweet:
        x_thread.append(record_tweet)
    bsky_text = x_thread[0] if x_thread else match_label

    # 9. Pubblica
    results = publish_to_all_platforms(
        image_path=card_path, x_thread=x_thread,
        ig_caption=ig_caption, bsky_text=bsky_text)
    logger.info(f"Pubblicazione: {results}")

    # 10. Aggiorna history
    try:
        update_match_history(match, stats, None, history)
    except Exception as e:
        logger.warning(f"History: {e}")

    Path("data/last_match.json").write_text(json.dumps({
        "match_id": mid, "date": match["date"],
        "published_at": datetime.utcnow().isoformat(),
        "results": results,
    }, indent=2))
    logger.info("=== Completato ===")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force",     action="store_true")
    p.add_argument("--half-time", action="store_true")
    args = p.parse_args()
    run(force=args.force, half_time=args.half_time)
