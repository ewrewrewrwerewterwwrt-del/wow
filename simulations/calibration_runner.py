"""
Route to Ítaca — Vote Model Calibration Runner
================================================
Integrates the v4 engine loop with the vote model, checking predicted
seat counts at the three election checkpoints against anchor targets.

Election months (1 = Aug 2012):
  2012-11  ->  month 4
  2015-09  ->  month 38
  2017-12  ->  month 65

Usage:
  python calibration_runner.py            # single run, verbose comparison
  python calibration_runner.py --tune     # auto-tune matrix coefficients
"""

import importlib, argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Dynamic import for hyphenated filename
import importlib.util
spec = importlib.util.spec_from_file_location(
    'eng4', 'economic_engine.py')
eng4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng4)

import vote_model as vm_mod
from vote_model import (VoteModel, FAMILIES, FAM_IDX, BASE_T , N_VARS, VAR_NAMES)

ELECTION_MONTHS = {4: '2012', 38: '2015', 65: '2017'}
ANCHOR_PATH     = 'results/election_anchors.pkl'

# ---- TARGET SEATS -----------------------------------------------------------

def anchor_seats(year):
    """Seat counts implied by the raw anchor support via D'Hondt."""
    tmp = VoteModel(anchor_path=ANCHOR_PATH)
    tmp._load_from_anchor(year)
    return tmp.seat_counts()

# ---- MAIN SIMULATION --------------------------------------------------------

