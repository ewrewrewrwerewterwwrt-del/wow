import numpy as np
import pandas as pd
from copy import deepcopy

# ══════════════════════════════════════════════════════════════════════════════
# Route to Ítaca — Economic Simulation Engine v4
# Variables: gdp_growth, unemployment, public_debt (real %), generalitat_surplus,
#            cat_spa_relations, independence_movement, independence_trust,
#            social_dissent, welfare_index
# Month 1 = August 2012 | 90 months = December 2019
#
# v4 changes vs v3:
#   - Debt is now 1:1 real % (no game-scale conversion)
#   - Full declarative event system (trigger_fn / effects_fn)
#   - FLA entry + escalation as conditional debt-threshold events
#   - Yearly Diada events (2012–2019) with per-year parameters
#   - Procés cluster: 9-N, 27-S, 1-O, 155/DUI, 21-D
#   - ECB QE event (fixed m=18, optional via kwarg)
#   - Podemos surge (conditional on dissent + year, channeling multiplier)
# ══════════════════════════════════════════════════════════════════════════════

# ── STRUCTURAL BASELINE ───────────────────────────────────────────────────────
# Pure Eurozone/Spain macro cycle with NO party effects.
# NOTE: structural baseline was computed with QE baked in for 2015+.
# When ecb_qe=False, a correction is applied in simulate() to strip that out.

IRL_GOBIERNO_BY_YEAR = {
    2012: 'PP_abs', 2013: 'PP_abs', 2014: 'PP_abs', 2015: 'PP_abs',
    2016: 'PP_care', 2017: 'PP_min', 2018: 'PP_min', 2019: 'PSOE_min'
}
IRL_GENERALITAT_BY_YEAR = {
    2012: 'CiU',  2013: 'CiU',  2014: 'CiU',
    2015: 'CDC_ERC_15', 2016: 'CDC_ERC_16', 2017: 'CDC_ERC_16',
    2018: 'ART155', 2019: 'JxCat'
}

GOB_GDP_ABS = {
    'PP_abs':    -1.5,
    'PP_care':   -0.2,
    'PP_min':    -0.4,
    'PSOE_min':  +0.3,
    'PSOE_maj':  +0.8,
    'Podemos':   +0.4,
    'PP_VOX':    -1.0,
}

GEN_GDP_ABS = {
    'CiU':         -0.8,
    'CDC_ERC_15':  -0.3,
    'CDC_ERC_16':  -0.5,
    'ART155':      -1.5,
    'JxCat':       -0.6,
    'PSC':         +0.5,
    'Comuns':      +0.4,
    'ERC':         +0.1,
    'ERC_min':     -0.1,
    'CUP':         -1.2,
    'PSC_ERC':     +0.3,
    'PSC_Comuns':  +0.6,
}

IRL_GDP_BY_YEAR = {
    2012: -3.1, 2013: -1.4, 2014: 1.5,
    2015: 3.7,  2016: 3.5,  2017: 3.4,
    2018: 2.6,  2019: 1.9
}

def structural_gdp(year):
    irl_gdp = IRL_GDP_BY_YEAR.get(year, 2.0)
    irl_gob = IRL_GOBIERNO_BY_YEAR.get(year, 'PP_min')
    irl_gen = IRL_GENERALITAT_BY_YEAR.get(year, 'JxCat')
    return irl_gdp - GOB_GDP_ABS[irl_gob] - GEN_GDP_ABS[irl_gen]

STRUCTURAL_GDP = {yr: round(structural_gdp(yr), 2) for yr in range(2012, 2020)}

# ── GOVERNMENT TIMELINES (IRL defaults) ──────────────────────────────────────
GOBIERNO_IRL_TIMELINE = [
    (1,  41, 'PP_abs'),
    (42, 50, 'PP_care'),
    (51, 70, 'PP_min'),
    (71, 90, 'PSOE_min'),
]

GENERALITAT_IRL_TIMELINE = [
    (1,  29, 'CiU'),
    (30, 41, 'CDC_ERC_15'),
    (42, 62, 'CDC_ERC_16'),
    (63, 69, 'ART155'),
    (70, 90, 'JxCat'),
]

def get_gov(month, timeline):
    for start, end, party in timeline:
        if start <= month <= end:
            return party
    return timeline[-1][2]

# ── CAT-SPAIN INTERACTION ─────────────────────────────────────────────────────
def cat_spa_gdp_adj(relations):
    delta = relations - 38.0
    return delta * 0.015

# ── INDEPENDENCE UNCERTAINTY DRAG ────────────────────────────────────────────
def indy_gdp_drag(independence_movement, independence_trust):
    vol = max(0, (independence_movement - independence_trust) / 100)
    return -vol * 1.2

# ── UNEMPLOYMENT MODEL ───────────────────────────────────────────────────────
UNEMP_PARAMS = {
    'destruct_coeff':  0.30,
    'recover_coeff':   0.55,
    'reform_bonus':    0.50,
    'natural_floor':   10.0,
}

GEN_UNEMP_MOD = {
    'CiU':         1.00,
    'CDC_ERC_15':  1.10,
    'CDC_ERC_16':  0.85,
    'ART155':      0.55,
    'JxCat':       0.90,
    'PSC':         1.35,
    'Comuns':      1.40,
    'ERC':         1.20,
    'ERC_min':     1.10,
    'CUP':         0.70,
    'PSC_ERC':     1.30,
    'PSC_Comuns':  1.40,
}

GOB_UNEMP_MOD = {
    'PP_abs':    1.00,
    'PP_care':   0.90,
    'PP_min':    0.95,
    'PSOE_min':  1.10,
    'PSOE_maj':  1.20,
    'Podemos':   1.15,
    'PP_VOX':    0.75,
}

# ── DEBT ACCOUNTING ───────────────────────────────────────────────────────────
# Debt is now 1:1 real % of Catalan GDP.
# Initial value 26.0 (IRL Aug 2012).
# delta units are percentage points of GDP per month.

def compute_debt_delta(surplus_pct, gdp_growth_monthly, current_debt):
    """
    Monthly change in debt (real % of GDP).
    Three components:
      deficit_flow : full deficit becomes debt (FLA loans are still liabilities)
      interest     : ~2% blended rate on outstanding stock (FLA ~1.5% + market ~3%)
      gdp_effect   : GDP growth reduces debt/GDP ratio; contraction raises it
    Calibrated to match IRL Catalan debt path 26%→35% (2012→2017).
    """
    deficit_flow = -(surplus_pct / 12)
    interest     = current_debt * 0.020 / 12
    gdp_effect   = -gdp_growth_monthly * 0.18
    return deficit_flow + interest + gdp_effect

# ── FLA THRESHOLDS ────────────────────────────────────────────────────────────
FLA_ENTRY_THRESHOLD      = 28.0   # % GDP — triggers FLA entry event
FLA_ESCALATION_THRESHOLD = 35.0   # % GDP — tighter conditionality

# ── SURPLUS DYNAMICS ──────────────────────────────────────────────────────────
SURPLUS_GDP_SENSITIVITY = 0.6

SURPLUS_DRIFT_BY_GEN = {
    'CiU':         +0.022,
    'CDC_ERC_15':  +0.012,
    'CDC_ERC_16':  +0.005,
    'ART155':      +0.028,
    'JxCat':       +0.008,
    'PSC':         -0.008,
    'Comuns':      -0.018,
    'ERC':         +0.010,
    'ERC_min':     +0.008,
    'CUP':         -0.020,
    'PSC_ERC':     -0.010,
    'PSC_Comuns':  -0.015,
}

