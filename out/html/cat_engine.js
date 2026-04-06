(function () {
  "use strict";

  // --- CONSTANTS & MAPPINGS ---

  const FAMILIES = [
    "icr",
    "il",
    "cup",
    "unio",
    "pdcat",
    "fl",
    "psc",
    "cs",
    "ppc",
    "vox",
    "fnc",
    "abs",
  ];

  // Macro Constants
  const STRUCTURAL_GDP_DEFAULT = {
    2012: -0.8,
    2013: -0.8,
    2014: 2.7,
    2015: 4.3,
    2016: 4.2,
    2017: 4.3,
    2018: 3.4,
    2019: 1.3,
  };

  // --- UTILS ---

  function gaussianRandom(mean = 0, stdev = 1) {
    let u = 1 - Math.random();
    let v = Math.random();
    let z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
    return z * stdev + mean;
  }

  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  function familyOf(party, pdcat_split = false, unio_split = false) {
    switch (party) {
      case "ciu":
      case "cdc":
      case "dl":
      case "junts":
      case "jxcat":
        return "icr";
      case "pdcat":
        return pdcat_split ? "pdcat" : "icr";
      case "udc":
      case "unio":
        return unio_split ? "unio" : "icr";
      case "cup":
        return "cup";
      case "icv":
      case "icv-euia":
      case "csqp":
      case "cecp":
      case "ecp":
        return "fl";
      case "pp":
      case "ppc":
        return "ppc";
      case "psoe":
      case "psc":
        return "psc";
      case "vox":
        return "vox";
      case "fnc":
      case "pxc":
        return "fnc";
      case "abstain":
        return "abs";
      default:
        return party;
    }
  }

  function getGovKey(coalition, map, defaultVal) {
    if (!coalition || coalition.length === 0) return defaultVal;
    return map[coalition[0]] || defaultVal;
  }

  function getArrowGoodUp(oldVal, newVal) {
    if (newVal > oldVal) return '<img src="img/arrowup.png"> ';
    if (newVal < oldVal) return '<img src="img/arrowdown.png"> ';
    return "";
  }

  function getArrowBadUp(oldVal, newVal) {
    if (newVal > oldVal)
      return '<img src="img/arrowdown.png" style="transform: rotate(180deg);"> ';
    if (newVal < oldVal)
      return '<img src="img/arrowup.png" style="transform: rotate(180deg);"> ';
    return "";
  }

  // --- ENGINE ---

  function monthPasses(Q) {
    console.log("Running engine tick for", Q.month, Q.year);

    const PROVINCES = Q.parlament_constituencies;
    const DEMOS = Q.parlament_demographics;

    const prev_gdp = Q.gdp_growth;
    const prev_unemployment = Q.unemployment;
    const prev_welfare = Q.welfare_index;
    const prev_cat_spa = Q.cat_spa_relations;
    const prev_indy_mov = Q.independence_movement;
    const prev_indy_trust = Q.independence_trust;
    const prev_dissent = Q.social_dissent;
    const prev_surplus = Q.generalitat_surplus;

    const gen_key = getGovKey(Q.cat_coalition, Q.GEN_MAP, "CiU");
    const gob_key = getGovKey(Q.spanish_coalition, Q.GOB_MAP, "PP_min");

    // 1. GDP GROWTH
    const struc =
      (Q.STRUCTURAL_GDP
        ? Q.STRUCTURAL_GDP[Q.year]
        : STRUCTURAL_GDP_DEFAULT[Q.year]) || 2.0;
    const gob_mod_gdp = Q.GOB_GDP_ABS[gob_key] || 0;
    const gen_mod_gdp = Q.GEN_GDP_ABS[gen_key] || 0;
    const spa_adj = (Q.cat_spa_relations - 38.0) * 0.015;
    const indy_drag =
      -Math.max(0, (Q.independence_movement - Q.independence_trust) / 100) *
      1.2;

    const qe_strip = !Q.ecb_qe && Q.year >= 2015 ? -0.4 : 0.0;
    const gdp_target =
      struc + gob_mod_gdp + gen_mod_gdp + spa_adj + indy_drag + qe_strip;
    const ar = gen_key === "ART155" ? 0.6 : 0.72;
    Q.gdp_growth =
      ar * Q.gdp_growth + (1 - ar) * gdp_target + gaussianRandom(0, 0.28);
    Q.gdp_growth = clamp(Q.gdp_growth, -9, 7);
    Q.gdp_growth_change = getArrowGoodUp(prev_gdp, Q.gdp_growth);

    // 2. UNEMPLOYMENT
    const gdp_m = Q.gdp_growth / 12;
    const recover =
      0.55 *
      1.5 *
      (Q.GEN_UNEMP_MOD[gen_key] || 1.0) *
      (Q.GOB_UNEMP_MOD[gob_key] || 1.0);
    const u_delta = gdp_m < 0 ? -gdp_m * 0.3 : -gdp_m * recover;
    Q.unemployment = clamp(Q.unemployment + u_delta, 10, 36);
    Q.unemployment_change = getArrowBadUp(prev_unemployment, Q.unemployment);

    // 3. SURPLUS & DEBT
    const base_drift = Q.SURPLUS_DRIFT_BY_GEN[gen_key] || 0.02;
    const gdp_surplus_effect = ((Q.gdp_growth / 100) * 0.6) / 12;
    const SURPLUS_FLA_ESCALATION_BONUS = 0.006;

    let fla_bonus = 0.0;
    if (Q.fla_active) {
      fla_bonus += Q.SURPLUS_FLA_BONUS_BY_GOB[gob_key] || 0;
      if (Q.fla_escalated) fla_bonus += SURPLUS_FLA_ESCALATION_BONUS;
    }

    // Then include fla_bonus in the surplus update:
    Q.generalitat_surplus = clamp(
      Q.generalitat_surplus +
        base_drift +
        fla_bonus +
        gdp_surplus_effect +
        gaussianRandom(0, 0.1),
      -5,
      2,
    );
    Q.generalitat_surplus_change = getArrowGoodUp(
      prev_surplus,
      Q.generalitat_surplus,
    );

    const deficit_flow = -(Q.generalitat_surplus / 12);
    const interest = (Q.public_debt * 0.02) / 12;
    const gdp_debt_effect = -gdp_m * 0.18;
    Q.public_debt = clamp(
      Q.public_debt + deficit_flow + interest + gdp_debt_effect,
      0,
      80,
    );

    // 4. WELFARE
    const spending_pressure = Q.WELFARE_SPENDING_BY_GEN[gen_key] || 0;
    const gdp_welfare_boost = gdp_m * 0.1;
    let welfare_delta =
      spending_pressure + gdp_welfare_boost + gaussianRandom(0, 0.2);
    welfare_delta =
      welfare_delta > 0
        ? Math.min(welfare_delta, 0.8)
        : Math.max(welfare_delta, -1.2);
    Q.welfare_index = clamp(Q.welfare_index + welfare_delta, 20, 100);

    // 5. CAT-SPA RELATIONS
    const CAT_SPA_POST155_FLOOR = 18.0;
    const CAT_SPA_POST155_RECOVERY_CAP = 0.08;

    function getCatSpaDrift(gob_key, gen_key) {
      const key = `${gob_key},${gen_key}`;
      if (Q.CAT_SPA_DRIFT[key] !== undefined) return Q.CAT_SPA_DRIFT[key];
      if (["PP_abs", "PP_min", "PP_care", "PP_VOX"].includes(gob_key))
        return -0.15;
      if (["PSOE_min", "PSOE_maj"].includes(gob_key)) return +0.1;
      if (gob_key === "Podemos") return +0.15;
      return -0.05;
    }

    let cat_spa_drift;
    if (gen_key === "ART155") {
      cat_spa_drift = -2.0;
    } else {
      cat_spa_drift = getCatSpaDrift(gob_key, gen_key);
      // Post-155 recovery cap
      if (
        Q.art155_ever &&
        Q.cat_spa_relations < CAT_SPA_POST155_FLOOR &&
        cat_spa_drift > 0
      ) {
        cat_spa_drift = Math.min(cat_spa_drift, CAT_SPA_POST155_RECOVERY_CAP);
      }
    }
    Q.cat_spa_relations = clamp(
      Q.cat_spa_relations + cat_spa_drift + gaussianRandom(0, 0.6),
      5,
      80,
    );

    // 6. INDEPENDENCE MOVEMENT & TRUST
    const imov_reversion = 0.035 * (52.0 - Q.independence_movement);
    const phase = (Q.month - 1) * ((2 * Math.PI) / 12);

    // In constants block (alongside the other INDY_ constants):
    const AMPLITUDE_MOV_WEIGHT = 4.0; // tune upward to widen the range
    const AMPLITUDE_TRUST_WEIGHT = 0.5; // 0 = trust has no effect, 1 = full effect

    // Replace the seasonal_amplitude line:
    const mov_norm = clamp((Q.independence_movement - 25) / (95 - 25), 0, 1);
    const trust_inv = clamp(1 - (Q.independence_trust - 15) / (60 - 15), 0, 1);
    // trust_inv = 1 when trust is at floor (15), 0 when at ceiling (60)

    const seasonal_amplitude = clamp(
      1.0 +
        AMPLITUDE_MOV_WEIGHT *
          mov_norm *
          (AMPLITUDE_TRUST_WEIGHT + AMPLITUDE_TRUST_WEIGHT * trust_inv),
      1.0,
      4.5,
    );

    const seasonal = seasonal_amplitude * Math.cos(phase - (8 * Math.PI) / 6);
    Q.independence_movement = clamp(
      Q.independence_movement +
        imov_reversion +
        seasonal +
        gaussianRandom(0, 0.7),
      25,
      95,
    );

    const trust_drift = gen_key === "ART155" ? -1.8 : 0.06;
    Q.independence_trust = clamp(
      Q.independence_trust + trust_drift + gaussianRandom(0, 0.4),
      15,
      60,
    );

    // 7. SOCIAL DISSENT
    let unemp_contrib;
    if (Q.unemployment > 20) {
      unemp_contrib = 30 + (Q.unemployment - 20) * 2.5;
    } else {
      unemp_contrib = Math.max(0, (Q.unemployment - 10) * 3.0);
    }
    const welfare_contrib = (100 - Q.welfare_index) * 0.35;
    const gob_mod_diss = Q.GOB_DISSENT_MOD[gob_key] || 0;
    const gen_mod_diss = Q.GEN_DISSENT_MOD[gen_key] || 0;
    const channeling_discount = (Q.podemos_channeling || 0) * 12.0;

    let eq =
      unemp_contrib +
      welfare_contrib +
      gob_mod_diss +
      gen_mod_diss -
      channeling_discount;
    eq = clamp(eq, 15, 92);

    const gap = eq - Q.social_dissent;
    Q.social_dissent = clamp(
      Q.social_dissent + 0.04 * gap + gaussianRandom(0, 0.8),
      0,
      100,
    );

    if (Q.podemos_surged) {
      const dissent_falling = Q.social_dissent < prev_dissent - 0.5;
      if (dissent_falling) {
        Q.podemos_channeling = Math.min(
          1.0,
          (Q.podemos_channeling || 0) + 0.01,
        );
      } else {
        Q.podemos_channeling = Math.max(
          0.0,
          (Q.podemos_channeling || 0) - 0.03,
        );
      }
    }

    // --- VOTE ALLOCATION ---

    const d_vars = [
      Q.independence_movement - prev_indy_mov,
      Q.independence_trust - prev_indy_trust,
      0, // dissent handled nonlinearly
      0, // welfare handled nonlinearly
      0, // cat_spa handled nonlinearly
      Q.unemployment - prev_unemployment,
      Q.podemos_channeling || 0,
    ];

    const d_dissent = Q.social_dissent - prev_dissent;
    const d_welfare = Q.welfare_index - prev_welfare;
    const d_cat_spa = Q.cat_spa_relations - prev_cat_spa;

    const matrices = Q.PARLAMENT_MATRICES;
    if (!matrices) return;

    for (const prov of PROVINCES) {
      for (const demo of DEMOS) {
        let delta_vec = new Array(FAMILIES.length).fill(0);

        // Matrix update
        const T_base = matrices.BASE_T;
        const T_demo = matrices._DELTA_T[demo] || [];
        const T_prov = matrices._DELTA_PROV[prov] || [];

        for (let i = 0; i < FAMILIES.length; i++) {
          for (let j = 0; j < d_vars.length; j++) {
            const val =
              T_base[i][j] +
              (T_demo[i] ? T_demo[i][j] : 0) +
              (T_prov[i] ? T_prov[i][j] : 0);
            delta_vec[i] += val * d_vars[j];
          }
        }

        // Nonlinear Scaling
        const nl_d = Q.parlament_NONLIN_DEMO_SCALE[demo];
        const nl_p = Q.parlament_NONLIN_PROV_SCALE[prov];

        // Simplified Nonlinear Handlers
        if (d_dissent > 0) {
          const total_in = d_dissent * 0.04 * nl_d.dissent * nl_p.dissent;
          delta_vec[FAMILIES.indexOf("fl")] += total_in * 0.5;
          delta_vec[FAMILIES.indexOf("abs")] += total_in * 0.5;
          delta_vec[FAMILIES.indexOf("icr")] -= total_in;
        }

        if (d_welfare < 0) {
          const total_out =
            Math.abs(d_welfare) * 0.05 * nl_d.welfare * nl_p.welfare;
          delta_vec[FAMILIES.indexOf("cup")] += total_out;
          delta_vec[FAMILIES.indexOf("icr")] -= total_out;
        }

        if (d_cat_spa < 0) {
          const total_in =
            Math.abs(d_cat_spa) * 0.06 * nl_d.cat_spa * nl_p.cat_spa;
          delta_vec[FAMILIES.indexOf("cs")] += total_in;
          delta_vec[FAMILIES.indexOf("icr")] -= total_in;
        }

        // ── TRUST DISENGAGEMENT ──────────────────────────────────────────
        // Falling indytrust at high indymov → icr+il bleed into abs
        const TRUST_DISENGAGE_THRESHOLD = 60.0;
        const TRUST_DISENGAGE_COEFF = 0.08;
        if (
          d_vars[1] < 0 &&
          Q.independence_movement > TRUST_DISENGAGE_THRESHOLD
        ) {
          const indy_factor =
            (Q.independence_movement - TRUST_DISENGAGE_THRESHOLD) /
            (100.0 - TRUST_DISENGAGE_THRESHOLD);
          const abs_gain =
            TRUST_DISENGAGE_COEFF *
            Math.abs(d_vars[1]) *
            indy_factor *
            nl_d.cup_trust *
            nl_p.cup_trust;
          delta_vec[FAMILIES.indexOf("abs")] += abs_gain;
          delta_vec[FAMILIES.indexOf("icr")] -= abs_gain * 0.55;
          delta_vec[FAMILIES.indexOf("il")] -= abs_gain * 0.45;
        }

        // ── ICR SATURATION ───────────────────────────────────────────────
        // Above indymov=82, further rises no longer convert to icr
        const ICR_SATURATION_THRESHOLD = 82.0;
        const ICR_SATURATION_COEFF = 0.045;
        if (
          d_vars[0] > 0 &&
          Q.independence_movement > ICR_SATURATION_THRESHOLD
        ) {
          const saturation =
            (Q.independence_movement - ICR_SATURATION_THRESHOLD) /
            (100.0 - ICR_SATURATION_THRESHOLD);
          const offset = ICR_SATURATION_COEFF * d_vars[0] * saturation;
          delta_vec[FAMILIES.indexOf("icr")] += offset; // gives back what matrix bled
          delta_vec[FAMILIES.indexOf("abs")] -= offset;
        }

        // ── CUP TRUST EXTRA
        // Below indytrust=30, falling trust amplifies CUP gains at icr's expense
        const CUP_TRUST_THRESHOLD = 30.0;
        const CUP_TRUST_EXTRA = 0.025;
        if (
          Math.abs(d_vars[1]) > 1e-9 &&
          Q.independence_trust < CUP_TRUST_THRESHOLD
        ) {
          const depth =
            (CUP_TRUST_THRESHOLD - Q.independence_trust) / CUP_TRUST_THRESHOLD;
          const extra_cup =
            -CUP_TRUST_EXTRA *
            d_vars[1] *
            depth *
            nl_d.cup_trust *
            nl_p.cup_trust;
          delta_vec[FAMILIES.indexOf("cup")] += extra_cup;
          delta_vec[FAMILIES.indexOf("icr")] -= extra_cup * 0.7;
          delta_vec[FAMILIES.indexOf("il")] -= extra_cup * 0.3;
        }

        // ── ART155 BACKLASH
        // PPC and PSC supported 155 → penalised while gen=ART155
        if (gen_key === "ART155") {
          const punishment = 0.55;
          delta_vec[FAMILIES.indexOf("ppc")] -= punishment * 0.4;
          delta_vec[FAMILIES.indexOf("psc")] -= punishment * 0.6;
          delta_vec[FAMILIES.indexOf("fl")] += punishment * 0.5;
          delta_vec[FAMILIES.indexOf("il")] += punishment * 0.5;
        }

        // ── PSC RECOVERY
        // Post-Navarro PSC slowly recovers from abs+fl
        if (Q.psc_recovery_mult > 0) {
          delta_vec[FAMILIES.indexOf("psc")] += 0.015 * Q.psc_recovery_mult;
          delta_vec[FAMILIES.indexOf("abs")] -= 0.015 * Q.psc_recovery_mult;
          // When relations fall, PSC loses those same voters
          if (d_cat_spa < 0) {
            delta_vec[FAMILIES.indexOf("psc")] +=
              0.45 * d_cat_spa * Q.psc_recovery_mult;
            delta_vec[FAMILIES.indexOf("fl")] -=
              0.45 * d_cat_spa * Q.psc_recovery_mult;
          }
        }

        // Apply to Q support variables
        const family_deltas = {};
        FAMILIES.forEach((f, idx) => (family_deltas[f] = delta_vec[idx]));

        // Map families to active parties
        const party_deltas = {};
        const parties_and_abs = [...Q.parties, "abstain"];
        parties_and_abs.forEach((p) => {
          const f = familyOf(p, Q.pdcat_split, Q.unio_split);
          if (!party_deltas[f]) party_deltas[f] = [];
          party_deltas[f].push(p);
        });

        FAMILIES.forEach((f) => {
          const delta = family_deltas[f];
          const parties = party_deltas[f] || [];
          // Find the active party (one with support > 0)
          let active_party = null;
          for (const p of parties) {
            if (Q[p + "_parlament_" + prov + "_" + demo + "_support"] > 0) {
              active_party = p;
              break;
            }
          }
          if (!active_party && parties.length > 0) active_party = parties[0];

          if (active_party) {
            const key =
              active_party + "_parlament_" + prov + "_" + demo + "_support";
            Q[key] = Math.max(0, (Q[key] || 0) + delta);
          }
        });

        // Renormalize cell
        let total = 0;
        parties_and_abs.forEach((p) => {
          total += Q[p + "_parlament_" + prov + "_" + demo + "_support"] || 0;
        });
        if (total > 0) {
          parties_and_abs.forEach((p) => {
            const key = p + "_parlament_" + prov + "_" + demo + "_support";
            Q[key] = (Q[key] / total) * 100.0;
          });
        }
      }
    }

    updateLocalBarcelona(
      Q,
      prev_indy_mov,
      prev_indy_trust,
      prev_dissent,
      prev_welfare,
      prev_cat_spa,
      prev_unemployment,
    );
  }

  // --- LOCAL BARCELONA TICK ---
  // ICR family for local BCN: ciu/cdc/dl/jxcat/junts/pdcat are one bloc.
  // Only the currently active ICR party (the one with support > 0) receives
  // the delta. "ciu" is the canonical key for matrix lookups throughout.
  const BCN_ICR_PARTIES = new Set([
    "ciu",
    "cdc",
    "dl",
    "jxcat",
    "junts",
    "pdcat",
  ]);
  const BCN_ICR_CANONICAL = "ciu";

  function _bcnMatrixKey(party) {
    return BCN_ICR_PARTIES.has(party) ? BCN_ICR_CANONICAL : party;
  }

  function updateLocalBarcelona(
    Q,
    prev_indy_mov,
    prev_indy_trust,
    prev_dissent,
    prev_welfare,
    prev_cat_spa,
    prev_unemployment,
  ) {
    const bcnMatrices = Q.LOCAL_BCN_MATRICES;
    if (!bcnMatrices) return;

    const BCN_PARTIES = Q.parties_bcn;
    const REVERSION = bcnMatrices.BCN_MEAN_REVERSION_SPEED || 0.012;

    const bcn_d = [
      Q.independence_movement - prev_indy_mov,
      Q.independence_trust - prev_indy_trust,
      Q.social_dissent - prev_dissent,
      Q.welfare_index - prev_welfare,
      Q.cat_spa_relations - prev_cat_spa,
      Q.unemployment - prev_unemployment,
      Q.podemos_channeling || 0,
    ];

    // Find the active ICR party (the one with support > 0)
    const icrCandidates = BCN_PARTIES.filter((p) => BCN_ICR_PARTIES.has(p));
    const activeIcr =
      icrCandidates.find((p) => (Q[`${p}_local_barcelona_support`] || 0) > 0) ??
      icrCandidates[0] ??
      null;

    for (const party of BCN_PARTIES) {
      // Skip inactive ICR parties — only the active one carries support
      if (BCN_ICR_PARTIES.has(party) && party !== activeIcr) continue;

      const matrixKey = _bcnMatrixKey(party);
      const key = `${party}_local_barcelona_support`;
      if (Q[key] === undefined) {
        Q[key] = bcnMatrices.BCN_BASELINE[matrixKey] || 0.0;
      }

      const sens = bcnMatrices.BCN_SENSITIVITY[matrixKey] || new Array(7).fill(0);
      let delta = 0;
      for (let i = 0; i < 7; i++) delta += sens[i] * bcn_d[i];

      // Post-2015 nonlinear surge: high IM amplifies established indy parties when
      // trust is healthy, and radical parties (CUP/primaries) when trust is low.
      if (Q.year > 2015 && Q.independence_movement > 60) {
        const imSurplus = (Q.independence_movement - 60) * 0.1;
        if (BCN_ICR_PARTIES.has(party) || party === "erc") {
          const trustFactor = clamp((Q.independence_trust - 25) / 20, 0, 1);
          const coeff = party === "erc" ? 0.35 : 0.22;
          delta += coeff * imSurplus * trustFactor;
        } else if (party === "cup" || party === "primaries") {
          const frustrationFactor = clamp((38 - Q.independence_trust) / 20, 0, 1);
          delta += 0.18 * imSurplus * frustrationFactor;
        }
      }

      const baseline = bcnMatrices.BCN_BASELINE[matrixKey] || 0.0;
      delta += REVERSION * (baseline - Q[key]);

      Q[key] = clamp(Q[key] + delta, 0.0, 100.0);
    }

    // Renormalise city-wide
    let total = 0;
    for (const party of BCN_PARTIES)
      total += Q[`${party}_local_barcelona_support`] || 0;
    if (total > 0) {
      for (const party of BCN_PARTIES) {
        const key = `${party}_local_barcelona_support`;
        Q[key] = (Q[key] / total) * 100.0;
      }
    }
  }

  window.engineTick = monthPasses;
})();
