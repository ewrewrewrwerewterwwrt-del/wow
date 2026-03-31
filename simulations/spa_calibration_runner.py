"""
spa_calibration_runner.py — Spanish Congreso calibration runner.
=================================================================
Integrates economic_engine.py (Catalan macro) with spa_vote_model.py
and spa_economic_timeline.py to simulate Spanish congressional vote
dynamics from Aug 2012 to Nov 2019 (88 months).

Election checkpoints (month 1 = Aug 2012):
  Month 41 — Dec 2015 (20-D)
  Month 47 — Jun 2016 (26-J)
  Month 81 — Apr 2019 (28-A)
  Month 88 — Nov 2019 (10-N)

Usage:
  python spa_calibration_runner.py              # single run, verbose
  python spa_calibration_runner.py --tune       # Nelder-Mead tuning
  python spa_calibration_runner.py --seed 123   # fix random seed
"""

import sys
import os
import argparse
import importlib.util

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from copy import deepcopy

# ── Module imports ────────────────────────────────────────────────────────────

# Load economic_engine.py from the same directory
_HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location('eng', os.path.join(_HERE, 'economic_engine.py'))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

from spa_vote_model import (                                        # noqa: E402
    SpaVoteModel, CONSTITUENCIES, get_active_families,
    ECON_BASE_DEFAULT, DEFAULTS as VM_DEFAULTS,
)
from spa_economic_timeline import (                                 # noqa: E402
    EVENTS_SPA, SPA_UNEMP_OFFSET, get_spa_gob,
)

# ── ELECTION CHECKPOINTS ─────────────────────────────────────────────────────

ELECTION_MONTHS = {
    41: '2015',
    47: '2016',
    81: '2019a',
    88: '2019n',
}
N_MONTHS = 88   # Aug 2012 → Nov 2019

# ── PARTY → FAMILY MAPPING (for anchor loading) ──────────────────────────────

PARTY_TO_FAMILY = {
    'pp':        'pp',
    'psoe':      'psoe',
    'podemos':   'podemos',
    'up':        'podemos',   # Unidas Podemos (2019)
    'sumar':     'podemos',   # Sumar (post-period, not in our window)
    'cs':        'cs',
    'vox':       'vox',
    'iu':        'iu',
    'mpais':     'mas_pais',  # Más País
    # Catalunya
    'erc':       'erc',
    'dl':        'cat_conv',
    'cdc':       'cat_conv',
    'jxsi':      'cat_conv',
    'jxcat':     'cat_conv',
    'junts':     'cat_conv',
    'cup':       'cup_spa',
    # Euskadi
    'pnv':       'pnv',
    'ehbildu':   'bildu',
    'amaiur':    'bildu',
    # Galicia — NOS is the En Marea coalition (bng + leftists), maps to bng family
    'bng':       'bng',
    'nos':       'bng',
    # Valencia
    'compromis': 'compromis',
    # Navarra
    'nsuma':     'nsuma',
    'upn':       'upn',
    'gbai':      'geroa_bai',
    # Balears
    'mes':       'mes',
    # Rest minors
    'cc':        'cc',
    'prc':       'prc',
    'te':        'te',
    'fac':       'foro',
}


def load_anchor_targets():
    """Load and aggregate real seat counts per family from simulation_results/."""
    data_dir = os.path.join(_HERE, '..', 'demographics_data')
    year_files = {
        '2015':  'spa_2015_results.csv',
        '2016':  'spa_2016_results.csv',
        '2019a': 'spa_2019-a_results.csv',
        '2019n': 'spa_2019-n_results.csv',
    }
    targets = {}
    for yr_key, fname in year_files.items():
        fpath = os.path.join(data_dir, 'simulation_results', fname)
        df    = pd.read_csv(fpath)
        seats = {}
        for _, row in df.iterrows():
            fam = PARTY_TO_FAMILY.get(str(row['party']).lower(), str(row['party']).lower())
            seats[fam] = seats.get(fam, 0) + int(row['seats'])
        targets[yr_key] = seats
    return targets


def load_initial_support():
    """Load Aug 2012 starting support % from spa_initial_2012.csv."""
    fpath = os.path.join(_HERE, '..', 'demographics_data', 'clean', 'spa_initial_2012.csv')
    df    = pd.read_csv(fpath)
    support = {c: {} for c in CONSTITUENCIES}
    for _, row in df.iterrows():
        support[str(row['constituency'])][str(row['party'])] = float(row['pct'])
    return support


