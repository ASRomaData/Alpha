"""
ASRomaData Bot — AI Narrative Generator
Usa Groq API (FREE) con Llama 3.3 70B per generare testi contestualizzati.
- 14.400 richieste/giorno gratuite
- No carta di credito richiesta
- Registrazione: https://console.groq.com
"""

import os
import json
import time
import logging
import re
from typing import Optional, Dict, List, Any
import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _call_groq(
    prompt: str,
    system: str = "",
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 600,
    temperature: float = 0.7,
    retries: int = 3,
) -> Optional[str]:
    """
    Chiamata base a Groq API (compatibile OpenAI).
    Free tier: 14.400 req/giorno, no credit card.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        logger.error("GROQ_API_KEY non configurata")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    for attempt in range(retries):
        try:
            r = requests.post(GROQ_API_URL, headers=headers,
                              json=payload, timeout=30)
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                logger.warning(f"Groq rate limit, attendo {wait}s...")
                time.sleep(wait)
                # Fallback su modello più piccolo
                payload["model"] = "llama-3.1-8b-instant"
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Groq call error (tentativo {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(10)
    return None


SYSTEM_PROMPT = """
Sei il redattore di @ASRomaData, account di football analytics dedicato all'AS Roma.
Stile: analitico, appassionato, conciso. Usi il gergo tecnico corretto:
- xG (non "gol attesi" o "expected goals")
- xGA (expected goals against)
- xPTS (punti attesi)
- PPDA (pressione avversaria)
Non usi emoji eccessive (max 2 per post). Citi sempre la fonte del dato.
Scrivi SEMPRE in italiano. Evita frasi banali.
Ogni testo deve contenere almeno un dato statistico concreto.
Non superare mai la lunghezza richiesta.
"""


# ──────────────────────────────────────────────────────────────────
# POST-PARTITA: thread X
# ──────────────────────────────────────────────────────────────────

def generate_post_match_thread(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict] = None,
    top_players: Optional[List[Dict]] = None,
    history_context: Optional[str] = None,
) -> List[str]:
    """
    Genera un thread X di 5-6 tweet per il post-partita.
    Restituisce lista di stringhe (un tweet per elemento, max 270 char).
    """
    h_team = match.get("home_team", "")
    a_team = match.get("away_team", "")
    h_scr  = match.get("home_score", 0)
    a_scr  = match.get("away_score", 0)
    comp   = match.get("competition", "Serie A")
    date   = match.get("date", "")

    xg_block = ""
    if xg_data:
        xg_r = xg_data.get("xg_roma", 0)
        xg_o = xg_data.get("xg_opp", 0)
        xg_block = f"xG Roma: {xg_r:.2f} | xG Avversario: {xg_o:.2f}"

    players_block = ""
    if top_players:
        is_home = match.get("is_home", True)
        roma_key = "home" if is_home else "away"
        roma_top = [p for p in top_players if p.get("team") == roma_key][:3]
        if roma_top:
            lines = [f"{p['shortName']}: {p['rating']:.1f}" for p in roma_top]
            players_block = "Rating giocatori Roma: " + " | ".join(lines)

    prompt = f"""
Genera un thread Twitter/X di ESATTAMENTE 5 tweet per la partita:
{h_team} {h_scr}-{a_scr} {a_team} ({comp}, {date})

Dati disponibili:
- Possesso: Roma {stats.get('possession_roma',50)}% | Avversario {stats.get('possession_opp',50)}%
- Tiri totali: Roma {stats.get('shots_roma',0)} | Avversario {stats.get('shots_opp',0)}
- Tiri in porta: Roma {stats.get('shots_on_target_roma',0)} | Avversario {stats.get('shots_on_target_opp',0)}
- Passaggi: Roma {stats.get('passes_roma',0)} | Avversario {stats.get('passes_opp',0)}
- Angoli: Roma {stats.get('corners_roma',0)} | Avversario {stats.get('corners_opp',0)}
- {xg_block}
- {players_block}
{f"Contesto storico: {history_context}" if history_context else ""}

