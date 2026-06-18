"""
diada_participation.py — stress-test Q.diada_size (street turnout, millions) OFF the
IRL path, to check we are not overfitting the participation model to history.

The turnout model has only SIX global constants and NO per-year terms, so it cannot
overfit in the per-year sense. The real risk is a mis-shaped response *off* the
historical manifold. So instead of plotting the 8 IRL years, this plots the full
response surface over synthetic states the IRL path never visited, plus counterfactual
archetypes. The 8 IRL years are overlaid only as a reality check — they should look
like ordinary samples of a smooth surface, not specially-placed points.

Panels (saved to diada_participation.png):
  (A) turnout surface over (street gap, Cat-Spain relations), NO vote pending
  (B) same surface WITH a vote pending (+0.6M draw)
  (C) marginal sweeps: turnout vs gap and vs relations, vote vs no-vote
  (D) counterfactual archetypes + grief behaviour (bars), with the clamp band shown

Run:  python diada_participation.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from diada_dynamics import street_diada, load_real_data, SITUATION, PARAMS, _full_state


def synth(gap, csr, sd=40.0, vote=None, broken=False):
    """A synthetic pre-Diada state with a chosen street gap and relations level."""
    s = dict(independence_movement=65.0, independence_trust=65.0 - gap,
             social_dissent=sd, cat_spa_relations=csr, podemos_channeling=0.0,
             broken_roadmap=broken, referendum_pending=False,
             consultation_pending=False, cat_caretaker_gov=False)
    if vote == 'ref':
        s['referendum_pending'] = True
    elif vote == 'cons':
        s['consultation_pending'] = True
    elif vote == 'elec':
        s['cat_caretaker_gov'] = True
    return s


def size_of(state):
    return street_diada(state)['_diada_size']


def main():
    states, _, src = load_real_data()
    years = sorted(states)

    gaps = np.linspace(0, 50, 120)
    csrs = np.linspace(5, 80, 120)
    GG, CC = np.meshgrid(gaps, csrs)

    def surface(vote=None):
        Z = np.zeros_like(GG)
        for i in range(GG.shape[0]):
            for j in range(GG.shape[1]):
                Z[i, j] = size_of(synth(GG[i, j], CC[i, j], vote=vote))
        return Z

    Z_novote = surface(None)
    Z_vote = surface('cons')
    vmin, vmax = PARAMS.TURN_MIN, PARAMS.TURN_MAX

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle('Diada turnout model (Q.diada_size, millions) — off-path stress test',
                 fontsize=14, fontweight='bold')

    # IRL year positions (gap, relations) + real flags/size
    irl = {}
    for y in years:
        st = _full_state(y, states)
        out = street_diada(st)
        irl[y] = (out['_gap'], states[y]['cat_spa_relations'], out['_diada_size'],
                  bool(SITUATION[y].get('referendum_pending') or SITUATION[y].get('consultation_pending')
                       or SITUATION[y].get('cat_caretaker_gov')),
                  bool(SITUATION[y].get('broken_roadmap')))

    def draw_surface(ax, Z, title, want_vote):
        pc = ax.pcolormesh(GG, CC, Z, cmap='viridis', vmin=vmin, vmax=vmax, shading='auto')
        cs = ax.contour(GG, CC, Z, levels=[0.5, 0.75, 1.0, 1.25, 1.5, 1.75],
                        colors='white', linewidths=0.7, alpha=0.7)
        ax.clabel(cs, fmt='%.2fM', fontsize=7)
        fig.colorbar(pc, ax=ax, label='turnout (M)')
        # overlay the IRL years whose vote-state matches this panel and not broken
        for y, (g, c, sz, has_vote, broken) in irl.items():
            if has_vote == want_vote and not broken:
                ax.plot(g, c, 'o', ms=9, mfc='white', mec='black', mew=1.5, zorder=5)
                ax.annotate(f'{y}\n{sz:.2f}M', (g, c), color='white', fontsize=8,
                            ha='center', va='center', fontweight='bold')
        ax.set_xlabel('street gap  (independence_movement − independence_trust)')
        ax.set_ylabel('cat_spa_relations  (← repression | dialogue →)')
        ax.set_title(title)

    draw_surface(axes[0, 0], Z_novote,
                 '(A) NO vote pending — IRL non-vote, non-grief years overlaid', want_vote=False)
    draw_surface(axes[0, 1], Z_vote,
                 '(B) vote pending (+draw) — IRL vote years overlaid', want_vote=True)

    # ── (C) marginal sweeps ──────────────────────────────────────────────────
    ax = axes[1, 0]
    for csr0, ls in [(40, '-'), (15, '--')]:
        ax.plot(gaps, [size_of(synth(g, csr0)) for g in gaps], ls, color='#1f77b4',
                label=f'no vote, relations={csr0}')
        ax.plot(gaps, [size_of(synth(g, csr0, vote='cons')) for g in gaps], ls, color='#ff7f0e',
                label=f'vote pending, relations={csr0}')
    ax.axhline(vmin, color='gray', ls=':', lw=1); ax.axhline(vmax, color='gray', ls=':', lw=1)
    ax.annotate('clamp floor 0.2M', (1, vmin + 0.02), fontsize=7, color='gray')
    ax.annotate('clamp ceiling 2.0M', (1, vmax - 0.08), fontsize=7, color='gray')
    ax.set_xlabel('street gap  (IM − IT)'); ax.set_ylabel('turnout (M)')
    ax.set_title('(C) Marginal response: turnout vs gap\n(blue = no vote, orange = vote; solid relations=40, dashed=15)')
    ax.legend(fontsize=8, loc='lower right'); ax.grid(alpha=0.3)

    # ── (D) counterfactual archetypes ────────────────────────────────────────
    ax = axes[1, 1]
    scen = [
        ('Apathetic\n(gap5, dialogue)',      synth(5,  60)),
        ('Simmering\n(gap25, neutral)',      synth(25, 35)),
        ('Hot, no vote\n(gap40, tense)',     synth(40, 30)),
        ('Repression\n(gap40, CSR8)',        synth(40, 8)),
        ('Referendum\n(gap25, CSR20)',       synth(25, 20, vote='ref')),
        ('Plebiscite elec\n(gap25, CSR25)',  synth(25, 25, vote='elec')),
        ('Grief\n(broken, CSR6, SD55)',      synth(30, 6,  sd=55, broken=True)),
        ('Healing\n(broken, CSR8, SD42)',    synth(25, 8,  sd=42, broken=True)),
        ('Max-out\n(gap50, CSR5, ref)',      synth(50, 5,  vote='ref')),
    ]
    labels = [s[0] for s in scen]
    vals = [size_of(s[1]) for s in scen]
    cols = ['#7f7f7f', '#1f77b4', '#1f77b4', '#9467bd', '#ff7f0e', '#ff7f0e',
            '#d62728', '#2ca02c', '#8c564b']
    bars = ax.bar(range(len(scen)), vals, color=cols)
    ax.axhline(vmin, color='gray', ls=':', lw=1); ax.axhline(vmax, color='gray', ls=':', lw=1)
    ax.set_xticks(range(len(scen)))
    ax.set_xticklabels(labels, fontsize=7.5, rotation=0)
    ax.set_ylabel('turnout (M)'); ax.set_ylim(0, 2.15)
    ax.set_title('(D) Counterfactual archetypes (synthetic, NOT IRL years)')
    for b, v in zip(bars, vals):
        ax.annotate(f'{v:.2f}', (b.get_x() + b.get_width()/2, v), ha='center', va='bottom', fontsize=8)
    ax.grid(axis='y', alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig('diada_participation.png', dpi=130)
    print('saved diada_participation.png')

    # console echo of the archetypes for quick scanning
    print('\narchetype turnout (M):')
    for lab, s in scen:
        print(f'  {lab.replace(chr(10), " "):36} {size_of(s):.2f}')


if __name__ == '__main__':
    main()
