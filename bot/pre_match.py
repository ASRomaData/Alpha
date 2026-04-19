"""
ASRomaData Bot — Pre-Match Preview
Trigger: cron ogni giorno 09:00 UTC.
Pubblica se c'è una partita Roma entro le prossime 48h.
Dati: SofaScore (form, xG, xGA, tiri) + football-data.co.uk (H2H storico).
"""

import logging
import sys
from datetime import datetime

from bot.fetch_data import (
    ROMA_ID,
    get_next_match,
    parse_event,
    get_team_form_stats,
    fd_h2h,
)
from bot.generate_visuals import generate_form_chart
from bot.ai_narrative import generate_pre_match_text
from bot.publishers import publish_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# Alias called by main.py CLI
run = None  # defined below

def run_pre_match():
    logger.info("═══ ASRomaData Bot — Pre-Match ═══")

    # ── 1. Prossima partita da SofaScore ─────────────────────────
    logger.info("SofaScore: prossima partita Roma...")
    event = get_next_match(ROMA_ID)
    if not event:
        logger.info("Nessuna partita trovata. Skip.")
        sys.exit(0)

    next_match  = parse_event(event)
    start_ts    = next_match.get("start_ts", 0)
    hours_until = (start_ts - datetime.utcnow().timestamp()) / 3600

    if not (0 < hours_until <= 52):
        logger.info(f"Prossima partita tra {hours_until:.0f}h — fuori finestra 48h. Skip.")
        sys.exit(0)

    opponent     = next_match.get("opponent", "N/A")
    opponent_id  = next_match.get("opponent_id")
    comp         = next_match.get("competition", "Serie A")
    date_str     = next_match.get("date", "")
    logger.info(f"Preview: Roma vs {opponent} ({date_str}) — tra {hours_until:.0f}h")

    # ── 2. Stats Roma (ultimi 5) ──────────────────────────────────
    logger.info("SofaScore: stats Roma ultimi 5...")
    roma_stats = get_team_form_stats(ROMA_ID, n=5)
    logger.info(
        f"Roma — Forma: {roma_stats['form']} | "
        f"xG: {roma_stats['avg_xg']} | xGA: {roma_stats['avg_xga']} | "
        f"Tiri: {roma_stats['avg_shots_for']} | Tiri subiti: {roma_stats['avg_shots_against']}"
    )

    # ── 3. Stats avversario (ultimi 5) ────────────────────────────
    opp_stats = {"form": ["?"] * 5, "avg_xg": 0.0, "avg_xga": 0.0,
                 "avg_shots_for": 0.0, "avg_shots_against": 0.0}
    if opponent_id:
        logger.info(f"SofaScore: stats {opponent} (id={opponent_id}) ultimi 5...")
        try:
            opp_stats = get_team_form_stats(opponent_id, n=5)
            logger.info(
                f"{opponent} — Forma: {opp_stats['form']} | "
                f"xG: {opp_stats['avg_xg']} | xGA: {opp_stats['avg_xga']} | "
                f"Tiri: {opp_stats['avg_shots_for']} | Tiri subiti: {opp_stats['avg_shots_against']}"
            )
        except Exception as e:
            logger.warning(f"Stats avversario failed: {e}")
    else:
        logger.warning("opponent_id non trovato, skip stats avversario")

    # ── 4. H2H da football-data.co.uk ────────────────────────────
    logger.info("football-data.co.uk: H2H storico...")
    h2h = None
    try:
        h2h = fd_h2h(opponent, last_n=5)
        logger.info(f"H2H: W{h2h['roma_wins']} D{h2h['draws']} L{h2h['opp_wins']}")
    except Exception as e:
        logger.warning(f"H2H failed: {e}")

    # ── 5. Genera form chart ──────────────────────────────────────
    form_img = None
    try:
        form_img = generate_form_chart(
            roma_form=roma_stats["form"] or ["?"] * 5,
            opp_form=opp_stats["form"] or ["?"] * 5,
            opp_name=opponent,
            roma_xg_form=None,
            filename=f"pre_{date_str.replace('/','_')}.png",
        )
        logger.info(f"Form chart: {form_img}")
    except Exception as e:
        logger.warning(f"Form chart failed: {e}")

    # ── 6. AI narrative ───────────────────────────────────────────
    logger.info("Groq: narrative pre-partita...")
    content = generate_pre_match_text(
        opponent=opponent,
        competition=comp,
        match_date=date_str,
        roma_form=roma_stats["form"] or ["?"] * 5,
        opp_form=opp_stats["form"] or ["?"] * 5,
        roma_avg_xg=roma_stats["avg_xg"],
        opp_avg_xg=opp_stats["avg_xg"],
        roma_avg_xga=roma_stats["avg_xga"],
        opp_avg_xga=opp_stats["avg_xga"],
        roma_avg_shots=roma_stats["avg_shots_for"],
        opp_avg_shots=opp_stats["avg_shots_for"],
        h2h_record=h2h,
    )

    x_thread   = content.get("thread", [])
    ig_caption = content.get("caption", "")
    bsky_text  = x_thread[0] if x_thread else f"Domani Roma vs {opponent} — {comp}"

    logger.info(f"Thread X: {len(x_thread)} tweet | IG caption: {len(ig_caption)} chars")

    # ── 7. Pubblica su tutte le piattaforme ───────────────────────
    logger.info("Pubblicazione preview...")
    results = publish_to_all_platforms(
        image_path=form_img,
        x_thread=x_thread,
        ig_caption=ig_caption,
        bsky_text=bsky_text,
    )
    logger.info(f"Risultati: {results}")


if __name__ == "__main__":
    run_pre_match()

# Alias
run = run_pre_match