REGOLE STRINGENTI:
1. Ogni tweet deve iniziare con "1/5", "2/5", etc.
2. Ogni tweet max 270 caratteri (CONTALI)
3. Primo tweet: risultato + giudizio immediato con dato statistico
4. Secondo tweet: analisi xG e cosa dicono i numeri
5. Terzo tweet: stats offensive Roma
6. Quarto tweet: top performer con rating
7. Quinto tweet: contesto storico o record (se disponibile) + mention fonte

Separali con ---
"""

    raw = _call_groq(prompt, SYSTEM_PROMPT, max_tokens=800, temperature=0.72)
    if not raw:
        # Fallback manuale se Groq non disponibile
        return _fallback_thread(match, stats, xg_data, top_players)

    tweets = [t.strip() for t in raw.split("---") if t.strip()]
    # Tronca a 270 caratteri per sicurezza
    tweets = [t[:270] for t in tweets[:6]]
    return tweets if tweets else _fallback_thread(match, stats, xg_data, top_players)


def _fallback_thread(match, stats, xg_data, top_players) -> List[str]:
    """Thread di fallback senza AI — dati puri."""
    h  = match.get("home_team", "")
    a  = match.get("away_team", "")
    hs = match.get("home_score", 0)
    as_ = match.get("away_score", 0)
    xg_r = xg_data.get("xg_roma", 0) if xg_data else 0
    xg_o = xg_data.get("xg_opp", 0) if xg_data else 0
    poss = stats.get("possession_roma", 0)
    shots = stats.get("shots_roma", 0)
    sot   = stats.get("shots_on_target_roma", 0)

    tweets = [
        f"1/5 📊 {h} {hs}-{as_} {a} — Full time. La Roma chiude con {shots} tiri e {poss:.0f}% di possesso palla. [SofaScore]",
        f"2/5 xG Roma: {xg_r:.2f} | xG Avversario: {xg_o:.2f}. {'Prestazione superiore al risultato. ⬆️' if xg_r > xg_o else 'Risultato leggermente oltre i numeri. ⬇️'} [Understat]",
        f"3/5 Fase offensiva: {shots} tiri di cui {sot} in porta (conversion rate: {sot/max(shots,1)*100:.0f}%). Angoli: {stats.get('corners_roma',0)}.",
        f"4/5 📈 Statistiche complete e shot map nella prossima card. Segui @ASRomaData per analisi avanzate dopo ogni partita della Roma.",
        f"5/5 🔢 Dati: SofaScore (stats) · Understat (xG) · @ASRomaData per serie storiche e analisi stagionali.",
    ]
    return tweets


# ──────────────────────────────────────────────────────────────────
# CAPTION INSTAGRAM
# ──────────────────────────────────────────────────────────────────

def generate_instagram_caption(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict] = None,
) -> str:
    """
    Genera caption Instagram per il post-partita (max 400 caratteri + hashtag).
    """
    xg_block = ""
    if xg_data:
        xg_r = xg_data.get("xg_roma", 0)
        xg_o = xg_data.get("xg_opp", 0)
        xg_block = f"xG {xg_r:.2f}–{xg_o:.2f}"

    prompt = f"""
Genera una caption Instagram per il post-partita:
{match.get('home_team','')} {match.get('home_score',0)}-{match.get('away_score',0)} {match.get('away_team','')}
{match.get('competition','')} · {match.get('date','')}
Dati: possesso {stats.get('possession_roma',0):.0f}%, tiri {stats.get('shots_roma',0)}, {xg_block}

