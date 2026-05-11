"""
ASRomaData Bot — Visual Generation
=====================================
Genera PNG per Instagram/X.
Input: dati da SofaScore (coordinate shot map 0-100, xG, stats).
Output: PNG in visuals/ ottimizzati per social.
"""

import logging
import os
import warnings
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Brand ────────────────────────────────────────────────────────────────────
ROMA_RED   = "#8C0000"
ROMA_GOLD  = "#C8953A"
BG_DARK    = "#0F0F0F"
BG_CARD    = "#1A1A1A"
TEXT_LIGHT = "#F0EAE0"
TEXT_MUTED = "#888888"
OPP_GREY   = "#505050"
PITCH_BG   = "#1B2B1B"
PITCH_LINE = "#2E4A2E"

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "figure.facecolor":  BG_DARK,
    "axes.facecolor":    BG_CARD,
    "text.color":        TEXT_LIGHT,
    "axes.labelcolor":   TEXT_LIGHT,
    "xtick.color":       TEXT_MUTED,
    "ytick.color":       TEXT_MUTED,
    "axes.edgecolor":    "#333333",
    "grid.color":        "#2A2A2A",
})

os.makedirs("visuals", exist_ok=True)


def _save(fig, filename: str) -> str:
    path = f"visuals/{filename}"
    fig.savefig(path, dpi=150, bbox_inches="tight",
                facecolor=BG_DARK, edgecolor="none")
    plt.close(fig)
    logger.info(f"Visual: {path}")
    return path


def _watermark(fig, source: str = "SofaScore/Opta"):
    fig.text(0.99, 0.005, f"@ASRomaData · {source}",
             ha="right", va="bottom", color=TEXT_MUTED,
             fontsize=7, transform=fig.transFigure)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SHOT MAP  (coordinate SofaScore native x/y 0-100)
# ══════════════════════════════════════════════════════════════════════════════

def _draw_half_pitch(ax):
    """Metà campo semplificata in coordinate SofaScore (0-100)."""
    ax.set_facecolor(PITCH_BG)
    ax.set_xlim(0, 100)
    ax.set_ylim(50, 105)
    ax.axis("off")
    kw = dict(color=PITCH_LINE, linewidth=1.0)
    ax.axhline(50, xmin=0, xmax=1, **kw)
    # area di rigore
    ax.add_patch(mpatches.Rectangle((21.1, 83.5), 57.8, 16.5,
                                    fill=False, edgecolor=PITCH_LINE, linewidth=1.0))
    # area piccola
    ax.add_patch(mpatches.Rectangle((36.8, 94.5), 26.4, 5.5,
                                    fill=False, edgecolor=PITCH_LINE, linewidth=1.0))
    # porta
    ax.add_patch(mpatches.Rectangle((45.2, 100), 9.6, 2,
                                    fill=False, edgecolor=PITCH_LINE, linewidth=1.0))
    # dischetto rigore
    ax.plot(50, 88.5, "o", color=PITCH_LINE, markersize=2)
    # arco area
    ax.add_patch(mpatches.Arc((50, 88.5), 18.3, 18.3, theta1=308, theta2=232,
                               color=PITCH_LINE, linewidth=1.0))


