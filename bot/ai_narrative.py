"""
ASRomaData Bot — AI Narrative (Groq, gratuito)
================================================
Usa Groq API con Llama 3.3 70B. Free tier: 14.400 req/giorno, no carta.
Registrazione: https://console.groq.com
"""

import logging
import os
import time
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_MODEL_FAST = "llama-3.1-8b-instant"
_MODEL_GOOD = "llama-3.3-70b-versatile"

_SYSTEM = """
Sei il redattore di @ASRomaData, account di football analytics dedicato all'AS Roma.
Stile: analitico, appassionato, conciso. Usa sempre il gergo tecnico:
- xG (non "gol attesi"), xGA, xPTS, PPDA
Non usare più di 2 emoji per post. Cita sempre la fonte del dato.
Scrivi SEMPRE in italiano. Evita frasi banali tipo "grande prestazione".
Ogni testo deve contenere almeno un dato statistico concreto.
Non superare mai la lunghezza richiesta.
"""


def _groq(prompt: str, max_tokens: int = 600, temp: float = 0.70) -> Optional[str]:
    """Chiamata Groq con fallback su modello veloce in caso di rate limit."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        logger.error("GROQ_API_KEY non impostata")
        return None
    hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for model in (_MODEL_GOOD, _MODEL_FAST):
        payload = {
            "model":    model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens":  max_tokens,
            "temperature": temp,
        }
        for attempt in range(3):
            try:
                r = requests.post(_GROQ_URL, headers=hdrs, json=payload, timeout=30)
                if r.status_code == 429:
                    wait = 60 * (attempt + 1)
                    logger.warning(f"Groq 429 (model={model}), attendo {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"Groq attempt {attempt+1}: {e}")
                if attempt < 2:
                    time.sleep(10)
        logger.warning(f"Groq: fallback da {model}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# POST-PARTITA — thread X
# ══════════════════════════════════════════════════════════════════════════════

def generate_post_match_thread(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict] = None,
    top_players: Optional[List[Dict]] = None,
    history_context: Optional[str] = None,
) -> List[str]:

    xg_r = (xg_data or stats).get("xg_roma", 0)
    xg_o = (xg_data or stats).get("xg_opp", 0)
    xg_block = f"xG Roma: {xg_r:.2f} | xG Avv: {xg_o:.2f}" if (xg_r or xg_o) else ""

    roma_side = "home" if match.get("is_home") else "away"
    top_str = ""
    if top_players:
        top = [p for p in top_players if p.get("side") == roma_side][:3]
        if top:
            top_str = "Rating Roma: " + " | ".join(
                f"{p['shortName']}: {p['rating']:.1f}" for p in top)

    prompt = f"""
Genera un thread Twitter/X di ESATTAMENTE 5 tweet per questa partita:
{match.get('home_team','')} {match.get('home_score',0)}-{match.get('away_score',0)} {match.get('away_team','')}
{match.get('competition','')} · {match.get('date','')}

Dati:
- Possesso: Roma {stats.get('possession_roma',50):.0f}% | Avv {stats.get('possession_opp',50):.0f}%
- Tiri: Roma {stats.get('shots_roma',0)} | Avv {stats.get('shots_opp',0)}
- In porta: Roma {stats.get('shots_on_target_roma',0)} | Avv {stats.get('shots_on_target_opp',0)}
- Big chances: Roma {stats.get('big_chances_roma',0)} | Avv {stats.get('big_chances_opp',0)}
- {xg_block}
- {top_str}
{f"Contesto storico: {history_context}" if history_context else ""}

