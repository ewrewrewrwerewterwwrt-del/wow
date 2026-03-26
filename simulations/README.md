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
