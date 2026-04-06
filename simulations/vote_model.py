"""
Route to Ítaca — Vote Model
============================
Tracks party family support continuously, updated monthly via delta mechanics.

Architecture
-------------
State:  support[family, province, demographic]  — sums to 100 per (prov, demo) cell
Update: support += T_BY_DEMO[demo] @ dvars   per cell, then clamp+renorm

Each T_BY_DEMO[demo] is a full (N_FAM × N_VARS) matrix built as:
    T[demo] = BASE_T + delta_T[demo]
where delta_T[demo] has column-sum zero by construction — vote conservation
is guaranteed mathematically, not by a post-hoc correction.

Nonlinear handlers (dissent, welfare, cat_spa, cup_trust) return family-level
delta vectors that are already balanced. They are scaled per-demographic via
NONLIN_DEMO_SCALE before being added to the matrix-driven delta.

Party Families (12 + abstain = 12 total inc. abs)
--------------------------------------------------
  icr   — Indy Centre-Right    (CiU -> JxSi-CDC share -> JxCat)
  il    — Indy Left             (ERC/SI -> JxSi-ERC share -> ERC)
  cup   — Far Indy              (CUP throughout)
  unio  — Social-Christian Indy (Unio - 2015 era only; dormant otherwise)
  pdcat — Indy Liberal Split    (PDCat splinter; alt-history relevant)
  fl    — Fed Left              (ICV -> CSQP -> CECP)
  psc   — Social-Democrat       (PSC throughout)
  cs    — Liberal Unionist      (CS throughout)
  ppc   — Conservative Unionist (PPC throughout)
  vox   — Far Right             (Vox / PxC fringe)
  fnc   — Far Indy Fringe       (FNC)
  abs   — Abstain               (non-participation)

Variables driving the transfer matrix (7 columns)
---------------------------------------------------
  0: delta_indy_mov    - mobilization strength delta
  1: delta_indy_trust  - trust in indy leadership delta
  2: delta_dissent     - social dissent delta  [nonlinear - handled separately]
  3: delta_welfare     - welfare index delta   [nonlinear - handled separately]
  4: delta_cat_spa     - cat-spa relations delta [nonlinear - handled separately]
  5: delta_unemp       - unemployment rate delta
  6: podemos_pulse     - one-shot binary (0/1) when Podemos surges

Non-linear cases handled explicitly (not via matrix):
  - cs/ppc boost compounded by indy_mov level (cat_spa interaction)
  - dissent->fl vs abs split by podemos_channeling level
  - welfare credit goes to governing families (gen_party, gob_party)
  - cup trust amplification below threshold
"""

import numpy as np
import pickle
from collections import defaultdict

# ---- CONSTANTS --------------------------------------------------------------

FAMILIES   = ['icr', 'il', 'cup', 'unio', 'pdcat', 'fl', 'psc', 'cs', 'ppc', 'vox', 'fnc', 'abs']
PROVINCES  = ['barcelona', 'girona', 'lleida', 'tarragona']
DEMOS      = ['buss', 'ind', 'middle', 'young', 'retired', 'rural', 'unemployed']
N_FAM  = len(FAMILIES)
N_PROV = len(PROVINCES)
N_DEMO = len(DEMOS)

FAM_IDX  = {f: i for i, f in enumerate(FAMILIES)}
PROV_IDX = {p: i for i, p in enumerate(PROVINCES)}
DEMO_IDX = {d: i for i, d in enumerate(DEMOS)}

SEATS = {'barcelona': 85, 'girona': 17, 'lleida': 15, 'tarragona': 18}

# ---- VARIABLE INDICES -------------------------------------------------------
V_INDY_MOV   = 0
V_INDY_TRUST = 1
V_DISSENT    = 2
V_WELFARE    = 3
V_CAT_SPA    = 4
V_UNEMP      = 5
V_PODEMOS    = 6
N_VARS       = 7
VAR_NAMES    = ['indy_mov', 'indy_trust', 'dissent', 'welfare', 'cat_spa', 'unemp', 'podemos']

# ---- BASE TRANSFER MATRIX ---------------------------------------------------
# Shape: (N_FAM, N_VARS)
# Each column must sum to 0 (vote conservation).
# Units: approx % support shift per 1-unit variable change.
# Dissent, welfare, cat_spa columns set to 0 here (handled nonlinearly).
#
# Column order: [indy_mov, indy_trust, dissent, welfare, cat_spa, unemp, podemos]
# 'middle' demographic IS the reference (T_BY_DEMO['middle'] == BASE_T exactly).
_T = np.zeros((N_FAM, N_VARS))
def _r(fam): return FAM_IDX[fam]

#               imov   itrust diss   welf   cspa   unemp  pod
_T[_r('icr')]  = [ 0.060,  0.040,  0.000,  0.000,  0.000, -0.030,  0.000]
_T[_r('il')]   = [ 0.220,  0.120,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('cup')]  = [ 0.020, -0.015,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('unio')] = [ 0.008,  0.015,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('pdcat')]= [ 0.010,  0.010,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('fl')]   = [-0.020,  0.000,  0.000,  0.000,  0.000,  0.025,  0.150]
_T[_r('psc')]  = [-0.004,  0.000,  0.000,  0.000,  0.000, -0.020, -0.040]
_T[_r('cs')]   = [-0.020,  0.000,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('ppc')]  = [-0.040,  0.000,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('vox')]  = [-0.008,  0.000,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('fnc')]  = [ 0.005, -0.010,  0.000,  0.000,  0.000,  0.000,  0.000]
_T[_r('abs')]  = [-0.060, -0.045,  0.000,  0.000,  0.000,  0.025, -0.070]

# Auto-correct column sums to zero (dump residual into abs)
for j in range(N_VARS):
    residual = _T[:, j].sum()
    if abs(residual) > 1e-9:
        _T[_r('abs'), j] -= residual

BASE_T = _T.copy()

