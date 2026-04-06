"""
local_elections.py
Route to Ítaca — Local Election Model

Unified model for all Catalan local elections. Covers:
  1. Barcelona city council  : full demographic matrix (monthly tick)
  2. Red Belt cities         : PSC damage / challenger score system
  3. Interior Catalonia      : CiU decay / ERC-CUP-FNC race
  4. Provincial capitals     : Parliament-extrapolated
  5. Decorative locations    : map anchors, Parliament matrix only

Public API
----------
  init_local_barcelona(Q)
  update_local_barcelona(Q, ...)             monthly tick
  fire_split_event(Q, split_type)
  resolve_local_barcelona(Q) → dict
  compute_redbelt_scores(Q, params) → dict
  compute_interior_scores(Q, params) → dict
  run_municipal_election(Q, year, rb_params, int_params) → dict
  display_barcelona_results(res, Q)
  display_results(results)

Calibration exports
-------------------
  RB_DEFAULTS    — default red belt score formula coefficients
  INT_DEFAULTS   — default interior score formula coefficients
  RB_HISTORICAL  — expected winners per red belt city for 2015 / 2019
  INT_HISTORICAL — expected winners per interior city for 2015 / 2019
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# BARCELONA — CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

DEMOGRAPHICS = ["ind", "middle", "buss", "young", "retired", "unemployed"]  # kept for province/capital use

LOCAL_BCN_PARTIES = ["bcomuns", "ciu", "erc", "psc", "cs", "cup", "pp", "primaries"]

_BCN_PARTY_LABELS: Dict[str, str] = {
    "bcomuns":   "Barcelona en Comú",
    "ciu":       "CiU / CDC / PDeCat",
    "erc":       "ERC",
    "psc":       "PSC",
    "cs":        "Cs",
    "cup":       "CUP",
    "pp":        "PP",
    "primaries": "Primàries (2019)",
    "jxcat":     "CiU / CDC / PDeCat",
    "pdcat":     "CiU / CDC / PDeCat",
}

BCN_TOTAL_SEATS = 41
BCN_THRESHOLD   = 5.0  # Standard 5% threshold; CUP 3.9% + Primàries 3.76% got 0 seats in 2019

# Trias candidacy bonus: Xavier Trias (CiU) was the 2015 candidate; not running in 2019.
# Applied at resolution time only (not during monthly ticks).
TRIAS_BONUS = 17.0

# City-wide party baselines (2012 starting points; demographic-weighted averages; sum to 100).
# CiU: low — Trias bonus (+17) at resolution time pushes from ~12% → ~22% in 2015
# PSC: starts above 9.6% 2015 target; IM crisis + negative cat_spa sensitivity drives collapse then 2019 recovery
# CUP: below 2015 result; grows with dissent and IM-trust gap over 34 months
BCN_BASELINE: Dict[str, float] = {
    "bcomuns":   29.0,  # social dissent + podemos channeling drives toward 25% by 2015
    "ciu":       12.5,  # Trias incumbent bonus applied at resolution pushes to ~22% in 2015
    "erc":       11.0,  # IM + trust sensitivity drives toward 11%
    "psc":       16.5,  # sensitivities pull down 2012-15, then unionist consolidation up 2017-19
    "cs":        13.5,  # IM crisis consolidates anti-indy vote upward
    "cup":        7.0,  # grows with dissent; IM-trust gap keeps it relevant
    "pp":        10.5,  # weakening; post-ART155 PP collapse via m=67 transfer event
    "primaries":  0.0,  # zero until split event at m=81 (Apr 2019)
}

# Sensitivity to macro deltas: [d_im, d_it, d_sd, d_welfare, d_cat_spa, d_unemployment, podemos_pulse]
BCN_SENSITIVITY: Dict[str, List[float]] = {
    "bcomuns": [  0.02,   0.00,   0.22,  -0.10,   0.00,   0.05,   0.10 ],
    "ciu":     [  0.08,   0.15,  -0.10,   0.05,   0.05,  -0.05,  -0.05 ],
    "erc":     [  0.15,   0.15,   0.05,  -0.05,   0.05,   0.05,   0.04 ],
    # PSC: unionist consolidation — cat_spa falling (indy crisis) boosts PSC; rising indy_trust hurts PSC
    "psc":     [  0.00,  -0.15,  -0.05,   0.18,  -0.30,  -0.05,  -0.05 ],
    # Cs: gains as IM rises (anti-indy consolidation) and as cat_spa falls
    "cs":      [ +0.08,  -0.05,  -0.05,   0.05,  -0.10,  -0.05,  -0.02 ],
    "cup":     [  0.08,  -0.10,   0.12,  -0.10,  -0.05,   0.10,   0.05 ],
    "pp":      [ -0.12,  -0.05,  -0.05,   0.05,   0.20,  -0.05,  -0.04 ],
    "primaries": [ 0.00,   0.00,   0.00,   0.00,   0.00,   0.00,   0.00 ],
}

BCN_MEAN_REVERSION_SPEED: float = 0.012

# ═══════════════════════════════════════════════════════════════════════════════
# CATALONIA — CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Capital cities skew more middle-class and younger than their province average.
CAPITAL_DEMO_WEIGHTS: Dict[str, Dict[str, float]] = {
    "barcelona": {"ind": 0.25, "middle": 0.30, "buss": 0.12,
                  "young": 0.18, "retired": 0.10, "unemployed": 0.05},
    "girona":    {"ind": 0.22, "middle": 0.28, "buss": 0.14,
                  "young": 0.16, "retired": 0.14, "unemployed": 0.06},
    "lleida":    {"ind": 0.28, "middle": 0.25, "buss": 0.12,
                  "young": 0.15, "retired": 0.14, "unemployed": 0.06},
    "tarragona": {"ind": 0.27, "middle": 0.26, "buss": 0.11,
                  "young": 0.16, "retired": 0.14, "unemployed": 0.06},
}

PARTY_TO_FAMILY: Dict[str, str] = {
    "ciu":   "icr", "cdc":  "icr", "dl":    "icr", "junts": "icr",
    "jxcat": "icr", "pdcat":"icr", "udc":   "icr", "unio":  "icr",
    "erc":   "erc",
    "cup":   "cup",
    "icv":   "fl",  "icv-euia": "fl", "csqp": "fl", "cecp": "fl",
    "ecp":   "fl",  "bcomuns":  "fl",
    "psc":   "psc",
    "cs":    "cs",
    "pp":    "pp",  "ppc": "pp",
    "vox":   "vox",
    "fnc":   "fnc", "pxc": "fnc",
}

ALL_FAMILIES = ["icr", "erc", "cup", "fl", "psc", "cs", "pp", "vox", "fnc"]

_CAT_PARTY_LABELS: Dict[str, str] = {
    "bcomuns": "BComú/Comuns", "icr": "CiU/CDC",  "ciu": "CiU/CDC",
    "erc":     "ERC",          "cup": "CUP",       "psc": "PSC",
    "cs":      "Cs",           "pp":  "PP",        "vox": "VOX",
    "fnc":     "FNC/PxC",      "fl":  "Comuns/ICV","comuns": "Comuns",
}

@dataclass
class Location:
    name: str
    system: str
    province: str
    population_2015: int
    rb_resistance: float = 0.0
    rb_primary: str = ""
    rb_secondary: str = ""
    rb_secondary_threshold: float = 999.0
    int_tier: str = ""
    int_primary: str = ""
    int_fnc_risk: bool = False
    int_ebre: bool = False
    int_resistance: float = 0.0
    cap_province: str = ""
    notes: str = ""

LOCATIONS: List[Location] = [
    Location("Barcelona", "barcelona", "barcelona", 1_656_000),
    Location("Lleida",    "capital",   "lleida",    143_000, cap_province="lleida"),
    Location("Tarragona", "capital",   "tarragona", 138_000, cap_province="tarragona"),
    Location("Reus",      "capital",   "tarragona", 108_500, cap_province="tarragona"),
    Location("Girona",    "capital",   "girona",    104_000, cap_province="girona"),

    # ── RED BELT ──
    Location("L'Hospitalet de Llobregat", "redBelt", "barcelona", 276_600, rb_resistance=55, rb_primary="cs"),
    Location("Sant Boi de Llobregat",     "redBelt", "barcelona",  83_700, rb_resistance=55, rb_primary="cs"),
    Location("El Prat de Llobregat",      "redBelt", "barcelona",  65_400, rb_resistance=55, rb_primary="cs"),
    Location("Viladecans",                "redBelt", "barcelona",  61_200, rb_resistance=55, rb_primary="cs"),
    Location("Esplugues de Llobregat",    "redBelt", "barcelona",  46_800, rb_resistance=55, rb_primary="cs"),
    Location("Ripollet",                  "redBelt", "barcelona",  35_400, rb_resistance=25, rb_primary="cup"),  # early CUP flipper
    Location("Sant Adrià de Besòs",       "redBelt", "barcelona",  32_600, rb_resistance=55, rb_primary="cs"),
    Location("Terrassa",              "redBelt", "barcelona", 225_300, rb_resistance=75, rb_primary="cs"),
    Location("Sabadell",              "redBelt", "barcelona", 218_000, rb_resistance=75, rb_primary="cs",
             rb_secondary="erc", rb_secondary_threshold=50, int_tier="bridge"),
    Location("Cornellà de Llobregat", "redBelt", "barcelona",  90_100, rb_resistance=78, rb_primary="cs"),
    Location("Rubí",                  "redBelt", "barcelona",  80_000, rb_resistance=72, rb_primary="cs"),
    Location("Granollers",            "redBelt", "barcelona",  58_900, rb_resistance=78, rb_primary="erc"),
    Location("Mollet del Vallès",     "redBelt", "barcelona",  51_700, rb_resistance=67, rb_primary="cs"),
    Location("Mataró",                "redBelt", "barcelona", 129_600, rb_resistance=80, rb_primary="erc"),
    Location("Badalona",              "redBelt", "barcelona", 225_300, rb_resistance=80, rb_primary="cs",
             rb_secondary="erc", rb_secondary_threshold=50),
    Location("Santa Coloma de Gramenet", "redBelt", "barcelona", 119_200, rb_resistance=95, rb_primary="cs"),
    Location("Balaguer",              "redBelt", "lleida",     16_000, rb_resistance=38, rb_primary="erc"),
    Location("Sant Vicenç dels Horts","redBelt", "barcelona",  30_000, rb_resistance=32, rb_primary="erc"),
    Location("Martorell",             "redBelt", "barcelona",  28_000, rb_resistance=38, rb_primary="ciu"),

    # ── INTERIOR ──
    Location("Manresa",          "interior", "barcelona", 75_000, int_tier="A",      int_primary="erc",       int_fnc_risk=True),
    Location("Figueres",         "interior", "girona",    46_000, int_tier="A",      int_primary="erc"),
    Location("Vic",              "interior", "barcelona", 41_200, int_tier="A",      int_primary="three-way", int_fnc_risk=True, int_resistance=10),
    Location("Igualada",         "interior", "barcelona", 36_800, int_tier="A",      int_primary="erc"),
    Location("Olot",             "interior", "girona",    34_000, int_tier="A",      int_primary="erc",       int_fnc_risk=True),
    Location("La Seu d'Urgell",  "interior", "lleida",    12_000, int_tier="A",      int_primary="erc"),
    Location("Tàrrega",          "interior", "lleida",    17_000, int_tier="B",      int_primary="cup",       int_resistance=10),
    Location("Berga",            "interior", "barcelona", 15_000, int_tier="B",      int_primary="cup",       int_resistance=-65),  # long-term CUP stronghold
    Location("Solsona",          "interior", "lleida",     9_000, int_tier="A",      int_primary="erc",       int_resistance=-40),
    Location("Ripoll",           "interior", "girona",    10_000, int_tier="C",      int_primary="three-way", int_fnc_risk=True, int_resistance=10),
    Location("Tortosa",          "interior", "tarragona", 33_000, int_tier="A",      int_primary="erc",       int_ebre=True),
    Location("Amposta",          "interior", "tarragona", 22_000, int_tier="A",      int_primary="erc",       int_ebre=True, int_resistance=-40),
    Location("Móra d'Ebre",      "interior", "tarragona",  5_000, int_tier="B",      int_primary="cup",       int_ebre=True),
    Location("Sant Cugat del Vallès", "interior", "barcelona", 90_000, int_tier="bridge", int_primary="erc",  int_fnc_risk=True, int_resistance=10),

    # ── DECORATIVE ──
    Location("Banyoles",             "decorative", "girona",    18_000),
    Location("Vilanova i la Geltrú", "decorative", "barcelona", 62_000),
    Location("Tremp",                "decorative", "lleida",     6_000),
    Location("Sort",                 "decorative", "lleida",     2_500),
]

# ═══════════════════════════════════════════════════════════════════════════════
# TUNABLE PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════════
# These are the default coefficients used in the score formulas.
# local_calibrator.py can pass override dicts to compute_redbelt_scores()
# and compute_interior_scores() to tune them against historical results.

RB_DEFAULTS: Dict[str, float] = {
    # Cs score
    "cs_im_coeff":              0.90,
    "cs_spa_coeff":             0.70,
    "cs_diss_coeff":            0.30,
    # ERC score
    "erc_trust_coeff":          1.20,
    "erc_im_coeff":             0.60,
    "erc_no_outreach_penalty": 10.0,
    # Comuns score
    "comuns_diss_coeff":        0.60,
    "comuns_pp_scale":         15.0,
    "comuns_welf_coeff":        0.40,
}

INT_DEFAULTS: Dict[str, float] = {
    # CiU decay
    "decay_base":          8.0,
    "decay_corr_coeff":   10.0,   # corruption hurts but doesn't destroy interior base
    "decay_welf_coeff":    0.40,
    "decay_pdcat_bonus":   8.0,   # JxCat inherited the interior brand — small bonus
    "decay_unio_bonus":    5.0,   # Unió split barely reached interior
    # ERC interior
    "erc_trust_coeff":     0.75,
    "erc_im_coeff":        0.30,
    "erc_build_bonus":    28.0,
    "erc_base_bonus":      5.0,
    # CUP interior
    "cup_imtrust_coeff":   0.60,
    "cup_diss_coeff":      0.50,
    # Holdout
    "holdout_base":       95.0,
}

# ═══════════════════════════════════════════════════════════════════════════════
# HISTORICAL ANCHORS
# ═══════════════════════════════════════════════════════════════════════════════
# Sources: https://www.3cat.cat/324/eleccions-municipals-2015/catalunya/
#          https://www.3cat.cat/324/eleccions-26m-2019/

RB_HISTORICAL: Dict[int, Dict[str, Optional[str]]] = {
    2015: {
        "L'Hospitalet de Llobregat": "psc",
        "Sant Boi de Llobregat":     "psc",
        "El Prat de Llobregat":      "psc",
        "Viladecans":                "psc",
        "Esplugues de Llobregat":    "psc",
        "Ripollet":                  "cup",   # CUP won 2015 (noted in LOCATIONS)
        "Sant Adrià de Besòs":       "psc",
        "Terrassa":                  "psc",
        "Sabadell":                  "psc",
        "Cornellà de Llobregat":     "psc",
        "Rubí":                      "psc", #erc was VERY close, and Cs as well, but less
        "Granollers":                "psc", 
        "Mollet del Vallès":         "psc",
        "Mataró":                    "psc",
        "Badalona":                  "pp",    # PP (Albiol) held 2011–2015
        "Santa Coloma de Gramenet":  "psc",
        "Balaguer":                  "erc",
        "Sant Vicenç dels Horts":    "erc",   # ERC stronghold (noted)
        "Martorell":                 "ciu",   # fell to CiU in 2015 (noted)
    },
    2019: {
        "L'Hospitalet de Llobregat": "psc",
        "Sant Boi de Llobregat":     "psc",
        "El Prat de Llobregat":      "psc",
        "Viladecans":                "psc",
        "Esplugues de Llobregat":    "psc",
        "Ripollet":                  "cup",   # actually called Decidim, in conjunction with Comuns
        "Sant Adrià de Besòs":       "psc",   # erc relatively close
        "Terrassa":                  "psc",
        "Sabadell":                  "psc",
        "Cornellà de Llobregat":     "psc",
        "Rubí":                      "psc",  # psc won easy this time
        "Granollers":                "psc",
        "Mollet del Vallès":         "psc",
        "Mataró":                    "erc",   # ERC flipped 2019
        "Badalona":                  "pp",    # Albiol won again, followed by the erc-cup-comuns mega pact
        "Santa Coloma de Gramenet":  "psc",
        "Balaguer":                  "erc",
        "Sant Vicenç dels Horts":    "erc",
        "Martorell":                 "ciu", #jxcat
    },
}

INT_HISTORICAL: Dict[int, Dict[str, Optional[str]]] = {
    2015: {
        "Manresa":               "ciu",   # erc quite close
        "Figueres":              "ciu",   # erc/cup/erc tied, a bit far
        "Vic":                   "ciu",   # second erc, third cup
        "Igualada":              "ciu",   # by far
        "Olot":                  "ciu",   # ciu, then erc then psc/cup
        "La Seu d'Urgell":       "ciu",   # compromis (local list VERY close)
        "Tàrrega":               "ciu",   # then cup then erc
        "Berga":                 "cup",   # CiU VERY close
        "Solsona":               "erc",   # ERC (sharper crack noted)
        "Ripoll":                "ciu",   # by far, then erc
        "Tortosa":               "ciu",   # erc second
        "Amposta":               "erc",   # then ciu, psc very far
        "Móra d'Ebre":           "ciu",   # then erc
        "Sant Cugat del Vallès": "ciu",   # CiU held 2015, then cup!
    },
    2019: {
        "Manresa":               "erc",  # jxcat VERY close
        "Figueres":              "ciu",  # erc then psc
        "Vic":                   "ciu",   # JxCat (still ciu family); verify
        "Igualada":              "ciu",   # JxCat
        "Olot":                  "ciu",   # JxCat
        "La Seu d'Urgell":       None,   # local list won but jxcat governed though
        "Tàrrega":               "ciu",   # JxCat, then erc then cup
        "Berga":                 "cup",
        "Solsona":               "erc",
        "Ripoll":                "ciu",   # JxCat by far, thn ERC/PSC/CUP
        "Tortosa":               "ciu", #JxCat, then erc, then psc
        "Amposta":               "erc", # by super far
        "Móra d'Ebre":           "ciu", #jxcat, the rest not even close
        "Sant Cugat del Vallès": "ciu",   # JxCat, then erc then psc
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))

def _normalise_bcn(Q: dict) -> None:
    total = sum(Q.get(f"{p}_local_barcelona_support", 0.0) for p in LOCAL_BCN_PARTIES)
    if total > 0:
        for p in LOCAL_BCN_PARTIES:
            Q[f"{p}_local_barcelona_support"] /= (total / 100.0)

def _dhondt_seats(shares: Dict[str, float], total_seats: int, threshold: float) -> Dict[str, int]:
    valid = {p: v for p, v in shares.items() if v >= threshold}
    if not valid:
        return {p: 0 for p in shares}
    seats = {p: 0 for p in shares}
    for _ in range(total_seats):
        best_p = max(valid.keys(), key=lambda p: valid[p] / (seats[p] + 1))
        seats[best_p] += 1
    return seats

def _get_active_icr_party(Q: dict) -> str:
    if Q.get("pdcat_split_happened", False):
        return "pdcat"
    if Q.get("year", 2012) >= 2017:
        return "jxcat"
    return "ciu"

# ═══════════════════════════════════════════════════════════════════════════════
# BARCELONA — MODEL
# ═══════════════════════════════════════════════════════════════════════════════

def init_local_barcelona(Q: dict) -> None:
    """Seed per-party support variables into Q."""
    for party, val in BCN_BASELINE.items():
        Q[f"{party}_local_barcelona_support"] = val


def update_local_barcelona(
    Q: dict,
    d_vars: Optional[List[float]] = None,
    d_independence_movement: float = 0.0,
    d_independence_trust: float = 0.0,
    d_social_dissent: float = 0.0,
    d_welfare: float = 0.0,
    d_cat_spa: float = 0.0,
    d_unemployment: float = 0.0,
    podemos_pulse: float = 0.0,
) -> None:
    """Monthly tick: update party support from macro deltas."""
    if d_vars is None:
        d_vars = [
            d_independence_movement, d_independence_trust, d_social_dissent,
            d_welfare, d_cat_spa, d_unemployment, podemos_pulse,
        ]
    for party in LOCAL_BCN_PARTIES:
        key = f"{party}_local_barcelona_support"
        if key not in Q:
            Q[key] = BCN_BASELINE.get(party, 0.0)

        sens  = BCN_SENSITIVITY.get(party, [0.0] * 7)
        delta = sum(sens[i] * d_vars[i] for i in range(7))

        if Q.get("year", 2012) > 2015 and party in ["erc", "ciu"] and Q.get("independence_movement", 50) > 60:
            surge_coeff = 0.35 if party == "erc" else 0.22  # ERC is main IM beneficiary; JxCat gains less
            delta += surge_coeff * (Q.get("independence_movement", 50) - 60) * 0.1

        reversion = BCN_MEAN_REVERSION_SPEED * (BCN_BASELINE.get(party, 0.0) - Q[key])
        Q[key] = _clamp(Q[key] + delta + reversion, 0.0, 100.0)

    _normalise_bcn(Q)


def fire_split_event(Q: dict, split_type: str) -> None:
    """Redirect CiU support on a Unió or PDeCat split event."""
    BCN_SPLIT_REDIRECTS = {
        "unio":  {"psc": 0.15, "pp": 0.05, "ciu": -0.20},
        "pdcat": {"erc": 0.30, "cup": 0.08, "ciu": -0.38},
    }
    if split_type not in BCN_SPLIT_REDIRECTS:
        return
    reds = BCN_SPLIT_REDIRECTS[split_type]
    current_ciu = Q.get("ciu_local_barcelona_support", 0.0)
    for party, factor in reds.items():
        key = f"{party}_local_barcelona_support"
        Q[key] = _clamp(Q.get(key, 0.0) + current_ciu * factor, 0.0, 100.0)
    _normalise_bcn(Q)


def resolve_local_barcelona(Q: dict) -> dict:
    """
    Apply Trias bonus to a copy, normalise, D'Hondt seats → mayor result dict.
    Writes to _pv only; does not overwrite the running _support state variables.
    """
    # Work on a copy so the Trias bonus doesn't corrupt the ongoing monthly model.
    city_wide = {p: Q.get(f"{p}_local_barcelona_support", 0.0) for p in LOCAL_BCN_PARTIES}

    # Trias candidacy bonus: CiU ran Xavier Trias (incumbent) in 2015 — not in 2019.
    if Q.get("trias_leading", True):
        city_wide["ciu"] += TRIAS_BONUS

    total = sum(city_wide.values())
    if total > 0:
        city_wide = {p: v / total * 100.0 for p, v in city_wide.items()}

    for party, share in city_wide.items():
        Q[f"{party}_local_barcelona_pv"] = share

    active_icr = _get_active_icr_party(Q)
    if active_icr != "ciu":
        Q[f"{active_icr}_local_barcelona_pv"] = city_wide.get("ciu", 0.0)

    seats  = _dhondt_seats(city_wide, BCN_TOTAL_SEATS, BCN_THRESHOLD)
    for party, n in seats.items():
        Q[f"{party}_local_barcelona_s"] = n

    winner = max(seats, key=seats.get)
    mode   = "majority" if seats[winner] > 20 else "hung"
    if winner == "bcomuns" and mode == "hung" and seats.get("psc", 0) >= 4:
        mode = "psc_abstention"

    Q["barcelona_mayor"]      = winner
    Q["barcelona_mayor_mode"] = mode

    return {
        "city_wide_support": city_wide,
        "shares":            city_wide,
        "seats":             seats,
        "mayor":             winner,
        "winner":            winner,
        "gov_mode":          mode,
    }


def display_barcelona_results(res: dict, Q: dict) -> None:
    shares  = res["shares"]
    seats   = res["seats"]
    winner  = res["mayor"]
    mode    = res["gov_mode"]
    sorted_p = sorted(shares.keys(), key=lambda x: shares[x], reverse=True)
    print(f"\n{'═'*60}\n  BARCELONA CITY COUNCIL — Route to Ítaca\n{'═'*60}")
    print(f"  {'Party':<26} {'Share':>6}  {'Seats':>5}  {'Bar'}")
    print(f"  {'─'*56}")
    for p in sorted_p:
        print(f"  {_BCN_PARTY_LABELS.get(p, p):<26} {shares[p]:>5.1f}%  "
              f"{seats.get(p, 0):>3}   {'█' * int(shares[p] / 2.5)}")
    print(f"\n  Mayor  : {_BCN_PARTY_LABELS.get(winner, winner)}")
    print(f"  Mode   : {mode.replace('_', ' ')}")

# ═══════════════════════════════════════════════════════════════════════════════
# CATALONIA — SCORE SYSTEMS
# ═══════════════════════════════════════════════════════════════════════════════

def _province_family_support(Q: dict, province: str) -> Dict[str, float]:
    """Aggregate Parliament support by family for a province, weighted by capital demographics."""
    weights = CAPITAL_DEMO_WEIGHTS.get(province, {d: 1/6 for d in DEMOGRAPHICS})
    totals: Dict[str, float] = {f: 0.0 for f in ALL_FAMILIES}
    for party, family in PARTY_TO_FAMILY.items():
        for demo, w in weights.items():
            key = f"{party}_parlament_{province}_{demo}_support"
            totals[family] += Q.get(key, 0.0) * w
    total = sum(totals.values())
    if total > 0:
        totals = {f: v / total * 100 for f, v in totals.items()}
    return totals


def compute_redbelt_scores(Q: dict, params: Optional[Dict[str, float]] = None) -> dict:
    """
    Compute challenger pressure scores for the red belt.
    Returns cs_redbelt, erc_redbelt, comuns_redbelt (0–100 each).
    """
    p = {**RB_DEFAULTS, **(params or {})}

    cs = _clamp(
        _clamp(Q.get("independence_movement", 50) - 30, 0, 60) * p["cs_im_coeff"]
        + _clamp(40 - Q.get("cat_spa_relations", 38), 0, 35) * p["cs_spa_coeff"]
        + _clamp(Q.get("social_dissent", 50) - 35, 0, 25) * p["cs_diss_coeff"],
        0, 100)

    erc = _clamp(
        _clamp(Q.get("independence_trust", 35) - 12, 0, 48) * p["erc_trust_coeff"]
        + _clamp(Q.get("independence_movement", 50) - 30, 0, 40) * p["erc_im_coeff"]
        - (0 if Q.get("erc_redbelt_outreach", False) else p["erc_no_outreach_penalty"]),
        0, 100)

    comuns = _clamp(
        _clamp(Q.get("social_dissent", 50) - 20, 0, 50) * p["comuns_diss_coeff"]
        + _clamp(Q.get("podemos_pulse", 0) * p["comuns_pp_scale"], 0, 25)
        + _clamp(50 - Q.get("welfare_index", 50), 0, 30) * p["comuns_welf_coeff"],
        0, 40)

    # CUP red belt: radical-left dissent + independence gap (mirrors cup_interior)
    cup = _clamp(
        _clamp(Q.get("social_dissent", 50) - 25, 0, 50) * 0.70
        + _clamp(Q.get("independence_movement", 50) - Q.get("independence_trust", 35), 0, 40) * 0.50,
        0, 100)

    return {"cs_redbelt": cs, "erc_redbelt": erc, "comuns_redbelt": comuns, "cup_redbelt": cup}


def compute_interior_scores(Q: dict, params: Optional[Dict[str, float]] = None) -> dict:
    """
    Compute CiU decay and challenger scores for interior Catalonia.
    Returns ciu_decay, erc_interior, cup_interior, fnc_interior and flags.
    """
    p = {**INT_DEFAULTS, **(params or {})}

    ciu_decay = _clamp(
        p["decay_base"]
        + Q.get("corruption_events_ciu", 0) * p["decay_corr_coeff"]
        + _clamp(50 - Q.get("welfare_index", 50), 0, 30) * p["decay_welf_coeff"]
        + (p["decay_pdcat_bonus"] if Q.get("pdcat_split_happened", False) else 0)
        + (p["decay_unio_bonus"]  if Q.get("unio_split_happened",  False) else 0),
        0, 100)

    erc = _clamp(
        _clamp(Q.get("independence_trust", 35) - 10, 0, 50) * p["erc_trust_coeff"]
        + _clamp(Q.get("independence_movement", 50) - 25, 0, 45) * p["erc_im_coeff"]
        + (p["erc_build_bonus"] if Q.get("erc_party_building_interior", False) else p["erc_base_bonus"]),
        0, 100)

    cup = _clamp(
        _clamp(Q.get("independence_movement", 50) - Q.get("independence_trust", 35), 0, 65) * p["cup_imtrust_coeff"]
        + _clamp(Q.get("social_dissent", 50) - 20, 0, 45) * p["cup_diss_coeff"],
        0, 100)

    if erc > 45 and cup > 45 and abs(erc - cup) < 12:
        erc *= 0.70
        cup *= 0.70

    fnc_gate = (Q.get("independence_trust", 35) < 35
                and Q.get("independence_movement", 50) > 55
                and ciu_decay > 50
                and erc < 50)
    fnc = _clamp(
        (Q.get("independence_movement", 50) - Q.get("independence_trust", 35)) * 0.60
        + ciu_decay * 0.30 - cup * 0.30,
        0, 100) if fnc_gate else 0.0

    return {
        "ciu_decay":    ciu_decay,
        "erc_interior": erc,
        "cup_interior": cup,
        "fnc_interior": fnc,
        "split_active": erc > 45 and cup > 45 and abs(erc - cup) < 12,
        "fnc_gate":     fnc_gate,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# CATALONIA — LOCATION RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_redbelt(Q: dict, loc: Location, rb: dict) -> dict:
    cs, erc, comuns = rb["cs_redbelt"], rb["erc_redbelt"], rb["comuns_redbelt"]

    if loc.name == "Badalona":
        pp_score = 60.0 + _clamp(Q.get("independence_movement", 50) - 40, 0, 20) * 0.5
        if pp_score > max(cs, erc, comuns):
            return {"winner": "pp", "psc_holds": False,
                    "dominant_score": pp_score, "resistance": 0, "note": "Albiol factor"}

    # Determine primary challenger and dominant score.
    if loc.rb_primary == "erc":
        # ERC is the expected challenger. Only switch to Cs if it leads by 15+ points
        # (captures cases where Cs surges while ERC-primary territory is just that).
        if cs > erc + 20:
            dominant, party = cs, "cs"
        else:
            dominant, party = erc, "erc"
    elif loc.rb_primary == "comuns":
        dominant, party = comuns, "comuns"
    elif loc.rb_primary == "cup":
        dominant, party = rb["cup_redbelt"], "cup"
    elif loc.rb_primary == "ciu":
        # CiU is the challenger (e.g. Martorell). Use max of cs/erc as PSC resistance proxy.
        dominant, party = max(cs, erc), "ciu"
    else:
        dominant, party = cs, "cs"
        if loc.rb_secondary == "erc" and erc > loc.rb_secondary_threshold and erc > cs:
            dominant, party = erc, "erc"

    tier_bonus = (15 if loc.name in {
        "L'Hospitalet de Llobregat", "Sant Boi de Llobregat", "El Prat de Llobregat",
        "Viladecans", "Esplugues de Llobregat", "Sant Adrià de Besòs",
    } else 10 if loc.name in {
        "Terrassa", "Sabadell", "Cornellà de Llobregat", "Rubí",
        "Granollers", "Mollet del Vallès", "Mataró",
    } else 5)

    res = loc.rb_resistance + tier_bonus
    if Q.get("year", 2012) >= 2019:
        res -= 3

    psc_holds = dominant < res
    return {"winner": "psc" if psc_holds else party,
            "psc_holds": psc_holds, "dominant_score": dominant, "resistance": res}


def _resolve_interior(loc: Location, intr: dict) -> dict:
    if loc.int_ebre:
        res = 75 + loc.int_resistance  # Ebre CiU base is strong; raised from 55
        return {"winner": "erc" if intr["erc_interior"] > res else "ciu", "note": "Ebre two-way (res={:.0f})".format(res)}

    holdout = _clamp(intr["holdout_base"] - intr["ciu_decay"] + loc.int_resistance, 0, 100)

    challengers: Dict[str, float] = {}
    if loc.int_tier in ("A", "C", "bridge", "three-way") or loc.int_primary == "erc":
        challengers["erc"] = intr["erc_interior"]
    if loc.int_tier in ("B", "C", "three-way") or loc.int_primary == "cup":
        challengers["cup"] = intr["cup_interior"]
        if "erc" not in challengers:
            challengers["erc"] = intr["erc_interior"] * 0.60
    if not challengers:
        challengers["erc"] = intr["erc_interior"]

    if loc.int_fnc_risk and intr["fnc_interior"] > 0:
        challengers["fnc"] = intr["fnc_interior"]

    top_challenger = max(challengers, key=challengers.get)
    winner = top_challenger if challengers[top_challenger] > holdout else "ciu"
    return {"winner": winner, "ciu_holdout": holdout,
            "challenger_scores": challengers, "split_active": intr["split_active"]}


def _resolve_capital(Q: dict, loc: Location) -> dict:
    s = _province_family_support(Q, loc.cap_province)
    if loc.name == "Girona":
        s["psc"] *= 1.20
        t = sum(s.values())
        if t > 0:
            s = {f: v / t * 100 for f, v in s.items()}
    return {"winner": max(s, key=s.get), "scores": s}


def _resolve_decorative(Q: dict, loc: Location) -> dict:
    s = _province_family_support(Q, loc.province)
    return {"winner": max(s, key=s.get), "scores": s, "note": "decorative"}


def run_municipal_election(
    Q: dict,
    year: int,
    rb_params: Optional[Dict[str, float]] = None,
    int_params: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Resolve all locations for a given election year.
    Barcelona uses the full demographic model (Q must be up to date via
    update_local_barcelona). Red belt and interior use snapshot scores.
    """
    rb   = compute_redbelt_scores(Q, rb_params)
    intr = compute_interior_scores(Q, int_params)
    # Expose holdout_base used so _resolve_interior can access it
    intr["holdout_base"] = (int_params or INT_DEFAULTS).get("holdout_base", INT_DEFAULTS["holdout_base"])

    res = {}
    for loc in LOCATIONS:
        if loc.system == "barcelona":
            r = resolve_local_barcelona(Q)
        elif loc.system == "capital":
            r = _resolve_capital(Q, loc)
        elif loc.system == "redBelt":
            r = _resolve_redbelt(Q, loc, rb)
        elif loc.system == "interior":
            r = _resolve_interior(loc, intr)
        else:
            r = _resolve_decorative(Q, loc)
        res[loc.name] = r

    for name, r in res.items():
        if "shares" in r:
            for p_key, v in r["shares"].items():
                Q[f"{p_key}_{name}_pv"] = v
        if "scores" in r:
            for p_key, v in r["scores"].items():
                Q[f"{p_key}_{name}_pv"] = v

    return {"year": year, "locations": res, "rb_scores": rb, "int_scores": intr}


