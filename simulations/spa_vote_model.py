"""
spa_vote_model.py — Python port of design/spa_congreso_engine.js

Tracks Spanish Congreso support as % per (constituency, party family).
All active families including 'abs' sum to 100 per constituency.

D'Hondt seat counting delegates to demographics_data/spa_simulation.py
for the 'rest' constituency (virtual province simulation) and runs
standard D'Hondt for the other six constituencies.

Month 1 = Aug 2012  |  Timeframe: Aug 2012 – Nov 2019 (88 months)
"""

import numpy as np
import sys
import os
from copy import deepcopy

# Allow importing from demographics_data/
_DEMO_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'demographics_data'))
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)
from spa_simulation import dhondt_method, simulate_rest_constituency  # noqa: E402

# ── CONSTITUENCIES ────────────────────────────────────────────────────────────

CONSTITUENCIES     = ['catalunya', 'euskadi', 'galicia', 'valencia', 'navarra', 'balears', 'rest']
URBAN_CONSTITUENCIES = ['catalunya', 'euskadi', 'valencia', 'balears']

# Seats per constituency (Spanish Congreso, 2016 configuration — 350 total)
SEAT_DISTRIBUTION = {
    'catalunya': 47, 'euskadi': 18, 'galicia': 23, 'valencia': 33,
    'navarra':    5, 'balears':  8, 'rest':   216,
}

# Approximate eligible electorate per constituency (2015 era, used for D'Hondt
# synthetic vote conversion; relative scale matters, not absolute).
ELECTORATE = {
    'catalunya':  5_130_000,
    'euskadi':    1_680_000,
    'galicia':    2_180_000,
    'valencia':   3_710_000,
    'navarra':      430_000,
    'balears':      720_000,
    'rest':      24_200_000,
}

# ── NAVARRA STATE MACHINE ─────────────────────────────────────────────────────
# Mirrors the JS implementation exactly.
#
#  "default"    — PP, UPN, CS run separately (UPN reabsorbed into PP for IRL
#                 general elections 2012-2016; UPN support hardcoded to 0)
#  "upn_rival"  — UPN has broken from PP
#  "nsuma"      — PP + UPN + CS merged into NSuma (Nov 2019 election)
#  "post_split" — NSuma broke up; UPN re-emerged separately

def get_navarra_state(flags):
    if flags.get('spa_nsuma_formed'):
        return 'post_split' if flags.get('spa_upn_defect') else 'nsuma'
    return 'upn_rival' if flags.get('spa_upn_independent') else 'default'


# ── ACTIVE FAMILIES PER CONSTITUENCY ─────────────────────────────────────────

def get_active_families(c, flags):
    """Return list of internal family names active in constituency c."""
    ns = get_navarra_state(flags)

    cs_active = flags.get('spa_cs_active', False)

    navarra_base = ['pp', 'upn', 'psoe', 'podemos', 'bildu', 'geroa_bai', 'abs']
    navarra_cs   = ['pp', 'upn', 'cs', 'psoe', 'podemos', 'bildu', 'geroa_bai', 'abs']
    NAVARRA_FAM = {
        'default':    navarra_cs   if cs_active else navarra_base,
        'upn_rival':  navarra_cs   if cs_active else navarra_base,
        'nsuma':      ['nsuma', 'psoe', 'podemos', 'bildu', 'geroa_bai', 'abs'],
        'post_split': ['pp', 'upn', 'psoe', 'podemos', 'bildu', 'geroa_bai', 'abs'],
    }

    if c == 'catalunya':
        fams = ['pp', 'psoe', 'podemos', 'cat_conv', 'erc', 'abs']
        if cs_active:                       fams.append('cs')
        if flags.get('spa_cup_spa_active'): fams.append('cup_spa')
        if flags.get('spa_fr_active'):      fams.append('fr')
    elif c == 'euskadi':
        fams = ['pp', 'psoe', 'podemos', 'pnv', 'bildu', 'abs']
        if cs_active: fams.append('cs')
    elif c == 'galicia':
        fams = ['pp', 'psoe', 'podemos', 'bng', 'abs']
        if cs_active: fams.append('cs')
    elif c == 'valencia':
        fams = ['pp', 'psoe', 'podemos', 'abs']
        if flags.get('spa_compromis_active'): fams.append('compromis')
        if cs_active: fams.append('cs')
    elif c == 'navarra':
        fams = list(NAVARRA_FAM.get(ns, NAVARRA_FAM['default']))
    elif c == 'balears':
        fams = ['pp', 'psoe', 'podemos', 'abs']
        if flags.get('spa_mes_active'): fams.append('mes')
        if cs_active: fams.append('cs')
    elif c == 'rest':
        fams = ['pp', 'psoe', 'podemos', 'cc', 'prc', 'te', 'abs']
        if cs_active:                    fams.append('cs')
        if flags.get('spa_foro_active'): fams.append('foro')
    else:
        fams = []

    # Nationwide optional parties (not in Navarra — absorbed into NSuma dynamics)
    if c != 'navarra':
        if flags.get('vox_active'):         fams.append('vox')
        if flags.get('spa_iu_split'):       fams.append('iu')
        if flags.get('spa_up_masq_split'):  fams.append('mas_pais')

    return fams