# ---- PER-DEMOGRAPHIC TRANSFER MATRICES -------------------------------------
# T_BY_DEMO[demo] = BASE_T + delta_T[demo]
# Each delta_T[demo] has column-sum ZERO by construction (verified by assert).
# 'middle' is the identity demographic (delta = 0 -> exactly BASE_T).
#
# Design principle: for every entry that increases one family's coefficient,
# the helper below balances the residual into abs — or explicit compensating
# entries are provided. No one-sided multipliers.

_DELTA_T = {d: np.zeros((N_FAM, N_VARS)) for d in DEMOS}

# Helper: apply indy_mov overrides for a demo.
# mults = {fam: multiplier vs BASE_T}; remaining budget balanced into abs.
def _imov_override(demo, mults):
    dT = _DELTA_T[demo]
    net = 0.0
    base_imov = {
        'icr': 0.060, 'il': 0.220, 'cup': 0.020, 'fl': -0.020,
        'psc': -0.004, 'cs': -0.020, 'ppc': -0.040, 'abs': -0.250,
    }
    for fam, mult in mults.items():
        base = base_imov.get(fam, 0.0)
        delta = base * (mult - 1.0)
        dT[_r(fam), V_INDY_MOV] += delta
        net += delta
    dT[_r('abs'), V_INDY_MOV] -= net   # absorb residual

# Helper: apply unemp overrides.
def _unemp_override(demo, mults):
    dT = _DELTA_T[demo]
    net = 0.0
    base_unemp = {
        'icr': -0.030, 'fl': 0.025, 'psc': -0.020, 'abs': 0.025,
    }
    for fam, mult in mults.items():
        base = base_unemp.get(fam, 0.0)
        delta = base * (mult - 1.0)
        dT[_r(fam), V_UNEMP] += delta
        net += delta
    dT[_r('abs'), V_UNEMP] -= net

# ── buss (business owners) ────────────────────────────────────────────────────
# Less indy-responsive (icr/il), cs loses more, ppc/psc damped
# Unemployment: abs much less (businesses park in cs/ppc, not home)
_imov_override('buss', {'icr': 0.80, 'il': 0.30, 'cs': 2.50, 'ppc': 0.60, 'psc': 0.60})
_unemp_override('buss', {'abs': 0.20, 'cs': 1.50, 'ppc': 1.50})

# ── ind (blue-collar / industrial workers) ────────────────────────────────────
# Low indy response; cs loses more; fl gets less from indy (dampened)
# Unemployment: fl picks up more (labour solidarity)
_imov_override('ind',  {'icr': 0.40, 'il': 0.50, 'cs': 1.80, 'psc': 0.50, 'fl': 2.00})
_unemp_override('ind',  {'fl': 1.50})

# ── middle ── identity (no delta — BASE_T is calibrated to this cohort) ───────

# ── young ────────────────────────────────────────────────────────────────────
# Strongly il (ERC youth); less icr; cup gets a bonus; abstain mobilises hard
_imov_override('young', {'icr': 0.50, 'il': 1.80, 'cup': 3.00})

# ── retired ──────────────────────────────────────────────────────────────────
# icr sticky; il less responsive; moderate indy retired partly go psc
_imov_override('retired', {'icr': 1.30, 'il': 0.60, 'psc': 1.50})

# ── rural ────────────────────────────────────────────────────────────────────
# Very indy; cs barely loses (rural unionism is weak); strong abs mobilisation
_imov_override('rural', {'icr': 1.60, 'il': 1.80, 'cs': 0.10, 'ppc': 0.10, 'psc': 0.30})

# ── unemployed ───────────────────────────────────────────────────────────────
# Weak indy sentiment; cs more negative (no stake in unionist project)
# Economic signals amplified: icr penalised harder, fl/psc pick up
_imov_override('unemployed', {'icr': 0.40, 'il': 0.60, 'cs': 1.80, 'fl': 2.00, 'psc': 1.50})
_unemp_override('unemployed', {'icr': 2.00, 'fl': 1.50, 'psc': 1.50})

# Build and validate T_BY_DEMO
T_BY_DEMO = {d: BASE_T + _DELTA_T[d] for d in DEMOS}

for _demo, _Td in T_BY_DEMO.items():
    for _j in range(N_VARS):
        _s = _Td[:, _j].sum()
        assert abs(_s) < 1e-7, (
            f"vote_model: T_BY_DEMO['{_demo}'] column {VAR_NAMES[_j]} sum = {_s:.2e} (must be 0)")

# ---- NONLINEAR DEMO SCALE ---------------------------------------------------
# Per-demographic sensitivity multiplier for the nonlinear handlers
# (dissent, welfare, cat_spa, cup_trust).
# Applied to the OUTPUT vector of each handler before adding to support delta.
#
# Rationale:
#   buss       — insulated from dissent; cat_spa raises stakes (unionist or silent)
#   ind        — high dissent sensitivity; low welfare payoff (they don't see it)
#   middle     — reference = 1.0
#   young      — maximum dissent + welfare mobilisation; high cup_trust depth
#   retired    — low dissent; very welfare-sensitive (pensions); low cup_trust
#   rural      — moderate; high cat_spa (conflict mobilises rural indy bloc)
#   unemployed — extreme dissent; welfare means little (they're excluded from it)

NONLIN_DEMO_SCALE = {
    'buss':       {'dissent': 0.40, 'welfare': 0.60, 'cat_spa': 1.20, 'cup_trust': 0.50},
    'ind':        {'dissent': 1.60, 'welfare': 0.80, 'cat_spa': 0.80, 'cup_trust': 0.80},
    'middle':     {'dissent': 1.00, 'welfare': 1.00, 'cat_spa': 1.00, 'cup_trust': 1.00},
    'young':      {'dissent': 1.80, 'welfare': 1.40, 'cat_spa': 0.90, 'cup_trust': 1.60},
    'retired':    {'dissent': 0.40, 'welfare': 1.80, 'cat_spa': 0.60, 'cup_trust': 0.40},
    'rural':      {'dissent': 0.80, 'welfare': 0.70, 'cat_spa': 1.50, 'cup_trust': 0.60},
    'unemployed': {'dissent': 2.00, 'welfare': 0.50, 'cat_spa': 1.00, 'cup_trust': 0.90},
}

