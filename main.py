#!/usr/bin/env python3
"""
ASRomaData Bot — Entry Point

  python main.py post-match [--force] [--half-time]
  python main.py pre-match
  python main.py weekly
  python main.py init-history [--start-year 2000]
  python main.py test-fetch
  python main.py test-publish
"""
import argparse, logging, os, sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)


def cmd_post_match(args):
    from bot.post_match import run
    run(force=args.force, half_time=args.half_time)

def cmd_pre_match(args):
    from bot.pre_match import run
    run()

def cmd_weekly(args):
    from bot.weekly_review import run_weekly_review
    run_weekly_review()

def cmd_init_history(args):
    from bot.update_history import build_historical_database
    result = build_historical_database(start_year=args.start_year)
    ss = result.get("season_summary", {})
    logger.info(f"Database: {len(ss)} stagioni")

def cmd_test_fetch(args):
    from bot.fetch_data import get_last_match, parse_event, current_season_code, download_season_csv
    logger.info("Test SofaScore...")
    event = get_last_match()
    if event:
        m = parse_event(event)
        logger.info(f"Ultima partita: {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']} ({m['status']})")
    else:
        logger.error("SofaScore: non raggiungibile")
    logger.info("Test football-data.co.uk...")
    rows = download_season_csv(current_season_code())
    if rows:
        logger.info(f"football-data OK: {len(rows)} partite")
    else:
        logger.warning("football-data: nessun dato")

def cmd_test_publish(args):
    import os, requests
    logger.info("Test image upload chain...")
    from bot.publishers import upload_image
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    test_img = "/tmp/test_asromadata.png"
    fig, ax = plt.subplots(figsize=(4, 4))
    fig.patch.set_facecolor("#0F0F0F"); ax.set_facecolor("#0F0F0F")
    ax.text(0.5, 0.5, "ASRomaData\nTest", ha="center", va="center",
            color="white", fontsize=18, transform=ax.transAxes)
    ax.axis("off"); fig.savefig(test_img, bbox_inches="tight"); plt.close(fig)
    url = upload_image(test_img)
    logger.info(f"Upload: {url or 'FALLITO'}")
    key = os.getenv("GROQ_API_KEY", "")
    if key:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"Di' solo OK"}],"max_tokens":5},
            timeout=15)
        logger.info(f"Groq: {'OK' if r.status_code == 200 else r.status_code}")
    if os.path.exists(test_img):
        os.remove(test_img)


def main():
    p = argparse.ArgumentParser(description="ASRomaData Bot")
    s = p.add_subparsers(dest="command", required=True)

    pm = s.add_parser("post-match");  pm.add_argument("--force", action="store_true")
    pm.add_argument("--half-time", action="store_true"); pm.set_defaults(func=cmd_post_match)

    pre = s.add_parser("pre-match");   pre.set_defaults(func=cmd_pre_match)
    wk  = s.add_parser("weekly");      wk.set_defaults(func=cmd_weekly)

    ih  = s.add_parser("init-history")
    ih.add_argument("--start-year", type=int, default=2000); ih.set_defaults(func=cmd_init_history)

    tf  = s.add_parser("test-fetch");   tf.set_defaults(func=cmd_test_fetch)
    tp  = s.add_parser("test-publish"); tp.set_defaults(func=cmd_test_publish)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