# ── MAIN SIMULATION ───────────────────────────────────────────────────────────

def run_simulation(params=None, verbose=True, seed=42):
    """
    Run the full Aug 2012 → Nov 2019 simulation.

    Parameters
    ----------
    params : dict or None
        Override any DEFAULTS from spa_vote_model.py (e.g. noise_stdev, etc.)
    verbose : bool
    seed : int

    Returns
    -------
    (rmse, seat_results_dict, history_df)
    """
    np.random.seed(seed)

    targets         = load_anchor_targets()
    initial_support = load_initial_support()
    vmodel          = SpaVoteModel(initial_support, params=params)

    # ── Catalan economic engine initial state (mirrors calibration_runner.py) ──
    Q = {
        'gdp_growth':           -3.1,
        'unemployment':          22.5,
        'public_debt':           26.0,
        'generalitat_surplus':   -2.3,
        'cat_spa_relations':     38.0,
        'independence_movement': 65.0,
        'independence_trust':    28.0,
        'social_dissent':        72.0,
        'welfare_index':         72.0,
    }

    cat_flags = {
        'ecb_qe_enabled': True, 'fla_active': True, 'fla_escalated': False,
        'art155_ever': False, 'podemos_surged': False, 'podemos_channeling': 0.0,
        # Spanish vote model flags (shared dict, read by get_active_families)
        'vox_active': False, 'spa_cs_active': False,
        'spa_compromis_active': False, 'spa_mes_active': False,
        'spa_iu_split': False, 'spa_up_masq_split': False,
        'spa_nsuma_formed': False, 'spa_upn_independent': False,
        'spa_upn_defect': False, 'spa_cup_spa_active': False,
        'spa_fr_active': False, 'spa_foro_active': False,
        # Leadership recovery multipliers (set by timeline events)
        'psoe_leadership_mult': 0.0,
        'pp_leadership_mult':   0.0,
    }

    # Spanish political state (separate from Catalan flags)
    spa = {
        'corruption_pp':          0.0,
        'corruption_psoe':        0.0,
        'corruption_pp_decay':    0.998,
        'corruption_psoe_decay':  0.998,
        'coalition':              ['pp'],
    }

    cat_events_fired = {ev['id']: False for ev in eng.EVENTS}
    spa_events_fired = set()
    pulse_queue      = []
    dissent_prev     = Q['social_dissent']

    # Previous Spanish macro values for delta computation
    prev_spa = {
        'gdp':     Q['gdp_growth'],
        'unemp':   Q['unemployment'] + SPA_UNEMP_OFFSET,
        'welfare': Q['welfare_index'],
        'dissent': Q['social_dissent'],
        'cat_spa': Q['cat_spa_relations'],
    }

    gob_tl = eng.GOBIERNO_IRL_TIMELINE
    gen_tl = eng.GENERALITAT_IRL_TIMELINE

    seat_results = {}
    history      = []

    for m in range(1, N_MONTHS + 1):
        year      = 2012 + (m - 1) // 12
        cal_month = ((m - 1 + 7) % 12) + 1
        gob       = eng.get_gov(m, gob_tl)
        gen       = eng.get_gov(m, gen_tl)

        if gen == 'ART155':
            cat_flags['art155_ever'] = True

        Q_prev = dict(Q)

        # ── Catalan pulses ─────────────────────────────────────────────────
        still = []
        for pulse in pulse_queue:
            Q[pulse['variable']] += pulse['monthly_delta']
            pulse['remaining'] -= 1
            if pulse['remaining'] > 0:
                still.append(pulse)
        pulse_queue = still

        # ── Catalan events ─────────────────────────────────────────────────
        podemos_fired = False
        for ev in eng.EVENTS:
            eid = ev['id']
            if ev['one_time'] and cat_events_fired[eid]:
                continue
            if ev['trigger_fn'](m, year, cal_month, Q, cat_flags):
                for var, delta in ev['effects'].items():
                    if var in Q:
                        Q[var] += delta
                if ev['flag_set']:
                    cat_flags[ev['flag_set']] = True
                if ev['pulse']:
                    p = ev['pulse']
                    pulse_queue.append({
                        'variable': p['variable'],
                        'monthly_delta': p['monthly_delta'],
                        'remaining': p['duration'],
                    })
                if eid == 'podemos_surge':
                    cat_flags['podemos_channeling'] = 1.0
                    podemos_fired = True
                if ev['one_time']:
                    cat_events_fired[eid] = True

        # Podemos channeling decay
        if cat_flags.get('podemos_surged'):
            if Q['social_dissent'] < dissent_prev - 0.5:
                cat_flags['podemos_channeling'] = min(1.0, cat_flags.get('podemos_channeling', 0) + 0.01)
            else:
                cat_flags['podemos_channeling'] = max(0.0, cat_flags.get('podemos_channeling', 0) - 0.03)
        dissent_prev = Q['social_dissent']

        # ── Clips ──────────────────────────────────────────────────────────
        Q['independence_movement'] = np.clip(Q['independence_movement'], 25, 95)
        Q['independence_trust']    = np.clip(Q['independence_trust'],    15, 60)
        Q['social_dissent']        = np.clip(Q['social_dissent'],         0, 100)
        Q['cat_spa_relations']     = np.clip(Q['cat_spa_relations'],       5, 80)
        Q['welfare_index']         = np.clip(Q['welfare_index'],          20, 100)

        # ── Catalan economic tick ──────────────────────────────────────────
        # GDP
        struc      = eng.STRUCTURAL_GDP.get(year, 2.0)
        gob_mod    = eng.GOB_GDP_ABS.get(gob, 0.0)
        gen_mod    = eng.GEN_GDP_ABS.get(gen, 0.0)
        spa_adj    = eng.cat_spa_gdp_adj(Q['cat_spa_relations'])
        i_drag     = eng.indy_gdp_drag(Q['independence_movement'], Q['independence_trust'])
        gdp_target = struc + gob_mod + gen_mod + spa_adj + i_drag
        ar = 0.60 if gen == 'ART155' else 0.72
        Q['gdp_growth'] = np.clip(
            ar * Q['gdp_growth'] + (1 - ar) * gdp_target + np.random.normal(0, 0.28), -9, 7)

        # Unemployment
        gdp_m = Q['gdp_growth'] / 12
        lrm   = 1 + eng.UNEMP_PARAMS['reform_bonus']
        rec   = (eng.UNEMP_PARAMS['recover_coeff'] * lrm
                 * eng.GEN_UNEMP_MOD.get(gen, 1.0)
                 * eng.GOB_UNEMP_MOD.get(gob, 1.0))
        u_delta = -gdp_m * eng.UNEMP_PARAMS['destruct_coeff'] if gdp_m < 0 else -gdp_m * rec
        Q['unemployment'] = np.clip(Q['unemployment'] + u_delta, eng.UNEMP_PARAMS['natural_floor'], 36)

        # Surplus / Debt
        fla_bonus = 0.0
        if cat_flags.get('fla_active'):
            fla_bonus += eng.SURPLUS_FLA_BONUS_BY_GOB.get(gob, 0.0)
        if cat_flags.get('fla_escalated'):
            fla_bonus += eng.SURPLUS_FLA_ESCALATION_BONUS
        base_drift = eng.SURPLUS_DRIFT_BY_GEN.get(gen, 0.020)
        gse = (Q['gdp_growth'] / 100) * eng.SURPLUS_GDP_SENSITIVITY / 12
        Q['generalitat_surplus'] = np.clip(
            Q['generalitat_surplus'] + base_drift + fla_bonus + gse + np.random.normal(0, 0.10), -5, 2)
        Q['public_debt'] = np.clip(
            Q['public_debt'] + eng.compute_debt_delta(Q['generalitat_surplus'], gdp_m, Q['public_debt']), 0, 80)

        # Welfare
        sp    = eng.WELFARE_SPENDING_BY_GEN.get(gen, 0.0)
        gwb   = (Q['gdp_growth'] / 12) * eng.WELFARE_GDP_SENSITIVITY
        raw_w = sp + gwb + np.random.normal(0, 0.20)
        wdelta = min(raw_w, eng.WELFARE_RECOVERY_CAP) if raw_w > 0 else max(raw_w, -eng.WELFARE_CUT_CAP)
        Q['welfare_index'] = np.clip(Q['welfare_index'] + wdelta, 20, 100)

        # Cat-spa relations
        if gen == 'ART155':
            csd = eng.CAT_SPA_ART155_DRIFT
        else:
            csd = eng.get_cat_spa_drift(gob, gen)
        if (cat_flags.get('art155_ever') and gen != 'ART155'
                and Q['cat_spa_relations'] < eng.CAT_SPA_POST155_FLOOR and csd > 0):
            csd = min(csd, eng.CAT_SPA_POST155_RECOVERY_CAP)
        Q['cat_spa_relations'] = np.clip(
            Q['cat_spa_relations'] + csd + np.random.normal(0, 0.6), 5, 80)

        # Independence movement
        seasonal = eng.indy_seasonal_pulse(cal_month, year)
        gap = eng.INDY_RESTING_LEVEL - Q['independence_movement']
        Q['independence_movement'] = np.clip(
            Q['independence_movement'] + eng.INDY_REVERSION_SPEED * gap
            + seasonal + np.random.normal(0, 0.7), 25, 95)
        trust_drift = -1.8 if gen == 'ART155' else +0.06
        Q['independence_trust'] = np.clip(
            Q['independence_trust'] + trust_drift + np.random.normal(0, 0.4), 15, 60)

        # Social dissent
        eq  = eng.dissent_equilibrium(Q['unemployment'], Q['welfare_index'], gob, gen,
                                       podemos_channeling=cat_flags.get('podemos_channeling', 0.0))
        gap = eq - Q['social_dissent']
        Q['social_dissent'] = np.clip(
            Q['social_dissent'] + eng.DISSENT_REVERSION_SPEED * gap + np.random.normal(0, 0.8), 0, 100)

        # ── Spanish macro deltas ───────────────────────────────────────────
        spa_gdp     = Q['gdp_growth']
        spa_unemp   = Q['unemployment'] + SPA_UNEMP_OFFSET
        spa_welfare = Q['welfare_index']
        spa_dissent = Q['social_dissent']
        spa_cat_spa = Q['cat_spa_relations']

        d_gdp     = spa_gdp     - prev_spa['gdp']
        d_unemp   = spa_unemp   - prev_spa['unemp']
        d_welfare = spa_welfare - prev_spa['welfare']
        d_dissent = spa_dissent - prev_spa['dissent']
        d_cat_spa = spa_cat_spa - prev_spa['cat_spa']

        prev_spa = {
            'gdp': spa_gdp, 'unemp': spa_unemp, 'welfare': spa_welfare,
            'dissent': spa_dissent, 'cat_spa': spa_cat_spa,
        }

        # ── Spanish political events ───────────────────────────────────────
        for ev in EVENTS_SPA:
            eid = ev['id']
            if eid in spa_events_fired or ev['month'] != m:
                continue

            # Corruption
            if 'corruption_pp' in ev:
                spa['corruption_pp'] = max(0.0, spa['corruption_pp'] + ev['corruption_pp'])
            if 'corruption_psoe' in ev:
                spa['corruption_psoe'] = max(0.0, spa['corruption_psoe'] + ev['corruption_psoe'])

            # Government change
            if 'gob_coalition' in ev:
                spa['coalition'] = ev['gob_coalition']

            # Flag values (numeric multipliers, e.g. leadership_mult)
            if 'flag_values' in ev:
                for fk, fv in ev['flag_values'].items():
                    cat_flags[fk] = fv

            # Flag set / clear
            if 'flag_clear' in ev:
                cat_flags[ev['flag_clear']] = False
            if 'flag_set' in ev:
                cat_flags[ev['flag_set']] = True

                # Special: Vox emergence — inject initial support as PP drain
                if ev['flag_set'] == 'vox_active':
                    vox_init = ev.get('vox_init_pct', 2.5)
                    for c in CONSTITUENCIES:
                        if c == 'navarra':
                            continue
                        pp_cur = vmodel._r('pp', c)
                        drain  = min(vox_init / 100.0 * 100.0, pp_cur * 0.22)
                        vmodel._w('pp',  c, pp_cur - drain)
                        vmodel._w('vox', c, drain)

                # Special: FAC (Foro Asturias) breaks from PP — player-triggered.
                # Seeds initial foro support in 'rest' by draining from PP,
                # mirroring the Vox emergence pattern.
                if ev['flag_set'] == 'spa_foro_active':
                    foro_init = ev.get('foro_init_pct', 0.40)
                    pp_cur = vmodel._r('pp', 'rest')
                    drain  = min(foro_init, pp_cur * 0.06)
                    vmodel._w('pp',   'rest', pp_cur - drain)
                    vmodel._w('foro', 'rest', drain)

                # Special: NSuma formation — merge pp + upn + cs → nsuma in Navarra
                if ev.get('navarra_nsuma'):
                    merged = (vmodel._r('pp',  'navarra')
                            + vmodel._r('upn', 'navarra')
                            + vmodel._r('cs',  'navarra'))
                    vmodel._w('nsuma', 'navarra', merged)
                    vmodel._w('pp',   'navarra', 0.0)
                    vmodel._w('upn',  'navarra', 0.0)
                    vmodel._w('cs',   'navarra', 0.0)

            # Support injections
            for inj in ev.get('support_inject', []):
                fam, target_c, delta, funded_by = (
                    inj['family'], inj['c'], inj['delta'], inj['from'])
                cs_to_update = CONSTITUENCIES if target_c == 'all' else [target_c]
                for c in cs_to_update:
                    fams = get_active_families(c, cat_flags)
                    if fam not in fams or funded_by not in fams:
                        continue
                    funded_cur = vmodel._r(funded_by, c)
                    # Transfer at most 50% of the funding source's current support
                    actual     = min(delta, funded_cur * 0.5)
                    vmodel._w(funded_by, c, funded_cur - actual)
                    vmodel._w(fam, c, vmodel._r(fam, c) + actual)

            spa_events_fired.add(eid)

        # ── Corruption passive decay ───────────────────────────────────────
        if spa['corruption_pp'] > 0:
            spa['corruption_pp'] = max(0.0, spa['corruption_pp'] * spa['corruption_pp_decay'])
        if spa['corruption_psoe'] > 0:
            spa['corruption_psoe'] = max(0.0, spa['corruption_psoe'] * spa['corruption_psoe_decay'])

        # ── Vote model tick ────────────────────────────────────────────────
        vmodel.update(
            d_gdp, d_unemp, d_welfare, d_dissent, d_cat_spa,
            spa['corruption_pp'], spa['corruption_psoe'],
            spa['coalition'], cat_flags,
            podemos_channeling=cat_flags.get('podemos_channeling', 0.0),
        )

        # ── Election snapshot ──────────────────────────────────────────────
        if m in ELECTION_MONTHS:
            yr    = ELECTION_MONTHS[m]
            seats = vmodel.seat_counts(cat_flags)
            seat_results[yr] = dict(seats)

            if verbose:
                tgt = targets[yr]
                all_fams = sorted(set(list(seats.keys()) + list(tgt.keys())),
                                  key=lambda f: -tgt.get(f, 0))
                print(f"\n{'='*56}")
                print(f"  Month {m} — {yr} Election")
                print(f"  {'Family':<12}  {'Pred':>5}  {'Real':>5}  {'Diff':>5}")
                print(f"  {'-'*40}")
                for fam in all_fams:
                    p = seats.get(fam, 0)
                    t = tgt.get(fam, 0)
                    d = p - t
                    if p > 0 or t > 0:
                        flag = ' <--' if abs(d) >= 5 else ''
                        print(f"  {fam:<12}  {p:>5}  {t:>5}  {d:>+5}{flag}")

        # ── Record monthly state ───────────────────────────────────────────
        row = {'month': m, 'year': year, 'cal_month': cal_month,
               'gdp': Q['gdp_growth'], 'unemp': Q['unemployment'],
               'welfare': Q['welfare_index'], 'dissent': Q['social_dissent'],
               'cat_spa': Q['cat_spa_relations'],
               'corr_pp': spa['corruption_pp'], 'corr_psoe': spa['corruption_psoe']}
        # Average support across constituencies for major parties
        for fam in ['pp', 'psoe', 'podemos', 'cs', 'vox']:
            cs_with_fam = [c for c in CONSTITUENCIES if fam in get_active_families(c, cat_flags)]
            row[fam] = np.mean([vmodel._r(fam, c) for c in cs_with_fam]) if cs_with_fam else 0.0
        history.append(row)

    # ── RMSE ──────────────────────────────────────────────────────────────────
    sq_err, n = 0.0, 0
    for yr, predicted in seat_results.items():
        tgt = targets[yr]
        all_fams = set(list(predicted.keys()) + list(tgt.keys()))
        for fam in all_fams:
            diff    = predicted.get(fam, 0) - tgt.get(fam, 0)
            sq_err += diff ** 2
            n      += 1
    rmse = (sq_err / n) ** 0.5 if n else 999.0

    if verbose:
        print(f"\n{'='*56}")
        print(f"  CALIBRATION SUMMARY")
        print(f"  Seat RMSE across 4 elections × all families: {rmse:.2f}")

    return rmse, seat_results, pd.DataFrame(history)