# ---- GOVERNING PARTY -> FAMILY MAPPING --------------------------------------
GEN_FAMILY = {
    'ciu': 'icr', 'cdc': 'icr', 'jxcat': 'icr', 'pdcat': 'pdcat',
    'erc': 'il',
    'psc': 'psc',
    'cs':  'cs',
    'ppc': 'ppc',
    'cup': 'cup',
    'csqp': 'fl', 'cecp': 'fl', 'fl': 'fl',
}
GOB_FAMILY = {
    'pp':      'ppc',
    'psoe':    'psc',
    'cs':      'cs',
    'podemos': 'fl',
}

# Welfare distribution magnitudes
WELFARE_GAIN_GEN = 0.025
WELFARE_GAIN_GOB = 0.010

# ---- NONLINEAR COEFFICIENTS -------------------------------------------------
DISSENT_FL_MAX    = 0.040   # max fl gain per unit dissent (full channeling)
DISSENT_CUP_FRAC  = 0.20    # fraction of overflow -> cup
DISSENT_ABS_FRAC  = 0.80    # fraction of overflow -> abs

CS_CATSPAN_COEFF   = 0.60   # CS rally: -coeff * delta_cat_spa * (indy_mov/100)
PPC_CATSPAN_COEFF  = 0.008

# Useful-vote PPC→CS transfer: stronger when indy_mov is high (CS dominance established)
USEFUL_VOTE_BASE   = 0.018
USEFUL_VOTE_HIGH   = 0.038   # fires when indy_mov > 72

# Trust disengagement: falling trust + high indy_mov → frustrated voters go to abs
TRUST_DISENGAGE_COEFF     = 0.08
TRUST_DISENGAGE_THRESHOLD = 60.0

CUP_TRUST_THRESHOLD = 30.0  # below this, cup trust sensitivity amplifies
CUP_TRUST_EXTRA     = 0.025

# ICR saturation: above this indy_mov level, ICR stops bleeding to indy outbidding.
# At extreme indy_mov (>85), voters already committed — marginal effect approaches 0.
ICR_SATURATION_THRESHOLD = 82.0
ICR_SATURATION_COEFF     = 0.045  # partial offset per unit indy_mov delta above threshold


# ---- VOTE MODEL CLASS -------------------------------------------------------

