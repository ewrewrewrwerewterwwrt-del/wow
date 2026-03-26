"""
Route to Ítaca — Demographics Module
=====================================
Tracks population by province × demographic group, updated monthly
based on the unemployment rate from the economic engine.

Provinces  : barcelona, girona, lleida, tarragona
Demographics: buss, ind, middle, young, retired, rural, unemployed

Key design decisions
---------------------
- unemployed_pop moves inversely with the unemployment rate
- job flows distribute as: 55% middle, 30% ind, 15% buss
- rural and retired are unaffected by employment flows
- young grows with population growth; growth is the only source of
  new young entrants each month
- Provincial recovery lag: Barcelona recovers fastest, Lleida slowest.
  Lag only affects speed, NOT total headcount — normalized each month
  so Σ provincial Δjobs = national Δjobs implied by rate change.
- Population growth: simple fixed annual rate per province,
  applied monthly to young_pop only.
"""

import numpy as np
import pandas as pd

# ── PROVINCES ────────────────────────────────────────────────────────────────
PROVINCES = ['barcelona', 'girona', 'lleida', 'tarragona']

# ── DEMOGRAPHICS ─────────────────────────────────────────────────────────────
DEMOGRAPHICS = ['buss', 'ind', 'middle', 'young', 'retired', 'rural', 'unemployed']

# Demographics that participate in employment flows (rural/retired/young excluded)
FLOW_DEMOS   = ['buss', 'ind', 'middle']

# Share of job gains/losses absorbed by each flow demographic
FLOW_SHARES  = {'buss': 0.15, 'ind': 0.30, 'middle': 0.55}

# ── PROVINCIAL RECOVERY LAG MULTIPLIERS ──────────────────────────────────────
# Applied to job recovery speed only (NOT to recession/destruction).
# Normalized each month so total Δjobs matches national rate-implied figure.
# Sources: Idescat provincial unemployment trajectories 2013-2019.
RECOVERY_LAG = {
    'barcelona': 1.10,   # Services, tourism, exports — fastest recovery
    'girona':    1.00,   # Average
    'tarragona': 0.90,   # More industrial/petrochemical — slightly slower
    'lleida':    0.80,   # Agricultural/interior — slowest
}

# During recessions, job destruction is symmetric (no lag — all provinces
# lose jobs proportional to their current employed working-age pool).

# ── ANNUAL POPULATION GROWTH RATES ───────────────────────────────────────────
# IRL Catalan population barely grew 2012-2019; Barcelona grew slightly,
# interior provinces flat or mildly depopulating.
# All growth enters young_pop (new working-age entrants).
ANNUAL_POP_GROWTH = {
    'barcelona': +0.004,   # +0.4%/year
    'girona':    +0.002,   # +0.2%/year
    'tarragona': +0.001,   # +0.1%/year
    'lleida':    -0.001,   # -0.1%/year (mild interior depopulation)
}

# Monthly growth rate derived from annual
MONTHLY_POP_GROWTH = {p: (1 + r) ** (1/12) - 1
                      for p, r in ANNUAL_POP_GROWTH.items()}

# ── INITIAL POPULATIONS (Idescat 2012, pre-election) ─────────────────────────
# unemployed_pop values are ADJUSTED from raw Idescat to match the engine's
# starting unemployment rate of 22.5%.
#
# Adjustment method:
#   working_age_pool(p) = sum of all non-retired demos (including unemployed)
#   target_unemployed(p) = non_unemployed_working_age(p) × (0.225 / 0.775)
#
# Raw Idescat unemployed:  BCN 556295, GIR 67473, LLE 28728, TAR 77586
# Adjusted unemployed:     BCN 730999, GIR 96712, LLE 61503, TAR 100140
#
# The working_age_pool per province is fixed at these initial sums and used
# as the denominator for unemployment rate ↔ headcount conversion.