Regole:
- Max 300 caratteri di testo narrativo (NON contare gli hashtag)
- Tono: analitico e appassionato
- 1-2 insight statistici concreti
- Termina con una riga vuota e poi hashtag separati: #ASRoma #SerieA #ASRomaData #FootballAnalytics #xG
- NON aggiungere altri hashtag
"""
    raw = _call_groq(prompt, SYSTEM_PROMPT, max_tokens=200, temperature=0.65)
    if not raw:
        h = match.get("home_team", "Roma")
        a = match.get("away_team", "")
        hs = match.get("home_score", 0)
        as_ = match.get("away_score", 0)
        return (f"⚽ {h} {hs}–{as_} {a} | {match.get('competition','')}\n\n"
                f"📊 Possesso {stats.get('possession_roma',0):.0f}% · "
                f"Tiri {stats.get('shots_roma',0)} · {xg_block}\n\n"
                f"#ASRoma #SerieA #ASRomaData #FootballAnalytics #xG")
    return raw


# ──────────────────────────────────────────────────────────────────
# PREVIEW PRE-PARTITA
# ──────────────────────────────────────────────────────────────────

def generate_pre_match_text(
    opponent: str,
    competition: str,
    match_date: str,
    roma_form: List[str],
    opp_form: List[str],
    roma_avg_xg: float = 0,
    opp_avg_xg: float = 0,
    roma_avg_xga: float = 0,
    opp_avg_xga: float = 0,
    roma_avg_shots: float = 0,
    opp_avg_shots: float = 0,
    h2h_record: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Genera testi pre-partita per X (thread 3 tweet) e Instagram (caption).
    Returns dict con 'thread' (lista tweet) e 'caption' (stringa).
    """
    roma_pts = sum(3 if r=="W" else 1 if r=="D" else 0 for r in roma_form[-5:])
    opp_pts  = sum(3 if r=="W" else 1 if r=="D" else 0 for r in opp_form[-5:])
    h2h_str = ""
    if h2h_record:
        h2h_str = f"H2H recente: Roma W{h2h_record.get('roma_wins',0)} D{h2h_record.get('draws',0)} L{h2h_record.get('opp_wins',0)}"

    prompt = f"""
Domani: AS Roma vs {opponent} — {competition} ({match_date})

Dati:
- Forma Roma (ult 5): {' '.join(roma_form[-5:])} → {roma_pts}/15 punti
- Forma {opponent} (ult 5): {' '.join(opp_form[-5:])} → {opp_pts}/15 punti
- xG medio Roma: {roma_avg_xg:.2f}/partita | xGA medio Roma: {roma_avg_xga:.2f}/partita
- xG medio {opponent}: {opp_avg_xg:.2f}/partita | xGA medio {opponent}: {opp_avg_xga:.2f}/partita
- Tiri medi Roma: {roma_avg_shots:.1f}/partita | Tiri medi {opponent}: {opp_avg_shots:.1f}/partita
{h2h_str}

Genera:
THREAD (3 tweet separati da ---):
- Tweet 1 (max 270 char): presentazione sfida con forma e dato più interessante
- Tweet 2 (max 270 char): analisi xG/xGA e chi parte favorito secondo i numeri
- Tweet 3 (max 270 char): dato storico H2H o record e attesa tattica

CAPTION (max 250 char + hashtag): insight pre-gara per Instagram

Separa thread e caption con ===
"""
    raw = _call_groq(prompt, SYSTEM_PROMPT, max_tokens=600, temperature=0.68)
    if not raw:
        thread = [
            f"1/3 📅 Domani Roma vs {opponent} — {competition}. Forma Roma: {' '.join(roma_form[-5:])} ({roma_pts}/15 pt). {opponent}: {' '.join(opp_form[-5:])} ({opp_pts}/15 pt).",
            f"2/3 Secondo i numeri: xG/90 Roma {roma_avg_xg:.2f} vs {opponent} {opp_avg_xg:.2f}. {'Roma favorita per xG.' if roma_avg_xg > opp_avg_xg else f'{opponent} leggermente avanti per xG.'} [Understat]",
            f"3/3 {h2h_str or 'Segui @ASRomaData per analisi live e post-partita.'} #ASRoma #{opponent.replace(' ','')} #SerieA",
        ]
        caption = (f"📊 Domani Roma vs {opponent}\nForma: {' '.join(roma_form[-5:])} · xG medio {roma_avg_xg:.2f}\n\n"
                   f"#ASRoma #SerieA #ASRomaData")
        return {"thread": thread, "caption": caption}

    parts = raw.split("===")
    thread_raw = parts[0] if parts else raw
    caption = parts[1].strip() if len(parts) > 1 else ""

    thread = [t.strip()[:270] for t in thread_raw.split("---") if t.strip()]

    return {"thread": thread[:3], "caption": caption}