class VoteModel:
    """
    Continuous monthly vote model for Catalan parliament families.

    Parameters
    ----------
    initial_support : dict or None
        If None, loads 2012 anchor from election_anchors.pkl.
        Otherwise dict keyed (family, province, demo) -> pct.
    anchor_path : str
        Path to the pickle file with parsed anchors.
    """

    def __init__(self, initial_support=None,
                 anchor_path='simulations/results/election_anchors.pkl'):
        self.anchor_path = anchor_path
        self.support = np.zeros((N_FAM, N_PROV, N_DEMO))

        if initial_support is None:
            self._load_from_anchor('2012')
        else:
            for (fam, prov, demo), val in initial_support.items():
                self.support[FAM_IDX[fam], PROV_IDX[prov], DEMO_IDX[demo]] = val
            self._renorm_all()

        self.history = []   # list of (month, support_snapshot)
        self._events_fired = set()

    # ---- INITIALIZATION -----------------------------------------------------

    def _load_from_anchor(self, year):
        with open(self.anchor_path, 'rb') as f:
            data = pickle.load(f)
        anchor = data['anchors'][year]
        self.support[:] = 0.0
        for pi, prov in enumerate(PROVINCES):
            for di, demo in enumerate(DEMOS):
                cell = anchor.get(prov, {}).get(demo, {})
                for fam, val in cell.items():
                    if fam in FAM_IDX:
                        self.support[FAM_IDX[fam], pi, di] = val
        self._renorm_all()

    # ---- CORE UPDATE --------------------------------------------------------

    def update(self, engine_state, delta_vars):
        """
        Apply one monthly tick to vote support.

        Parameters
        ----------
        engine_state : dict
            Current variable LEVELS (not deltas).
            Keys: indy_movement, indy_trust, social_dissent, welfare_index,
                  cat_spa_relations, unemployment, podemos_channeling,
                  gen_party, gob_party, jxsi_formed, jxsi_dissolved, cup_veto_fired
        delta_vars : dict
            Variable DELTAS this month.
            Keys: indy_movement, indy_trust, social_dissent, welfare_index,
                  cat_spa_relations, unemployment, podemos_pulse (0/1)
        """
        indy_mov   = engine_state.get('indy_movement', 50.0)
        indy_trust = engine_state.get('indy_trust', 40.0)
        channeling = engine_state.get('podemos_channeling', 0.0)
        gen_party  = engine_state.get('gen_party', 'ciu')
        gob_party  = engine_state.get('gob_party', 'pp')

        # ── Flag-driven one-time shifts ───────────────────────────────────────
        if engine_state.get('jxsi_formed', False) and 'jxsi_formation' not in self._events_fired:
            apply_jxsi_formation(self)
            self._events_fired.add('jxsi_formation')

        if engine_state.get('jxsi_dissolved', False) and 'jxsi_dissolution' not in self._events_fired:
            apply_jxsi_dissolution(self)
            self._events_fired.add('jxsi_dissolution')

        # Create a local copy of dvars to include transient pulses detected from flags
        dv_mod = dict(delta_vars)
        if engine_state.get('cup_veto_fired', False) and 'cup_veto' not in self._events_fired:
            dv_mod['cup_veto_pulse'] = 1.0
            self._events_fired.add('cup_veto')

        # Standard Δvars vector (nonlinear cols zeroed — handled below)
        dv = np.zeros(N_VARS)
        dv[V_INDY_MOV]   = dv_mod.get('indy_movement', 0.0)
        dv[V_INDY_TRUST] = dv_mod.get('indy_trust', 0.0)
        dv[V_UNEMP]      = dv_mod.get('unemployment', 0.0)
        dv[V_PODEMOS]    = dv_mod.get('podemos_pulse', 0.0)
        # dissent/welfare/cat_spa = 0 in dv; handled via dedicated delta vectors below

        # Nonlinear family-level delta vectors (UNSCALED — scaled per-demo below)
        d_dissent   = self._dissent_delta(
            dv_mod.get('social_dissent', 0.0), channeling)
        d_welfare   = self._welfare_delta(
            dv_mod.get('welfare_index', 0.0), gen_party, gob_party)
        d_cat_spa   = self._catspa_delta(
            dv_mod.get('cat_spa_relations', 0.0), indy_mov)
        d_cup_trust       = self._cup_trust_extra(
            dv_mod.get('indy_trust', 0.0), indy_trust)
        d_trust_disengage = self._trust_disengage_delta(
            dv_mod.get('indy_trust', 0.0), indy_mov)
        d_icr_saturation  = self._icr_saturation_delta(
            dv_mod.get('indy_movement', 0.0), indy_mov)
        
        # New: Iceta recovery (PSC) and 2017 consolidation (Indy)
        d_psc_recovery = self._psc_iceta_recovery(
            engine_state, dv_mod)
        d_indy_consolidation = self._indy_useful_vote_consolidation(
            engine_state, dv_mod)

        for pi, prov in enumerate(PROVINCES):
            for di, demo in enumerate(DEMOS):
                # Combined matrix: demo behaviour + province differential
                T_eff = T_BY_DEMO[demo] + _DELTA_PROV[prov]

                nl_d = NONLIN_DEMO_SCALE[demo]
                nl_p = NONLIN_PROV_SCALE[prov]

                # Matrix-driven delta
                raw = T_eff @ dv

                # Per-(demo × province) scaled nonlinear deltas
                raw += d_dissent   * nl_d['dissent']   * nl_p['dissent']
                raw += d_welfare   * nl_d['welfare']   * nl_p['welfare']
                raw += d_cat_spa   * nl_d['cat_spa']   * nl_p['cat_spa']
                raw += d_cup_trust       * nl_d['cup_trust'] * nl_p['cup_trust']
                raw += d_trust_disengage * nl_d['cup_trust'] * nl_p['cup_trust']
                raw += d_icr_saturation
                raw += d_psc_recovery
                raw += d_indy_consolidation
                raw += self._art155_backlash(engine_state)

                self.support[:, pi, di] += raw
                self._renorm_cell(pi, di)

        self.history.append((self.support.copy()))

    # ---- PLAYER/EVENT ACTIONS -----------------------------------------------

    def add_support(self, family, province, demo, amount):
        """
        Add `amount` percentage points to one (family, prov, demo) cell.
        Draws proportionally from all other families in that cell.
        Safe for player actions and event-driven direct adjustments.
        """
        fi = FAM_IDX[family]
        pi = PROV_IDX[province]
        di = DEMO_IDX[demo]

        current      = self.support[fi, pi, di]
        others_total = 100.0 - current
        if others_total < 1e-6:
            return

        self.support[fi, pi, di] += amount
        for fj in range(N_FAM):
            if fj != fi:
                share = self.support[fj, pi, di] / others_total
                self.support[fj, pi, di] -= amount * share
        self._renorm_cell(pi, di)

    def add_support_province(self, family, province, amount_by_demo):
        """
        Convenience: add support to all demos in a province.
        amount_by_demo: dict {demo: amount} or float (applied uniformly).
        """
        for di, demo in enumerate(DEMOS):
            if isinstance(amount_by_demo, dict):
                amt = amount_by_demo.get(demo, 0.0)
            else:
                amt = amount_by_demo
            if abs(amt) > 1e-9:
                self.add_support(family, province, demo, amt)

    # ---- SEAT CALCULATION ---------------------------------------------------

    def seat_counts(self, demo_populations=None):
        """
        Compute D'Hondt seat allocation across all provinces.

        Abstain is excluded from the vote pool entirely — it reduces
        participation but does not compete for seats (matching cat_simulation.py).

        Parameters
        ----------
        demo_populations : dict or None
            {province: {demo: population}} for weighted aggregation.
            If None, uniform demographic weights.

        Returns
        -------
        dict {family: total_seats}  (abs key will always be 0 / absent)
        """
        total_seats = defaultdict(int)
        abs_fi = FAM_IDX['abs']

        for pi, prov in enumerate(PROVINCES):
            n_seats = SEATS[prov]

            # 1. Aggregate support across demographics (weighted by population)
            prov_support = np.zeros(N_FAM)
            if demo_populations and prov in demo_populations:
                pop = demo_populations[prov]
                total_pop = sum(pop.values())
                if total_pop < 1e-6:
                    prov_support = self.support[:, pi, :].mean(axis=1)
                else:
                    for di, demo in enumerate(DEMOS):
                        w = pop.get(demo, 0.0) / total_pop
                        prov_support += self.support[:, pi, di] * w
            else:
                prov_support = self.support[:, pi, :].mean(axis=1)

            # 2. Remove abstain from the vote pool entirely.
            #    Remaining shares are the "active vote" pool.
            prov_support[abs_fi] = 0.0
            active_total = prov_support.sum()
            if active_total < 1e-9:
                continue

            # 3. Convert to % of active vote (not of total incl. abstain)
            active_pct = prov_support / active_total * 100.0

            # 4. Apply 3% threshold against active vote share
            active_pct[active_pct < 3.0] = 0.0
            threshold_total = active_pct.sum()
            if threshold_total < 1e-9:
                continue
            vote_shares = active_pct / threshold_total   # normalised [0,1]

            # 5. D'Hondt
            seats = self._dhondt(vote_shares, n_seats)
            for fi, fam in enumerate(FAMILIES):
                total_seats[fam] += seats[fi]

        return dict(total_seats)

    def _dhondt(self, vote_shares, n_seats):
        seats = np.zeros(N_FAM, dtype=int)
        quotients = vote_shares.copy()
        for _ in range(n_seats):
            winner = int(np.argmax(quotients))
            seats[winner] += 1
            quotients[winner] = vote_shares[winner] / (seats[winner] + 1)
        return seats

    def snapshot(self, demo_populations=None):
        seats = self.seat_counts(demo_populations)
        avg_support = {fam: float(self.support[FAM_IDX[fam]].mean())
                       for fam in FAMILIES}
        return {'seats': seats, 'avg_support': avg_support}

    def print_snapshot(self, label="", demo_populations=None):
        snap = self.snapshot(demo_populations)
        print(f"\n{'='*55}")
        print(f"  {label}")
        print(f"{'='*55}")
        seats = snap['seats']
        total = sum(seats.values())
        print(f"  {'Family':<10}  {'Seats':>5}  {'Avg%':>6}")
        print(f"  {'-'*30}")
        for fam in FAMILIES:
            s = seats.get(fam, 0)
            avg = snap['avg_support'][fam]
            if s > 0 or avg > 0.5:
                print(f"  {fam:<10}  {s:>5}  {avg:>5.1f}%")
        print(f"  {'TOTAL':<10}  {total:>5}")

    # ---- HELPERS ------------------------------------------------------------

    def _renorm_all(self):
        self.support = np.clip(self.support, 0.0, None)
        totals = self.support.sum(axis=0, keepdims=True)
        totals = np.where(totals < 1e-6, 1.0, totals)
        self.support = self.support / totals * 100.0

    def _renorm_cell(self, pi, di):
        col = self.support[:, pi, di]
        np.clip(col, 0.0, None, out=col)
        total = col.sum()
        if total > 1e-6:
            self.support[:, pi, di] = col / total * 100.0

    # ---- NONLINEAR HELPERS --------------------------------------------------

    def _dissent_delta(self, d_dissent, channeling):
        """
        Rising dissent: fl absorbs up to channeling capacity,
        overflow splits cup (20%) / abs (80%).
        Falling dissent reverses this.
        Returns UNSCALED vector — caller applies NONLIN_DEMO_SCALE['dissent'].
        """
        delta = np.zeros(N_FAM)
        if abs(d_dissent) < 1e-9:
            return delta

        if d_dissent > 0:
            # Baseline gains independent of channeling
            cup_base_gain = d_dissent * 0.045
            abs_base_gain = d_dissent * 0.015
            
            # Channeling-dependent gain for fl (Comuns)
            fl_gain  = DISSENT_FL_MAX * channeling * d_dissent
            
            # Additional overflow for cup/abs if channeling is LOW
            overflow = DISSENT_FL_MAX * max(0, 0.7 - channeling) * d_dissent
            cup_extra = overflow * 0.4
            abs_extra = overflow * 0.6
            
            total_in = fl_gain + cup_base_gain + cup_extra + abs_base_gain + abs_extra

            delta[FAM_IDX['fl']]   += fl_gain
            delta[FAM_IDX['cup']]  += cup_base_gain + cup_extra
            delta[FAM_IDX['abs']]  += abs_base_gain + abs_extra
            # Draw from establishment parties
            delta[FAM_IDX['icr']]  -= total_in * 0.45
            delta[FAM_IDX['psc']]  -= total_in * 0.30
            delta[FAM_IDX['unio']] -= total_in * 0.15
            delta[FAM_IDX['pdcat']]-= total_in * 0.10
        else:
            total_out = abs(d_dissent) * DISSENT_FL_MAX
            # When channeling is active, some fl recovery goes to psc (bleed-back)
            psc_bleedback = total_out * channeling * 0.35
            delta[FAM_IDX['fl']]   -= total_out * channeling
            delta[FAM_IDX['abs']]  -= total_out * (1.0 - channeling)
            delta[FAM_IDX['icr']]  += total_out * 0.50
            delta[FAM_IDX['psc']]  += total_out * 0.30 + psc_bleedback
            delta[FAM_IDX['unio']] += total_out * 0.20
            delta[FAM_IDX['fl']]   += psc_bleedback   # fl gives back to psc

        return delta

    def _welfare_delta(self, d_welfare, gen_party, gob_party):
        """
        Welfare credit/blame distributed to governing families.
        Returns UNSCALED vector — caller applies NONLIN_DEMO_SCALE['welfare'].
        """
        delta = np.zeros(N_FAM)
        if abs(d_welfare) < 1e-9:
            return delta

        gen_fam = GEN_FAMILY.get(gen_party, 'icr')
        gob_fam = GOB_FAMILY.get(gob_party, 'ppc')
        governing = {gen_fam, gob_fam}

        delta[FAM_IDX[gen_fam]] += WELFARE_GAIN_GEN * d_welfare
        delta[FAM_IDX[gob_fam]] += WELFARE_GAIN_GOB * d_welfare

        total_in = (WELFARE_GAIN_GEN + WELFARE_GAIN_GOB) * d_welfare
        # PSC excluded from opposition blame — doesn't govern; its voters are insulated
        # from Generalitat/Moncloa welfare credit/blame dynamics in this period
        opposition = [f for f in FAMILIES if f not in governing and f != 'psc']
        if opposition:
            per_opp = total_in / len(opposition)
            for fam in opposition:
                delta[FAM_IDX[fam]] -= per_opp

        # CUP and fl have extra anti-austerity response to welfare falling
        if d_welfare < 0:
            anti_austerity = abs(d_welfare) * 0.14
            delta[FAM_IDX['cup']] += anti_austerity * 0.45
            delta[FAM_IDX['fl']]  += anti_austerity * 0.55
            delta[FAM_IDX['icr']] -= anti_austerity * 0.60
            delta[FAM_IDX['ppc']] -= anti_austerity * 0.40

        return delta

    def _catspa_delta(self, d_cat_spa, indy_mov):
        """
        Cat-spa falling -> CS/PPC rally, compounded by indy_mov level.
        PSC benefits from improving relations.
        Abstain falls when conflict is high (crisis mobilization).
        Returns UNSCALED vector — caller applies NONLIN_DEMO_SCALE['cat_spa'].
        """
        delta = np.zeros(N_FAM)
        if abs(d_cat_spa) < 1e-9:
            return delta

        indy_factor = indy_mov / 100.0

        cs_gain  = -CS_CATSPAN_COEFF  * d_cat_spa * indy_factor
        ppc_gain = -PPC_CATSPAN_COEFF * d_cat_spa * indy_factor
        delta[FAM_IDX['cs']]  += cs_gain
        delta[FAM_IDX['ppc']] += ppc_gain

        # PSC: symmetric cat_spa sensitivity.
        # When relations improve, PSC's federalist pitch works — it gains moderates.
        # When relations fall, PSC loses those same voters.
        delta[FAM_IDX['psc']] += 0.015 * d_cat_spa

        # "Useful vote" consolidation
        uv_coeff    = USEFUL_VOTE_HIGH if indy_mov > 72.0 else USEFUL_VOTE_BASE
        useful_vote = uv_coeff * max(0.0, -d_cat_spa) * indy_factor
        delta[FAM_IDX['cs']]  += useful_vote
        delta[FAM_IDX['ppc']] -= useful_vote

        # Abstain: falling cat_spa -> mobilization -> abstain falls
        delta[FAM_IDX["abs"]] += 0.50 * d_cat_spa

        # Balance: cs/ppc gains draw from indy bloc; losses go back to indy
        unionist_net = cs_gain + ppc_gain
        if unionist_net > 0:   # cat_spa fell
            delta[FAM_IDX['icr']] -= unionist_net * 0.40
            delta[FAM_IDX['il']]  -= unionist_net * 0.30
            delta[FAM_IDX['psc']] -= unionist_net * 0.15
            delta[FAM_IDX['fl']]  -= unionist_net * 0.15
        else:                   # cat_spa rose, cs/ppc lose
            delta[FAM_IDX['icr']] -= unionist_net * 0.50
            delta[FAM_IDX['il']]  -= unionist_net * 0.30
            delta[FAM_IDX['fl']]  -= unionist_net * 0.20

        return delta

    def _trust_disengage_delta(self, d_indy_trust, indy_mov):
        """
        When indy_trust falls AND indy_mov is above threshold, frustrated
        indy-sympathetic voters disengage into abstention rather than switching
        party. Captures the 2015 plebiscitary abstention dynamic.
        Draws from icr and il. Scaled per-demo via NONLIN_DEMO_SCALE['cup_trust'].
        """
        delta = np.zeros(N_FAM)
        if d_indy_trust >= 0 or indy_mov < TRUST_DISENGAGE_THRESHOLD:
            return delta
        indy_factor = (indy_mov - TRUST_DISENGAGE_THRESHOLD) / (
            100.0 - TRUST_DISENGAGE_THRESHOLD)
        abs_gain = TRUST_DISENGAGE_COEFF * abs(d_indy_trust) * indy_factor
        delta[FAM_IDX['abs']]  += abs_gain
        delta[FAM_IDX['icr']]  -= abs_gain * 0.55
        delta[FAM_IDX['il']]   -= abs_gain * 0.45
        return delta

    def _icr_saturation_delta(self, d_indy_mov, indy_mov):
        """
        At very high indy_mov levels (>82), ICR has already captured all
        convertible voters — further indy_mov rises no longer bleed ICR.
        This counteracts the BASE_T icr×indy_mov term to model saturation.
        Applied directly (no per-demo/prov scaling needed — it's a ceiling effect).
        Returns a balanced vector: ICR gains back what it would have bled.
        """
        delta = np.zeros(N_FAM)
        if d_indy_mov <= 0 or indy_mov <= ICR_SATURATION_THRESHOLD:
            return delta
        saturation = (indy_mov - ICR_SATURATION_THRESHOLD) / (
            100.0 - ICR_SATURATION_THRESHOLD)
        # How much ICR would bleed from this indy_mov tick (BASE_T icr col)
        icr_bleed_prevented = ICR_SATURATION_COEFF * d_indy_mov * saturation
        delta[FAM_IDX['icr']]  += icr_bleed_prevented
        # Balance: offset drawn from abs (the votes that would have gone nowhere)
        delta[FAM_IDX['abs']]  -= icr_bleed_prevented
        return delta

    def _psc_iceta_recovery(self, state, dvars):
        """
        Replaces the old psc_recovery_delta. 
        Triggered when psc_recovery_active flag is True (post-Navarro).
        Iceta-era PSC recovers from abs and fl (Comuns).
        Also draws from Cs/PPC when conflict is high but people want moderation.
        """
        delta = np.zeros(N_FAM)
        if not state.get('psc_recovery_active', False):
            return delta
        
        # Monthly base recovery from abs
        base_gain = 0.018
        delta[FAM_IDX['psc']] += base_gain
        delta[FAM_IDX['abs']] -= base_gain
        
        # Additional recovery from fl (Comuns) if cat_spa is low
        cat_spa = state.get('cat_spa_relations', 40.0)
        if cat_spa < 25.0:
            fl_gain = 0.012 * (25.0 - cat_spa) / 20.0
            delta[FAM_IDX['psc']] += fl_gain
            delta[FAM_IDX['fl']]  -= fl_gain
            
        # 2017 Crisis: moderate unionists return from Cs/PPC to PSC
        # when 155 is loomng or active (cat_spa < 12).
        if cat_spa < 12.0:
            shift = 0.45
            delta[FAM_IDX['psc']] += shift
            delta[FAM_IDX['cs']]  -= shift * 0.5
            delta[FAM_IDX['ppc']] -= shift * 0.5
            
        return delta

    def _indy_useful_vote_consolidation(self, state, dvars):
        """
        Consolidates the indy bloc around the main parties (icr, il)
        when the state is in high crisis (post-1-O, 155).
        Voters flee CUP to the governing/repressed leaders.
        Also handles the Jan 2016 CUP-veto-Mas fallout.
        """
        delta = np.zeros(N_FAM)
        
        # 1. One-time fallout from CUP vetoing Mas (Jan 2016)
        if dvars.get('cup_veto_pulse', 0.0) > 0:
            veto_shift = 2.4
            delta[FAM_IDX['cup']] -= veto_shift
            delta[FAM_IDX['icr']] += veto_shift * 0.8
            delta[FAM_IDX['il']]  += veto_shift * 0.2
            
        # 2. 2017 peak consolidation (useful vote for JxCat/ERC)
        # Driven by high crisis events (1-O, 155, 21-D)
        is_high_crisis = state.get('1o_fired', False) or state.get('art155_ever', False)
        if not is_high_crisis:
            return delta
            
        # 3. Consolidation peak (2017 cycle)
        # Stops entirely after 21-D: useful-vote is an election-campaign phenomenon,
        # not a structural post-crisis state. Continuing after 21-D drains CUP to 0.
        is_21d_fired = state.get('21d_fired', False)
        if is_21d_fired:
            return delta
        shift_mult = 1.0

        # Transfer from CUP to main parties
        # In reality, CUP went from 8% to 4% in 2017.
        shift = 2.50 * shift_mult
        delta[FAM_IDX['cup']] -= shift
        delta[FAM_IDX['icr']] += shift * 0.5
        delta[FAM_IDX['il']]  += shift * 0.5
        
        # Also consolidation from fl (Comuns) to indy bloc (especially ERC/il)
        # and from Cs (who is over-performing) to indy bloc
        fl_shift = 0.45 * shift_mult
        delta[FAM_IDX['fl']]  -= fl_shift
        delta[FAM_IDX['il']]  += fl_shift
        
        cs_drain = 0.40 * shift_mult
        delta[FAM_IDX['cs']]  -= cs_drain
        delta[FAM_IDX['icr']] += cs_drain
        
        return delta

    def _cup_trust_extra(self, d_indy_trust, current_trust):
        """
        Below CUP_TRUST_THRESHOLD, falling trust amplifies CUP gains
        at the expense of icr (leadership betrayal dynamic).
        Returns UNSCALED vector — caller applies NONLIN_DEMO_SCALE['cup_trust'].
        """
        delta = np.zeros(N_FAM)
        if abs(d_indy_trust) < 1e-9 or current_trust >= CUP_TRUST_THRESHOLD:
            return delta

        depth = (CUP_TRUST_THRESHOLD - current_trust) / CUP_TRUST_THRESHOLD
        extra_cup = -CUP_TRUST_EXTRA * d_indy_trust * depth
        delta[FAM_IDX['cup']]  += extra_cup
        delta[FAM_IDX['icr']]  -= extra_cup * 0.70
        delta[FAM_IDX['il']]   -= extra_cup * 0.30
        return delta

    def _art155_backlash(self, state):
        """
        Backlash against the application of Article 155.
        Penalizes PPC and PSC (who supported it).
        Redistributes to il (ERC) and fl (Comuns).
        """
        delta = np.zeros(N_FAM)
        if state.get('gen_party', '') != 'art155':
            return delta
            
        punishment = 0.55
        delta[FAM_IDX['ppc']] -= punishment * 0.4
        delta[FAM_IDX['psc']] -= punishment * 0.6
        
        # Moderate backlash goes to the "third space" (fl) and il
        delta[FAM_IDX['fl']]  += punishment * 0.5
        delta[FAM_IDX['il']]  += punishment * 0.5
        
        return delta

