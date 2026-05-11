"""ASRomaData Bot — Pre-Match Preview"""
import logging, sys
from datetime import datetime
from bot.fetch_data import get_next_match, get_team_form, get_xg_form, parse_event, download_season_csv, get_h2h, current_season_code, ROMA_ID
from bot.generate_visuals import generate_form_chart
from bot.ai_narrative import generate_pre_match_text
from bot.publishers import publish_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run():
    logger.info("=== Pre-Match Preview ===")
    event = get_next_match()
    if not event:
        logger.info("Nessuna partita — skip"); sys.exit(0)
    match       = parse_event(event)
    opponent    = match.get("opponent", "")
    hours_until = (match["start_ts"] - datetime.utcnow().timestamp()) / 3600
    if not (0 < hours_until <= 52):
        logger.info(f"Partita tra {hours_until:.0f}h — fuori finestra 48h"); sys.exit(0)
    logger.info(f"Preview: Roma vs {opponent} — tra {hours_until:.0f}h")

    roma_form    = get_team_form(ROMA_ID, last_n=5)
    opp_id       = match.get("opponent_id")
    opp_form     = get_team_form(opp_id, last_n=5) if opp_id else ["?"] * 5
    roma_xg_form = get_xg_form(ROMA_ID, last_n=5)
    roma_avg_xg  = round(sum(roma_xg_form) / len(roma_xg_form), 2) if roma_xg_form else 0.0
    opp_xg_form  = get_xg_form(opp_id, last_n=5) if opp_id else []
    opp_avg_xg   = round(sum(opp_xg_form) / len(opp_xg_form), 2) if opp_xg_form else 0.0

    h2h = None
    try:
        rows = download_season_csv(current_season_code())
        if rows:
            h2h = get_h2h(rows, team_a="Roma", team_b=opponent)
    except Exception as e:
        logger.warning(f"H2H: {e}")

    form_img = None
    try:
        form_img = generate_form_chart(
            roma_form=roma_form or ["?"] * 5, opp_form=opp_form, opp_name=opponent,
            roma_xg_form=roma_xg_form or None,
            filename=f"pre_match_{match['date'].replace('/', '_')}.png")
    except Exception as e:
        logger.warning(f"Form chart: {e}")

    content    = generate_pre_match_text(opponent=opponent, competition=match.get("competition",""),
                    match_date=match.get("date",""), roma_form=roma_form or ["?"]*5,
                    opp_form=opp_form, roma_avg_xg=roma_avg_xg, opp_avg_xg=opp_avg_xg, h2h_record=h2h)
    x_thread   = content.get("thread", [])
    ig_caption = content.get("caption", "")
    bsky_text  = x_thread[0] if x_thread else f"Domani Roma vs {opponent}"

    results = publish_to_all_platforms(image_path=form_img, x_thread=x_thread,
                                       ig_caption=ig_caption, bsky_text=bsky_text)
    logger.info(f"Preview: {results}")

if __name__ == "__main__":
    run()
