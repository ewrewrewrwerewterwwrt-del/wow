"""
local_calibrator.py
Route to Ítaca — Local Election Runner & Calibrator

Drives the v4 economic engine (Aug 2012 – Dec 2019) and fires local election
resolution at:
    m=34  →  May 2015
    m=82  →  May 2019

IRL event schedule:
    m=24  →  Pujol confession (July 2014):  corruption_events_ciu += 1
    m=30  →  Second CDC corruption wave:    corruption_events_ciu += 1
    m=36  →  Unió splits from CDC
    m=50  →  PDeCat formed

Usage:
    cd simulations/
    python -X utf8 local_calibrator.py [--seed N] [--quiet] [--tune]

Tuning targets (IRL results, verified):
    Barcelona 2015: BComú 11s (25.2%), CiU 10s (22.75%), Cs 5s (11.0%), ERC 5s (11.0%),
                    PSC 4s (9.6%), PP 3s (8.7%), CUP 3s (7.4%)
    Barcelona 2019: BComú 10s (20.8%), ERC 10s (21.4%), JxCat 10s (10.6%), PSC 8s (18.5%),
                    Cs 6s (13.2%), PP 2s (5.0%), CUP 0s (3.9%), Primàries 0s (3.8%)
    Red Belt:       see local_elections.RB_HISTORICAL
    Interior:       see local_elections.INT_HISTORICAL
"""

import importlib.util
import numpy as np
from typing import Optional

# ── Dynamic import for economic_engine (avoids hyphens in path) ──────────────
spec = importlib.util.spec_from_file_location("eng4", "economic_engine.py")
eng4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng4)

import local_elections as le

# ── Election and event schedule ───────────────────────────────────────────────
# Month 1 = August 2012; calendar helpers below.
ELECTION_MONTHS   = {34: 2015, 82: 2019}
CORRUPTION_MONTHS = {24, 30}
UNIO_SPLIT_MONTH  = 36
PDCAT_SPLIT_MONTH = 50

# ── Historical Barcelona targets ──────────────────────────────────────────────
HISTORICAL_BCN_SEATS = {
    2015: {"bcomuns": 11, "ciu": 10, "psc": 4, "pp": 3, "cs": 5, "erc": 5, "cup": 3},
    2019: {"bcomuns": 10, "ciu": 5, "erc": 10, "psc": 8, "cs": 6, "pp": 2, "cup": 0, "primaries": 0},
}

HISTORICAL_BCN_VOTE = {
    2015: {"bcomuns": 25.21, "ciu": 22.75, "psc": 9.63, "pp": 8.71,
           "cs":  11.03, "erc": 11.01, "cup":  7.42},
    2019: {"bcomuns": 20.82, "ciu": 10.55, "erc": 21.44, "psc": 18.47,
           "cs":  13.23, "pp":  5.03, "cup":  3.9, "primaries": 3.76},
}

# ── Calibrator param keys (order matters — defines the scipy vector layout) ──
_RB_PARAM_KEYS = [
    "cs_im_coeff", "cs_spa_coeff", "cs_diss_coeff",
    "erc_trust_coeff", "erc_im_coeff", "erc_no_outreach_penalty",
    "comuns_diss_coeff", "comuns_pp_scale", "comuns_welf_coeff",
]