# ---- PER-PROVINCE TRANSFER DELTAS -----------------------------------------
# delta_T_PROV[province] has column-sum ZERO by construction.
# Barcelona is the reference province (delta = 0).
# T_eff[demo, prov] = T_BY_DEMO[demo] + _DELTA_PROV[prov]
# Column sum of T_eff = 0 + 0 = 0  (additive of two zero-sum matrices)
#
# Province character:
#   barcelona  — urban/diverse reference; no adjustment needed
#   girona     — most indy province; strong ICR+IL response; CS loses harder
#   lleida     — agrarian; ICR dominant; IL less reactive; high abs inertia
#   tarragona  — unionist-adjacent; CS stronger; ICR weaker; PSC holds better

_DELTA_PROV = {p: np.zeros((N_FAM, N_VARS)) for p in PROVINCES}

def _imov_prov(prov, mults):
    _base = {'icr':0.060,'il':0.220,'cup':0.020,'fl':-0.020,
             'psc':-0.025,'cs':-0.020,'ppc':-0.040,'abs':-0.250}
    dT = _DELTA_PROV[prov]; net = 0.0
    for fam, mult in mults.items():
        d = _base.get(fam, 0.0) * (mult - 1.0)
        dT[_r(fam), V_INDY_MOV] += d; net += d
    dT[_r('abs'), V_INDY_MOV] -= net