# Applied on top of base drift when fla_active flag is set
SURPLUS_FLA_BONUS_BY_GOB = {
    'PP_abs':    +0.012,
    'PP_care':   +0.005,
    'PP_min':    +0.008,
    'PSOE_min':  +0.002,
    'PSOE_maj':  -0.002,
    'Podemos':   -0.004,
    'PP_VOX':    +0.010,
}

# Additional tightening under escalation conditionality
SURPLUS_FLA_ESCALATION_BONUS = 0.006   # pp/month extra on top of entry bonus

# ── WELFARE INDEX ─────────────────────────────────────────────────────────────
WELFARE_SPENDING_BY_GEN = {
    'CiU':         -0.55,
    'CDC_ERC_15':  -0.15,
    'CDC_ERC_16':  -0.20,
    'ART155':      -0.60,
    'JxCat':       -0.10,
    'PSC':         +0.40,
    'Comuns':      +0.55,
    'ERC':         +0.25,
    'ERC_min':     +0.15,
    'CUP':         +0.35,
    'PSC_ERC':     +0.35,
    'PSC_Comuns':  +0.50,
}
WELFARE_GDP_SENSITIVITY  = 0.10
WELFARE_RECOVERY_CAP     = 0.80
WELFARE_CUT_CAP          = 1.20

# ── SOCIAL DISSENT — MEAN-REVERTING EQUILIBRIUM ───────────────────────────────
DISSENT_REVERSION_SPEED = 0.04

def dissent_equilibrium(unemployment, welfare_index, gob, gen,
                        podemos_channeling=0.0):
    """
    Natural equilibrium for social dissent.
    podemos_channeling: 0.0 = no effect, 1.0 = full channeling active.
    When active, reduces the ceiling by up to 12 points — energy is being
    expressed electorally rather than on the streets.
    """
    if unemployment > 20:
        unemp_contrib = 30 + (unemployment - 20) * 2.5
    else:
        unemp_contrib = max(0, (unemployment - 10) * 3.0)

    welfare_contrib = (100 - welfare_index) * 0.35

    gob_mod = {
        'PP_abs':    +12, 'PP_care':  +4, 'PP_min':   +6,
        'PSOE_min':  -5,  'PSOE_maj': -10,'Podemos':  -8,
        'PP_VOX':    +15,
    }.get(gob, 0)

    gen_mod = {
        'CiU':         +4,  'CDC_ERC_15': +2, 'CDC_ERC_16': +1,
        'ART155':      +8,  'JxCat':      +2,
        'PSC':         -6,  'Comuns':     -8, 'ERC':        -3,
        'ERC_min':     -2,  'CUP':        -4,
        'PSC_ERC':     -5,  'PSC_Comuns': -7,
    }.get(gen, 0)

    # Podemos channeling: full effect = -12 on equilibrium ceiling
    channeling_discount = podemos_channeling * 12.0

    eq = unemp_contrib + welfare_contrib + gob_mod + gen_mod - channeling_discount
    return np.clip(eq, 15, 92)

# ── INDEPENDENCE MOVEMENT — SEASONAL + RESTING LEVEL ─────────────────────────
INDY_RESTING_LEVEL   = 52.0
INDY_REVERSION_SPEED = 0.035

# Seasonal amplitude by year — grows to 2014 peak, plateaus.
# NOTE: Diada events (see EVENTS below) add on top of this sinusoid.
# The sinusoid provides background seasonal texture; Diadas provide the spike.
INDY_SEASONAL_AMPLITUDE = {
    2012: 2.0, 2013: 3.0, 2014: 3.5,
    2015: 3.0, 2016: 2.5, 2017: 3.5,
    2018: 1.5, 2019: 2.0,
}

def indy_seasonal_pulse(cal_month, year):
    """Background sinusoidal seasonal — Diada spike is separate (event system)."""
    amplitude = INDY_SEASONAL_AMPLITUDE.get(year, 2.5)
    phase      = (cal_month - 1) * (2 * np.pi / 12)
    peak_phase = (9 - 1) * (2 * np.pi / 12)
    return amplitude * np.cos(phase - peak_phase)

# ── CAT-SPA RELATIONS — PARTY-PAIR MATRIX ────────────────────────────────────
CAT_SPA_DRIFT = {
    ('PP_abs',   'CiU'):         -0.10,
    ('PP_abs',   'CDC_ERC_15'):  -0.30,
    ('PP_abs',   'CDC_ERC_16'):  -0.50,
    ('PP_abs',   'ART155'):       0.00,
    ('PP_abs',   'JxCat'):       -0.25,
    ('PP_abs',   'PSC'):         +0.05,
    ('PP_abs',   'Comuns'):      -0.10,
    ('PP_abs',   'ERC'):         -0.25,
    ('PP_abs',   'ERC_min'):     -0.15,
    ('PP_abs',   'CUP'):         -0.60,

    ('PP_care',  'CiU'):         -0.08,
    ('PP_care',  'CDC_ERC_15'):  -0.22,
    ('PP_care',  'CDC_ERC_16'):  -0.38,
    ('PP_care',  'JxCat'):       -0.18,
    ('PP_care',  'PSC'):         +0.05,
    ('PP_care',  'ERC'):         -0.20,

    ('PP_min',   'CiU'):         -0.08,
    ('PP_min',   'CDC_ERC_15'):  -0.25,
    ('PP_min',   'CDC_ERC_16'):  -0.45,
    ('PP_min',   'ART155'):       0.00,
    ('PP_min',   'JxCat'):       -0.20,
    ('PP_min',   'PSC'):         +0.05,
    ('PP_min',   'ERC'):         -0.22,

    ('PSOE_min', 'CiU'):         +0.12,
    ('PSOE_min', 'CDC_ERC_15'):  +0.05,
    ('PSOE_min', 'CDC_ERC_16'):  +0.08,
    ('PSOE_min', 'ART155'):       0.00,
    ('PSOE_min', 'JxCat'):       +0.18,
    ('PSOE_min', 'PSC'):         +0.35,
    ('PSOE_min', 'Comuns'):      +0.28,
    ('PSOE_min', 'ERC'):         +0.22,
    ('PSOE_min', 'ERC_min'):     +0.20,
    ('PSOE_min', 'CUP'):         -0.05,

    ('PSOE_maj', 'PSC'):         +0.50,
    ('PSOE_maj', 'Comuns'):      +0.40,
    ('PSOE_maj', 'ERC'):         +0.30,
    ('PSOE_maj', 'PSC_ERC'):     +0.45,
    ('PSOE_maj', 'PSC_Comuns'):  +0.55,
    ('PSOE_maj', 'JxCat'):       +0.20,
    ('PSOE_maj', 'CDC_ERC_16'):  +0.10,
    ('PSOE_maj', 'CUP'):         -0.08,

    ('Podemos',  'CUP'):         +0.00,
    ('Podemos',  'ERC'):         +0.25,
    ('Podemos',  'Comuns'):      +0.45,
    ('Podemos',  'PSC'):         +0.35,
    ('Podemos',  'JxCat'):       +0.05,
    ('Podemos',  'CDC_ERC_16'):  +0.00,

    ('PP_VOX',   'CiU'):         -0.20,
    ('PP_VOX',   'PSC'):         -0.05,
    ('PP_VOX',   'JxCat'):       -0.55,
    ('PP_VOX',   'ERC'):         -0.50,
    ('PP_VOX',   'CUP'):         -0.80,
    ('PP_VOX',   'Comuns'):      -0.35,
}