REGOLE:
1. Inizia ogni tweet con "1/5", "2/5", etc.
2. Max 270 caratteri PER TWEET (contali)
3. Tweet 1: risultato + giudizio con dato chiave
4. Tweet 2: analisi xG
5. Tweet 3: statistiche offensive Roma
6. Tweet 4: top performer con rating
7. Tweet 5: contesto o record + fonte @ASRomaData
Separa i tweet con ---
"""
    raw = _groq(prompt, max_tokens=800, temp=0.72)
    if not raw:
        return _fallback_thread(match, stats, xg_r, xg_o)
    tweets = [t.strip()[:270] for t in raw.split("---") if t.strip()]
    return tweets[:6] if tweets else _fallback_thread(match, stats, xg_r, xg_o)


def _fallback_thread(match, stats, xg_r, xg_o) -> List[str]:
    ht, at = match.get('home_team',''), match.get('away_team','')
    hs, as_ = match.get('home_score',0), match.get('away_score',0)
    return [
        f"1/5 📊 {ht} {hs}-{as_} {at} — FT. Roma: {stats.get('shots_roma',0)} tiri, "
        f"{stats.get('possession_roma',50):.0f}% possesso. [SofaScore]",
        f"2/5 xG Roma: {xg_r:.2f} | xG Avversario: {xg_o:.2f}. "
        f"{'Prestazione sopra il risultato. ↑' if xg_r > xg_o else 'Numeri oltre il risultato. ↓'} [SofaScore/Opta]",
        f"3/5 Fase offensiva: {stats.get('shots_roma',0)} tiri, "
        f"{stats.get('shots_on_target_roma',0)} in porta, "
        f"{stats.get('big_chances_roma',0)} big chances. Angoli: {stats.get('corners_roma',0)}.",
        f"4/5 📈 Shot map e statistiche complete sul prossimo post. Segui @ASRomaData.",
        f"5/5 Fonte: SofaScore (stats) · SofaScore/Opta (xG) · @ASRomaData",
    ]


# ══════════════════════════════════════════════════════════════════════════════
# POST-PARTITA — caption Instagram
# ══════════════════════════════════════════════════════════════════════════════

def generate_instagram_caption(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict] = None,
) -> str:
    xg_r = (xg_data or stats).get("xg_roma", 0)
    xg_o = (xg_data or stats).get("xg_opp", 0)
    xg_block = f"xG {xg_r:.2f}–{xg_o:.2f}" if (xg_r or xg_o) else ""

    prompt = f"""
Caption Instagram per:
{match.get('home_team','')} {match.get('home_score',0)}-{match.get('away_score',0)} {match.get('away_team','')}
{match.get('competition','')} · {match.get('date','')}
Dati: possesso {stats.get('possession_roma',50):.0f}%, tiri {stats.get('shots_roma',0)}, {xg_block}

Regole:
- Max 300 caratteri di testo narrativo (non contare gli hashtag)
- 1-2 insight statistici
- Riga vuota dopo il testo, poi: #ASRoma #SerieA #ASRomaData #FootballAnalytics #xG
"""
    raw = _groq(prompt, max_tokens=200, temp=0.65)
    if not raw:
        h, a = match.get('home_team','Roma'), match.get('away_team','')
        hs, as_ = match.get('home_score',0), match.get('away_score',0)
        return (f"⚽ {h} {hs}–{as_} {a}\n\n"
                f"📊 Possesso {stats.get('possession_roma',50):.0f}% · "
                f"Tiri {stats.get('shots_roma',0)} · {xg_block}\n\n"
                f"#ASRoma #SerieA #ASRomaData #FootballAnalytics #xG")
    return raw


# ══════════════════════════════════════════════════════════════════════════════
# PRE-PARTITA
# ══════════════════════════════════════════════════════════════════════════════

def generate_pre_match_text(
    opponent: str,
    competition: str,
    match_date: str,
    roma_form: List[str],
    opp_form: List[str],
    roma_avg_xg: float = 0,
    opp_avg_xg: float = 0,
    h2h_record: Optional[Dict] = None,
) -> Dict[str, Any]:

    roma_pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in roma_form)
    opp_pts  = sum(3 if r == "W" else 1 if r == "D" else 0 for r in opp_form)
    h2h_str  = ""
    if h2h_record:
        h2h_str = f"H2H stagione: Roma W{h2h_record.get('a_wins',0)} D{h2h_record.get('draws',0)} L{h2h_record.get('b_wins',0)}"

    prompt = f"""
Domani: Roma vs {opponent} — {competition} ({match_date})

Dati:
- Forma Roma (ult 5): {' '.join(roma_form)} → {roma_pts}/15 pt
- Forma {opponent} (ult 5): {' '.join(opp_form)} → {opp_pts}/15 pt
- xG medio Roma: {roma_avg_xg:.2f}/partita
- xG medio {opponent}: {opp_avg_xg:.2f}/partita
{h2h_str}