def _unemp_prov(prov, mults):
    _base = {'icr':-0.030,'fl':0.025,'psc':-0.020,'abs':0.025}
    dT = _DELTA_PROV[prov]; net = 0.0
    for fam, mult in mults.items():
        d = _base.get(fam, 0.0) * (mult - 1.0)
        dT[_r(fam), V_UNEMP] += d; net += d
    dT[_r('abs'), V_UNEMP] -= net

# barcelona — identity (reference)

# girona: most indy; ICR/IL more reactive; CS loses harder; abs mobilises strongly
_imov_prov('girona',    {'icr': 1.40, 'il': 1.30, 'cs': 1.60, 'psc': 0.60, 'fl': 0.50})

# lleida: agrarian; ICR dominant; IL less reactive; fl less relevant economically
_imov_prov('lleida',    {'icr': 1.50, 'il': 0.80, 'cs': 0.70, 'psc': 0.50, 'cup': 0.50})
_unemp_prov('lleida',   {'icr': 1.40, 'fl': 0.70})

# tarragona: most unionist-adjacent; CS stronger; ICR/IL less reactive; PSC holds
_imov_prov('tarragona', {'icr': 0.80, 'il': 0.90, 'cs': 0.60, 'psc': 1.30})
_unemp_prov('tarragona',{'psc': 1.40, 'fl': 1.30})

