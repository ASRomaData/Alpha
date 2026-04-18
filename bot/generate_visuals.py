"""
ASRomaData Bot — Visual Generation
Genera immagini per Instagram/X usando matplotlib + mplsoccer.
Tutti gli output sono PNG ottimizzati per social (1080x1080 o 1200x675).
"""

import os
import io
import logging
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend per GitHub Actions
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.gridspec import GridSpec
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

# ── COLORI BRAND ────────────────────────────────────────────────────────────
ROMA_RED   = "#8C0000"
ROMA_GOLD  = "#C8953A"
BG_DARK    = "#0F0F0F"
BG_CARD    = "#1A1A1A"
TEXT_LIGHT = "#F0EAE0"
TEXT_MUTED = "#888888"
OPP_GREY   = "#555555"

# Font fallback - non richiede font speciali
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": BG_DARK,
    "axes.facecolor": BG_CARD,
    "text.color": TEXT_LIGHT,
    "axes.labelcolor": TEXT_LIGHT,
    "xtick.color": TEXT_MUTED,
    "ytick.color": TEXT_MUTED,
    "axes.edgecolor": "#333333",
    "grid.color": "#2A2A2A",
})

os.makedirs("visuals", exist_ok=True)


def _save_figure(fig, filename: str) -> str:
    """Salva figura e restituisce il path."""
    path = f"visuals/{filename}"
    fig.savefig(path, dpi=150, bbox_inches="tight",
                facecolor=BG_DARK, edgecolor="none")
    plt.close(fig)
    logger.info(f"Visual saved: {path}")
    return path


# ──────────────────────────────────────────────────────────────────
# 1. SHOT MAP  (richiede mplsoccer)
# ──────────────────────────────────────────────────────────────────

def generate_shot_map(
    shots_data: Dict,
    home_team: str,
    away_team: str,
    is_home_roma: bool,
    match_label: str = "",
    filename: str = "shot_map.png"
) -> Optional[str]:
    """
    Genera shot map con mplsoccer.
    shots_data: dict con chiavi 'roma' e 'opp' (formato Fotmob).
    Ogni tiro: {x, y, xg, xgot, player, minute, is_goal, on_target}
    """
    try:
        from mplsoccer import VerticalPitch
    except ImportError:
        logger.warning("mplsoccer non installato, skip shot map")
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    fig.patch.set_facecolor(BG_DARK)

    opp_name = away_team if is_home_roma else home_team

    sides = [
        ("AS ROMA", shots_data.get("roma", []), ROMA_RED,  axes[0]),
        (opp_name,  shots_data.get("opp",  []), OPP_GREY, axes[1]),
    ]

    for team_name, shots, color, ax in sides:
        pitch = VerticalPitch(
            pitch_type="opta",
            pitch_color=BG_CARD,
            line_color="#333333",
            linewidth=1.2,
            half=True,
        )
        pitch.draw(ax=ax)
        ax.set_facecolor(BG_CARD)

        for shot in shots:
            # Fotmob usa x,y 0-100 (percentuale del campo)
            x   = float(shot.get("x", 50))
            y   = float(shot.get("y", 50))
            xg  = float(shot.get("xg", 0.05))

            is_goal = shot.get("is_goal", False) or shot.get("result","") == "Goal"
            marker  = "*" if is_goal else "o"
            size    = 300 + xg * 800

            ax.scatter(
                y * 0.68 + 16,
                x * 0.52 + 50,
                s=size,
                c=ROMA_GOLD if is_goal else color,
                alpha=0.85 if is_goal else 0.55,
                marker=marker,
                edgecolors="white" if is_goal else "none",
                linewidths=1.5 if is_goal else 0,
                zorder=5 if is_goal else 3,
            )

        total_xg = sum(float(s.get("xg", 0)) for s in shots)
        n_shots  = len(shots)
        n_goals  = sum(1 for s in shots if s.get("is_goal", False))

        ax.set_title(
            f"{team_name}\n{n_goals} gol · {n_shots} tiri · xG {total_xg:.2f}",
            color=TEXT_LIGHT, fontsize=11, pad=10, fontweight="bold"
        )

    # Titolo figura
    fig.suptitle(
        f"Shot Map — {match_label}",
        color=ROMA_GOLD, fontsize=13, fontweight="bold", y=1.01
    )

    # Legenda
    legend_els = [
        mpatches.Patch(color=ROMA_GOLD, label="Gol"),
        plt.scatter([], [], s=100, c=ROMA_RED, alpha=0.7, label="Tiro Roma"),
        plt.scatter([], [], s=100, c=OPP_GREY, alpha=0.7, label="Tiro avversario"),
    ]
    fig.legend(handles=legend_els, loc="lower center", ncol=3,
               facecolor=BG_CARD, edgecolor="none", labelcolor=TEXT_LIGHT,
               fontsize=9, bbox_to_anchor=(0.5, -0.03))

    # Watermark
    fig.text(0.99, 0.01, "@ASRomaData · Dati: Understat",
             ha="right", va="bottom", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)