# ──────────────────────────────────────────────────────────────────
# REVIEW SETTIMANALE
# ──────────────────────────────────────────────────────────────────

def generate_weekly_narrative(week_data: Dict) -> Dict[str, str]:
    """Genera testo per la review settimanale del lunedì."""
    prompt = f"""
Review settimanale AS Roma — {week_data.get('week_label', '')}

Dati settimana:
- Partite giocate: {week_data.get('games_played', 0)}
- Punti conquistati: {week_data.get('points_won', 0)} / {week_data.get('games_played',0)*3}
- Gol segnati: {week_data.get('goals_for', 0)} | subiti: {week_data.get('goals_against', 0)}
- xG totale: {week_data.get('total_xg', 0):.2f} | xGA: {week_data.get('total_xga', 0):.2f}
- Top performer: {week_data.get('top_player', {}).get('name', 'N/A')} (rating {week_data.get('top_player', {}).get('rating', 0):.1f})
- Posizione classifica: {week_data.get('league_position', 'N/A')}

Genera:
1. TITOLO: max 60 caratteri, deve catturare l'essenza della settimana
2. THREAD_X: 3 tweet (separati da ---), max 270 char ciascuno
3. CAPTION_IG: max 280 char + hashtag

Separa con === tra i tre elementi.
"""
    raw = _call_groq(prompt, SYSTEM_PROMPT, max_tokens=700, temperature=0.7)
    if not raw:
        pts = week_data.get("points_won", 0)
        gp  = week_data.get("games_played", 1)
        title   = f"Roma: {pts}/{gp*3} punti questa settimana"
        thread  = [f"📊 Week in review: Roma raccoglie {pts} punti su {gp*3} disponibili. xG {week_data.get('total_xg',0):.2f} | xGA {week_data.get('total_xga',0):.2f}. [Understat]"]
        caption = f"Settimana AS Roma — {pts}/{gp*3} punti · xG {week_data.get('total_xg',0):.2f}\n\n#ASRoma #SerieA #ASRomaData"
        return {"title": title, "thread": thread, "caption": caption}

    parts = raw.split("===")
    title   = parts[0].strip() if len(parts) > 0 else ""
    thread_raw = parts[1] if len(parts) > 1 else ""
    caption = parts[2].strip() if len(parts) > 2 else ""

    thread = [t.strip()[:270] for t in thread_raw.split("---") if t.strip()]

    return {"title": title, "thread": thread[:3], "caption": caption}


# ──────────────────────────────────────────────────────────────────
# RECORD / MILESTONE DETECTOR
# ──────────────────────────────────────────────────────────────────

def detect_and_narrate_record(
    event_type: str,
    value: Any,
    historical_data: Dict,
) -> Optional[str]:
    """
    Rileva se un evento è un record storico e genera testo celebrativo.
    event_type: es. "consecutive_wins", "xg_season", "goals_scored"
    """
    record_context = json.dumps(historical_data, ensure_ascii=False)[:500]

    prompt = f"""
Dato questo evento nella stagione Roma: {event_type} = {value}
Contesto storico: {record_context}

È un record o milestone notevole? Se sì, genera un tweet celebrativo (max 250 char)
che citi il dato storico specifico ("per la prima volta dal [anno]..." o "miglior [metric] da...").
Se NON è un record significativo, rispondi solo con: NO_RECORD
"""
    raw = _call_groq(prompt, SYSTEM_PROMPT, max_tokens=120, temperature=0.6)
    if raw and raw.strip() != "NO_RECORD":
        return raw.strip()[:270]
    return None