# Validate
for _prov, _dP in _DELTA_PROV.items():
    for _j in range(N_VARS):
        _s = _dP[:, _j].sum()
        assert abs(_s) < 1e-7, (
            f"vote_model: _DELTA_PROV['{_prov}'] column {VAR_NAMES[_j]} sum = {_s:.2e}")

# Per-province nonlinear scale (dissent, welfare, cat_spa, cup_trust)
# Applied multiplicatively on top of NONLIN_DEMO_SCALE.
# e.g. total_scale = NONLIN_DEMO_SCALE[demo][key] * NONLIN_PROV_SCALE[prov][key]
NONLIN_PROV_SCALE = {
    'barcelona': {'dissent': 1.00, 'welfare': 1.00, 'cat_spa': 1.00, 'cup_trust': 1.00},
    'girona':    {'dissent': 1.10, 'welfare': 0.90, 'cat_spa': 1.40, 'cup_trust': 1.20},
    'lleida':    {'dissent': 0.80, 'welfare': 0.90, 'cat_spa': 1.10, 'cup_trust': 0.80},
    'tarragona': {'dissent': 1.00, 'welfare': 1.10, 'cat_spa': 0.80, 'cup_trust': 0.90},
}


# JxSí era: months 25-64 (coalition formed ~Jan 2015, dissolved after Dec 2017 election)
JXSI_ACTIVE_MONTHS = (25, 64)   # Jan 2015 to Dec 2017 election (inclusive)