# ──────────────────────────────────────────────────────────────────
# 2. POST-MATCH CARD  (per Instagram — 1080x1080)
# ──────────────────────────────────────────────────────────────────

def generate_match_card(
    match: Dict,
    stats: Dict,
    xg_data: Optional[Dict] = None,
    top_players: Optional[List[Dict]] = None,
    filename: str = "match_card.png"
) -> str:
    """
    Genera la card principale post-partita per Instagram.
    Format: 1:1 square, info partita + statistiche chiave + xG + top players
    """
    fig = plt.figure(figsize=(10.8, 10.8))
    fig.patch.set_facecolor(BG_DARK)
    gs = GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.25,
                  top=0.92, bottom=0.06, left=0.08, right=0.92)

    # ── HEADER: nome squadre + risultato ─────────────────────────
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.axis("off")
    ax_header.set_facecolor(BG_DARK)

    home_t = match.get("home_team", "Roma")
    away_t = match.get("away_team", "Avversario")
    h_scr  = match.get("home_score", 0)
    a_scr  = match.get("away_score", 0)

    ax_header.text(0.25, 0.6, home_t.upper(), ha="center", va="center",
                   color=TEXT_LIGHT, fontsize=14, fontweight="bold")
    ax_header.text(0.75, 0.6, away_t.upper(), ha="center", va="center",
                   color=TEXT_LIGHT, fontsize=14, fontweight="bold")
    ax_header.text(0.5,  0.6, f"{h_scr}  —  {a_scr}", ha="center", va="center",
                   color=ROMA_GOLD, fontsize=28, fontweight="bold")
    ax_header.text(0.5, 0.15,
                   f"{match.get('competition','')}  ·  {match.get('date','')}",
                   ha="center", va="center", color=TEXT_MUTED, fontsize=9)

    # Linea separatrice rossa
    ax_header.axhline(0.0, xmin=0.1, xmax=0.9, color=ROMA_RED, linewidth=2)

    # ── STATISTICHE: barre orizzontali ────────────────────────────
    stat_pairs = [
        ("Possesso %",      stats.get("possession_roma", 50),    stats.get("possession_opp", 50),    100),
        ("Tiri totali",     stats.get("shots_roma", 0),          stats.get("shots_opp", 0),          None),
        ("Tiri in porta",   stats.get("shots_on_target_roma", 0),stats.get("shots_on_target_opp", 0),None),
        ("Passaggi",        stats.get("passes_roma", 0),         stats.get("passes_opp", 0),         None),
        ("Calci d'angolo",  stats.get("corners_roma", 0),        stats.get("corners_opp", 0),        None),
        ("Falli",           stats.get("fouls_roma", 0),          stats.get("fouls_opp", 0),          None),
    ]

    ax_stats = fig.add_subplot(gs[1, :])
    ax_stats.axis("off")
    ax_stats.set_facecolor(BG_DARK)

    for i, (label, r_val, o_val, scale) in enumerate(stat_pairs):
        y = 1.0 - i * 0.18
        total = scale if scale else max(r_val + o_val, 1)
        r_pct = r_val / total
        o_pct = o_val / total

        # Bar Roma (sinistra)
        ax_stats.barh(y, r_pct * 0.38, left=0.08, height=0.10,
                      color=ROMA_RED, alpha=0.85)
        # Bar avversario (destra)
        ax_stats.barh(y, o_pct * 0.38, left=0.54, height=0.10,
                      color=OPP_GREY, alpha=0.70)

        # Valori e label
        ax_stats.text(0.07, y, str(int(r_val)), ha="right", va="center",
                      color=TEXT_LIGHT, fontsize=9, fontweight="bold")
        ax_stats.text(0.93, y, str(int(o_val)), ha="left", va="center",
                      color=TEXT_LIGHT, fontsize=9, fontweight="bold")
        ax_stats.text(0.5, y, label, ha="center", va="center",
                      color=TEXT_MUTED, fontsize=8)

    ax_stats.set_xlim(0, 1)
    ax_stats.set_ylim(-0.1, 1.1)

    # ── xG BLOCK ─────────────────────────────────────────────────
    ax_xg = fig.add_subplot(gs[2, :])
    ax_xg.axis("off")
    ax_xg.set_facecolor(BG_DARK)

    if xg_data:
        xg_r = xg_data.get("xg_roma", 0)
        xg_o = xg_data.get("xg_opp", 0)
        ax_xg.text(0.25, 0.65, f"{xg_r:.2f}", ha="center", va="center",
                   color=ROMA_RED, fontsize=30, fontweight="bold")
        ax_xg.text(0.25, 0.2,  "xG Roma", ha="center", va="center",
                   color=TEXT_MUTED, fontsize=9)
        ax_xg.text(0.5, 0.65,  "vs", ha="center", va="center",
                   color=TEXT_MUTED, fontsize=12)
        ax_xg.text(0.75, 0.65, f"{xg_o:.2f}", ha="center", va="center",
                   color=OPP_GREY, fontsize=30, fontweight="bold")
        ax_xg.text(0.75, 0.2,  "xG Avversario", ha="center", va="center",
                   color=TEXT_MUTED, fontsize=9)
        ax_xg.text(0.5, 0.2,   "Expected Goals · Understat", ha="center", va="center",
                   color=TEXT_MUTED, fontsize=7, style="italic")

    # ── TOP PLAYERS ──────────────────────────────────────────────
    ax_players = fig.add_subplot(gs[3, :])
    ax_players.axis("off")
    ax_players.set_facecolor(BG_DARK)

    if top_players:
        # Filtra solo giocatori Roma
        roma_key = "home" if match.get("is_home") else "away"
        roma_players = [p for p in top_players if p.get("team") == roma_key][:3]

        ax_players.text(0.5, 0.9, "TOP PERFORMERS ROMA",
                        ha="center", va="top", color=ROMA_GOLD,
                        fontsize=9, fontweight="bold", letter_spacing=1)

        for i, p in enumerate(roma_players):
            x = 0.2 + i * 0.3
            rating = p.get("rating", 0)
            color = ROMA_GOLD if rating >= 8.0 else TEXT_LIGHT
            ax_players.text(x, 0.6, p.get("shortName", p.get("name", ""))[:12],
                            ha="center", va="center", color=TEXT_LIGHT, fontsize=9)
            ax_players.text(x, 0.3, f"{rating:.1f}",
                            ha="center", va="center", color=color,
                            fontsize=18, fontweight="bold")

    # Watermark
    fig.text(0.5, 0.01, "@ASRomaData · SofaScore · Understat",
             ha="center", va="bottom", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)