def generate_shot_map(
    shots_roma: List[Dict],
    shots_opp: List[Dict],
    match_label: str,
    filename: str = "shot_map.png",
) -> Optional[str]:
    """
    Shot map con coordinate SofaScore (x 0-100, y 0-100).
    Ogni tiro: {playerCoordinates:{x,y}, shotType, xg, player, time}
    shotType: 'goal'|'save'|'miss'|'block'|'post'
    """
    try:
        from mplsoccer import VerticalPitch
        use_mpl = True
    except ImportError:
        use_mpl = False

    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    fig.patch.set_facecolor(BG_DARK)

    for ax, shots, label, is_roma in [
        (axes[0], shots_roma, "AS ROMA", True),
        (axes[1], shots_opp,  "Avversario", False),
    ]:
        if use_mpl:
            pitch = VerticalPitch(pitch_type="opta", pitch_color=PITCH_BG,
                                  line_color=PITCH_LINE, linewidth=1.0, half=True)
            pitch.draw(ax=ax)
        else:
            _draw_half_pitch(ax)

        for shot in shots:
            coords = shot.get("playerCoordinates", {})
            x  = float(coords.get("x", 50))
            y  = float(coords.get("y", 50))
            xg = float(shot.get("xg", 0.05) or 0.05)
            st = shot.get("shotType", "miss")
            is_goal = (st == "goal")
            color   = ROMA_GOLD if (is_goal and is_roma) else (ROMA_RED if is_roma else OPP_GREY)
            size    = 80 + xg * 600
            alpha   = 0.90 if is_goal else min(0.55 + xg * 0.3, 0.85)

            if use_mpl:
                ax.scatter(y, x, s=size, c=color, alpha=alpha,
                           marker="*" if is_goal else "o",
                           edgecolors="white" if is_goal else "none",
                           linewidths=1.5 if is_goal else 0,
                           zorder=6 if is_goal else 4)
            else:
                ax.scatter(x, y, s=size, c=color, alpha=alpha,
                           marker="*" if is_goal else "o",
                           edgecolors="white" if is_goal else "none",
                           linewidths=1.5 if is_goal else 0,
                           zorder=6 if is_goal else 4)

        xg_tot = sum(float(s.get("xg", 0) or 0) for s in shots)
        goals  = sum(1 for s in shots if s.get("shotType") == "goal")
        ax.set_title(f"{label}\n{goals} gol · {len(shots)} tiri · xG {xg_tot:.2f}",
                     color=TEXT_LIGHT, fontsize=10, pad=8, fontweight="bold")

    fig.suptitle(f"Shot Map — {match_label}", color=ROMA_GOLD,
                 fontsize=12, fontweight="bold", y=1.01)
    fig.legend(
        handles=[mpatches.Patch(color=ROMA_GOLD, label="Gol Roma"),
                 mpatches.Patch(color=ROMA_RED,  label="Tiro Roma"),
                 mpatches.Patch(color=OPP_GREY,  label="Tiro avversario")],
        loc="lower center", ncol=3, facecolor=BG_CARD, edgecolor="none",
        labelcolor=TEXT_LIGHT, fontsize=8, bbox_to_anchor=(0.5, -0.02),
    )
    _watermark(fig)
    return _save(fig, filename)


# ══════════════════════════════════════════════════════════════════════════════
# 2. MATCH CARD — post-partita 1:1 per Instagram
# ══════════════════════════════════════════════════════════════════════════════