CAT_SPA_ART155_DRIFT       = -2.0
CAT_SPA_POST155_FLOOR      = 18.0
CAT_SPA_POST155_RECOVERY_CAP = 0.08

def get_cat_spa_drift(gob, gen):
    key = (gob, gen)
    if key in CAT_SPA_DRIFT:
        return CAT_SPA_DRIFT[key]
    if gob in ('PP_abs', 'PP_min', 'PP_care', 'PP_VOX'):
        return -0.15
    elif gob in ('PSOE_min', 'PSOE_maj'):
        return +0.10
    elif gob == 'Podemos':
        return +0.15
    return -0.05


# ══════════════════════════════════════════════════════════════════════════════
# EVENT SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
#
# Each event is a dict:
#   id          : str — unique identifier
#   label       : str — human-readable name (for logging)
#   one_time    : bool — if True, fires at most once across the simulation
#   trigger_fn  : callable(month, year, cal_month, Q, flags) -> bool
#                   Q    = current state dict
#                   flags = mutable dict of named flags set by prior events
#   effects     : dict of immediate state deltas applied to Q when triggered
#                   keys match Q keys; values are additive adjustments
#   flag_set    : str | None — if set, writes True to flags[flag_set] when fired
#   pulse       : dict | None — if set, applies a fading pulse over N months:
#                   {'variable': str, 'monthly_delta': float, 'duration': int}
#                   The pulse is stored in a separate pulse queue in simulate().
#   notes       : str — design rationale
#
# Events are evaluated in list order each month. One-time events are skipped
# after firing. All matching events in a given month fire (no exclusivity).
# ══════════════════════════════════════════════════════════════════════════════