# ──────────────────────────────────────────────────────────────────
# 3. FORM CHART  (ultimi 5 risultati per pre-partita)
# ──────────────────────────────────────────────────────────────────

def generate_form_chart(
    roma_form: List[str],    # es. ["W","W","D","L","W"]
    opp_form: List[str],
    opp_name: str,
    roma_xg_form: List[float] = None,
    filename: str = "form_chart.png"
) -> str:
    """
    Genera il grafico di forma per la preview pre-partita.
    forma: lista "W"/"D"/"L" delle ultime 5 partite (più recente = destra)
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(BG_DARK)

    color_map = {"W": "#4CAF50", "D": ROMA_GOLD, "L": ROMA_RED}

    for ax, form, label, color_team in [
        (ax1, roma_form, "AS ROMA", ROMA_RED),
        (ax2, opp_form,  opp_name.upper(), OPP_GREY)
    ]:
        ax.set_facecolor(BG_CARD)
        ax.set_xlim(-0.5, 4.5)
        ax.set_ylim(-0.5, 1.5)
        ax.axis("off")

        for i, res in enumerate(form[-5:]):
            c = color_map.get(res, TEXT_MUTED)
            circle = plt.Circle((i, 0.5), 0.35, color=c, alpha=0.85)
            ax.add_patch(circle)
            ax.text(i, 0.5, res, ha="center", va="center",
                    color="white", fontsize=14, fontweight="bold")

        # Punti ultimi 5
        pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in form[-5:])
        ax.set_title(f"{label}\n{pts}/15 punti (ultime 5)",
                     color=TEXT_LIGHT, fontsize=11, fontweight="bold", pad=12)

        # xG media se disponibile
        if ax == ax1 and roma_xg_form:
            avg_xg = sum(roma_xg_form) / len(roma_xg_form) if roma_xg_form else 0
            ax.text(2, -0.2, f"xG medio: {avg_xg:.2f}",
                    ha="center", va="center", color=TEXT_MUTED, fontsize=8)

    fig.suptitle("ULTIME 5 PARTITE", color=ROMA_GOLD,
                 fontsize=12, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02, "@ASRomaData · Dati: football-data.co.uk",
             ha="center", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)


# ──────────────────────────────────────────────────────────────────
# 4. SEASON XG CHART  (serie storica — mensile/annuale)
# ──────────────────────────────────────────────────────────────────

def generate_xg_season_chart(
    history: List[Dict],
    title: str = "AS Roma — xG per stagione",
    filename: str = "xg_history.png"
) -> str:
    """
    Grafico linea xG/xGA per stagione (serie storica).
    history: lista di dict con chiavi season, xg_per_game, xga_per_game
    """
    if not history:
        return ""

    seasons  = [h["season"] for h in history]
    xg_vals  = [h["xg_per_game"] for h in history]
    xga_vals = [h["xga_per_game"] for h in history]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.set_facecolor(BG_CARD)
    fig.patch.set_facecolor(BG_DARK)

    x = range(len(seasons))

    # Area fill
    ax.fill_between(x, xg_vals, alpha=0.2, color=ROMA_RED)
    ax.fill_between(x, xga_vals, alpha=0.15, color=ROMA_GOLD)

    # Linee
    ax.plot(x, xg_vals, color=ROMA_RED, linewidth=2.5, label="xG/partita",
            marker="o", markersize=5)
    ax.plot(x, xga_vals, color=ROMA_GOLD, linewidth=2, label="xGA/partita",
            marker="s", markersize=4, linestyle="--")

    # Annota stagione corrente
    if xg_vals:
        ax.annotate(f"{xg_vals[-1]:.2f}",
                    xy=(len(x)-1, xg_vals[-1]),
                    xytext=(5, 8), textcoords="offset points",
                    color=ROMA_RED, fontsize=9, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(seasons, rotation=45, ha="right", fontsize=9, color=TEXT_MUTED)
    ax.set_ylabel("xG per partita", color=TEXT_MUTED, fontsize=10)
    ax.set_title(title, color=ROMA_GOLD, fontsize=13, fontweight="bold", pad=14)
    ax.legend(facecolor=BG_CARD, edgecolor="#333", labelcolor=TEXT_LIGHT, fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    fig.text(0.99, 0.01, "@ASRomaData · Dati: Understat",
             ha="right", va="bottom", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)


# ──────────────────────────────────────────────────────────────────
# 5. PUNTI PER STAGIONE  (dal 2000)
# ──────────────────────────────────────────────────────────────────

def generate_points_history_chart(
    history: List[Dict],
    title: str = "AS Roma — Punti per stagione (Serie A)",
    filename: str = "points_history.png"
) -> str:
    """Bar chart punti stagionali."""
    if not history:
        return ""

    seasons = [h.get("season_label", h.get("season", "")) for h in history]
    points  = [h["points"] for h in history]

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.set_facecolor(BG_CARD)
    fig.patch.set_facecolor(BG_DARK)

    colors = [ROMA_GOLD if p == max(points) else ROMA_RED for p in points]
    bars = ax.bar(range(len(seasons)), points, color=colors, alpha=0.85, width=0.7)

    # Linea media
    mean_pts = sum(points) / len(points)
    ax.axhline(mean_pts, color=TEXT_MUTED, linewidth=1, linestyle="--", alpha=0.6)
    ax.text(len(seasons) - 0.5, mean_pts + 0.5, f"Media: {mean_pts:.0f}",
            ha="right", color=TEXT_MUTED, fontsize=8)

    ax.set_xticks(range(len(seasons)))
    ax.set_xticklabels(seasons, rotation=45, ha="right", fontsize=7.5, color=TEXT_MUTED)
    ax.set_ylabel("Punti", color=TEXT_MUTED, fontsize=10)
    ax.set_title(title, color=ROMA_GOLD, fontsize=13, fontweight="bold", pad=14)
    ax.grid(axis="y", alpha=0.25)

    fig.text(0.99, 0.01, "@ASRomaData · Dati: football-data.co.uk",
             ha="right", va="bottom", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)


# ──────────────────────────────────────────────────────────────────
# 6. WEEKLY REVIEW CARD
# ──────────────────────────────────────────────────────────────────

def generate_weekly_card(
    week_data: Dict,
    filename: str = "weekly_review.png"
) -> str:
    """
    Card riepilogativa settimanale.
    week_data: {games:[...], total_xg, total_xga, points_won, top_player}
    """
    fig = plt.figure(figsize=(10.8, 10.8))
    fig.patch.set_facecolor(BG_DARK)
    gs = GridSpec(3, 3, figure=fig, hspace=0.5, wspace=0.4,
                  top=0.88, bottom=0.06, left=0.08, right=0.92)

    # Titolo
    fig.text(0.5, 0.93, "WEEK IN REVIEW · AS ROMA",
             ha="center", color=ROMA_GOLD, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.89, week_data.get("week_label", ""),
             ha="center", color=TEXT_MUTED, fontsize=9)

    # Metriche chiave
    metrics = [
        ("Punti",          week_data.get("points_won", 0),   "/ {0}".format(week_data.get("games_played",0)*3)),
        ("xG totale",      f"{week_data.get('total_xg',0):.2f}", ""),
        ("xGA totale",     f"{week_data.get('total_xga',0):.2f}", ""),
        ("Gol segnati",    week_data.get("goals_for", 0),   ""),
        ("Gol subiti",     week_data.get("goals_against", 0),""),
        ("Tiri totali",    week_data.get("total_shots", 0),  ""),
    ]

    for i, (label, val, suffix) in enumerate(metrics):
        row, col = divmod(i, 3)
        ax = fig.add_subplot(gs[row, col])
        ax.axis("off")
        ax.set_facecolor(BG_CARD)
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.05, 0.1), 0.9, 0.8,
            boxstyle="round,pad=0.05",
            facecolor=BG_CARD, edgecolor="#333", linewidth=1
        ))
        ax.text(0.5, 0.65, str(val), ha="center", va="center",
                color=ROMA_GOLD, fontsize=24, fontweight="bold")
        ax.text(0.5, 0.3, f"{label}{suffix}", ha="center", va="center",
                color=TEXT_MUTED, fontsize=8)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    fig.text(0.5, 0.02, "@ASRomaData · SofaScore · Understat",
             ha="center", color=TEXT_MUTED, fontsize=7)

    return _save_figure(fig, filename)

# Alias for backwards compatibility
generate_points_history = generate_points_history_chart