def run_simulation(T_override=None, verbose=True, seed=42):
    """
    Run the full IRL simulation (engine v4 + vote model).

    Parameters
    ----------
    T_override : np.ndarray or None
        If provided, replaces BASE_T in vote_model for this run.
    verbose : bool
    seed : int

    Returns
    -------
    (rmse, seat_results_dict, seat_history_df)
    """
    np.random.seed(seed)

    # Optionally inject a custom transfer matrix
    if T_override is not None:
        vm_mod.BASE_T = T_override
    else:
        vm_mod.BASE_T = BASE_T.copy()

    # Compute anchor targets
    targets = {yr: anchor_seats(yr) for yr in ['2012', '2015', '2017']}

    if verbose:
        print("\n=== TARGET SEATS (D'Hondt from anchor support) ===")
        for yr, seats in targets.items():
            row = '  '.join(f"{f}:{s}" for f,s in
                            sorted(seats.items(), key=lambda x:-x[1]) if s > 0)
            print(f"  {yr}: {row}")

    # --- Engine initialisation (mirrors eng4.simulate internals) -------------
    Q = {
        'gdp_growth':             -3.1,
        'unemployment':            22.5,
        'public_debt':             26.0,
        'generalitat_surplus':     -2.3,
        'cat_spa_relations':       38.0,
        'independence_movement':   65.0,
        'independence_trust':      28.0,
        'social_dissent':          72.0,
        'welfare_index':           72.0,
    }
    flags = {
        'ecb_qe_enabled':     True,
        'fla_active':         True,
        'fla_escalated':      False,
        'art155_ever':        False,
        'podemos_surged':     False,
        'podemos_channeling': 0.0,
    }
    event_fired  = {ev['id']: False for ev in eng4.EVENTS}
    pulse_queue  = []
    dissent_prev = Q['social_dissent']
    gob_tl       = eng4.GOBIERNO_IRL_TIMELINE
    gen_tl       = eng4.GENERALITAT_IRL_TIMELINE

    # --- Vote model init (2012 anchor) ---------------------------------------
    vmodel = VoteModel(anchor_path=ANCHOR_PATH)

    seat_results  = {}
    vote_results  = {}
    seat_history  = []

    for m in range(1, 91):
        year      = 2012 + (m - 1) // 12
        cal_month = ((m - 1 + 7) % 12) + 1
        gob       = eng4.get_gov(m, gob_tl)
        gen       = eng4.get_gov(m, gen_tl)

        if gen == 'ART155':
            flags['art155_ever'] = True

        # Save pre-tick state for deltas
        Q_prev = dict(Q)

        # ── Pulses ────────────────────────────────────────────────────────────
        still = []
        for pulse in pulse_queue:
            Q[pulse['variable']] += pulse['monthly_delta']
            pulse['remaining'] -= 1
            if pulse['remaining'] > 0:
                still.append(pulse)
        pulse_queue = still

        # ── Events ───────────────────────────────────────────────────────────
        podemos_fired_this_month = False
        for ev in eng4.EVENTS:
            eid = ev['id']
            if ev['one_time'] and event_fired[eid]:
                continue
            if ev['trigger_fn'](m, year, cal_month, Q, flags):
                for var, delta in ev['effects'].items():
                    if var in Q:
                        Q[var] += delta
                if ev['flag_set']:
                    flags[ev['flag_set']] = True
                if ev['pulse']:
                    p = ev['pulse']
                    pulse_queue.append({
                        'variable':      p['variable'],
                        'monthly_delta': p['monthly_delta'],
                        'remaining':     p['duration'],
                    })
                if eid == 'podemos_surge':
                    flags['podemos_channeling'] = 1.0
                    podemos_fired_this_month = True
                if ev['one_time']:
                    event_fired[eid] = True

        # ── Podemos channeling decay ──────────────────────────────────────────
        if flags['podemos_surged']:
            if Q['social_dissent'] < dissent_prev - 0.5:
                flags['podemos_channeling'] = min(1.0, flags['podemos_channeling'] + 0.01)
            else:
                flags['podemos_channeling'] = max(0.0, flags['podemos_channeling'] - 0.03)
        dissent_prev = Q['social_dissent']

        # ── Clips ────────────────────────────────────────────────────────────
        Q['independence_movement'] = np.clip(Q['independence_movement'], 25, 95)
        Q['independence_trust']    = np.clip(Q['independence_trust'],    15, 60)
        Q['social_dissent']        = np.clip(Q['social_dissent'],         0, 100)
        Q['cat_spa_relations']     = np.clip(Q['cat_spa_relations'],       5, 80)
        Q['welfare_index']         = np.clip(Q['welfare_index'],          20, 100)

        # ── GDP ───────────────────────────────────────────────────────────────
        struc     = eng4.STRUCTURAL_GDP.get(year, 2.0)
        gob_mod   = eng4.GOB_GDP_ABS.get(gob, 0.0)
        gen_mod   = eng4.GEN_GDP_ABS.get(gen, 0.0)
        spa_adj   = eng4.cat_spa_gdp_adj(Q['cat_spa_relations'])
        i_drag    = eng4.indy_gdp_drag(Q['independence_movement'], Q['independence_trust'])
        gdp_target = struc + gob_mod + gen_mod + spa_adj + i_drag
        ar = 0.60 if gen == 'ART155' else 0.72
        Q['gdp_growth'] = np.clip(
            ar * Q['gdp_growth'] + (1 - ar) * gdp_target + np.random.normal(0, 0.28),
            -9, 7)

        # ── Unemployment ──────────────────────────────────────────────────────
        gdp_m = Q['gdp_growth'] / 12
        lrm   = 1 + eng4.UNEMP_PARAMS['reform_bonus']
        rec   = (eng4.UNEMP_PARAMS['recover_coeff'] * lrm
                 * eng4.GEN_UNEMP_MOD.get(gen, 1.0)
                 * eng4.GOB_UNEMP_MOD.get(gob, 1.0))
        u_delta = -gdp_m * eng4.UNEMP_PARAMS['destruct_coeff'] if gdp_m < 0 else -gdp_m * rec
        Q['unemployment'] = np.clip(
            Q['unemployment'] + u_delta, eng4.UNEMP_PARAMS['natural_floor'], 36)

        # ── Surplus ───────────────────────────────────────────────────────────
        fla_bonus = 0.0
        if flags['fla_active']:
            fla_bonus += eng4.SURPLUS_FLA_BONUS_BY_GOB.get(gob, 0.0)
        if flags['fla_escalated']:
            fla_bonus += eng4.SURPLUS_FLA_ESCALATION_BONUS
        base_drift = eng4.SURPLUS_DRIFT_BY_GEN.get(gen, 0.020)
        gse        = (Q['gdp_growth'] / 100) * eng4.SURPLUS_GDP_SENSITIVITY / 12
        Q['generalitat_surplus'] = np.clip(
            Q['generalitat_surplus'] + base_drift + fla_bonus + gse
            + np.random.normal(0, 0.10), -5, 2)

        # ── Debt ─────────────────────────────────────────────────────────────
        Q['public_debt'] = np.clip(
            Q['public_debt'] + eng4.compute_debt_delta(
                Q['generalitat_surplus'], gdp_m, Q['public_debt']), 0, 80)

        # ── Welfare ──────────────────────────────────────────────────────────
        sp  = eng4.WELFARE_SPENDING_BY_GEN.get(gen, 0.0)
        gwb = (Q['gdp_growth'] / 12) * eng4.WELFARE_GDP_SENSITIVITY
        raw_w = sp + gwb + np.random.normal(0, 0.20)
        wdelta = min(raw_w, eng4.WELFARE_RECOVERY_CAP) if raw_w > 0 else max(raw_w, -eng4.WELFARE_CUT_CAP)
        Q['welfare_index'] = np.clip(Q['welfare_index'] + wdelta, 20, 100)

        # ── Cat-Spa ───────────────────────────────────────────────────────────
        if gen == 'ART155':
            csd = eng4.CAT_SPA_ART155_DRIFT
        else:
            csd = eng4.get_cat_spa_drift(gob, gen)
        if flags['art155_ever'] and gen != 'ART155':
            if Q['cat_spa_relations'] < eng4.CAT_SPA_POST155_FLOOR and csd > 0:
                csd = min(csd, eng4.CAT_SPA_POST155_RECOVERY_CAP)
        Q['cat_spa_relations'] = np.clip(
            Q['cat_spa_relations'] + csd + np.random.normal(0, 0.6), 5, 80)

        # ── Indy movement ────────────────────────────────────────────────────
        seasonal  = eng4.indy_seasonal_pulse(cal_month, year)
        gap       = eng4.INDY_RESTING_LEVEL - Q['independence_movement']
        Q['independence_movement'] = np.clip(
            Q['independence_movement'] + eng4.INDY_REVERSION_SPEED * gap
            + seasonal + np.random.normal(0, 0.7), 25, 95)

        trust_drift = -1.8 if gen == 'ART155' else +0.06
        Q['independence_trust'] = np.clip(
            Q['independence_trust'] + trust_drift + np.random.normal(0, 0.4), 15, 60)

        # ── Social dissent ────────────────────────────────────────────────────
        eq  = eng4.dissent_equilibrium(
            Q['unemployment'], Q['welfare_index'], gob, gen,
            podemos_channeling=flags['podemos_channeling'])
        gap = eq - Q['social_dissent']
        Q['social_dissent'] = np.clip(
            Q['social_dissent'] + eng4.DISSENT_REVERSION_SPEED * gap
            + np.random.normal(0, 0.8), 0, 100)

        # ── Vote model tick ──────────────────────────────────────────────────
        engine_state = {
            'indy_movement':      Q['independence_movement'],
            'indy_trust':         Q['independence_trust'],
            'social_dissent':     Q['social_dissent'],
            'welfare_index':      Q['welfare_index'],
            'cat_spa_relations':  Q['cat_spa_relations'],
            'unemployment':       Q['unemployment'],
            'podemos_channeling': flags['podemos_channeling'],
            **flags,
            'gen_party':          gen.lower().replace('_abs','').replace('_min',''),
            'gob_party':          gob.lower().replace('_abs','').replace('_min',''),
        }
        delta_vars = {
            'indy_movement':     Q['independence_movement']  - Q_prev['independence_movement'],
            'indy_trust':        Q['independence_trust']     - Q_prev['independence_trust'],
            'social_dissent':    Q['social_dissent']         - Q_prev['social_dissent'],
            'welfare_index':     Q['welfare_index']          - Q_prev['welfare_index'],
            'cat_spa_relations': Q['cat_spa_relations']      - Q_prev['cat_spa_relations'],
            'unemployment':      Q['unemployment']           - Q_prev['unemployment'],
            'podemos_pulse':     1.0 if podemos_fired_this_month else 0.0,
        }
        vmodel.update(engine_state, delta_vars)

        # ── Record seats ─────────────────────────────────────────────────────
        seats = vmodel.seat_counts()
        seat_history.append({'month': m, **{f: seats.get(f, 0) for f in FAMILIES}})

        # ── Election check ────────────────────────────────────────────────────
        if m in ELECTION_MONTHS:
            yr = ELECTION_MONTHS[m]
            seat_results[yr] = dict(seats)
            
            # Record popular vote %
            avg_support = vmodel.support.mean(axis=(1,2))
            active_support = avg_support.copy()
            active_support[FAM_IDX['abs']] = 0.0
            total_active = active_support.sum()
            if total_active > 0:
                vote_results[yr] = {fam: (active_support[FAM_IDX[fam]] / total_active * 100.0) 
                                   for fam in FAMILIES if fam != 'abs'}
            else:
                vote_results[yr] = {fam: 0.0 for fam in FAMILIES if fam != 'abs'}

            if verbose:
                target = targets[yr]
                vmodel.print_snapshot(label=f"Month {m} — {yr} Election")
                print(f"\n  vs. anchor target:")
                print(f"  {'Family':<10}  {'Pred':>5}  {'Real':>5}  {'Diff':>5}")
                print(f"  {'-'*35}")
                for fam in FAMILIES:
                    p = seats.get(fam, 0)
                    t = target.get(fam, 0)
                    d = p - t
                    if p > 0 or t > 0:
                        flag = " <--" if abs(d) >= 5 else ""
                        print(f"  {fam:<10}  {p:>5}  {t:>5}  {d:>+5}{flag}")

    # ── RMSE ─────────────────────────────────────────────────────────────────
    sq_err = 0.0
    n      = 0
    for yr, predicted in seat_results.items():
        for fam in FAMILIES:
            diff = predicted.get(fam, 0) - targets[yr].get(fam, 0)
            sq_err += diff ** 2
            n      += 1
    rmse = (sq_err / n) ** 0.5 if n > 0 else 999.0

    if verbose:
        print(f"\n=== CALIBRATION SUMMARY ===")
        print(f"  Seat RMSE across 3 elections × {len(FAMILIES)} families: {rmse:.2f}")

    return rmse, seat_results, vote_results, pd.DataFrame(seat_history)