EVENTS = [

    # ── FLA ENTRY (alternate-history only) ───────────────────────────────────
    # In the IRL baseline, FLA was already active before sim start (July 2012).
    # flags['fla_active'] is therefore initialised to True.
    # This event only fires in alt-history scenarios where the Generalitat
    # managed to keep debt below 28% — meaning FLA was avoided entirely.
    # If debt was already below threshold when sim starts AND later crosses it,
    # this event fires. For IRL it is effectively dormant.
    {
        'id':        'fla_entry',
        'label':     'FLA Entry — Fons de Liquiditat Autonòmica activated',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (
            Q['public_debt'] >= FLA_ENTRY_THRESHOLD
            and not flags.get('fla_active', False)
        ),
        'effects': {
            'cat_spa_relations':    -2.0,
            'social_dissent':       +3.0,
            'welfare_index':        -2.0,
        },
        'flag_set': 'fla_active',
        'pulse':    None,
        'notes':    'FLA historically activated July 2012 (before sim start). '
                    'This event fires only in alt-history where debt was kept below threshold.',
    },

    # ── FLA ESCALATION ────────────────────────────────────────────────────────
    # Fires when debt crosses 35% GDP — tighter conditionality.
    # IRL this roughly coincides with 2015–2016 when Madrid demanded structural
    # reform compliance, not just deficit targets.
    {
        'id':        'fla_escalation',
        'label':     'FLA Escalation — conditionality tightens at 35% debt',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (
            Q['public_debt'] >= FLA_ESCALATION_THRESHOLD
            and flags.get('fla_active', False)
            and not flags.get('fla_escalated', False)
        ),
        'effects': {
            'cat_spa_relations':    -1.5,
            'social_dissent':       +2.0,
            'welfare_index':        -1.5,
            'generalitat_surplus':  +0.3,   # forced one-off consolidation measure
        },
        'flag_set': 'fla_escalated',
        'pulse':    None,
        'notes':    'Escalation point: Madrid demands structural reforms as condition '
                    'of continued FLA access. Catalan government loses remaining fiscal margin.',
    },

    # ── DIADA 2012 (Sept 11, month 2) ────────────────────────────────────────
    # First mass Diada. ~1.5M on the streets. "Catalunya, nou estat d'Europa."
    # Artur Mas calls snap elections within weeks.
    # Strong independence spike; dissent partially channels into indy energy.
    {
        'id':        'diada_2012',
        'label':     'Diada 2012 — 1.5M march, "Catalunya, nou estat d\'Europa"',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2012 and cm == 9),
        'effects': {
            'independence_movement': +9.0,
            'independence_trust':    +2.0,
            'social_dissent':        -3.0,   # dissent channels into indy energy
            'cat_spa_relations':     -2.5,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Historically the watershed moment. Mas calls elections '
                    '(Sept 25 2012) within 2 weeks of the march.',
    },

    # ── DIADA 2013 (month 14) ─────────────────────────────────────────────────
    # Via Catalana — 400km human chain across Catalonia. ~400k participants.
    # More symbolic than 2012; IRL momentum was actually slightly lower.
    {
        'id':        'diada_2013',
        'label':     'Diada 2013 — Via Catalana human chain',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2013 and cm == 9),
        'effects': {
            'independence_movement': +6.0,
            'independence_trust':    +1.5,
            'social_dissent':        -1.5,
            'cat_spa_relations':     -1.5,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Symbolic but large. Less electoral energy than 2012; '
                    'movement consolidating rather than surging.',
    },

    # ── DIADA 2014 (month 26) ─────────────────────────────────────────────────
    # "V" formation. ~1.8M. Peak pre-9N energy — strongest raw attendance IRL.
    # Just 2 months before the 9-N consulta.
    {
        'id':        'diada_2014',
        'label':     'Diada 2014 — "V" formation, 1.8M, peak pre-9N energy',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2014 and cm == 9),
        'effects': {
            'independence_movement': +11.0,
            'independence_trust':    +2.5,
            'social_dissent':        -2.0,
            'cat_spa_relations':     -3.0,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Highest attendance of the decade. ANC/Omnium at peak '
                    'organisational capacity. 9-N is 2 months away.',
    },

    # ── DIADA 2015 (month 38) ─────────────────────────────────────────────────
    # "Via Fora". Electoral focus — 27-S plebiscitary elections in 2 weeks.
    # Energy is in ballots not streets; moderate street attendance.
    {
        'id':        'diada_2015',
        'label':     'Diada 2015 — "Via Fora", overshadowed by 27-S elections',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2015 and cm == 9),
        'effects': {
            'independence_movement': +5.0,
            'independence_trust':    +1.0,
            'social_dissent':        -1.0,
            'cat_spa_relations':     -1.5,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    '27-S elections are 2 weeks away. Movement energy is '
                    'channelled electorally; street numbers lower than 2014.',
    },

    # ── DIADA 2016 (month 50) ─────────────────────────────────────────────────
    # Post-27S disillusionment. No budget. CUP blocking. Smaller attendance.
    # Movement is institutionally paralysed; this Diada reflects that.
    {
        'id':        'diada_2016',
        'label':     'Diada 2016 — post-27S disillusionment, smaller crowds',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2016 and cm == 9),
        'effects': {
            'independence_movement': +3.0,
            'independence_trust':    +0.5,
            'social_dissent':        -0.5,
            'cat_spa_relations':     -1.0,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'CUP-CDC standoff, no budget. Movement visibly frustrated '
                    'with institutional gridlock.',
    },

    # ── DIADA 2017 (month 62) ─────────────────────────────────────────────────
    # Exceptional year — referendum is 20 days away. Record energy.
    # Also accelerates cat_spa deterioration toward the 1-O cliff.
    {
        'id':        'diada_2017',
        'label':     'Diada 2017 — 1-O is 20 days away, maximum energy',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2017 and cm == 9),
        'effects': {
            'independence_movement': +12.0,
            'independence_trust':    +3.0,
            'social_dissent':        -2.5,
            'cat_spa_relations':     -4.0,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Largest Diada since 2014 in political charge. '
                    'Referendum mobilisation fully active.',
    },

    # ── DIADA 2018 (month 74) ─────────────────────────────────────────────────
    # Post-155 deflation. JxCat in office, leaders in exile or prison.
    # Attendance down significantly; emotional but directionless.
    {
        'id':        'diada_2018',
        'label':     'Diada 2018 — post-155 deflation, leaders jailed or in exile',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2018 and cm == 9),
        'effects': {
            'independence_movement': -2.0,   # net negative — deflation exceeds mobilisation
            'independence_trust':    -1.0,
            'social_dissent':        +2.0,   # grief and anger, not hope
            'cat_spa_relations':     -0.5,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Movement is in shock. Puigdemont in Brussels, Junqueras '
                    'in Soto del Real. Attendance drops sharply.',
    },

    # ── DIADA 2019 (month 86) ─────────────────────────────────────────────────
    # Mixed recovery. Trial verdict expected soon (sentenced Oct 14).
    # Energy rebuilding but not at pre-155 levels.
    {
        'id':        'diada_2019',
        'label':     'Diada 2019 — moderate recovery, trial verdict approaching',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2019 and cm == 9),
        'effects': {
            'independence_movement': +5.0,
            'independence_trust':    +1.0,
            'social_dissent':        +1.0,   # anger at impending verdict
            'cat_spa_relations':     -1.5,
        },
        'flag_set': None,
        'pulse':    None,
        'notes':    'Movement rebuilding. Trial of Junqueras et al. looming; '
                    'verdict (and Tsunami Democràtic response) expected October.',
    },

    # ── 9-N 2014 CONSULTA (November, month 28) ───────────────────────────────
    # Nov 9 2014. ~2.3M participate in the non-binding consulta.
    # PP immediately challenges at Constitutional Court.
    # Big trust boost — movement proves it can organise.
    {
        'id':        '9n_2014',
        'label':     '9-N Consulta — 2.3M vote, PP challenges at Const. Court',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2014 and cm == 11),
        'effects': {
            'independence_movement': +6.0,
            'independence_trust':    +5.0,   # proves organisational capacity
            'cat_spa_relations':     -5.0,   # PP legal challenge, Mas charged
            'social_dissent':        -2.0,
        },
        'flag_set': '9n_fired',
        'pulse':    None,
        'notes':    'Mas and organisers later charged with disobedience. '
                    'Sets template for 2017 referendum.',
    },

    # ── 27-S 2015 PLEBISCITARY ELECTIONS (September, month 38) ───────────────
    # Junts pel Sí + CUP win majority of seats (but not votes).
    # Framed as plebiscite on independence — partial mandate claim.
    # Indy trust boost (institutions functional) but also exposes divisions.
    {
        'id':        '27s_2015',
        'label':     '27-S Elections — Junts pel Sí wins, plebiscite claimed',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2015 and cm == 9),
        'effects': {
            'independence_movement': +4.0,
            'independence_trust':    +4.0,
            'cat_spa_relations':     -4.0,
            'social_dissent':        -3.0,   # electoral result channels dissent
        },
        'flag_set': '27s_fired',
        'pulse':    None,
        'notes':    '72 seats for Junts pel Sí + CUP = majority. '
                    'But 47.8% of votes = majority disputed by unionists.',
    },

    # ── CUP VETOES MAS (January 2016, month 42) ──────────────────────────────
    # After 3 months of gridlock, CUP assembly ties 1515-1515 (!) and then 
    # decides to veto Artur Mas as president. CDC (icr) voters are furious.
    # Puigdemont eventually becomes president as a compromise.
    {
        'id':        'cup_veto_mas',
        'label':     'CUP vetoes Artur Mas — "塵 to the dustbin of history"',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2016 and cm == 1),
        'effects': {
            'independence_trust':    -5.0,   # paralysis damage
            'cat_spa_relations':     +1.0,   # Madrid sees pro-indy division as weakness
            'social_dissent':        +2.0,   # base frustration
        },
        'flag_set': 'cup_veto_fired',
        'pulse':    None,
        'notes':    'January 2016. CUP assembly blocks Mas. '
                    'Puigdemont investiture Jan 10. '
                    'Huge fallout for CUP among moderate-indy voters.',
    },

    # ── 1-O REFERENDUM (October 2017, month 63) ───────────────────────────────
    # Oct 1 2017. Police violence on polling stations.
    # ~2.3M vote (43% turnout under repression).
    # Largest single cat_spa crash outside ART155; massive dissent spike.
    {
        'id':        '1o_referendum',
        'label':     '1-O Referendum — police violence, 2.3M vote',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2017 and cm == 10),
        'effects': {
            'independence_movement': +14.0,
            'independence_trust':    +6.0,
            'cat_spa_relations':     -12.0,   # biggest single crash
            'social_dissent':        +8.0,    # police violence radicalises moderates
            'welfare_index':         -3.0,    # general strike, economic disruption
        },
        'flag_set': '1o_fired',
        'pulse':    None,
        'notes':    'Spanish national police and Guardia Civil deployed. '
                    '900+ injured. International media coverage. '
                    'Triggers general strike Oct 3.',
    },

    # ── DUI + ART155 CLUSTER (Oct 27 2017, month 63) ─────────────────────────
    # Declaration of Independence + Article 155 applied same day.
    # ART155 was already baked into the Generalitat timeline (gen='ART155'),
    # so this event handles the shock effects not covered by the party modifiers.
    # DUI is declared but not enforced — creates a surreal suspended state.
    {
        'id':        'dui_155_cluster',
        'label':     'DUI declared + Art.155 applied — Oct 27 2017',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2017 and cm == 11),
        'effects': {
            'independence_movement': +5.0,    # DUI spike — quickly reverses
            'independence_trust':    -8.0,    # institutions suspended = trust crash
            'cat_spa_relations':     -8.0,    # on top of ART155 monthly drift
            'social_dissent':        +5.0,
            'welfare_index':         -4.0,    # spending freeze, civil servants uncertainty
            'gdp_growth':            -1.2,    # business confidence shock
        },
        'flag_set': '155_fired',
        'pulse': {
            'variable': 'independence_movement',
            'monthly_delta': -2.5,            # DUI spike fades quickly; movement deflates
            'duration': 4,
        },
        'notes':    'DUI is declared in the Parlament but Puigdemont does not '
                    'activate it. Surreal suspended independence. '
                    'Massive capital flight begins (banks relocate to Madrid).',
    },

    # ── 21-D 2017 ELECTIONS (December 2017, month 65) ────────────────────────
    # Elections called by Madrid under Art.155.
    # Ciudadanos becomes largest party; pro-indy parties retain majority.
    # Partial institutional recovery: Generalitat elections held = legitimacy.
    {
        'id':        '21d_elections',
        'label':     '21-D Elections — pro-indy majority retained under Art.155',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2017 and cm == 12),
        'effects': {
            'independence_movement': +3.0,
            'independence_trust':    +4.0,    # movement proves electoral resilience
            'cat_spa_relations':     +2.0,    # elections held = minimal normalisation
            'social_dissent':        -3.0,    # electoral result channels energy
        },
        'flag_set': '21d_fired',
        'pulse':    None,
        'notes':    'Cs wins seats (37) but pro-indy bloc (JxCat+ERC+CUP) retains '
                    'majority. Carles Puigdemont claims right to be president from Brussels.',
    },

    # ── ECB QE (January 2015, month 18) ──────────────────────────────────────
    # Draghi announces €60bn/month asset purchases.
    # Structural baseline already encodes the IRL recovery partly, but QE
    # provided an additional direct GDP boost via bond spread compression
    # and business confidence. Applied as a 6-month fading pulse.
    # Controlled by ecb_qe flag passed into simulate().
    {
        'id':        'ecb_qe',
        'label':     'ECB QE — Draghi announces €60bn/month asset purchases',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (
            m == 42 and flags.get('ecb_qe_enabled', True)   # m=42 = January 2015
        ),
        'effects': {
            'generalitat_surplus':  +0.15,   # lower borrowing costs
            'cat_spa_relations':    +1.0,    # Spain's recovery stabilises Madrid
        },
        'flag_set': 'ecb_qe_fired',
        'pulse': {
            'variable': 'gdp_growth',
            'monthly_delta': +0.07,          # ~+0.4pp annual over 6 months
            'duration': 6,
        },
        'notes':    'QE compressed Spanish 10yr spread by ~100bp in 2015. '
                    'Direct GDP effect ~0.3–0.5pp for Spain via investment channel.',
    },

    # ── PODEMOS SURGE ─────────────────────────────────────────────────────────
    # Fires when dissent is high enough and the year allows Podemos to emerge.
    # Condition: dissent > 68, year >= 2014, not yet fired.
    # Effect: sets podemos_channeling flag to 1.0 (full effect).
    # The channeling multiplier then decays if dissent stops falling (see simulate()).
    # Includes a small indy_movement dent — Podemos drew left-indy votes.
    {
        'id':        'podemos_surge',
        'label':     'Podemos surge — street energy routes to electoral channel',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (
            yr >= 2014
            and Q['social_dissent'] > 68
            and not flags.get('podemos_surged', False)
        ),
        'effects': {
            'independence_movement': -4.0,   # draws left-indy voters; plurinational appeal
            'social_dissent':        -4.0,   # immediate channeling effect
        },
        'flag_set': 'podemos_surged',
        'pulse':    None,
        'notes':    'Podemos founded Jan 2014, European elections May 2014 (8%). '
                    'Surge to ~25% in polls by late 2014. '
                    'Explicitly plurinational — competes with pro-indy left in Catalonia.',
    },

    # ── JXSI FORMATION (month 30, Jan 2015) ──────────────────────────────────
    {
        'id':        'jxsi_formation',
        'label':     'Junts pel Sí formation — CDC and ERC unite',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2015 and cm == 1),
        'effects': {
            'independence_trust':    +2.0,
            'cat_spa_relations':     -1.0,
        },
        'flag_set': 'jxsi_formed',
        'pulse':    None,
        'notes':    'Electoral coalition formed for 27-S. structural shift in vote model.',
    },

    # ── JXSI DISSOLUTION (month 65, Dec 2017) ────────────────────────────────
    {
        'id':        'jxsi_dissolution',
        'label':     'Junts pel Sí dissolution — separate lists for 21-D',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2017 and cm == 12),
        'effects': {
            'independence_trust':    -1.5,
        },
        'flag_set': 'jxsi_dissolved',
        'pulse':    None,
        'notes':    'Coalition ends after the 2017 election cycle.',
    },

    # ── PERE NAVARRO OUSTER (June 2014, month 23) ─────────────────────────────
    # Navarro resigns after poor European results (where PSC was overtaken by ERC).
    # Iceta takes over, stabilises the party, and starts the "Third Way" pitch.
    {
        'id':        'pere_navarro_ouster',
        'label':     'Pere Navarro ousted — Iceta takes over PSC',
        'one_time':  True,
        'trigger_fn': lambda m, yr, cm, Q, flags: (yr == 2014 and cm == 6),
        'effects': {
            'cat_spa_relations':    +1.5,   # Iceta more dialogue-prone than Navarro
            'social_dissent':       -1.0,   # slight calming of unionist left
        },
        'flag_set': 'psc_recovery_active',
        'pulse':    None,
        'notes':    'June 2014. Navarro resigns. Iceta begins the slow recovery '
                    'of PSC from its 2012–2014 nadir.',
    },

]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def simulate(
    n_months=90,
    gob_timeline=None,
    gen_timeline=None,
    ecb_qe=True,
    seed=42,
):
    """
    Simulate Catalan economic and socio-political variables month by month.

    Parameters
    ----------
    n_months : int
        Number of months to simulate (90 = Aug 2012 → Dec 2019)
    gob_timeline : list of (start_month, end_month, party_key) | None
        Custom Gobierno timeline. None = IRL default.
    gen_timeline : list of (start_month, end_month, party_key) | None
        Custom Generalitat timeline. None = IRL default.
    ecb_qe : bool
        Whether ECB QE fires at month 18 (default True).
        Set False for scenarios where the Eurozone does not pursue QE.
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    pd.DataFrame with monthly variables + event_log list
    """
    np.random.seed(seed)

    gob_tl = gob_timeline or GOBIERNO_IRL_TIMELINE
    gen_tl = gen_timeline or GENERALITAT_IRL_TIMELINE

    # ── Initial state (Aug 2012) ─────────────────────────────────────────────
    Q = {
        'gdp_growth':            -3.1,
        'unemployment':           22.5,
        'public_debt':            26.0,   # real % of GDP, 1:1
        'generalitat_surplus':    -2.3,
        'cat_spa_relations':      38.0,
        'independence_movement':  65.0,
        'independence_trust':     28.0,
        'social_dissent':         72.0,
        'welfare_index':          72.0,
    }

    # ── Flags — mutable state set by events ─────────────────────────────────
    flags = {
        'ecb_qe_enabled':     ecb_qe,
        'fla_active':         True,    # FLA already active at sim start (Jul 2012, pre-game)
        'fla_escalated':      False,
        'art155_ever':        False,
        'podemos_surged':     False,
        'podemos_channeling': 0.0,     # 0.0 → 1.0, then decays based on dissent trajectory
    }

    # ── Event state: track which one-time events have fired ──────────────────
    event_fired = {ev['id']: False for ev in EVENTS}

    # ── Pulse queue: list of active fading pulses ────────────────────────────
    # Each pulse: {'variable': str, 'monthly_delta': float, 'remaining': int}
    pulse_queue = []

    # ── Dissent tracking for Podemos channeling decay ─────────────────────────
    dissent_prev = Q['social_dissent']

    history    = []
    event_log  = []   # records (month, event_id, label, effects applied)

    for m in range(1, n_months + 1):
        year      = 2012 + (m - 1) // 12
        cal_month = ((m - 1 + 7) % 12) + 1
        gob       = get_gov(m, gob_tl)
        gen       = get_gov(m, gen_tl)

        if gen == 'ART155':
            flags['art155_ever'] = True

        # ── Apply active pulses ──────────────────────────────────────────────
        still_active = []
        for pulse in pulse_queue:
            Q[pulse['variable']] += pulse['monthly_delta']
            pulse['remaining'] -= 1
            if pulse['remaining'] > 0:
                still_active.append(pulse)
        pulse_queue = still_active

        # ── Evaluate and fire events ─────────────────────────────────────────
        for ev in EVENTS:
            eid = ev['id']
            if ev['one_time'] and event_fired[eid]:
                continue
            if ev['trigger_fn'](m, year, cal_month, Q, flags):
                # Apply immediate effects
                for var, delta in ev['effects'].items():
                    if var in Q:
                        Q[var] += delta
                # Set flag if specified
                if ev['flag_set']:
                    flags[ev['flag_set']] = True
                # Queue pulse if specified
                if ev['pulse']:
                    p = ev['pulse']
                    pulse_queue.append({
                        'variable':      p['variable'],
                        'monthly_delta': p['monthly_delta'],
                        'remaining':     p['duration'],
                    })
                # Special post-fire logic
                if eid == 'podemos_surge':
                    flags['podemos_channeling'] = 1.0
                if ev['one_time']:
                    event_fired[eid] = True
                event_log.append({
                    'month': m, 'year': year, 'cal_month': cal_month,
                    'event_id': eid, 'label': ev['label'],
                    'effects': dict(ev['effects']),
                })

        # ── Podemos channeling decay/sustain ─────────────────────────────────
        # If dissent is falling, channeling sustains (people feel represented).
        # If dissent is flat or rising, channeling decays at 3%/month.
        if flags['podemos_surged']:
            dissent_falling = Q['social_dissent'] < dissent_prev - 0.5
            if dissent_falling:
                flags['podemos_channeling'] = min(1.0, flags['podemos_channeling'] + 0.01)
            else:
                flags['podemos_channeling'] = max(0.0, flags['podemos_channeling'] - 0.03)
        dissent_prev = Q['social_dissent']

        # ── Clip all state variables after event application ─────────────────
        Q['independence_movement'] = np.clip(Q['independence_movement'], 25, 95)
        Q['independence_trust']    = np.clip(Q['independence_trust'],    15, 60)
        Q['social_dissent']        = np.clip(Q['social_dissent'],         0, 100)
        Q['cat_spa_relations']     = np.clip(Q['cat_spa_relations'],       5, 80)
        Q['welfare_index']         = np.clip(Q['welfare_index'],          20, 100)
        Q['gdp_growth']            = np.clip(Q['gdp_growth'],             -9, 7)

        # ── GDP target ───────────────────────────────────────────────────────
        struc     = STRUCTURAL_GDP.get(year, 2.0)
        gob_mod   = GOB_GDP_ABS.get(gob, 0.0)
        gen_mod   = GEN_GDP_ABS.get(gen, 0.0)
        spa_adj   = cat_spa_gdp_adj(Q['cat_spa_relations'])
        i_drag    = indy_gdp_drag(Q['independence_movement'], Q['independence_trust'])

        # Strip QE contribution from structural if ecb_qe=False
        # (structural baseline has ~+0.4pp baked in for 2015+)
        qe_strip = 0.0
        if not ecb_qe and year >= 2015:
            qe_strip = -0.4

        gdp_target = struc + gob_mod + gen_mod + spa_adj + i_drag + qe_strip

        ar = 0.60 if gen == 'ART155' else 0.72
        Q['gdp_growth'] = (ar * Q['gdp_growth']
                           + (1 - ar) * gdp_target
                           + np.random.normal(0, 0.28))
        Q['gdp_growth'] = np.clip(Q['gdp_growth'], -9, 7)

        # ── Unemployment ─────────────────────────────────────────────────────
        gdp_m = Q['gdp_growth'] / 12

        labor_reform_mult = 1 + UNEMP_PARAMS['reform_bonus']
        recover = (UNEMP_PARAMS['recover_coeff']
                   * labor_reform_mult
                   * GEN_UNEMP_MOD.get(gen, 1.0)
                   * GOB_UNEMP_MOD.get(gob, 1.0))

        u_delta = -gdp_m * UNEMP_PARAMS['destruct_coeff'] if gdp_m < 0 else -gdp_m * recover
        Q['unemployment'] = np.clip(
            Q['unemployment'] + u_delta,
            UNEMP_PARAMS['natural_floor'], 36
        )

        # ── Surplus ──────────────────────────────────────────────────────────
        fla_bonus = 0.0
        if flags['fla_active']:
            fla_bonus += SURPLUS_FLA_BONUS_BY_GOB.get(gob, 0.0)
        if flags['fla_escalated']:
            fla_bonus += SURPLUS_FLA_ESCALATION_BONUS

        base_drift         = SURPLUS_DRIFT_BY_GEN.get(gen, +0.020)
        gdp_surplus_effect = (Q['gdp_growth'] / 100) * SURPLUS_GDP_SENSITIVITY / 12

        Q['generalitat_surplus'] = np.clip(
            Q['generalitat_surplus'] + base_drift + fla_bonus + gdp_surplus_effect
            + np.random.normal(0, 0.10),
            -5, 2
        )

        # ── Public debt ───────────────────────────────────────────────────────
        Q['public_debt'] = np.clip(
            Q['public_debt'] + compute_debt_delta(Q['generalitat_surplus'], gdp_m, Q['public_debt']),
            0, 80
        )

        # ── Welfare index ─────────────────────────────────────────────────────
        spending_pressure = WELFARE_SPENDING_BY_GEN.get(gen, 0.0)
        gdp_welfare_boost  = (Q['gdp_growth'] / 12) * WELFARE_GDP_SENSITIVITY
        raw_delta = spending_pressure + gdp_welfare_boost + np.random.normal(0, 0.20)
        welfare_delta = min(raw_delta, WELFARE_RECOVERY_CAP) if raw_delta > 0 else max(raw_delta, -WELFARE_CUT_CAP)
        Q['welfare_index'] = np.clip(Q['welfare_index'] + welfare_delta, 20, 100)

        # ── Cat-Spain relations ───────────────────────────────────────────────
        if gen == 'ART155':
            cat_spa_drift = CAT_SPA_ART155_DRIFT
        else:
            cat_spa_drift = get_cat_spa_drift(gob, gen)

        if flags['art155_ever'] and gen != 'ART155':
            if Q['cat_spa_relations'] < CAT_SPA_POST155_FLOOR and cat_spa_drift > 0:
                cat_spa_drift = min(cat_spa_drift, CAT_SPA_POST155_RECOVERY_CAP)

        Q['cat_spa_relations'] = np.clip(
            Q['cat_spa_relations'] + cat_spa_drift + np.random.normal(0, 0.6),
            5, 80
        )

        # ── Independence movement ─────────────────────────────────────────────
        seasonal    = indy_seasonal_pulse(cal_month, year)
        gap_to_rest = INDY_RESTING_LEVEL - Q['independence_movement']
        reversion   = INDY_REVERSION_SPEED * gap_to_rest

        Q['independence_movement'] = np.clip(
            Q['independence_movement'] + reversion + seasonal + np.random.normal(0, 0.7),
            25, 95
        )

        trust_drift = -1.8 if gen == 'ART155' else +0.06
        Q['independence_trust'] = np.clip(
            Q['independence_trust'] + trust_drift + np.random.normal(0, 0.4),
            15, 60
        )

        # ── Social dissent ────────────────────────────────────────────────────
        eq  = dissent_equilibrium(
            Q['unemployment'], Q['welfare_index'], gob, gen,
            podemos_channeling=flags['podemos_channeling']
        )
        gap = eq - Q['social_dissent']
        Q['social_dissent'] = np.clip(
            Q['social_dissent'] + DISSENT_REVERSION_SPEED * gap + np.random.normal(0, 0.8),
            0, 100
        )

        history.append({
            'month':                 m,
            'year':                  year,
            'cal_month':             cal_month,
            'gobierno':              gob,
            'generalitat':           gen,
            'gdp_growth':            round(Q['gdp_growth'], 3),
            'gdp_target':            round(gdp_target, 3),
            'unemployment':          round(Q['unemployment'], 3),
            'public_debt':           round(Q['public_debt'], 2),
            'generalitat_surplus':   round(Q['generalitat_surplus'], 3),
            'cat_spa_relations':     round(Q['cat_spa_relations'], 2),
            'independence_movement': round(Q['independence_movement'], 2),
            'independence_trust':    round(Q['independence_trust'], 2),
            'social_dissent':        round(Q['social_dissent'], 2),
            'welfare_index':         round(Q['welfare_index'], 2),
            'fla_active':            flags['fla_active'],
            'fla_escalated':         flags['fla_escalated'],
            'art155_ever':           flags['art155_ever'],
            'podemos_channeling':    round(flags['podemos_channeling'], 3),
        })

    df = pd.DataFrame(history)
    return df, event_log