INITIAL_POP = {
    'barcelona': {
        'buss':       226_980,
        'ind':        739_625,
        'middle':     555_810,
        'young':      655_235,
        'retired':    887_550,
        'rural':      339_015,
        'unemployed': 730_999,   # adjusted from 556_295
    },
    'girona': {
        'buss':        34_272,
        'ind':         58_401,
        'middle':      33_201,
        'young':       87_885,
        'retired':    107_226,
        'rural':      119_133,
        'unemployed':  96_712,   # adjusted from 67_473
    },
    'lleida': {
        'buss':        10_184,
        'ind':         30_134,
        'middle':      17_176,
        'young':       52_668,
        'retired':     70_946,
        'rural':      101_574,
        'unemployed':  61_503,   # adjusted from 28_728
    },
    'tarragona': {
        'buss':        26_934,
        'ind':         82_812,
        'middle':      47_503,
        'young':       90_651,
        'retired':    119_059,
        'rural':       96_815,
        'unemployed': 100_140,   # adjusted from 77_586
    },
}

# ── WORKING-AGE POOL (fixed denominator per province) ────────────────────────
# = all demos except retired.  Computed once from initial populations.
# This is the base against which the unemployment RATE is applied.
# It grows slowly each month with population growth (young_pop grows,
# but working_age_pool as denominator tracks that too — see update logic).

def _working_age_pool(pop_dict):
    """Sum of all non-retired demographics."""
    return sum(v for k, v in pop_dict.items() if k != 'retired')


# ══════════════════════════════════════════════════════════════════════════════
# DemographicsState class
# ══════════════════════════════════════════════════════════════════════════════