def get_party_label(family, year):
    """Map family code to readable party name for a given election year."""
    labels = {
        '2012': {
            'icr': 'CiU', 'il': 'ERC', 'fl': 'ICV-EUiA', 'psc': 'PSC', 
            'cs': 'Cs', 'ppc': 'PPC', 'cup': 'CUP'
        },
        '2015': {
            'icr': 'JxSí', 'il': 'JxSí', 'fl': 'CSQP', 'psc': 'PSC', 
            'cs': 'Cs', 'ppc': 'PPC', 'cup': 'CUP', 'unio': 'Unió'
        },
        '2017': {
            'icr': 'JxCat', 'il': 'ERC', 'fl': 'CatComú', 'psc': 'PSC', 
            'cs': 'Cs', 'ppc': 'PPC', 'cup': 'CUP'
        }
    }
    # JxSí is a special case where icr/il are merged in 2015 results
    return labels.get(year, {}).get(family, family.upper())

def plot_calibration_results(seat_results, vote_results, targets):
    """Generate a visual comparison of predicted vs target seats."""
    years = sorted(seat_results.keys())
    fig, axes = plt.subplots(len(years), 1, figsize=(14, 6 * len(years)))
    if len(years) == 1: axes = [axes]

    colors = {
        'icr': '#34d399', 'il': '#fbbf24', 'cup': '#dc2626',
        'fl': '#8b5cf6', 'psc': '#ef4444', 'cs': '#f97316',
        'ppc': '#3b82f6', 'vox': '#1e3a8a', 'abs': '#94a3b8',
        'unio': '#064e3b', 'pdcat': '#059669'
    }

    for i, yr in enumerate(years):
        ax = axes[i]
        pred_seats = seat_results[yr]
        targ_seats = targets[yr]
        pred_votes = vote_results.get(yr, {})
        
        # Determine families to show (skip JxSí redundancy if needed, but here we show families)
        families = [f for f in FAMILIES if pred_seats.get(f,0) > 0 or targ_seats.get(f,0) > 0]
        # In 2015, icr and il were both JxSí, but we keep them separate in model. 
        # For the plot, let's keep them as they are but label them.
        
        x = np.arange(len(families))
        width = 0.35

        # Plot seats
        rects1 = ax.bar(x - width/2, [pred_seats.get(f, 0) for f in families], width, 
                       label='Predicted Seats', color=[colors.get(f, '#ccc') for f in families], alpha=0.8)
        rects2 = ax.bar(x + width/2, [targ_seats.get(f, 0) for f in families], width, 
                       label='Target Seats', color=[colors.get(f, '#ccc') for f in families], hatch='//', alpha=0.5)

        # Add seat delta labels and popular vote %
        for j, fam in enumerate(families):
            p_s = pred_seats.get(fam, 0)
            t_s = targ_seats.get(fam, 0)
            diff = p_s - t_s
            p_v = pred_votes.get(fam, 0.0)
            
            # Seat delta text
            color = 'green' if diff == 0 else ('blue' if diff > 0 else 'red')
            ax.text(j, max(p_s, t_s) + 1, f"{diff:+d}", ha='center', va='bottom', 
                    fontweight='bold', color=color, fontsize=10)
            
            # Popular vote % text (at the base of the bar)
            if p_v > 0:
                ax.text(j - width/2, p_s / 2 if p_s > 5 else p_s + 0.5, f"{p_v:.1f}%", 
                        ha='center', va='center', rotation=90, fontsize=9, color='white' if p_s > 5 else 'black')

        ax.set_ylabel('Seats')
        ax.set_title(f'Election {yr}: Predicted vs Target Seats', fontweight='bold', fontsize=14)
        
        # Use readable party names for labels
        labels = [get_party_label(f, yr) for f in families]
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=0, fontsize=11)
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        ax.set_ylim(0, max(max(pred_seats.values()), max(targ_seats.values())) + 5)

    plt.tight_layout()
    plt.savefig('results/election_performance_final.png', dpi=150)
    plt.close()
    print(f"Enhanced calibration plot saved to results/election_performance_final.png")

