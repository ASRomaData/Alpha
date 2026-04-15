# ASRomaData Bot — Setup Completo

Sistema di automazione per **@ASRomaData** che pubblica analisi, statistiche avanzate e serie storiche della Roma su **Instagram**, **X (Twitter)**, **Bluesky** e **Threads** — completamente automatizzato tramite GitHub Actions.

---

## 🤖 AI: Groq (gratuito, no carta di credito)

Questo bot usa **[Groq](https://console.groq.com)** con **Llama 3.3 70B** invece di Claude/GPT-4.

| Voce | Valore |
|------|--------|
| Costo | **€0** |
| Richieste/giorno | **14.400** (più che sufficienti) |
| Modello | Llama 3.3 70B Versatile |
| Qualità | Ottima per testo sportivo in italiano |
| Carta di credito | ❌ Non richiesta |

**Registrazione Groq (2 minuti):**
1. Vai su [console.groq.com](https://console.groq.com)
2. Sign up con email o Google
3. Dashboard → API Keys → Create API Key
4. Copia la chiave (inizia con `gsk_...`)

---

## 📊 Fonti Dati (tutte gratuite)

| Fonte | Dati | Note |
|-------|------|------|
| SofaScore | Statistiche live, rating giocatori | Già usato |
| Understat | xG, shot maps, Serie A dal 2014 | No registrazione |
| football-data.co.uk | Risultati Serie A dal 2000 | CSV diretto |
| Transfermarkt | Valori di mercato | Scraping |
| FBref | Statistiche avanzate (pressioni, xA) | Rate limited |

---

## 🚀 Setup Rapido (30 minuti)

### Step 1 — Clona o forka il repo

```bash
git clone https://github.com/TUO_USERNAME/asromadata-bot.git
cd asromadata-bot
```

### Step 2 — GitHub Secrets

Vai in **Settings → Secrets and variables → Actions → New repository secret**:

```
# AI (OBBLIGATORIO)
GROQ_API_KEY          → gsk_xxxxx (da console.groq.com)

# Instagram (già configurato nel progetto precedente)
IG_USER_ID            → ID numerico account Instagram
IG_ACCESS_TOKEN       → Token Graph API

# X / Twitter
X_API_KEY             → Da developer.twitter.com
X_API_SECRET          → Da developer.twitter.com
X_ACCESS_TOKEN        → Da developer.twitter.com
X_ACCESS_SECRET       → Da developer.twitter.com
X_BEARER_TOKEN        → Da developer.twitter.com

# Bluesky (già configurato)
BSKY_HANDLE           → tuonome.bsky.social
BSKY_PASSWORD         → App Password Bluesky

# GitHub (per upload immagini e persistenza history)
GH_PAT                → Personal Access Token (scope: repo, workflow)

# Threads (opzionale)
THREADS_ENABLED       → true (se vuoi attivarlo)
THREADS_ACCESS_TOKEN  → Token Threads API
THREADS_USER_ID       → ID account Threads
```

### Step 3 — Inizializza database storico (UNA SOLA VOLTA)

Vai su **Actions → Initialize Historical Database → Run workflow**.

Questo scarica:
- Risultati Serie A dal 2000 (football-data.co.uk)
- xG per stagione dal 2014 (Understat)
- Genera grafici storici automaticamente

⏱ Durata: ~25 minuti. Da fare una sola volta.

### Step 4 — Verifica bot post-partita

Vai su **Actions → Post-Match Bot → Run workflow → ✓ Ignora finestra temporale**.

Se tutto è configurato correttamente vedrai i post pubblicati.

---

## 📅 Calendario Automatizzato

| Trigger | Ora | Contenuto |
|---------|-----|-----------|
| Ogni 15 min (partita) | finestra -1h/+3h | Post-partita con xG, shot map, thread X |
| Ogni giorno 09:00 UTC | se partita entro 48h | Preview pre-gara con form chart |
| Lunedì 09:00 UTC | sempre | Weekly review settimanale |
| Manuale | su richiesta | Override qualsiasi contenuto |

---

## 🗂 Struttura Progetto

```
asromadata-bot/
├── bot/
│   ├── config.py         # Configurazione centralizzata
│   ├── fetch_data.py     # SofaScore, Understat, football-data, Transfermarkt
│   ├── generate_visuals.py  # matplotlib + mplsoccer
│   ├── ai_narrative.py   # Groq API (Llama 3.3 70B)
│   ├── publishers.py     # Instagram, X, Bluesky, Threads
│   ├── post_match.py     # Orchestratore post-partita
│   ├── pre_match.py      # Preview pre-gara
│   ├── weekly_review.py  # Review settimanale
│   └── update_history.py # Serie storiche + record detector
├── data/
│   ├── history.json      # Database storico (aggiornato automaticamente)
│   └── last_match.json   # Stato ultima pubblicazione
├── visuals/              # PNG generati (temporanei)
├── .github/workflows/
│   ├── post_match.yml    # Cron ogni 15min
│   ├── pre_match.yml     # Cron giornaliero
│   ├── weekly_review.yml # Cron lunedì
│   └── init_history.yml  # Setup iniziale (una tantum)
└── requirements.txt
```

---

## 🐛 Troubleshooting

**Bot non pubblica dopo la partita:**
- Verifica che la partita sia terminata (status "finished" su SofaScore)
- Controlla che siamo nella finestra -1h/+3h dall'inizio
- Usa "Run workflow → Force" per override manuale

**Errore Groq 429 (rate limit):**
- Il bot fa fallback automatico a `llama-3.1-8b-instant`
- Con 14.400 req/giorno non dovresti mai raggiungerlo

**Instagram non pubblica:**
- L'immagine deve avere URL pubblico
- Il bot la carica su GitHub (necessita GH_PAT con scope `repo`)
- Verifica che IG_ACCESS_TOKEN non sia scaduto (validità: 60 giorni)

**Understat non trova dati xG:**
- Understat aggiorna 1-2 ore dopo la partita
- Il bot usa SofaScore come fallback per il risultato

---

## 🔧 Comandi Utili

```bash
# Test locale (installa deps prima)
pip install -r requirements.txt

# Test post-partita (forza)
GROQ_API_KEY=gsk_xxx python -m bot.post_match --force

# Test pre-partita
python -m bot.pre_match

# Test weekly review
python -m bot.weekly_review

# Inizializza database storico
python -c "from bot.update_history import build_historical_database; build_historical_database(2000)"
```

---

## 💰 Costi

| Servizio | Costo mensile |
|----------|--------------|
| Groq API (Llama 3.3 70B) | **€0** |
| GitHub Actions | **€0** (2000 min/mese gratis) |
| Vercel (dashboard) | **€0** |
| Tutti i dati (FBref, Understat, etc.) | **€0** |
| **TOTALE** | **€0** |

---

*@ASRomaData · La Roma attraverso i numeri*