Genera:
THREAD (3 tweet separati da ---):
- Tweet 1 (max 270 char): presentazione sfida con dato di forma più rilevante
- Tweet 2 (max 270 char): analisi xG e chi è favorito secondo i numeri
- Tweet 3 (max 270 char): dato H2H o contesto tattico + invito a seguire

CAPTION (max 250 char + hashtag separati da riga vuota)

Separa THREAD e CAPTION con ===
"""
    raw = _groq(prompt, max_tokens=600, temp=0.68)
    if not raw:
        thread = [
            f"1/3 📅 Domani Roma vs {opponent} — {competition}. "
            f"Forma Roma: {' '.join(roma_form)} ({roma_pts}/15 pt).",
            f"2/3 xG/90 Roma {roma_avg_xg:.2f} vs {opponent} {opp_avg_xg:.2f}. "
            f"{'Roma favorita.' if roma_avg_xg >= opp_avg_xg else f'{opponent} davanti per xG.'} [SofaScore/Opta]",
            f"3/3 {h2h_str or 'Segui @ASRomaData per analisi live post-partita.'} #ASRoma",
        ]
        caption = (f"📊 Domani Roma vs {opponent}\n"
                   f"Forma: {' '.join(roma_form)} · xG medio {roma_avg_xg:.2f}\n\n"
                   f"#ASRoma #SerieA #ASRomaData")
        return {"thread": thread, "caption": caption}

    parts   = raw.split("===")
    thread  = [t.strip()[:270] for t in parts[0].split("---") if t.strip()]
    caption = parts[1].strip() if len(parts) > 1 else ""
    return {"thread": thread[:3], "caption": caption}


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY REVIEW
# ══════════════════════════════════════════════════════════════════════════════

def generate_weekly_narrative(week_data: Dict) -> Dict[str, Any]:
    prompt = f"""
Review settimanale Roma — {week_data.get('week_label','')}

Dati:
- Partite: {week_data.get('games_played',0)}
- Punti: {week_data.get('points_won',0)} / {week_data.get('games_played',1)*3}
- Gol: {week_data.get('goals_for',0)} segnati · {week_data.get('goals_against',0)} subiti
- xG: {week_data.get('total_xg',0):.2f} | xGA: {week_data.get('total_xga',0):.2f}
- Posizione: {week_data.get('league_position','N/A')}°

Genera:
THREAD (3 tweet separati da ---):
- Tweet 1 (max 270 char): sintesi settimana con dato chiave
- Tweet 2 (max 270 char): analisi xG vs risultati reali
- Tweet 3 (max 270 char): outlook e invito a seguire

CAPTION (max 280 char + hashtag)

Separa con ===
"""
    raw = _groq(prompt, max_tokens=600, temp=0.70)
    if not raw:
        pts = week_data.get("points_won", 0)
        gp  = week_data.get("games_played", 1)
        thread = [
            f"📊 Week in review: Roma {pts}/{gp*3} punti. "
            f"xG {week_data.get('total_xg',0):.2f} | xGA {week_data.get('total_xga',0):.2f}.",
        ]
        caption = (f"Roma: {pts}/{gp*3} pt questa settimana · "
                   f"xG {week_data.get('total_xg',0):.2f}\n\n"
                   f"#ASRoma #SerieA #ASRomaData")
        return {"thread": thread, "caption": caption}

    parts   = raw.split("===")
    thread  = [t.strip()[:270] for t in parts[0].split("---") if t.strip()]
    caption = parts[1].strip() if len(parts) > 1 else ""
    return {"thread": thread[:3], "caption": caption}


# ══════════════════════════════════════════════════════════════════════════════
# RECORD DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def detect_and_narrate_record(
    event_type: str, value: Any, historical_data: Dict,
) -> Optional[str]:
    import json
    ctx = json.dumps(historical_data, ensure_ascii=False)[:400]
    prompt = f"""
Evento Roma: {event_type} = {value}
Contesto storico: {ctx}

È un record o milestone significativo?
Se sì: genera UN tweet celebrativo (max 250 char) con dato storico specifico.
Se no: rispondi solo NO_RECORD
"""
    raw = _groq(prompt, max_tokens=100, temp=0.60)
    if raw and raw.strip() != "NO_RECORD":
        return raw.strip()[:270]
    return None