# ── ECONOMIC RESPONSE COEFFICIENTS ───────────────────────────────────────────
# Per unit of each driver delta, how much the family's support shifts.
# Drivers: d_gdp, d_unemp, d_welfare, d_dissent
# Regional/independence-space parties have near-zero economic sensitivity —
# they respond to cat_spa_relations instead (see update() section 4d).
# All values are [TUNE] — calibrated in spa_calibration_runner.py.

ECON_BASE_DEFAULT = {
    #               d_gdp   d_unemp  d_welfare  d_dissent
    'pp':        {'g':  0.06, 'u': -0.05, 'w':  0.03, 'd': -0.04},
    'psoe':      {'g':  0.06, 'u': -0.04, 'w':  0.04, 'd': -0.03},
    'podemos':   {'g': -0.04, 'u':  0.06, 'w': -0.04, 'd':  0.07},
    'cs':        {'g': -0.02, 'u':  0.03, 'w': -0.01, 'd':  0.02},
    'vox':       {'g': -0.01, 'u':  0.01, 'w': -0.01, 'd':  0.02},
    'iu':        {'g': -0.03, 'u':  0.04, 'w': -0.03, 'd':  0.05},
    'mas_pais':  {'g': -0.02, 'u':  0.03, 'w': -0.02, 'd':  0.04},
    'abs':       {'g': -0.02, 'u':  0.02, 'w': -0.02, 'd':  0.03},
    # Navarra
    'nsuma':     {'g':  0.05, 'u': -0.04, 'w':  0.03, 'd': -0.03},
    'upn':       {'g':  0.01, 'u':  0.00, 'w':  0.01, 'd': -0.01},
    'geroa_bai': {'g':  0.00, 'u':  0.01, 'w': -0.01, 'd':  0.02},
    # Euskadi
    'pnv':       {'g':  0.01, 'u':  0.00, 'w':  0.01, 'd': -0.01},
    'bildu':     {'g': -0.01, 'u':  0.01, 'w': -0.01, 'd':  0.01},
    # Galicia — bng tracks NOS/En Marea in 2015-16, pure BNG from 2019
    'bng':       {'g':  0.00, 'u':  0.01, 'w': -0.01, 'd':  0.01},
    # Valencia — dissent-driven, similar to Podemos but weaker
    'compromis': {'g': -0.02, 'u':  0.03, 'w': -0.02, 'd':  0.05},
    # Balears — same logic, slightly softer
    'mes':       {'g': -0.01, 'u':  0.02, 'w': -0.01, 'd':  0.04},
    # Catalunya independence space — driven by cat_spa, not national economics
    'erc':       {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'cat_conv':  {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'cup_spa':   {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'fr':        {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    # Rest minors — zero econ sensitivity; driven by mean reversion + noise instead
    'cc':        {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'prc':       {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'te':        {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
    'foro':      {'g':  0.00, 'u':  0.00, 'w':  0.00, 'd':  0.00},
}

# ── MINOR PARTY REVERSION (rest constituency) ─────────────────────────────────
# CC, PRC, TE, and FORO (FAC) are regional parties that win seats through
# geographic concentration the virtual province simulation cannot model.
# Instead of following national economic trends, they have:
#   - A long-run target support % that acts as a mean-reversion anchor
#   - Scaled-down noise so small vote shares don't drift to zero
#
# These targets represent the parties' stable regional base as a % of the
# full 'rest' electorate (abs included).  Events in the timeline inject
# extra support for emergence moments (TE 2018, CC 2019 growth, etc.).
#
# 'foro' target is only relevant when spa_foro_active is True (player-triggered);
# the runner seeds initial foro support from PP when the flag fires.

MINOR_REST_PARTIES = frozenset({'cc', 'prc', 'te', 'foro'})

MINOR_REST_TARGETS = {
    'cc':   1.00,   # Coalición Canaria — stable ~1% throughout
    'prc':  0.12,   # PRC resting base — below non-abs threshold through 2016;
                    # +0.22 event at month 79 lifts it to ~0.34% for 2019 elections
    'te':   0.08,   # TE below threshold until formation event (Sep 2018) injects it
    'foro': 0.40,   # FAC if player activates (seeded by runner; reverts here)
}

# ── NAMED SCALAR CONSTANTS (all [TUNE]) ───────────────────────────────────────

DEFAULTS = {
    'gov_gdp_boost':    0.041,    # extra incumbent delta per unit of positive d_gdp
    'corr_pp_cs_urban': 0.00075,  # PP→CS bleed per unit of corruption_pp, urban
    'corr_pp_cs_base':  0.00041,  # PP→CS bleed per unit of corruption_pp, rural
    'corr_pp_abs':      0.00031,  # PP→abs bleed per unit of corruption_pp
    'corr_psoe_pod':    0.00070,  # PSOE→Podemos bleed per unit of corruption_psoe
    'corr_psoe_abs':    0.00031,  # PSOE→abs bleed per unit of corruption_psoe
    'cat_spa_indy':     0.052,    # indy-space gain per unit of |d_cat_spa| (negative), in Cat
    'cat_spa_cs_cat':   0.041,    # CS gain per unit of |d_cat_spa| (negative), in Cat
    'cat_spa_pp_psoe':  0.041,    # PP gain vs PSOE per unit of |d_cat_spa| (neg), outside Cat
    'cat_spa_cs_pod':   0.031,    # CS gain vs Podemos per unit of |d_cat_spa| (neg), outside Cat
    'dom_momentum':      0.030,   # challenger momentum per unit of (1 - hold)
    'hold_decay':        0.0088,  # hold falls per tick when challenger leads
    'hold_recovery':     0.0051,  # hold rises per tick when incumbent leads
    'noise_stdev':       0.164,   # Gaussian noise stdev per family per tick
    'noise_stdev_minor': 0.008,   # noise for minor rest parties (cc/prc/te/foro)
                                   # σ/√(2r) ≈ 0.063 pp stationary stdev — keeps them
                                   # near target without random-walking to zero
    'minor_reversion_rate': 0.008, # pull toward MINOR_REST_TARGETS per tick
    # Podemos channeling — mirrors cat_engine.js dissent-channeling variable.
    # When podemos_channeling is high (peak dissent, 2014-2016), Podemos pulls
    # from PSOE.  When it decays to 0 (recovery, 2017-2019), PSOE recovers.
    # net_flow = channeling * channeling_rate - (1-channeling) * psoe_recover_rate
    # Positive → Podemos gains; negative → PSOE gains.
    'channeling_rate':   0.0024,  # Podemos←PSOE flow per tick at max channeling
    'psoe_recover_rate': 0.0027,  # PSOE←Podemos flow per tick when channeling = 0
    # Leadership recovery multipliers — set via flags by events in the timeline.
    # Mirrors the psc_recovery_mult pattern from cat_engine.js.
    # Each tick:  party += rate * mult  (pulled from abs)
    # When mult > 0 the party slowly regains ground it lost to abstention.
    'psoe_leadership_rate': 0.0123, # PSOE recovery per tick when psoe_leadership_mult > 0
    'pp_leadership_rate':   0.0155, # PP recovery per tick when pp_leadership_mult > 0
}


# ── VOTE MODEL ────────────────────────────────────────────────────────────────

class SpaVoteModel:
    """
    Stateful Spanish Congreso vote model.

    support: {constituency: {family: pct}}  — all active families sum to 100.
    All [TUNE] coefficients are exposed as constructor parameters so
    spa_calibration_runner.py can inject overrides for Nelder-Mead tuning.
    """

    def __init__(self, initial_support, econ_base=None, params=None):
        self.support   = deepcopy(initial_support)
        self.econ_base = econ_base if econ_base is not None else ECON_BASE_DEFAULT
        p = {**DEFAULTS, **(params or {})}
        for k in DEFAULTS:
            setattr(self, k, p[k])
        self.holds = {}  # dominance hold values {key: float 0-1}

    # ── internal read/write ────────────────────────────────────────────────────

    def _r(self, f, c):
        return self.support.get(c, {}).get(f, 0.0)

    def _w(self, f, c, v):
        self.support.setdefault(c, {})[f] = max(0.0, v)

    def _is_incumbent(self, family, coalition):
        for party in (coalition or []):
            p = party.lower()
            if family == 'pp'      and p in ('pp', 'ppc', 'nsuma'):              return True
            if family == 'psoe'    and p in ('psoe', 'psc'):                     return True
            if family == 'podemos' and p in ('podemos', 'up', 'unidas_podemos'): return True
            if family == 'iu'      and p in ('iu', 'unidas_podemos'):            return True
            if family == 'cs'      and p == 'cs':                                return True
            if family == 'nsuma'   and p in ('nsuma', 'pp'):                     return True
            if family == p:                                                       return True
        return False

    # ── dominance holds ───────────────────────────────────────────────────────

    def _update_holds(self, flags):
        for c in CONSTITUENCIES:
            if c == 'navarra':
                continue
            pp_sup = self._r('pp', c)

            # PP vs CS
            k = f'pp_hold_{c}'
            self.holds[k] = float(np.clip(
                self.holds.get(k, 1.0)
                + (-self.hold_decay if self._r('cs', c) > pp_sup else self.hold_recovery),
                0, 1))

            # PP vs VOX
            if flags.get('vox_active'):
                k2 = f'pp_vox_hold_{c}'
                self.holds[k2] = float(np.clip(
                    self.holds.get(k2, 1.0)
                    + (-self.hold_decay if self._r('vox', c) > pp_sup else self.hold_recovery),
                    0, 1))

            # PSOE vs Podemos
            k3 = f'psoe_hold_{c}'
            self.holds[k3] = float(np.clip(
                self.holds.get(k3, 1.0)
                + (-self.hold_decay if self._r('podemos', c) > self._r('psoe', c) else self.hold_recovery),
                0, 1))

    # ── main monthly tick ─────────────────────────────────────────────────────

    def update(self, d_gdp, d_unemp, d_welfare, d_dissent, d_cat_spa,
               corruption_pp, corruption_psoe, spanish_coalition, flags,
               podemos_channeling=0.0):
        """Apply one monthly tick. Mirrors monthPassesCongreso() from the JS.

        podemos_channeling (float 0–1): from cat_engine dissent dynamics.
          1 = peak dissent channeling → Podemos pulls from PSOE.
          0 = no channeling → PSOE slowly recovers from Podemos.
        """
        self._update_holds(flags)

        for c in CONSTITUENCIES:
            fams   = get_active_families(c, flags)
            deltas = dict.fromkeys(fams, 0.0)
            urban  = c in URBAN_CONSTITUENCIES

            # 4a. Base economic response + incumbent GDP boost
            for f in fams:
                coeff = self.econ_base.get(f)
                if not coeff:
                    continue
                d = (coeff['g'] * d_gdp  + coeff['u'] * d_unemp
                   + coeff['w'] * d_welfare + coeff['d'] * d_dissent)
                if d_gdp > 0 and self._is_incumbent(f, spanish_coalition):
                    d += self.gov_gdp_boost * d_gdp
                deltas[f] += d

            # 4b. PP corruption bleed (PP/NSuma → CS + abs)
            # In Navarra, when UPN runs as a PP rival (player-triggered), corruption
            # bleeds to UPN instead of CS — the "clean" local conservative option.
            # If both UPN and CS are active, UPN takes the larger share (70/30).
            if corruption_pp > 0:
                pp_fam = 'nsuma' if 'nsuma' in fams else ('pp' if 'pp' in fams else None)
                if pp_fam:
                    rate   = self.corr_pp_cs_urban if urban else self.corr_pp_cs_base
                    to_cs  = corruption_pp * rate
                    to_abs = corruption_pp * self.corr_pp_abs
                    deltas[pp_fam] -= to_cs + to_abs
                    upn_rival = 'upn' in fams and flags.get('spa_upn_independent', False)
                    if upn_rival and 'cs' in fams:
                        deltas['upn'] += to_cs * 0.70
                        deltas['cs']  += to_cs * 0.30
                    elif upn_rival:
                        deltas['upn'] += to_cs
                    elif 'cs' in fams:
                        deltas['cs']  += to_cs
                    if 'abs' in fams: deltas['abs'] += to_abs

            # 4c. PSOE corruption bleed (PSOE → Podemos + abs)
            if corruption_psoe > 0 and 'psoe' in fams:
                to_pod = corruption_psoe * self.corr_psoe_pod
                to_abs = corruption_psoe * self.corr_psoe_abs
                deltas['psoe'] -= to_pod + to_abs
                if 'podemos' in fams: deltas['podemos'] += to_pod
                if 'abs'     in fams: deltas['abs']     += to_abs

            # 4d. Cat-spa relations effects
            if d_cat_spa != 0:
                if c == 'catalunya' and d_cat_spa < 0:
                    # Deteriorating relations → indy-space + CS gain; PP/PSC lose
                    indy_gain  = abs(d_cat_spa) * self.cat_spa_indy
                    cs_gain    = abs(d_cat_spa) * self.cat_spa_cs_cat
                    total_gain = indy_gain + cs_gain
                    if 'erc'      in fams: deltas['erc']      += indy_gain * 0.65
                    if 'cat_conv' in fams: deltas['cat_conv'] += indy_gain * 0.35
                    if 'cs'       in fams: deltas['cs']       += cs_gain
                    if 'pp'       in fams: deltas['pp']       -= total_gain * 0.4
                    if 'psoe'     in fams: deltas['psoe']     -= total_gain * 0.6
                elif c not in ('catalunya', 'navarra') and d_cat_spa < 0:
                    # Outside Cat: national question salience → PP/CS benefit
                    mag    = abs(d_cat_spa)
                    pp_gain = mag * self.cat_spa_pp_psoe
                    cs_gain = mag * self.cat_spa_cs_pod
                    pp_fam  = 'nsuma' if 'nsuma' in fams else ('pp' if 'pp' in fams else None)
                    if pp_fam:              deltas[pp_fam]    += pp_gain
                    if 'psoe'    in fams:   deltas['psoe']    -= pp_gain
                    if 'cs'      in fams:   deltas['cs']      += cs_gain
                    if 'podemos' in fams:   deltas['podemos'] -= cs_gain

            # 4e. Dominance momentum
            ph_psoe = self.holds.get(f'psoe_hold_{c}', 1.0)
            if ph_psoe < 1.0 and 'psoe' in fams and 'podemos' in fams:
                mom = self.dom_momentum * (1 - ph_psoe)
                deltas['podemos'] += mom
                deltas['psoe']    -= mom

            ph_pp = self.holds.get(f'pp_hold_{c}', 1.0)
            if ph_pp < 1.0 and 'pp' in fams and 'cs' in fams:
                mom = self.dom_momentum * (1 - ph_pp)
                deltas['cs'] += mom
                deltas['pp'] -= mom

            if flags.get('vox_active'):
                ph_vox = self.holds.get(f'pp_vox_hold_{c}', 1.0)
                if ph_vox < 1.0 and 'pp' in fams and 'vox' in fams:
                    mom = self.dom_momentum * (1 - ph_vox)
                    deltas['vox'] += mom
                    deltas['pp']  -= mom

            # 4f. Podemos channeling — organic PSOE⇄Podemos flow driven by
            #     cat_engine dissent dynamics (mirrors the JS variable).
            if 'podemos' in fams and 'psoe' in fams:
                # net > 0 → Podemos gains; net < 0 → PSOE gains
                net = (podemos_channeling * self.channeling_rate
                       - (1.0 - podemos_channeling) * self.psoe_recover_rate)
                # cap transfer to avoid draining a party below ~1%
                if net > 0:
                    actual = min(net * self._r('psoe', c), self._r('psoe', c) - 1.0)
                else:
                    actual = max(net * self._r('podemos', c), -(self._r('podemos', c) - 1.0))
                actual = max(-5.0, min(5.0, actual))  # hard cap per tick
                deltas['podemos'] += actual
                deltas['psoe']    -= actual

            # 4g. Leadership recovery — sustained monthly pull from abs.
            #     Activated by flag-based multipliers set from timeline events.
            #     Mirrors the psc_recovery_mult mechanic in cat_engine.js.
            psoe_lm = flags.get('psoe_leadership_mult', 0.0)
            if psoe_lm > 0 and 'psoe' in fams and 'abs' in fams:
                pull = self.psoe_leadership_rate * psoe_lm
                pull = min(pull, self._r('abs', c) * 0.02)  # don't drain abs too fast
                deltas['psoe'] += pull
                deltas['abs']  -= pull

            pp_lm = flags.get('pp_leadership_mult', 0.0)
            if pp_lm > 0 and 'pp' in fams and 'abs' in fams:
                pull = self.pp_leadership_rate * pp_lm
                pull = min(pull, self._r('abs', c) * 0.02)
                deltas['pp']  += pull
                deltas['abs'] -= pull

            # 4h_minor. Mean reversion for minor rest parties toward their regional base.
            # Keeps CC/PRC/TE/FORO from drifting to zero under the large national noise.
            if c == 'rest':
                for f in MINOR_REST_PARTIES:
                    if f in fams:
                        target = MINOR_REST_TARGETS.get(f, 0.0)
                        deltas[f] += self.minor_reversion_rate * (target - self._r(f, c))

            # 4h. Gaussian noise — minor rest parties get scaled-down noise so
            # they don't random-walk to zero from their small base support.
            for f in fams:
                if c == 'rest' and f in MINOR_REST_PARTIES:
                    deltas[f] += np.random.normal(0, self.noise_stdev_minor)
                else:
                    deltas[f] += np.random.normal(0, self.noise_stdev)

            # 4i. Apply deltas
            for f in fams:
                self._w(f, c, self._r(f, c) + deltas[f])

            # 4j. Renormalize constituency to 100
            total = sum(max(0.0, self._r(f, c)) for f in fams)
            if total > 0:
                for f in fams:
                    self._w(f, c, max(0.0, self._r(f, c)) / total * 100.0)

    # ── seat counting ─────────────────────────────────────────────────────────

    def seat_counts(self, flags):
        """
        Convert support % → synthetic vote counts → D'Hondt per constituency.
        Returns {family: total_seats_across_spain}.
        """
        totals = {}
        for c in CONSTITUENCIES:
            fams      = get_active_families(c, flags)
            vote_fams = [f for f in fams if f != 'abs']
            elec      = ELECTORATE[c]
            votes     = {f: self._r(f, c) / 100.0 * elec for f in vote_fams}
            n_seats   = SEAT_DISTRIBUTION[c]

            if c == 'rest':
                # Virtual province simulation with rural/urban bias
                result = simulate_rest_constituency(votes)
            else:
                result = dhondt_method(votes, n_seats)

            for f, s in result.items():
                if s > 0:
                    totals[f] = totals.get(f, 0) + s

        return totals