# ── PLOTTING ─────────────────────────────────────────────────────────────────

def plot_results(seat_results, targets):
    years = sorted(seat_results.keys())
    fig, axes = plt.subplots(len(years), 1, figsize=(14, 6 * len(years)))
    if len(years) == 1:
        axes = [axes]

    colors = {
        'pp': '#3b82f6', 'psoe': '#ef4444', 'podemos': '#8b5cf6',
        'cs': '#f97316', 'vox': '#1e3a8a', 'cat_conv': '#34d399',
        'erc': '#fbbf24', 'pnv': '#065f46', 'bildu': '#064e3b',
        'bng': '#78350f', 'compromis': '#d97706', 'abs': '#94a3b8',
        'nsuma': '#1d4ed8', 'geroa_bai': '#6d28d9', 'mes': '#0891b2',
        'cup_spa': '#dc2626',
    }

    for i, yr in enumerate(years):
        ax = axes[i]
        pred = seat_results[yr]
        tgt  = targets[yr]
        fams = sorted(
            set(list(pred.keys()) + list(tgt.keys())),
            key=lambda f: -tgt.get(f, 0))
        fams = [f for f in fams if pred.get(f, 0) > 0 or tgt.get(f, 0) > 0]

        x     = np.arange(len(fams))
        width = 0.35
        c_list = [colors.get(f, '#ccc') for f in fams]

        ax.bar(x - width/2, [pred.get(f, 0) for f in fams], width,
               label='Predicted', color=c_list, alpha=0.85)
        ax.bar(x + width/2, [tgt.get(f, 0)  for f in fams], width,
               label='Target',    color=c_list, hatch='//', alpha=0.5)

        for j, fam in enumerate(fams):
            d = pred.get(fam, 0) - tgt.get(fam, 0)
            col = 'green' if d == 0 else ('blue' if d > 0 else 'red')
            ax.text(j, max(pred.get(fam, 0), tgt.get(fam, 0)) + 1,
                    f'{d:+d}', ha='center', va='bottom',
                    fontweight='bold', color=col, fontsize=9)

        ax.set_title(f'Election {yr}: Predicted vs Target Seats', fontsize=13, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(fams, rotation=0, fontsize=9)
        ax.set_ylabel('Seats')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        max_val = max(
            max((pred.get(f, 0) for f in fams), default=0),
            max((tgt.get(f, 0) for f in fams), default=0))
        ax.set_ylim(0, max_val + 12)

    plt.tight_layout()
    out = os.path.join(_HERE, 'results', 'spa_election_performance.png')
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Plot saved to results/spa_election_performance.png")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tune', action='store_true',
                        help='Run Nelder-Mead tuning on scalar model coefficients')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    targets = load_anchor_targets()

    if args.tune:
        from scipy.optimize import minimize

        # Tune the named scalar constants from DEFAULTS
        # (ECON_BASE coefficients are left for manual tuning — too many dims)
        param_keys = list(VM_DEFAULTS.keys())
        x0         = np.array([VM_DEFAULTS[k] for k in param_keys])
        lo         = np.array([0.0] * len(param_keys))  # all non-negative
        hi         = np.array([0.5] * len(param_keys))

        print(f"Tuning {len(param_keys)} scalar coefficients via Nelder-Mead...")

        def objective(x):
            overrides = {k: max(0.0, v) for k, v in zip(param_keys, x)}
            rmse, _, _ = run_simulation(params=overrides, verbose=False, seed=args.seed)
            return rmse

        result = minimize(objective, x0, method='Nelder-Mead',
                          options={'maxiter': 800, 'xatol': 0.02, 'fatol': 0.05})
        best = {k: max(0.0, v) for k, v in zip(param_keys, result.x)}
        print(f"\nOptimisation complete. Final RMSE: {result.fun:.2f}")
        print("Best scalar parameters:")
        for k, v in best.items():
            print(f"  {k:<22}: {v:.6f}  (default: {VM_DEFAULTS[k]:.6f})")

        rmse, results, history = run_simulation(params=best, verbose=True, seed=args.seed)

    else:
        rmse, results, history = run_simulation(verbose=True, seed=args.seed)

    history.to_csv(os.path.join(_HERE, 'results', 'spa_vote_history_irl.csv'), index=False)
    print(f"  History saved to results/spa_vote_history_irl.csv")
    plot_results(results, targets)
