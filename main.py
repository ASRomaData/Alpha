#!/usr/bin/env python3
"""
ASRomaData Bot — Entry Point
==============================
Esegui qualsiasi operazione del bot da qui.

Utilizzo:
  python main.py post-match [--force] [--half-time]
  python main.py pre-match
  python main.py weekly
  python main.py init-history [--start-year 2000]
  python main.py test-fetch
  python main.py test-publish

Variabili d'ambiente richieste (o in .env):
  GROQ_API_KEY, IG_USER_ID, IG_ACCESS_TOKEN,
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET, X_BEARER_TOKEN,
  BSKY_HANDLE, BSKY_PASSWORD
"""

import argparse
import logging
import os
import sys

# Carica .env se presente (sviluppo locale)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
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
    logger.info(f"Database costruito: {len(ss)} stagioni")


def cmd_test_fetch(args):
    """Verifica che SofaScore e football-data.co.uk siano raggiungibili."""
    logger.info("Test SofaScore...")
    from bot.fetch_data import get_last_match, parse_event, current_season_code, download_season_csv

    event = get_last_match()
    if event:
        match = parse_event(event)
        logger.info(f"Ultima partita: {match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']} ({match['status']})")
    else:
        logger.error("SofaScore: impossibile raggiungere")
        return

    logger.info("Test football-data.co.uk...")
    code = current_season_code()
    rows = download_season_csv(code)
    if rows:
        logger.info(f"football-data.co.uk OK: {len(rows)} partite stagione {code}")
    else:
        logger.warning("football-data.co.uk: nessun dato (potrebbe essere normale per stagione non ancora disponibile)")

    logger.info("✓ Test fetch completato")


def cmd_test_publish(args):
    """Testa l'upload immagine e le credenziali social (senza pubblicare)."""
    logger.info("Test image upload...")
    from bot.publishers import upload_image_for_instagram
    import os

    # Crea immagine di test
    test_img = "/tmp/test_asromadata.png"
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.text(0.5, 0.5, "ASRomaData\nTest", ha="center", va="center",
                fontsize=20, transform=ax.transAxes)
        ax.set_facecolor("#0F0F0F")
        fig.patch.set_facecolor("#0F0F0F")
        fig.savefig(test_img, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Immagine di test creata: {test_img}")
    except Exception as e:
        logger.error(f"Creazione immagine test: {e}")
        return

    url = upload_image_for_instagram(test_img)
    if url:
        logger.info(f"✓ Image upload OK: {url}")
    else:
        logger.error("✗ Image upload fallito")

    # Test credenziali Groq
    logger.info("Test Groq API...")
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        import requests
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Di' solo: OK"}], "max_tokens": 5},
            timeout=15,
        )
        if r.status_code == 200:
            logger.info("✓ Groq API OK")
        else:
            logger.error(f"✗ Groq API: {r.status_code}")
    else:
        logger.warning("GROQ_API_KEY non impostata")

    # Cleanup
    if os.path.exists(test_img):
        os.remove(test_img)

    logger.info("Test publish completato")


def main():
    parser = argparse.ArgumentParser(
        description="ASRomaData Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # post-match
    pm = sub.add_parser("post-match", help="Pubblica stats post-partita")
    pm.add_argument("--force",     action="store_true", help="Ignora finestra temporale")
    pm.add_argument("--half-time", action="store_true", help="Stats primo tempo")
    pm.set_defaults(func=cmd_post_match)

    # pre-match
    pre = sub.add_parser("pre-match", help="Pubblica preview pre-partita (se entro 48h)")
    pre.set_defaults(func=cmd_pre_match)

    # weekly
    wk = sub.add_parser("weekly", help="Pubblica review settimanale")
    wk.set_defaults(func=cmd_weekly)

    # init-history
    ih = sub.add_parser("init-history", help="Inizializza database storico (una tantum)")
    ih.add_argument("--start-year", type=int, default=2000, help="Anno di inizio (default: 2000)")
    ih.set_defaults(func=cmd_init_history)

    # test-fetch
    tf = sub.add_parser("test-fetch", help="Verifica connettività alle fonti dati")
    tf.set_defaults(func=cmd_test_fetch)

    # test-publish
    tp = sub.add_parser("test-publish", help="Testa upload immagine e credenziali")
    tp.set_defaults(func=cmd_test_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