# ---- ENTRY POINT ------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tune', action='store_true',
                        help='Run Nelder-Mead tuning on matrix magnitudes')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    if args.tune:
        from scipy.optimize import minimize
        print("Starting coefficient tuning (Nelder-Mead)...")
        print("Optimizing magnitude scalars for each column of BASE_T.\n")

        base = BASE_T.copy()
        x0   = np.ones(N_VARS)   # scale factors per variable column

        def objective(x):
            T = base.copy()
            for j in range(N_VARS):
                T[:, j] *= max(0.0, x[j])
            rmse, _, _, _ = run_simulation(T_override=T, verbose=False, seed=args.seed)
            return rmse

        result = minimize(objective, x0, method='Nelder-Mead',
                          options={'maxiter': 500, 'xatol': 0.02, 'fatol': 0.05})
        best_x = result.x
        print(f"\nOptimisation complete. Final RMSE: {result.fun:.2f}")
        print("Best column scalars:")
        for j, name in enumerate(VAR_NAMES):
            print(f"  {name:<15}: {best_x[j]:.4f}")

        # Re-run with best params, verbose
        T_best = base.copy()
        for j in range(N_VARS):
            T_best[:, j] *= max(0.0, best_x[j])
        rmse, results, vote_results, history = run_simulation(T_override=T_best, verbose=True, seed=args.seed)
        
        # Generate plot
        targets = {yr: anchor_seats(yr) for yr in ['2012', '2015', '2017']}
        plot_calibration_results(results, vote_results, targets)

    else:
        rmse, results, vote_results, history = run_simulation(verbose=True, seed=args.seed)
        history.to_csv('results/vote_history_irl.csv', index=False)
        print(f"\n  Seat history saved to results/vote_history_irl.csv")
        
        # Generate plot
        targets = {yr: anchor_seats(yr) for yr in ['2012', '2015', '2017']}
        plot_calibration_results(results, vote_results, targets)