# ══════════════════════════════════════════════════════════════════════════════
# USAGE EXAMPLES & VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import os, matplotlib.pyplot as plt, matplotlib.gridspec as gridspec
    from matplotlib.lines import Line2D
    os.makedirs('simulations/results', exist_ok=True)

    # ── 1. IRL baseline ───────────────────────────────────────────────────────
    df_irl, log_irl = simulate(seed=42)

    # ── 2. PSOE takes Gobierno in Jan 2016 ────────────────────────────────────
    gov_psoe_2016 = [
        (1,  41, 'PP_abs'),
        (42, 90, 'PSOE_min'),
    ]
    df_psoe, log_psoe = simulate(gob_timeline=gov_psoe_2016, seed=42)

    # ── 3. ERC leads Generalitat from 2015 (no 155) ───────────────────────────
    gen_erc = [
        (1,  29, 'CiU'),
        (30, 90, 'ERC'),
    ]
    df_erc, log_erc = simulate(gen_timeline=gen_erc, seed=42)

    # ── 4. No ECB QE ──────────────────────────────────────────────────────────
    df_noqe, _ = simulate(ecb_qe=False, seed=42)

    IRL_ACTUALS = {
        'gdp':   {2012:-3.1,2013:-1.4,2014:1.5,2015:3.7,2016:3.5,2017:3.4,2018:2.6,2019:1.9},
        'unemp': {2012:22.5,2013:24.0,2014:22.0,2015:19.8,2016:17.3,2017:14.8,2018:12.8,2019:11.4},
        'debt':  {2012:26.0,2013:29.0,2014:31.0,2015:33.0,2016:34.5,2017:35.0,2018:34.5,2019:33.4},
    }

    scenarios = {'IRL': df_irl, 'PSOE_2016': df_psoe, 'ERC_no155': df_erc, 'No_QE': df_noqe}
    colors    = {'IRL': '#2563eb', 'PSOE_2016': '#16a34a', 'ERC_no155': '#dc2626', 'No_QE': '#9333ea'}

    print("=== GDP GROWTH (annual avg) ===")
    print(f"{'Year':<6}", end="")
    for name in scenarios: print(f"{name:>12}", end="")
    print(f"{'IRL_actual':>12}")
    for yr in range(2012, 2020):
        print(f"{yr:<6}", end="")
        for df in scenarios.values():
            print(f"{df[df['year']==yr]['gdp_growth'].mean():>12.1f}", end="")
        print(f"{IRL_ACTUALS['gdp'][yr]:>12.1f}")

    print("\n=== UNEMPLOYMENT (annual avg) ===")
    print(f"{'Year':<6}", end="")
    for name in scenarios: print(f"{name:>12}", end="")
    print(f"{'IRL_actual':>12}")
    for yr in range(2012, 2020):
        print(f"{yr:<6}", end="")
        for df in scenarios.values():
            print(f"{df[df['year']==yr]['unemployment'].mean():>12.1f}", end="")
        print(f"{IRL_ACTUALS['unemp'][yr]:>12.1f}")

    print("\n=== PUBLIC DEBT % GDP (annual avg) ===")
    print(f"{'Year':<6}", end="")
    for name in scenarios: print(f"{name:>12}", end="")
    print(f"{'IRL_actual':>12}")
    for yr in range(2012, 2020):
        print(f"{yr:<6}", end="")
        for df in scenarios.values():
            print(f"{df[df['year']==yr]['public_debt'].mean():>12.1f}", end="")
        print(f"{IRL_ACTUALS['debt'][yr]:>12.1f}")

    print("\n=== SOCIAL/POLITICAL VARIABLES (IRL baseline) ===")
    print(f"{'Year':<6}{'Dissent':>10}{'Welfare':>10}{'IndyMov':>10}{'IndyTrst':>10}{'CatSpa':>10}{'Channeling':>12}")
    for yr in range(2012, 2020):
        d = df_irl[df_irl['year']==yr]
        print(f"{yr:<6}"
              f"{d['social_dissent'].mean():>10.1f}"
              f"{d['welfare_index'].mean():>10.1f}"
              f"{d['independence_movement'].mean():>10.1f}"
              f"{d['independence_trust'].mean():>10.1f}"
              f"{d['cat_spa_relations'].mean():>10.1f}"
              f"{d['podemos_channeling'].mean():>12.3f}")

    print("\n=== EVENT LOG (IRL baseline) ===")
    for entry in log_irl:
        print(f"  m{entry['month']:>3} ({entry['year']}-{entry['cal_month']:02d})  "
              f"{entry['event_id']:<25}  {entry['label'][:60]}")

    # ── Save CSVs ─────────────────────────────────────────────────────────────
    df_irl.to_csv('simulations/results/economic_sim_irl_v4.csv', index=False)
    df_psoe.to_csv('simulations/results/economic_sim_psoe2016_v4.csv', index=False)
    df_erc.to_csv('simulations/results/economic_sim_erc_v4.csv', index=False)
    pd.DataFrame(log_irl).to_csv('simulations/results/event_log_irl_v4.csv', index=False)

    # ── Charts ────────────────────────────────────────────────────────────────
    def annual_avg(df, col):
        return df.groupby('year')[col].mean()

    def add_event_vlines(ax, log, variables_shown, color='gray', alpha=0.25):
        """Draw vertical lines for events that affect the variables shown."""
        for entry in log:
            if any(v in entry['effects'] for v in variables_shown):
                ax.axvline(entry['month'], color=color, alpha=alpha, linewidth=0.8, linestyle=':')

    fig = plt.figure(figsize=(18, 22))
    gs  = gridspec.GridSpec(4, 2, figure=fig, hspace=0.50, wspace=0.35)

    # GDP
    ax1 = fig.add_subplot(gs[0, 0])
    for name, df in scenarios.items():
        ax1.plot(annual_avg(df, 'gdp_growth'), label=name, color=colors[name])
    ax1.plot(list(IRL_ACTUALS['gdp'].keys()), list(IRL_ACTUALS['gdp'].values()),
             'k--', label='IRL actual', linewidth=1.5)
    ax1.set_title('GDP Growth (annual avg %)', fontweight='bold')
    ax1.set_ylabel('%'); ax1.legend(fontsize=8); ax1.grid(alpha=0.3)

    # Unemployment
    ax2 = fig.add_subplot(gs[0, 1])
    for name, df in scenarios.items():
        ax2.plot(annual_avg(df, 'unemployment'), label=name, color=colors[name])
    ax2.plot(list(IRL_ACTUALS['unemp'].keys()), list(IRL_ACTUALS['unemp'].values()),
             'k--', label='IRL actual', linewidth=1.5)
    ax2.set_title('Unemployment Rate (annual avg %)', fontweight='bold')
    ax2.set_ylabel('%'); ax2.legend(fontsize=8); ax2.grid(alpha=0.3)

    # Public debt — monthly with event markers
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(df_irl['month'], df_irl['public_debt'], color=colors['IRL'], label='IRL')
    ax3.axhline(FLA_ENTRY_THRESHOLD,      color='orange', linestyle='--', linewidth=1, label=f'FLA entry ({FLA_ENTRY_THRESHOLD}%)')
    ax3.axhline(FLA_ESCALATION_THRESHOLD, color='red',    linestyle='--', linewidth=1, label=f'FLA escalation ({FLA_ESCALATION_THRESHOLD}%)')
    ax3.plot(list(IRL_ACTUALS['debt'].keys()), list(IRL_ACTUALS['debt'].values()),
             'k--', linewidth=1.5, label='IRL actual')
    ax3.set_title('Public Debt % GDP — monthly with FLA thresholds', fontweight='bold')
    ax3.set_xlabel('Month'); ax3.set_ylabel('% GDP')
    ax3.legend(fontsize=8); ax3.grid(alpha=0.3)

    # Social dissent — monthly with event markers
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.plot(df_irl['month'], df_irl['social_dissent'], color=colors['IRL'], label='IRL', linewidth=1.2)
    ax4.plot(df_psoe['month'], df_psoe['social_dissent'], color=colors['PSOE_2016'], label='PSOE_2016', linewidth=1.0, alpha=0.7)
    add_event_vlines(ax4, log_irl, ['social_dissent'], color='gray', alpha=0.3)
    ax4.axhline(50, color='gray', linestyle=':', linewidth=1)
    ax4.set_title('Social Dissent — monthly (events marked)', fontweight='bold')
    ax4.set_xlabel('Month'); ax4.set_ylabel('index (0–100)')
    ax4.legend(fontsize=8); ax4.grid(alpha=0.3)

    # Independence movement — monthly with Diada markers
    ax5 = fig.add_subplot(gs[2, 0])
    ax5.plot(df_irl['month'], df_irl['independence_movement'], color=colors['IRL'], label='IRL', linewidth=1.2)
    ax5.plot(df_erc['month'], df_erc['independence_movement'], color=colors['ERC_no155'], label='ERC_no155', linewidth=1.0, alpha=0.7)
    diada_events = [e for e in log_irl if e['event_id'].startswith('diada_')]
    for e in diada_events:
        ax5.axvline(e['month'], color='darkorange', alpha=0.6, linewidth=1.2, linestyle='--')
    proces_events = [e for e in log_irl if e['event_id'] in ('9n_2014','27s_2015','1o_referendum','dui_155_cluster','21d_elections')]
    for e in proces_events:
        ax5.axvline(e['month'], color='red', alpha=0.5, linewidth=1.5, linestyle='-.')
    ax5.add_artist(ax5.legend(
        handles=[
            Line2D([0],[0], color=colors['IRL'], linewidth=1.5),
            Line2D([0],[0], color=colors['ERC_no155'], linewidth=1.5, alpha=0.7),
            Line2D([0],[0], color='darkorange', linestyle='--', linewidth=1.2),
            Line2D([0],[0], color='red', linestyle='-.', linewidth=1.5),
        ],
        labels=['IRL', 'ERC_no155', 'Diada', 'Procés event'],
        loc='lower left', fontsize=8
    ))
    ax5.set_title('Independence Movement — monthly', fontweight='bold')
    ax5.set_xlabel('Month'); ax5.set_ylabel('index')
    ax5.grid(alpha=0.3)

    # Cat-Spa relations — monthly
    ax6 = fig.add_subplot(gs[2, 1])
    for name, df in {'IRL': df_irl, 'PSOE_2016': df_psoe, 'ERC_no155': df_erc}.items():
        ax6.plot(df['month'], df['cat_spa_relations'], label=name, color=colors[name], alpha=0.85)
    ax6.axhline(CAT_SPA_POST155_FLOOR, color='red', linestyle='--', linewidth=1,
                label=f'Post-155 floor ({CAT_SPA_POST155_FLOOR})')
    for e in proces_events:
        ax6.axvline(e['month'], color='gray', alpha=0.4, linewidth=1, linestyle=':')
    ax6.set_title('Cat-Spain Relations — monthly', fontweight='bold')
    ax6.set_xlabel('Month'); ax6.set_ylabel('index (5–80)')
    ax6.legend(fontsize=8); ax6.grid(alpha=0.3)

    # Welfare index
    ax7 = fig.add_subplot(gs[3, 0])
    for name, df in scenarios.items():
        ax7.plot(annual_avg(df, 'welfare_index'), label=name, color=colors[name])
    ax7.set_title('Welfare Index (annual avg, 0–100)', fontweight='bold')
    ax7.set_ylabel('index'); ax7.legend(fontsize=8); ax7.grid(alpha=0.3)

    # Podemos channeling + dissent equilibrium trace
    ax8 = fig.add_subplot(gs[3, 1])
    ax8_r = ax8.twinx()
    ax8.plot(df_irl['month'], df_irl['podemos_channeling'], color='#9333ea', label='Podemos channeling', linewidth=1.5)
    ax8_r.plot(df_irl['month'], df_irl['social_dissent'], color='#2563eb', label='Social dissent', linewidth=1.0, alpha=0.6)
    ax8.set_ylabel('Channeling (0–1)', color='#9333ea')
    ax8_r.set_ylabel('Dissent (0–100)', color='#2563eb')
    ax8.set_title('Podemos Channeling vs Social Dissent', fontweight='bold')
    ax8.set_xlabel('Month')
    lines1, labs1 = ax8.get_legend_handles_labels()
    lines2, labs2 = ax8_r.get_legend_handles_labels()
    ax8.legend(lines1 + lines2, labs1 + labs2, fontsize=8)
    ax8.grid(alpha=0.3)

    fig.suptitle('Route to Ítaca — Economic Engine v4\nEvent System Active', fontsize=14, fontweight='bold', y=0.99)
    plt.savefig('simulations/results/engine_v4_overview.png', dpi=150, bbox_inches='tight')
    plt.close()

    print("\nAll outputs saved to simulations/results/")