# ---- JXSI EVENTS ------------------------------------------------------------
# These should be fired from the calibration_runner / game engine at the right months.

def apply_jxsi_formation(vmodel, icr_erc_split=None):
    """
    JxSí coalition formation event (~Jan 2015, month 25).
    CDC and ERC run together; internally icr/il remain separate but
    we apply a small solidarity boost — each family gains a few pp
    from smaller parties and abstain as the broad coalition energizes voters.
    
    BUT we also add friction: moderate CDC voters dislike the deal with ERC,
    and radical ERC voters dislike the deal with CDC. Some bleed to CUP/FL/PSC.

    icr_erc_split: (icr_share, il_share) tuple, default (0.55, 0.45).
    If the player has run strong ERC campaigns, pass a different split.
    """
    if icr_erc_split is None:
        icr_erc_split = (0.55, 0.45)

    icr_share, il_share = icr_erc_split

    for pi in range(N_PROV):
        for di in range(N_DEMO):
            # 1. Mobilization boost
            mob = 1.2 # Reduced from 2.0
            vmodel.support[FAM_IDX['abs'], pi, di]  -= mob
            vmodel.support[FAM_IDX['icr'], pi, di]  += mob * icr_share
            vmodel.support[FAM_IDX['il'],  pi, di]  += mob * il_share
            
            # 2. Coalition friction (bleed to others)
            # Radical bleed to CUP (increased for 2015 breakout)
            radical_bleed = 2.8
            vmodel.support[FAM_IDX['il'],  pi, di] -= radical_bleed * 0.7
            vmodel.support[FAM_IDX['icr'], pi, di] -= radical_bleed * 0.3
            vmodel.support[FAM_IDX['cup'], pi, di] += radical_bleed
            
            # Moderate bleed to PSC / Comuns
            moderate_bleed = 1.5
            vmodel.support[FAM_IDX['icr'], pi, di] -= moderate_bleed * 0.8
            vmodel.support[FAM_IDX['il'],  pi, di] -= moderate_bleed * 0.2
            vmodel.support[FAM_IDX['psc'], pi, di] += moderate_bleed * 0.5
            vmodel.support[FAM_IDX['fl'],  pi, di] += moderate_bleed * 0.5
            vmodel._renorm_cell(pi, di)

    # CUP breakout surge: first serious national push, kingmaker positioning.
    # Fires together with JxSí formation — both events are part of the same
    # plebiscitary turn in Sep 2015 / Jan 2015 campaign period.
    # ~1.8pp CUP gain drawn from icr and abs — investiture abstention event at m=39
    # will knock ~1.6pp back, giving correct 2015 peak and lower 2017 level.
    for pi in range(N_PROV):
        for di in range(N_DEMO):
            cup_surge = 2.4
            vmodel.support[FAM_IDX['cup'], pi, di] += cup_surge
            vmodel.support[FAM_IDX['icr'], pi, di] -= cup_surge * 0.60
            vmodel.support[FAM_IDX['abs'], pi, di] -= cup_surge * 0.40
            vmodel._renorm_cell(pi, di)

    vmodel._jxsi_split = icr_erc_split


def apply_jxsi_dissolution(vmodel):
    """
    JxSí dissolution event (~Dec 2017, month 65).
    CDC and ERC split back into separate electoral lists.
    Small demobilization penalty as coalition excitement fades.
    """
    icr_share = getattr(vmodel, '_jxsi_split', (0.55, 0.45))[0]
    il_share  = 1.0 - icr_share

    for pi in range(N_PROV):
        for di in range(N_DEMO):
            demob = 1.5
            vmodel.support[FAM_IDX['icr'], pi, di] -= demob * icr_share
            vmodel.support[FAM_IDX['il'],  pi, di] -= demob * il_share
            vmodel.support[FAM_IDX['abs'], pi, di] += demob
            vmodel._renorm_cell(pi, di)
