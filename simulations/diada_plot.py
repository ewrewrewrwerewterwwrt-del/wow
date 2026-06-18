"""
diada_plot.py — assessment figure for the dynamic Diada model in diada_dynamics.py.

Produces a 2x2 panel saved to diada_dynamics.png:

  (A) IM-delta: proposed vs calibrated target, per year (the headline accuracy check).
  (B) Calibration fit: proposed vs target for ALL four state variables, vs the y=x line.
  (C) Magnitude decomposition: what drives each year's size (baseline / autonomous
      street floor / mobilisation), with the net antagonism+channel multiplier and the
      grief sign flip marked.
  (D) Trust sweep: holding everything else fixed, vary independence_trust to show the
      street's autonomy (stays hot while trust is low) and the institutionalisation
      cooldown (cools as trust closes the IM-IT gap).

2012 is treated as a HARDCODED special case (the watershed novelty premium is not in
any Q variable) and is drawn hollow / excluded from the fit scatter.

Run:  python diada_plot.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from diada_dynamics import (
    street_diada, load_real_data, SITUATION, PARAMS, _full_state,
)

VARS = ['independence_movement', 'independence_trust', 'social_dissent', 'cat_spa_relations']
VLAB = {'independence_movement': 'IM', 'independence_trust': 'IT',
        'social_dissent': 'SD', 'cat_spa_relations': 'CSR'}
VCOL = {'independence_movement': '#1f77b4', 'independence_trust': '#2ca02c',
        'social_dissent': '#d62728', 'cat_spa_relations': '#9467bd'}
HARDCODED = {2012}

PROP = '#1f77b4'   # proposed
TARG = '#bbbbbb'   # calibrated target


def main():
    states, targets, src = load_real_data()
    years = sorted(states)
    out = {y: street_diada(_full_state(y, states)) for y in years}

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'Dynamic Diada model — assessment (pre-Diada states: {src})',
                 fontsize=14, fontweight='bold')

    # ── (A) IM delta proposed vs target ──────────────────────────────────────
    ax = axes[0, 0]
    x = np.arange(len(years))
    w = 0.38
    prop_im = [out[y]['independence_movement'] for y in years]
    targ_im = [targets[y]['independence_movement'] for y in years]
    bars_p = ax.bar(x - w/2, prop_im, w, label='proposed', color=PROP)
    ax.bar(x + w/2, targ_im, w, label='calibrated target', color=TARG)
    # mark hardcoded years hollow
    for i, y in enumerate(years):
        if y in HARDCODED:
            bars_p[i].set_facecolor('white')
            bars_p[i].set_edgecolor(PROP)
            bars_p[i].set_hatch('////')
    ax.axhline(0, color='k', lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(years)
    ax.set_ylabel('independence_movement delta')
    ax.set_title('(A) IM delta: proposed vs target  (2012 = hardcoded, hatched)')
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)
    for i, (p, t) in enumerate(zip(prop_im, targ_im)):
        ax.annotate(f'{p:+.1f}', (x[i]-w/2, p), ha='center',
                    va='bottom' if p >= 0 else 'top', fontsize=8)

    # ── (B) calibration fit scatter (all 4 vars) ─────────────────────────────
    ax = axes[0, 1]
    lim = 0
    for v in VARS:
        xs = [targets[y][v] for y in years if y not in HARDCODED]
        ys = [out[y][v] for y in years if y not in HARDCODED]
        ax.scatter(xs, ys, color=VCOL[v], label=VLAB[v], s=55, zorder=3)
        lim = max(lim, max(abs(np.array(xs+ys)), default=0))
    lim = lim * 1.15 + 1
    ax.plot([-lim, lim], [-lim, lim], 'k--', lw=1, alpha=0.6, label='perfect (y=x)')
    ax.axhline(0, color='k', lw=0.6); ax.axvline(0, color='k', lw=0.6)
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_aspect('equal')
    ax.set_xlabel('calibrated target delta'); ax.set_ylabel('proposed delta')
    ax.set_title('(B) Fit across all 4 variables (2012 excluded)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(alpha=0.3)

    # ── (C) magnitude decomposition ──────────────────────────────────────────
    ax = axes[1, 0]
    base  = np.array([out[y]['_base'] for y in years])
    gapt  = np.array([out[y]['_gap_term'] for y in years])
    mobt  = np.array([out[y]['_mobil_term'] for y in years])
    ax.bar(x, base, w*1.6, label='baseline', color='#999999')
    ax.bar(x, gapt, w*1.6, bottom=base, label='autonomous street floor  GAP·(IM−IT)', color='#1f77b4')
    ax.bar(x, mobt, w*1.6, bottom=base+gapt, label='mobilisation (vote pending)', color='#ff7f0e')
    # net magnitude after antag x channel
    mags = [out[y]['_mag'] for y in years]
    ax.plot(x, mags, 'kD', ms=7, label='net magnitude (×antag ×channel)', zorder=5)
    for i, y in enumerate(years):
        v = out[y]['_valence']
        if v < 0:
            ax.annotate('GRIEF\n(sign flips)', (x[i], mags[i]), ha='center', va='bottom',
                        fontsize=8, color='#d62728', fontweight='bold')
        a, c = out[y]['_antag'], out[y]['_channel_mult']
        ax.annotate(f'×{a:.2f}' + (f'\n×{c:.2f}' if c < 1 else ''),
                    (x[i], (base+gapt+mobt)[i]), ha='center', va='bottom', fontsize=7, color='#555')
    ax.set_xticks(x); ax.set_xticklabels(years)
    ax.set_ylabel('magnitude (pre-valence)')
    ax.set_title('(C) What drives the size each year')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(axis='y', alpha=0.3)

    # ── (D) trust sweep: autonomy + institutionalisation cooldown ────────────
    ax = axes[1, 1]
    it_grid = np.linspace(15, 60, 91)
    for y, style in [(2016, '-'), (2014, '--')]:
        base_state = _full_state(y, states)
        curve = []
        for it in it_grid:
            s = dict(base_state); s['independence_trust'] = it
            curve.append(street_diada(s)['independence_movement'])
        lbl = f'{y} state'
        if SITUATION[y].get('consultation_pending') or SITUATION[y].get('referendum_pending'):
            lbl += ' (vote pending)'
        line, = ax.plot(it_grid, curve, style, lw=2, label=lbl)
        # marker at the historical trust
        it0 = states[y]['independence_trust']
        ax.plot(it0, street_diada(base_state)['independence_movement'],
                'o', color=line.get_color(), ms=9, zorder=5)
        ax.annotate(f'  IRL IT={it0:.0f}', (it0, street_diada(base_state)['independence_movement']),
                    fontsize=8, color=line.get_color())
    ax.axhline(0, color='k', lw=0.8)
    ax.set_xlabel('independence_trust  (institutional faith →)')
    ax.set_ylabel('resulting IM delta')
    ax.set_title('(D) Trust sweep: street stays hot at low trust,\ncools as trust closes the IM−IT gap')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(alpha=0.3)
    ax.annotate('STREET AUTONOMOUS\n(parties haven\'t earned trust)', (17, ax.get_ylim()[1]*0.6),
                fontsize=8, color='#1f77b4')
    ax.annotate('INSTITUTIONALISED\n(gap closed)', (50, ax.get_ylim()[1]*0.15),
                fontsize=8, color='#555')

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out_path = 'diada_dynamics.png'
    fig.savefig(out_path, dpi=130)
    print(f'saved {out_path}')


if __name__ == '__main__':
    main()