class DemographicsState:
    """
    Holds and updates the population state for all provinces.

    Usage
    -----
    demo = DemographicsState()
    # Inside the monthly simulation loop:
    demo.update(prev_unemp_rate, new_unemp_rate)
    # Access:
    demo.pop['barcelona']['middle']
    demo.to_series()   # flat dict suitable for appending to history row
    """

    def __init__(self):
        # Deep copy so mutations don't touch the module-level constant
        self.pop = {p: dict(d) for p, d in INITIAL_POP.items()}

        # Working-age pool per province — updated each month as young grows
        self.wa_pool = {p: _working_age_pool(self.pop[p]) for p in PROVINCES}

        # Verify initial unemployment rate consistency
        self._verify_initial_rate()

    def _verify_initial_rate(self):
        total_unemp = sum(self.pop[p]['unemployed'] for p in PROVINCES)
        total_wa    = sum(self.wa_pool[p] for p in PROVINCES)
        implied_rate = total_unemp / total_wa * 100
        assert abs(implied_rate - 22.5) < 0.2, (
            f"Initial unemployment rate mismatch: {implied_rate:.2f}% (expected 22.5%)"
        )

    # ── MONTHLY UPDATE ───────────────────────────────────────────────────────

    def update(self, prev_unemp_rate: float, new_unemp_rate: float):
        """
        Update population stocks for one month.

        Parameters
        ----------
        prev_unemp_rate : float
            Unemployment rate at end of previous month (%).
        new_unemp_rate : float
            Unemployment rate at end of current month (%).
        """
        delta_rate = new_unemp_rate - prev_unemp_rate   # positive = more unemployment

        # ── Step 1: Population growth (into young_pop) ───────────────────────
        for p in PROVINCES:
            growth = self.wa_pool[p] * MONTHLY_POP_GROWTH[p]
            self.pop[p]['young'] += growth
            # Update working-age pool to reflect new entrants
            self.wa_pool[p] += growth

        # ── Step 2: Employment flows ──────────────────────────────────────────
        if abs(delta_rate) < 1e-6:
            return   # no meaningful change this month

        # National total Δunemployed implied by rate change
        # Δunemployed = Δrate/100 × total_wa_pool
        total_wa     = sum(self.wa_pool[p] for p in PROVINCES)
        total_d_unemp = (delta_rate / 100) * total_wa   # positive = more unemployed

        if delta_rate > 0:
            # ── Recession: job destruction ───────────────────────────────────
            # Distribute proportional to each province's current employed pool.
            # No lag during destruction — pain is proportional.
            employed_pools = {
                p: sum(self.pop[p][d] for d in FLOW_DEMOS)
                for p in PROVINCES
            }
            total_employed = sum(employed_pools.values())

            for p in PROVINCES:
                if total_employed == 0:
                    provincial_share = 1 / len(PROVINCES)
                else:
                    provincial_share = employed_pools[p] / total_employed

                provincial_d_unemp = total_d_unemp * provincial_share

                # Move workers from flow demographics → unemployed
                for demo in FLOW_DEMOS:
                    loss = provincial_d_unemp * FLOW_SHARES[demo]
                    # Clamp: can't remove more than currently employed in that group
                    loss = min(loss, max(self.pop[p][demo], 0))
                    self.pop[p][demo]       -= loss
                    self.pop[p]['unemployed'] += loss

        else:
            # ── Recovery: job creation ───────────────────────────────────────
            # Distribute using recovery lag multipliers, normalized so
            # Σ provincial_d_unemp = total_d_unemp exactly.
            unemp_pools = {p: self.pop[p]['unemployed'] for p in PROVINCES}
            total_unemp_pool = sum(unemp_pools.values())

            # Raw provincial shares: proportional to unemployed pool × lag
            raw_weights = {
                p: (unemp_pools[p] / total_unemp_pool) * RECOVERY_LAG[p]
                if total_unemp_pool > 0 else 1 / len(PROVINCES)
                for p in PROVINCES
            }
            weight_sum = sum(raw_weights.values())
            norm_weights = {p: raw_weights[p] / weight_sum for p in PROVINCES}

            for p in PROVINCES:
                provincial_d_unemp = total_d_unemp * norm_weights[p]
                # total_d_unemp is negative here, so provincial_d_unemp < 0
                # meaning: unemployed decreases, employed increases

                for demo in FLOW_DEMOS:
                    gain = -provincial_d_unemp * FLOW_SHARES[demo]   # positive
                    self.pop[p][demo]         += gain
                    self.pop[p]['unemployed'] -= gain

        # ── Step 3: Rate reconciliation ───────────────────────────────────────
        # Absorb any floating-point residual from lag normalization so that
        # the implied national rate matches new_unemp_rate exactly.
        # Residual is distributed proportionally to unemployed pools
        # (invisible at the per-province level).
        total_wa    = sum(self.wa_pool[p] for p in PROVINCES)
        total_unemp = sum(self.pop[p]['unemployed'] for p in PROVINCES)
        target_unemp = (new_unemp_rate / 100) * total_wa
        residual     = target_unemp - total_unemp
        if abs(residual) > 0.001 and total_unemp > 0:
            for p in PROVINCES:
                share = self.pop[p]['unemployed'] / total_unemp
                self.pop[p]['unemployed'] += residual * share

    # ── ACCESSORS ────────────────────────────────────────────────────────────

    def unemployment_rate(self) -> float:
        """Implied unemployment rate from current headcounts (%)."""
        total_unemp = sum(self.pop[p]['unemployed'] for p in PROVINCES)
        total_wa    = sum(self.wa_pool[p] for p in PROVINCES)
        return (total_unemp / total_wa) * 100

    def total_population(self, province: str) -> float:
        """Total population (all demographics) for a province."""
        return sum(self.pop[province].values())

    def to_series(self) -> dict:
        """
        Flat dict of all population values, suitable for appending to a
        DataFrame row. Keys: demo_{province}_{demo}_pop
        """
        out = {}
        for p in PROVINCES:
            for d in DEMOGRAPHICS:
                out[f'demo_{p}_{d}'] = round(self.pop[p][d])
            out[f'demo_{p}_total']  = round(self.total_population(p))
            out[f'demo_{p}_wa_pool'] = round(self.wa_pool[p])
        return out


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))

    # ── 1. Verify initial state ───────────────────────────────────────────────
    demo = DemographicsState()
    print("=== INITIAL STATE ===")
    print(f"{'Province':<12} {'Unemployed':>12} {'WA Pool':>12} {'Rate %':>8} {'Total Pop':>12}")
    for p in PROVINCES:
        u  = demo.pop[p]['unemployed']
        wa = demo.wa_pool[p]
        t  = demo.total_population(p)
        print(f"{p:<12} {u:>12,.0f} {wa:>12,.0f} {u/wa*100:>8.2f}% {t:>12,.0f}")
    print(f"\nImplied national unemployment rate: {demo.unemployment_rate():.2f}% (target: 22.5%)")

    # ── 2. Simulate IRL unemployment path and check headcount evolution ───────
    # Use annual IRL unemployment rates, interpolate monthly
    IRL_UNEMP = {
        2012: 22.5, 2013: 24.0, 2014: 22.0, 2015: 19.8,
        2016: 17.3, 2017: 14.8, 2018: 12.8, 2019: 11.4,
    }

    # Build monthly series (linear interpolation between annual values)
    annual_months = {2012: 1, 2013: 13, 2014: 25, 2015: 37,
                     2016: 49, 2017: 61, 2018: 73, 2019: 85}
    monthly_unemp = {}
    years = sorted(IRL_UNEMP.keys())
    for i in range(len(years) - 1):
        y0, y1 = years[i], years[i+1]
        m0, m1 = annual_months[y0], annual_months[y1]
        u0, u1 = IRL_UNEMP[y0], IRL_UNEMP[y1]
        for m in range(m0, m1):
            t = (m - m0) / (m1 - m0)
            monthly_unemp[m] = u0 + t * (u1 - u0)
    # fill last year
    for m in range(annual_months[2019], 91):
        monthly_unemp[m] = IRL_UNEMP[2019]

    # Run through the monthly path
    demo = DemographicsState()
    history = []
    prev_rate = 22.5

    for m in range(1, 91):
        yr = 2012 + (m - 1) // 12
        new_rate = monthly_unemp[m]
        demo.update(prev_rate, new_rate)
        row = {'month': m, 'year': yr, 'unemp_rate_engine': new_rate,
               'unemp_rate_implied': demo.unemployment_rate()}
        row.update(demo.to_series())
        history.append(row)
        prev_rate = new_rate

    df = pd.DataFrame(history)

    print("\n=== UNEMPLOYMENT RATE: ENGINE vs IMPLIED ===")
    annual = df.groupby('year').last()[['unemp_rate_engine','unemp_rate_implied']]
    print(annual.round(2).to_string())

    print("\n=== BARCELONA DEMOGRAPHIC EVOLUTION (year-end) ===")
    bcn_cols = [c for c in df.columns if c.startswith('demo_barcelona_') and 'total' not in c and 'wa_pool' not in c]
    print(df.groupby('year').last()[bcn_cols].round(0).to_string())

    print("\n=== TOTAL POPULATION BY PROVINCE (year-end) ===")
    tot_cols = [f'demo_{p}_total' for p in PROVINCES]
    print(df.groupby('year').last()[tot_cols].round(0).to_string())

    print("\n=== PROVINCIAL UNEMPLOYMENT RATES (year-end) ===")
    print(f"{'Year':<6}", end="")
    for p in PROVINCES:
        print(f"{p:>12}", end="")
    print()
    for yr in range(2012, 2020):
        row = df[df['year'] == yr].iloc[-1]
        print(f"{yr:<6}", end="")
        for p in PROVINCES:
            u  = row[f'demo_{p}_unemployed']
            wa = row[f'demo_{p}_wa_pool']
            print(f"{u/wa*100:>12.1f}", end="")
        print()

    os.makedirs('simulations/results', exist_ok=True)
    df.to_csv('simulations/results/demographics_irl_v1.csv', index=False)
    print("\nCSV saved to simulations/results/demographics_irl_v1.csv")
