"""
ASRomaData Bot — Pre-Match Preview
Trigger: cron ogni giorno 09:00 UTC.
Pubblica se c'è una partita Roma entro le prossime 48h.
Dati: SofaScore (form, xG medio) + football-data.co.uk (H2H storico).
"""

import logging
import sys
from datetime import datetime

from bot.fetch_data import (
    ROMA_ID,
    get_next_match,
    parse_event,
    get_form,
    get_avg_xg,
    fd_h2h,
)
from bot.generate_visuals import generate_form_chart
from bot.ai_narrative import generate_pre_match_text
from bot.publishers import publish_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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

    opponent = next_match.get("opponent", "N/A")
    comp     = next_match.get("competition", "Serie A")
    date_str = next_match.get("date", "")
    logger.info(f"Preview: Roma vs {opponent} ({date_str}) — tra {hours_until:.0f}h")

    # ── 2. Forma Roma (ultimi 5 risultati) ────────────────────────
    logger.info("SofaScore: forma Roma...")
    roma_form = get_form(ROMA_ID, n=5)
    logger.info(f"Forma Roma: {roma_form}")
    opp_form = ["?"] * 5  # opponent form requires their team_id; best-effort placeholder

    # ── 3. xG medio Roma ultimi 5 ────────────────────────────────
    logger.info("SofaScore: xG medio ultimi 5...")
    roma_avg_xg = 0.0
    try:
        roma_avg_xg = get_avg_xg(ROMA_ID, n=5)
        logger.info(f"xG medio Roma: {roma_avg_xg:.2f}")
    except Exception as e:
        logger.warning(f"xG medio failed: {e}")

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
            roma_form=roma_form if roma_form else ["?"] * 5,
            opp_form=opp_form,
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
        roma_form=roma_form if roma_form else ["?"] * 5,
        opp_form=opp_form,
        roma_avg_xg=roma_avg_xg,
        opp_avg_xg=0.0,
        h2h_record=h2h,
    )

    x_thread   = content.get("thread", [])
    ig_caption = content.get("caption", "")
    bsky_text  = x_thread[0] if x_thread else f"Domani Roma vs {opponent} — {comp}"

    # ── 7. Pubblica ───────────────────────────────────────────────
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