def display_results(results: dict) -> None:
    y    = results["year"]
    rb   = results["rb_scores"]
    intr = results["int_scores"]
    print(f"\n{'═'*62}\n  MUNICIPAL ELECTION {y}  —  Route to Ítaca\n{'═'*62}")
    print(f"\n  ── Damage / Race Scores ──")
    print(f"    Cs red belt      : {rb['cs_redbelt']:.1f}")
    print(f"    ERC red belt     : {rb['erc_redbelt']:.1f}")
    print(f"    CUP red belt     : {rb['cup_redbelt']:.1f}")
    print(f"    Comuns red belt  : {rb['comuns_redbelt']:.1f}")
    print(f"    CiU decay        : {intr['ciu_decay']:.1f}")
    print(f"    ERC interior     : {intr['erc_interior']:.1f}")
    print(f"    CUP interior     : {intr['cup_interior']:.1f}")
    fnc_str = f"  [GATED]" if intr["fnc_gate"] else ""
    print(f"    FNC interior     : {intr['fnc_interior']:.1f}{fnc_str}")

    locs = results["locations"]
    rb_locs  = [loc for loc in LOCATIONS if loc.system == "redBelt"]
    int_locs = [loc for loc in LOCATIONS if loc.system == "interior"]

    print(f"\n  ── Red Belt ──")
    for loc in rb_locs:
        r = locs.get(loc.name, {})
        print(f"    {loc.name:<32} {r.get('winner', '?')}")

    print(f"\n  ── Interior ──")
    for loc in int_locs:
        r = locs.get(loc.name, {})
        print(f"    {loc.name:<32} {r.get('winner', '?')}")
    