_INT_PARAM_KEYS = [
    "decay_base", "decay_corr_coeff", "decay_welf_coeff",
    "decay_pdcat_bonus", "decay_unio_bonus",
    "erc_trust_coeff", "erc_im_coeff", "erc_build_bonus", "erc_base_bonus",
    "cup_imtrust_coeff", "cup_diss_coeff",
    "holdout_base",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _calendar_year(m: int) -> int:
    return 2012 + (m - 1 + 7) // 12

def _calendar_month(m: int) -> int:
    return ((m - 1 + 7) % 12) + 1

def _pack_defaults() -> list:
    rb_vals  = [le.RB_DEFAULTS[k]  for k in _RB_PARAM_KEYS]
    int_vals = [le.INT_DEFAULTS[k] for k in _INT_PARAM_KEYS]
    return rb_vals + int_vals

def _unpack_params(params: list):
    n_rb = len(_RB_PARAM_KEYS)
    rb_p  = dict(zip(_RB_PARAM_KEYS,  params[:n_rb]))
    int_p = dict(zip(_INT_PARAM_KEYS, params[n_rb:]))
    return rb_p, int_p

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SIMULATION LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run(
    seed: int = 42,
    verbose: bool = True,
    rb_params: Optional[dict] = None,
    int_params: Optional[dict] = None,
) -> dict:
    """
    Simulate Aug 2012 – Dec 2019.
    Returns {2015: municipal_result, 2019: municipal_result}.
    Each municipal_result is the dict from le.run_municipal_election().
    """
    np.random.seed(seed)

    Q = {
        "gdp_growth":              -3.1,
        "unemployment":             22.5,
        "public_debt":              26.0,
        "generalitat_surplus":      -2.3,
        "cat_spa_relations":        38.0,
        "independence_movement":    65.0,
        "independence_trust":       28.0,
        "social_dissent":           72.0,
        "welfare_index":            72.0,
        "podemos_pulse":             0.0,
        "corruption_events_ciu":     0,
        "pdcat_split_happened":      False,
        "unio_split_happened":       False,
        "erc_redbelt_outreach":      False,
        "erc_party_building_interior": False,
        # Trias was CiU's 2015 candidate (incumbent mayor). JxCat 2019 candidate was
        # Elsa Artadi (withdrew) / Carles Puigdemont from exile — no Trias bonus in 2019.
        "trias_leading":             True,
    }

    flags = {
        "ecb_qe_enabled":     True,
        "fla_active":         True,
        "fla_escalated":      False,
        "art155_ever":        False,
        "podemos_surged":     False,
        "podemos_channeling": 0.0,
    }

    event_fired  = {ev["id"]: False for ev in eng4.EVENTS}
    pulse_queue  = []
    dissent_prev = Q["social_dissent"]
    gob_tl       = eng4.GOBIERNO_IRL_TIMELINE
    gen_tl       = eng4.GENERALITAT_IRL_TIMELINE

    le.init_local_barcelona(Q)

    results = {}

    for m in range(1, 91):
        year      = 2012 + (m - 1) // 12
        cal_month = _calendar_month(m)
        Q["year"] = _calendar_year(m)

        gob = eng4.get_gov(m, gob_tl)
        gen = eng4.get_gov(m, gen_tl)

        if gen == "ART155":
            flags["art155_ever"] = True

        Q_prev = dict(Q)

        # ── Pulse queue ───────────────────────────────────────────────────────
        still = []
        for pulse in pulse_queue:
            Q[pulse["variable"]] += pulse["monthly_delta"]
            pulse["remaining"] -= 1
            if pulse["remaining"] > 0:
                still.append(pulse)
        pulse_queue = still

        # ── Events ───────────────────────────────────────────────────────────
        podemos_fired_this_month = False
        for ev in eng4.EVENTS:
            eid = ev["id"]
            if ev["one_time"] and event_fired[eid]:
                continue
            if ev["trigger_fn"](m, year, cal_month, Q, flags):
                for var, delta in ev["effects"].items():
                    if var in Q:
                        Q[var] += delta
                if ev["flag_set"]:
                    flags[ev["flag_set"]] = True
                if ev["pulse"]:
                    p = ev["pulse"]
                    pulse_queue.append({
                        "variable":      p["variable"],
                        "monthly_delta": p["monthly_delta"],
                        "remaining":     p["duration"],
                    })
                if eid == "podemos_surge":
                    flags["podemos_channeling"] = 1.0
                    podemos_fired_this_month = True
                if ev["one_time"]:
                    event_fired[eid] = True

        # ── Podemos channeling decay ──────────────────────────────────────────
        if flags["podemos_surged"]:
            if Q["social_dissent"] < dissent_prev - 0.5:
                flags["podemos_channeling"] = min(1.0, flags["podemos_channeling"] + 0.01)
            else:
                flags["podemos_channeling"] = max(0.0, flags["podemos_channeling"] - 0.03)
        dissent_prev = Q["social_dissent"]
        Q["podemos_pulse"] = flags["podemos_channeling"]

        # ── Variable clips ────────────────────────────────────────────────────
        Q["independence_movement"] = np.clip(Q["independence_movement"], 25, 95)
        Q["independence_trust"]    = np.clip(Q["independence_trust"],    15, 60)
        Q["social_dissent"]        = np.clip(Q["social_dissent"],         0, 100)
        Q["cat_spa_relations"]     = np.clip(Q["cat_spa_relations"],       5, 80)
        Q["welfare_index"]         = np.clip(Q["welfare_index"],          20, 100)

        # ── GDP ───────────────────────────────────────────────────────────────
        struc      = eng4.STRUCTURAL_GDP.get(year, 2.0)
        gob_mod    = eng4.GOB_GDP_ABS.get(gob, 0.0)
        gen_mod    = eng4.GEN_GDP_ABS.get(gen, 0.0)
        spa_adj    = eng4.cat_spa_gdp_adj(Q["cat_spa_relations"])
        i_drag     = eng4.indy_gdp_drag(Q["independence_movement"], Q["independence_trust"])
        gdp_target = struc + gob_mod + gen_mod + spa_adj + i_drag
        ar         = 0.60 if gen == "ART155" else 0.72
        Q["gdp_growth"] = np.clip(
            ar * Q["gdp_growth"] + (1 - ar) * gdp_target + np.random.normal(0, 0.28),
            -9, 7)

        # ── Unemployment ──────────────────────────────────────────────────────
        gdp_m = Q["gdp_growth"] / 12
        lrm   = 1 + eng4.UNEMP_PARAMS["reform_bonus"]
        rec   = (eng4.UNEMP_PARAMS["recover_coeff"] * lrm
                 * eng4.GEN_UNEMP_MOD.get(gen, 1.0)
                 * eng4.GOB_UNEMP_MOD.get(gob, 1.0))
        u_delta = (-gdp_m * eng4.UNEMP_PARAMS["destruct_coeff"] if gdp_m < 0
                   else -gdp_m * rec)
        Q["unemployment"] = np.clip(
            Q["unemployment"] + u_delta, eng4.UNEMP_PARAMS["natural_floor"], 36)

        # ── Surplus ───────────────────────────────────────────────────────────
        fla_bonus = 0.0
        if flags["fla_active"]:
            fla_bonus += eng4.SURPLUS_FLA_BONUS_BY_GOB.get(gob, 0.0)
        if flags["fla_escalated"]:
            fla_bonus += eng4.SURPLUS_FLA_ESCALATION_BONUS
        base_drift = eng4.SURPLUS_DRIFT_BY_GEN.get(gen, 0.020)
        gse        = (Q["gdp_growth"] / 100) * eng4.SURPLUS_GDP_SENSITIVITY / 12
        Q["generalitat_surplus"] = np.clip(
            Q["generalitat_surplus"] + base_drift + fla_bonus + gse
            + np.random.normal(0, 0.10), -5, 2)

        # ── Debt ──────────────────────────────────────────────────────────────
        Q["public_debt"] = np.clip(
            Q["public_debt"] + eng4.compute_debt_delta(
                Q["generalitat_surplus"], gdp_m, Q["public_debt"]), 0, 80)

        # ── Welfare ───────────────────────────────────────────────────────────
        sp    = eng4.WELFARE_SPENDING_BY_GEN.get(gen, 0.0)
        gwb   = (Q["gdp_growth"] / 12) * eng4.WELFARE_GDP_SENSITIVITY
        raw_w = sp + gwb + np.random.normal(0, 0.20)
        wdelta = (min(raw_w, eng4.WELFARE_RECOVERY_CAP) if raw_w > 0
                  else max(raw_w, -eng4.WELFARE_CUT_CAP))
        Q["welfare_index"] = np.clip(Q["welfare_index"] + wdelta, 20, 100)

        # ── Cat-Spa ───────────────────────────────────────────────────────────
        if gen == "ART155":
            csd = eng4.CAT_SPA_ART155_DRIFT
        else:
            csd = eng4.get_cat_spa_drift(gob, gen)
        if flags["art155_ever"] and gen != "ART155":
            if Q["cat_spa_relations"] < eng4.CAT_SPA_POST155_FLOOR and csd > 0:
                csd = min(csd, eng4.CAT_SPA_POST155_RECOVERY_CAP)
        Q["cat_spa_relations"] = np.clip(
            Q["cat_spa_relations"] + csd + np.random.normal(0, 0.6), 5, 80)

        # ── Independence movement ─────────────────────────────────────────────
        seasonal = eng4.indy_seasonal_pulse(cal_month, year)
        gap      = eng4.INDY_RESTING_LEVEL - Q["independence_movement"]
        Q["independence_movement"] = np.clip(
            Q["independence_movement"] + eng4.INDY_REVERSION_SPEED * gap
            + seasonal + np.random.normal(0, 0.7), 25, 95)

        trust_drift = -1.8 if gen == "ART155" else +0.06
        Q["independence_trust"] = np.clip(
            Q["independence_trust"] + trust_drift + np.random.normal(0, 0.4), 15, 60)

        # ── Social dissent ────────────────────────────────────────────────────
        eq  = eng4.dissent_equilibrium(
            Q["unemployment"], Q["welfare_index"], gob, gen,
            podemos_channeling=flags["podemos_channeling"])
        gap = eq - Q["social_dissent"]
        Q["social_dissent"] = np.clip(
            Q["social_dissent"] + eng4.DISSENT_REVERSION_SPEED * gap
            + np.random.normal(0, 0.8), 0, 100)

        # ── IRL corruption / split events ─────────────────────────────────────
        if m in CORRUPTION_MONTHS:
            Q["corruption_events_ciu"] += 1
            if verbose:
                print(f"  [m={m}] Corruption event → corruption_events_ciu = {Q['corruption_events_ciu']}")
        if m == UNIO_SPLIT_MONTH:
            le.fire_split_event(Q, "unio")
            Q["unio_split_happened"] = True
            if verbose:
                print(f"  [m={m}] Unió split fired")
        if m == PDCAT_SPLIT_MONTH:
            le.fire_split_event(Q, "pdcat")
            Q["pdcat_split"] = True
            if verbose:
                print(f"  [m={m}] PDeCat split fired")
        # m=62 ≈ Sep 2017: Trias no longer leads JxCat's Barcelona bid; imprisoned leadership
        if m == 62:
            Q["trias_leading"] = False
        # m=67 ≈ Feb 2018: PP voters split to PSC + Cs post-ART155 and PP national collapse
        if m == 67:
            pp_key  = "pp_local_barcelona_support"
            psc_key = "psc_local_barcelona_support"
            cs_key  = "cs_local_barcelona_support"
            psc_t = min(2.7, Q.get(pp_key, 0.0))
            cs_t  = min(0.5, max(0.0, Q.get(pp_key, 0.0) - psc_t))
            Q[pp_key]  -= (psc_t + cs_t)
            Q[psc_key]  = Q.get(psc_key, 0.0) + psc_t
            Q[cs_key]   = Q.get(cs_key,  0.0) + cs_t
            if verbose:
                print(f"  [m={m}] PP→PSC/Cs unionist consolidation (post-ART155 PP collapse)")
            if verbose:
                print(f"  [m={m}] Trias candidacy ended — JxCat 2019 runs without Trias")
        # m=81 ≈ Apr 2019: Primàries candidacy crystallises, splitting radical-left BCN vote
        if m == 81:
            cup_key  = "cup_local_barcelona_support"
            prim_key = "primaries_local_barcelona_support"
            transfer = min(4.0, Q.get(cup_key, 0.0))
            Q[cup_key]  -= transfer
            Q[prim_key]  = Q.get(prim_key, 0.0) + transfer
            if verbose:
                print(f"  [m={m}] Primàries split fired (CUP → primaries)")

        # ── Barcelona monthly tick ────────────────────────────────────────────
        le.update_local_barcelona(
            Q,
            d_independence_movement = Q["independence_movement"]  - Q_prev["independence_movement"],
            d_independence_trust    = Q["independence_trust"]     - Q_prev["independence_trust"],
            d_social_dissent        = Q["social_dissent"]         - Q_prev["social_dissent"],
            d_welfare               = Q["welfare_index"]          - Q_prev["welfare_index"],
            d_cat_spa               = Q["cat_spa_relations"]      - Q_prev["cat_spa_relations"],
            d_unemployment          = Q["unemployment"]           - Q_prev["unemployment"],
        )

        # ── Election resolution ───────────────────────────────────────────────
        if m in ELECTION_MONTHS:
            yr  = ELECTION_MONTHS[m]
            res = le.run_municipal_election(Q, yr, rb_params=rb_params, int_params=int_params)
            results[yr] = res

            if verbose:
                _print_q_snapshot(Q, yr)
                le.display_barcelona_results(res["locations"]["Barcelona"], Q)
                _print_barcelona_comparison(yr, res["locations"]["Barcelona"])
                le.display_results(res)
                _print_cat_validation(res, yr)

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════════

def objective(params: list) -> float:
    """
    Combined loss: red belt / interior location mismatches + Barcelona seat RMSE.
    Lower is better. Used by tune().
    """
    rb_p, int_p = _unpack_params(params)
    results = run(seed=42, verbose=False, rb_params=rb_p, int_params=int_p)

    score = 0.0
    for yr in [2015, 2019]:
        if yr not in results:
            continue
        locs = results[yr]["locations"]

        # Red belt: 1 point per mismatch (skip None anchors)
        for name, expected in le.RB_HISTORICAL.get(yr, {}).items():
            if expected is None:
                continue
            predicted = locs.get(name, {}).get("winner")
            if predicted != expected:
                score += 1.0

        # Interior: 1 point per mismatch
        for name, expected in le.INT_HISTORICAL.get(yr, {}).items():
            if expected is None:
                continue
            predicted = locs.get(name, {}).get("winner")
            if predicted != expected:
                score += 1.0

        # Barcelona: seat RMSE (scaled to similar magnitude as location mismatches)
        bcn_seats  = locs.get("Barcelona", {}).get("seats", {})
        hist_seats = HISTORICAL_BCN_SEATS.get(yr, {})
        seat_sq = sum((bcn_seats.get(p, 0) - hs) ** 2 for p, hs in hist_seats.items())
        score += (seat_sq / max(len(hist_seats), 1)) ** 0.5 * 0.5

    return score


def tune(n_trials: int = 1) -> dict:
    """
    Run scipy Nelder-Mead to minimise objective().
    n_trials: number of random restarts (best result returned).
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        print("scipy not installed — run: pip install scipy")
        return {}

    x0      = _pack_defaults()
    best    = None
    best_x  = x0[:]

    for trial in range(n_trials):
        if trial == 0:
            x_start = x0[:]
        else:
            # Perturb defaults by ±20%
            rng     = np.random.default_rng(trial)
            x_start = [v * (1 + rng.uniform(-0.2, 0.2)) for v in x0]

        res = minimize(objective, x_start, method="Nelder-Mead",
                       options={"maxiter": 2000, "xatol": 1e-3, "fatol": 1e-3})
        if best is None or res.fun < best:
            best   = res.fun
            best_x = res.x.tolist()
        print(f"  Trial {trial + 1}/{n_trials}  loss={res.fun:.3f}  {'(best)' if res.fun == best else ''}")

    rb_best, int_best = _unpack_params(best_x)
    print(f"\n  Best loss: {best:.3f}")
    print(f"\n  RB params:")
    for k, v in rb_best.items():
        print(f"    {k:<30}: {v:.4f}  (default {le.RB_DEFAULTS[k]:.4f})")
    print(f"\n  INT params:")
    for k, v in int_best.items():
        print(f"    {k:<30}: {v:.4f}  (default {le.INT_DEFAULTS[k]:.4f})")

    return {"loss": best, "rb_params": rb_best, "int_params": int_best}

# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _print_q_snapshot(Q: dict, year: int) -> None:
    print(f"\n  ── Q State at {year} election ──")
    keys = ["independence_movement", "independence_trust", "social_dissent",
            "welfare_index", "unemployment", "cat_spa_relations",
            "podemos_pulse", "corruption_events_ciu",
            "unio_split_happened", "pdcat_split_happened"]
    for k in keys:
        print(f"    {k:<32}: {Q.get(k)}")


def _print_barcelona_comparison(year: int, bcn_res: dict) -> None:
    hist_s = HISTORICAL_BCN_SEATS.get(year, {})
    hist_v = HISTORICAL_BCN_VOTE.get(year, {})
    shares = bcn_res.get("shares", {})
    seats  = bcn_res.get("seats", {})

    _labels = {
        "bcomuns": "BComú", "ciu": "CiU/CDC/JxCat", "erc": "ERC",
        "psc": "PSC", "cs": "Cs", "cup": "CUP", "pp": "PP",
        "primaries": "Primàries",
    }

    print(f"\n  ── Barcelona vs. IRL {year} ──")
    print(f"  {'Party':<20} {'Pred%':>6}  {'IRL%':>6}  {'PredS':>5}  {'IRLS':>5}  {'ΔS':>4}")
    print(f"  {'─'*58}")

    total_sq, n = 0.0, 0
    for party in le.LOCAL_BCN_PARTIES:
        pred_v = shares.get(party, 0.0)
        pred_s = seats.get(party, 0)
        irl_v  = hist_v.get(party, 0.0)
        irl_s  = hist_s.get(party, 0)
        delta  = pred_s - irl_s
        flag   = " <--" if abs(delta) >= 3 else ""
        print(f"  {_labels.get(party, party):<20} {pred_v:>6.1f}  {irl_v:>6.1f}  {pred_s:>5}  {irl_s:>5}  {delta:>+4}{flag}")
        total_sq += delta ** 2
        n += 1

    rmse = (total_sq / n) ** 0.5 if n else 0.0
    print(f"\n  Seat RMSE {year}: {rmse:.2f}")
    print(f"  Mayor predicted: {bcn_res.get('mayor')}  |  mode: {bcn_res.get('gov_mode')}")


def _print_cat_validation(results: dict, year: int) -> None:
    locs = results["locations"]
    rb   = results["rb_scores"]
    intr = results["int_scores"]

    rb_locs  = [loc for loc in le.LOCATIONS if loc.system == "redBelt"]
    int_locs = [loc for loc in le.LOCATIONS if loc.system == "interior"]

    # Red belt accuracy
    rb_anchors = {k: v for k, v in le.RB_HISTORICAL.get(year, {}).items() if v is not None}
    rb_correct = sum(1 for name, exp in rb_anchors.items()
                     if locs.get(name, {}).get("winner") == exp)
    print(f"\n  ── Red Belt validation {year} ({rb_correct}/{len(rb_anchors)} correct) ──")
    print(f"  {'Location':<32} {'Predicted':<10} {'Expected':<10} {'OK?'}")
    print(f"  {'─'*60}")
    for loc in rb_locs:
        pred = locs.get(loc.name, {}).get("winner", "?")
        exp  = le.RB_HISTORICAL.get(year, {}).get(loc.name)
        ok   = "✓" if exp is None else ("✓" if pred == exp else "✗")
        exp_str = exp or "?"
        print(f"  {loc.name:<32} {pred:<10} {exp_str:<10} {ok}")

    # Interior accuracy
    int_anchors = {k: v for k, v in le.INT_HISTORICAL.get(year, {}).items() if v is not None}
    int_correct = sum(1 for name, exp in int_anchors.items()
                      if locs.get(name, {}).get("winner") == exp)
    print(f"\n  ── Interior validation {year} ({int_correct}/{len(int_anchors)} correct) ──")
    print(f"  {'Location':<32} {'Predicted':<10} {'Expected':<10} {'OK?'}")
    print(f"  {'─'*60}")
    for loc in int_locs:
        pred = locs.get(loc.name, {}).get("winner", "?")
        exp  = le.INT_HISTORICAL.get(year, {}).get(loc.name)
        ok   = "✓" if exp is None else ("✓" if pred == exp else "✗")
        exp_str = exp or "?"
        r    = locs.get(loc.name, {})
        detail = ""
        if "ciu_holdout" in r:
            top = max(r.get("challenger_scores", {}).items(), key=lambda x: x[1], default=("?", 0))
            detail = f" holdout={r['ciu_holdout']:.0f} top={top[0]}@{top[1]:.0f}"
        print(f"  {loc.name:<32} {pred:<10} {exp_str:<10} {ok}{detail}")

    ciu_d = intr["ciu_decay"]
    tier_check = ("25–50: OK" if 25 <= ciu_d <= 50 else "25–50: MISS") if year == 2015 else ("20–55: OK" if 20 <= ciu_d <= 55 else "20–55: MISS")
    print(f"\n  ciu_decay={ciu_d:.1f}  [{tier_check}]")

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Local election runner/calibrator for Route to Ítaca")
    p.add_argument("--seed",    type=int, default=42,   help="RNG seed")
    p.add_argument("--quiet",   action="store_true",     help="Suppress per-month output")
    p.add_argument("--tune",    action="store_true",     help="Run Nelder-Mead optimiser")
    p.add_argument("--trials",  type=int, default=1,    help="Number of optimiser restarts (with --tune)")
    args = p.parse_args()

    if args.tune:
        print("Running calibration...")
        best = tune(n_trials=args.trials)
        print("\nRe-running with best params:")
        run(seed=args.seed, verbose=True,
            rb_params=best.get("rb_params"), int_params=best.get("int_params"))
    else:
        run(seed=args.seed, verbose=not args.quiet)