def generate_match_card(
    match: Dict,
    stats: Dict,
    top_players: Optional[List[Dict]] = None,
    filename: str = "match_card.png",
) -> str:
    fig = plt.figure(figsize=(10.8, 10.8))
    fig.patch.set_facecolor(BG_DARK)
    gs = GridSpec(4, 2, figure=fig, hspace=0.5, wspace=0.3,
                  top=0.91, bottom=0.07, left=0.07, right=0.93)

    # Header
    ax_h = fig.add_subplot(gs[0, :])
    ax_h.axis("off")
    hs = match.get("home_score", 0)
    as_ = match.get("away_score", 0)
    ax_h.text(0.22, 0.58, match.get("home_team", "").upper(),
              ha="center", va="center", color=TEXT_LIGHT, fontsize=13, fontweight="bold")
    ax_h.text(0.78, 0.58, match.get("away_team", "").upper(),
              ha="center", va="center", color=TEXT_LIGHT, fontsize=13, fontweight="bold")
    ax_h.text(0.50, 0.58, f"{hs}  —  {as_}",
              ha="center", va="center", color=ROMA_GOLD, fontsize=30, fontweight="bold")
    ax_h.text(0.50, 0.14,
              f"{match.get('competition','')}  ·  {match.get('date','')}",
              ha="center", va="center", color=TEXT_MUTED, fontsize=8)
    ax_h.axhline(0.0, xmin=0.08, xmax=0.92, color=ROMA_RED, linewidth=2)

    # xG block
    ax_xg = fig.add_subplot(gs[1, :])
    ax_xg.axis("off")
    xg_r = stats.get("xg_roma", 0)
    xg_o = stats.get("xg_opp", 0)
    if xg_r > 0 or xg_o > 0:
        ax_xg.text(0.25, 0.65, f"{xg_r:.2f}", ha="center", va="center",
                   color=ROMA_RED, fontsize=32, fontweight="bold")
        ax_xg.text(0.25, 0.20, "xG Roma",
                   ha="center", va="center", color=TEXT_MUTED, fontsize=9)
        ax_xg.text(0.50, 0.65, "vs",
                   ha="center", va="center", color=TEXT_MUTED, fontsize=12)
        ax_xg.text(0.75, 0.65, f"{xg_o:.2f}", ha="center", va="center",
                   color=OPP_GREY, fontsize=32, fontweight="bold")
        ax_xg.text(0.75, 0.20, "xG Avversario",
                   ha="center", va="center", color=TEXT_MUTED, fontsize=9)
        ax_xg.text(0.50, 0.20, "Expected Goals · SofaScore/Opta",
                   ha="center", va="center", color=TEXT_MUTED, fontsize=7, style="italic")

    # Stats bars
    stat_pairs = [
        ("Possesso %",  "possession_roma",      "possession_opp",      100),
        ("Tiri totali", "shots_roma",           "shots_opp",           None),
        ("In porta",    "shots_on_target_roma", "shots_on_target_opp", None),
        ("Big chances", "big_chances_roma",     "big_chances_opp",     None),
        ("Angoli",      "corners_roma",         "corners_opp",         None),
        ("Falli",       "fouls_roma",           "fouls_opp",           None),
    ]
    ax_st = fig.add_subplot(gs[2, :])
    ax_st.axis("off")
    ax_st.set_xlim(0, 1); ax_st.set_ylim(-0.05, 1.05)
    for i, (label, rk, ok, scale) in enumerate(stat_pairs):
        y   = 1.0 - i * 0.19
        rv  = float(stats.get(rk, 0))
        ov  = float(stats.get(ok, 0))
        tot = float(scale) if scale else max(rv + ov, 1)
        ax_st.barh(y, rv / tot * 0.38, left=0.07, height=0.11, color=ROMA_RED, alpha=0.85)
        ax_st.barh(y, ov / tot * 0.38, left=0.55, height=0.11, color=OPP_GREY, alpha=0.70)
        ax_st.text(0.06, y, str(int(rv)), ha="right", va="center",
                   color=TEXT_LIGHT, fontsize=8, fontweight="bold")
        ax_st.text(0.94, y, str(int(ov)), ha="left", va="center",
                   color=TEXT_LIGHT, fontsize=8, fontweight="bold")
        ax_st.text(0.50, y, label, ha="center", va="center",
                   color=TEXT_MUTED, fontsize=7.5)

    # Top players
    ax_pl = fig.add_subplot(gs[3, :])
    ax_pl.axis("off")
    roma_side = "home" if match.get("is_home") else "away"
    if top_players:
        top = [p for p in top_players if p.get("side") == roma_side][:4]
        ax_pl.text(0.50, 0.90, "TOP PERFORMERS ROMA",
                   ha="center", va="center", color=ROMA_GOLD, fontsize=9, fontweight="bold")
        for i, p in enumerate(top):
            x   = 0.15 + i * 0.24
            col = ROMA_GOLD if p["rating"] >= 8.0 else TEXT_LIGHT
            ax_pl.text(x, 0.55, p.get("shortName", "")[:10],
                       ha="center", va="center", color=TEXT_MUTED, fontsize=8)
            ax_pl.text(x, 0.20, f"{p['rating']:.1f}",
                       ha="center", va="center", color=col, fontsize=20, fontweight="bold")

    _watermark(fig)
    return _save(fig, filename)


# ══════════════════════════════════════════════════════════════════════════════
# 3. FORM CHART — pre-partita
# ══════════════════════════════════════════════════════════════════════════════

def generate_form_chart(
    roma_form: List[str],
    opp_form: List[str],
    opp_name: str,
    roma_xg_form: Optional[List[float]] = None,
    filename: str = "form_chart.png",
) -> str:
    color_map = {"W": "#4CAF50", "D": ROMA_GOLD, "L": ROMA_RED, "?": TEXT_MUTED}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(BG_DARK)

    for ax, form, label in [(ax1, roma_form, "AS ROMA"),
                             (ax2, opp_form, opp_name.upper())]:
        ax.set_facecolor(BG_CARD)
        ax.set_xlim(-0.5, 4.5); ax.set_ylim(-0.5, 1.5)
        ax.axis("off")
        for i, res in enumerate(form[-5:]):
            c = color_map.get(res, TEXT_MUTED)
            ax.add_patch(plt.Circle((i, 0.5), 0.35, color=c, alpha=0.85, zorder=3))
            ax.text(i, 0.5, res, ha="center", va="center",
                    color="white", fontsize=14, fontweight="bold", zorder=4)
        pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in form[-5:])
        ax.set_title(f"{label}\n{pts}/15 punti (ult. 5)",
                     color=TEXT_LIGHT, fontsize=11, fontweight="bold", pad=12)
        if ax == ax1 and roma_xg_form:
            avg = sum(roma_xg_form) / len(roma_xg_form)
            ax.text(2, -0.2, f"xG medio: {avg:.2f}",
                    ha="center", color=TEXT_MUTED, fontsize=8)

    fig.suptitle("ULTIME 5 PARTITE", color=ROMA_GOLD, fontsize=12, fontweight="bold", y=1.02)
    _watermark(fig, "SofaScore")
    return _save(fig, filename)


