# Route to Ítaca — Simulation Suite

This simulation suite exists to iterate on the core socio-economic-political engine of the game.

## Core Modules

- **`economic_engine.py` (v4)**: The heart of the simulation. A monthly discrete-time engine tracking:
  - Macroeconomic variables (GDP growth, unemployment, debt, surplus).
  - Socio-political indices (Independence movement/trust, social dissent, welfare index).
  - A declarative **Event System** (9-N, 1-O, Art. 155, Diades, etc.) that triggers state changes and fading pulses.
  - Party-pair interaction matrices (Madrid vs. Barcelona) driving diplomatic relations.

- **`vote_model.py`**: A continuous support model for 12 party families across 4 provinces and 7 demographics.
  - Uses a **Transfer Matrix** architecture: `support += T @ Δvars`.
  - Guarantees vote conservation (column-sum zero) mathematically.
  - Handles non-linear dynamics for social dissent, leadership trust, and "useful vote" consolidation.
  - Supports flag-based electoral events (JxSí, Art. 155 backlash, etc.).

- **`demographics.py`**: Tracks population stocks (7.5M+ individuals) across provinces.
  - Updates headcounts based on economic engine signals (unemployment rate).
  - Implements provincial recovery lags.

- **`calibration_runner.py`**: Integrates all modules to run the full 90-month loop.
  - Compares simulated seat counts against historical "anchor" targets (2012, 2015, 2017).
  - Current performance: **Seat RMSE ~1.39** (with Art. 155 backlash and Iceta recovery calibration).

## Technical Overview: Simulation Architecture

The simulation is built on three core pillars:

### 1. System Dynamics & Macro-Economic Feedback

The engine models the economy not as a black box, but as a series of coupled differential equations (discretized monthly).

- **The Debt-FLA Trap**: High debt triggers the FLA (Fons de Liquiditat Autonòmica), which in turn imposes structural surplus requirements, cutting welfare and increasing social dissent.
- **GDP Sensitivity**: Political instability (measured as the gap between Independence Movement and Trust) creates an "uncertainty drag" on growth.

### 2. Transfer Matrix Support Model

The vote model uses a **zero-sum transfer matrix**.

- Every gain in one party is mathematically balanced by a proportional loss in another, ensuring 100% vote conservation without arbitrary post-processing.
- Demographic weights (buss, ind, retired, etc.) provide granular behavior; for instance, "retired" voters are 1.8x more sensitive to welfare changes but less responsive to social dissent.

### 3. Declarative Event Machine

The simulation uses a declarative state machine for political events. Events like the **1-O Referendum** or **Art. 155** set persistent state flags that trigger long-term pulses (e.g., the DUI-155 cluster causes a multi-month confidence shock).

## Usage

### Run Historical Simulation

To run the standard IRL baseline and generate the summary charts:

```bash
python3 economic_engine.py
```

### Run Vote Model Calibration

To verify the vote model against historical election results:

```bash
python3 calibration_runner.py
```

### Auto-Tune Matrix Coefficients

To optimize the transfer matrix to better match historical seat counts:

```bash
python3 calibration_runner.py --tune
```

---

## Local Election Modules

Two additional modules extend the simulation suite to cover Catalan **municipal elections** (May 2015, May 2019).

- **`local_elections.py`**: The unified local election model. Covers five electoral systems:
  - **Barcelona city council**: full 8-party demographic matrix, monthly tick (sensitivity vectors per party), D'Hondt allocation with 5% threshold.
  - **Red Belt cities** (Hospitalet, Badalona, Terrassa, etc.): PSC damage / challenger score system driven by corruption and social dissent signals.
  - **Interior Catalonia**: CiU decay model (corruption events, welfare, PDeCat/Unió splits) and ERC-CUP-FNC challenger race.
  - **Provincial capitals**: Parliament-extrapolated results.
  - **Decorative locations**: map anchors, Parliament matrix only.
  - Handles party lifecycle events: Unió split from CDC (m=36), PDeCat formation (m=50), Trias candidacy bonus (2015 only), PP→PSC/Cs post-ART155 consolidation (m=67), Primàries CUP split (m=81).

- **`local_calibrator.py`**: Drives the v4 economic engine over Aug 2012 – Dec 2019 (90 months) and fires local election resolution at the correct months.
  - Fires IRL corruption events (Pujol confession, second CDC wave) and structural party splits on schedule.
  - Compares simulated seat counts and municipal winners against verified IRL targets for Barcelona, Red Belt, and Interior municipalities.
  - Combined loss function: Red Belt / Interior winner mismatches (1pt each) + Barcelona seat RMSE (scaled).

### IRL Calibration Targets

| Location | 2015 winner | 2019 winner |
| --- | --- | --- |
| Barcelona (41 seats) | BComú 11, CiU 10, Cs 5, ERC 5 | BComú 10, ERC 10, JxCat 5, PSC 8 |
| Red Belt cities | PSC / BComú / CiU depending on location | see `RB_HISTORICAL` |
| Interior municipalities | CiU holdouts / ERC challengers | see `INT_HISTORICAL` |

### Run Local Election Simulation

```bash
python -X utf8 local_calibrator.py
```

### Suppress per-month output

```bash
python -X utf8 local_calibrator.py --quiet
```

### Auto-Tune Local Model Coefficients

Runs Nelder-Mead optimisation over Red Belt and Interior score formula coefficients:

```bash
python -X utf8 local_calibrator.py --tune [--trials N]
```

`--trials N` runs N random restarts and returns the best result.
