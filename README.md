# ASRomaData Bot

Sistema di automazione per **@ASRomaData** che pubblica analisi, statistiche avanzate e serie storiche della Roma su **Instagram**, **X (Twitter)**, **Bluesky** e **Threads** — completamente automatizzato tramite GitHub Actions.

---

## Architettura fonti dati

| Fonte | Cosa fornisce | Note |
|-------|---------------|------|
| **SofaScore** (`www.sofascore.com/api/v1`) | Risultati live, xG Opta, shot map, ratings giocatori, classifica, forma | Fonte primaria — zero API key |
| **openfootball** (GitHub raw) | Serie storiche Serie A dal 2011 | Zero API key, CSV testuale |
| **football-data.org** | Serie storiche Serie A dal 2000 | Fallback — API key gratuita (`FD_API_KEY`) |
| **Groq** (Llama 3.3 70B) | Generazione testo narrativo | 14.400 req/giorno gratis |

> **Nota importante su SofaScore**: il bot usa `www.sofascore.com/api/v1` con una sessione cookie inizializzata dalla homepage. L'endpoint `api.sofascore.com` restituisce 403 a client senza cookie — non usarlo.

---

## AI: Groq (gratuito, no carta di credito)

| Voce | Valore |
|------|--------|
| Costo | **€0** |
| Richieste/giorno | **14.400** |
| Modello primario | Llama 3.3 70B Versatile |
| Modello fallback | Llama 3.1 8B Instant (in caso di rate limit) |
| Registrazione | [console.groq.com](https://console.groq.com) → API Keys → Create |

---

## Setup (30 minuti)

### Step 1 — Clona il repo

```bash
git clone https://github.com/TUO_USERNAME/asromadata-bot.git
cd asromadata-bot
```

### Step 2 — GitHub Secrets

Vai su **Settings → Secrets and variables → Actions → New repository secret** e aggiungi:

```
# AI (obbligatorio)
GROQ_API_KEY          → gsk_xxxxx

# Instagram
IG_USER_ID            → ID numerico account
IG_ACCESS_TOKEN       → Token Graph API (scade ogni 60 giorni)

# X / Twitter
X_API_KEY             → da developer.twitter.com
X_API_SECRET
X_ACCESS_TOKEN
X_ACCESS_SECRET
X_BEARER_TOKEN

# Bluesky
BSKY_HANDLE           → tuonome.bsky.social
BSKY_PASSWORD         → App Password (non la password principale)

# GitHub (per commit automatico di history.json)
GH_PAT                → Personal Access Token (scope: repo, workflow)

# Threads (opzionale)
THREADS_ENABLED       → true
THREADS_ACCESS_TOKEN
THREADS_USER_ID

# football-data.org (opzionale, fallback per storico pre-2011)
FD_API_KEY            → da football-data.org (piano gratuito)
```

### Step 3 — Inizializza il database storico (una volta sola)

Vai su **Actions → Initialize Historical Database → Run workflow**.

Scarica i risultati Serie A dal 2000 (o dall'anno impostato) e genera i grafici storici. Durata: circa 25 minuti.

### Step 4 — Test post-partita

Vai su **Actions → Post-Match Bot → Run workflow** e imposta "Ignora finestra temporale" su `true`.

Se le credenziali sono corrette vedrai i post pubblicati sui social.

---

## Calendario automatizzato

| Workflow | Trigger | Contenuto |
|----------|---------|-----------|
| `post_match.yml` | Ogni 15 min (11:00–24:00 UTC) | Stats post-partita, xG, shot map, thread X |
| `pre_match.yml` | Ogni giorno ore 09:00 UTC | Preview pre-gara se partita entro 48h |
| `weekly_review.yml` | Ogni lunedì ore 09:00 UTC | Review settimanale con aggregati |
| `init_history.yml` | Manuale (una volta sola) | Build database storico dal 2000 |

---

## Struttura progetto

```
asromadata-bot/
├── bot/
│   ├── config.py           # Variabili d'ambiente centralizzate
│   ├── fetch_data.py       # SofaScore + openfootball + football-data.org
│   ├── generate_visuals.py # Grafici matplotlib + mplsoccer
│   ├── ai_narrative.py     # Groq API (Llama 3.3 70B)
│   ├── publishers.py       # Instagram, X, Bluesky, Threads
│   ├── post_match.py       # Pipeline post-partita
│   ├── pre_match.py        # Preview pre-gara
│   ├── weekly_review.py    # Review settimanale
│   └── update_history.py   # Gestione serie storiche + record detector
├── data/
│   ├── history.json        # Database storico (aggiornato automaticamente)
│   └── last_match.json     # Stato ultima pubblicazione
├── visuals/                # PNG generati (temporanei)
├── .github/workflows/
│   ├── post_match.yml
│   ├── pre_match.yml
│   ├── weekly_review.yml
│   └── init_history.yml
├── main.py                 # Entry point CLI
└── requirements.txt
```

---

## Comandi CLI

```bash
# Installa dipendenze
pip install -r requirements.txt

# Copia .env.example e configura le variabili
cp .env.example .env

# Test connettività fonti dati
python main.py test-fetch

# Test credenziali social (senza pubblicare)
python main.py test-publish

# Esegui post-partita (forza senza controllo finestra)
python main.py post-match --force

# Preview pre-partita
python main.py pre-match

# Review settimanale
python main.py weekly

# Build database storico
python main.py init-history --start-year 2000
```

---

## Troubleshooting

**SofaScore 403 Forbidden**
Il bot usa `www.sofascore.com/api/v1` con sessione cookie. Se compare il 403:
- Verifica che `_SS_BASE` in `fetch_data.py` punti a `www.sofascore.com` e non a `api.sofascore.com`
- Il bot rigenera automaticamente la sessione al primo 403 — se persiste dopo 3 tentativi, SofaScore ha cambiato le protezioni; apri una issue

**Bot non pubblica dopo la partita**
- Verifica che la partita sia in stato `finished` su SofaScore
- La finestra è -60min/+180min dall'inizio: usa `--force` per override
- Controlla `data/last_match.json` — se l'ID coincide, la partita è già stata pubblicata

**Errore Groq 429 (rate limit)**
- Il bot fa fallback automatico su `llama-3.1-8b-instant`
- Con 14.400 req/giorno non dovrebbe succedere in uso normale

**Instagram non pubblica**
- Il token scade ogni 60 giorni: rinnova `IG_ACCESS_TOKEN` dalla Meta Developer Console
- Le immagini vengono caricate su GitHub (serve `GH_PAT` con scope `repo`)

**openfootball: dati mancanti per stagione corrente**
- Il repo openfootball viene aggiornato manualmente; la stagione in corso potrebbe essere incompleta
- Il bot usa `football-data.org` come fallback (configura `FD_API_KEY`)

---

## Costi

| Servizio | Costo mensile |
|----------|--------------|
| Groq API (Llama 3.3 70B) | **€0** |
| GitHub Actions | **€0** (2.000 min/mese inclusi) |
| SofaScore, openfootball | **€0** |
| football-data.org (piano Free) | **€0** |
| **TOTALE** | **€0** |

---

*@ASRomaData · La Roma attraverso i numeri*

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