# ══════════════════════════════════════════════════════════════════════════════
# 4. POINTS HISTORY — storico punti per stagione
# ══════════════════════════════════════════════════════════════════════════════

def generate_points_history(
    history: List[Dict],
    filename: str = "points_history.png",
) -> str:
    if not history:
        return ""
    seasons  = [h.get("season_label", "") for h in history]
    points   = [h["points"] for h in history]
    max_pts  = max(points)
    mean_pts = sum(points) / len(points)

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.set_facecolor(BG_CARD); fig.patch.set_facecolor(BG_DARK)
    colors = [ROMA_GOLD if p == max_pts else ROMA_RED for p in points]
    ax.bar(range(len(seasons)), points, color=colors, alpha=0.85, width=0.7, zorder=3)
    ax.axhline(mean_pts, color=TEXT_MUTED, linewidth=1, linestyle="--", alpha=0.6, zorder=2)
    ax.text(len(seasons) - 0.5, mean_pts + 0.5, f"Media: {mean_pts:.0f}",
            ha="right", color=TEXT_MUTED, fontsize=8)
    ax.set_xticks(range(len(seasons)))
    ax.set_xticklabels(seasons, rotation=45, ha="right", fontsize=7, color=TEXT_MUTED)
    ax.set_ylabel("Punti", color=TEXT_MUTED)
    ax.set_title("AS Roma — Punti per stagione (Serie A)", color=ROMA_GOLD,
                 fontsize=13, fontweight="bold", pad=14)
    ax.grid(axis="y", alpha=0.2, zorder=1)
    _watermark(fig, "football-data.co.uk")
    return _save(fig, filename)


# ══════════════════════════════════════════════════════════════════════════════
# 5. WEEKLY REVIEW CARD
# ══════════════════════════════════════════════════════════════════════════════

def generate_weekly_card(week_data: Dict, filename: str = "weekly_review.png") -> str:
    fig = plt.figure(figsize=(10.8, 10.8))
    fig.patch.set_facecolor(BG_DARK)
    gs = GridSpec(3, 3, figure=fig, hspace=0.5, wspace=0.4,
                  top=0.88, bottom=0.06, left=0.07, right=0.93)
    fig.text(0.5, 0.93, "WEEK IN REVIEW · AS ROMA",
             ha="center", color=ROMA_GOLD, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.89, week_data.get("week_label", ""),
             ha="center", color=TEXT_MUTED, fontsize=9)
    metrics = [
        ("Punti",   week_data.get("points_won", 0)),
        ("xG",      f"{week_data.get('total_xg', 0):.2f}"),
        ("xGA",     f"{week_data.get('total_xga', 0):.2f}"),
        ("Gol",     week_data.get("goals_for", 0)),
        ("Subiti",  week_data.get("goals_against", 0)),
        ("Tiri",    week_data.get("total_shots", 0)),
    ]
    for i, (label, val) in enumerate(metrics):
        row, col = divmod(i, 3)
        ax = fig.add_subplot(gs[row, col])
        ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.04, 0.06), 0.92, 0.88, boxstyle="round,pad=0.04",
            facecolor=BG_CARD, edgecolor="#333", linewidth=1))
        ax.text(0.5, 0.62, str(val), ha="center", va="center",
                color=ROMA_GOLD, fontsize=26, fontweight="bold")
        ax.text(0.5, 0.28, label, ha="center", va="center",
                color=TEXT_MUTED, fontsize=9)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _watermark(fig)
    return _save(fig, filename)
