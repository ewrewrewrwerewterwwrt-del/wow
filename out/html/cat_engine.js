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
      case "erc":
        // Indy-Left family slot. SI is intentionally left out (it phases out).
        return "il";
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

  // Coalition lists (JxSí / JxCat) absorb the family deltas of the parties folded
  // into them. Membership is driven SOLELY by the *_in_* flags set at formation,
  // so a component that is NOT folded in (e.g. CUP when cup_in_jxsi is false)
  // keeps receiving its own delta and stays a live party. The icr base is
  // unconditional because the coalition cannot exist without its CiU-bloc core.
  const COALITION_PARTIES = ["jxsi", "jxcat"];

  function coalitionFamilies(Q, party) {
    switch (party) {
      case "jxsi": {
        // JxSí = CiU-bloc (icr) + ERC (il) concentration list, + CUP if folded.
        const fams = ["icr"];
        if (Q.erc_in_jxsi) fams.push("il");
        if (Q.cup_in_jxsi) fams.push("cup");
        return fams;
      }
      case "jxcat": {
        // JxCat = post-CDC (icr) space; ERC/CUP only if folded in.
        const fams = ["icr"];
        if (Q.erc_in_jxcat) fams.push("il");
        if (Q.cup_in_jxcat) fams.push("cup");
        return fams;
      }
      default:
        return null;
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

        // Coalition routing for this cell: family -> coalition list party.
        // Only applies where the coalition is actually fielded (support > 0);
        // which families it absorbs is governed by the *_in_* flags, so a
        // non-member party keeps its own delta rather than feeding the list.
        const coalition_route = {};
        for (const cp of COALITION_PARTIES) {
          const cp_key = cp + "_parlament_" + prov + "_" + demo + "_support";
          if ((Q[cp_key] || 0) <= 0) continue;
          const fams = coalitionFamilies(Q, cp);
          if (!fams) continue;
          for (const cf of fams) coalition_route[cf] = cp;
        }

        FAMILIES.forEach((f) => {
          const delta = family_deltas[f];
          // Folded-in families route to the coalition list; everything else
          // goes to the normal active party of that family.
          let recipient = coalition_route[f] || null;
          if (!recipient) {
            const parties = party_deltas[f] || [];
            // Find the active party (one with support > 0)
            for (const p of parties) {
              if (Q[p + "_parlament_" + prov + "_" + demo + "_support"] > 0) {
                recipient = p;
                break;
              }
            }
            if (!recipient && parties.length > 0) recipient = parties[0];
          }

          if (recipient) {
            const key =
              recipient + "_parlament_" + prov + "_" + demo + "_support";
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

    // Spanish Congreso evolves off the same freshly-updated Catalan macro.
    monthPassesCongreso(Q);
  }

  // --- LOCAL BARCELONA TICK ---
  // ICR family for local BCN: ciu/cdc/dl/jxcat/junts/pdcat are one bloc.
  // jxsi is included as the united-list carrier (it borrows ciu's matrix profile
  // and only ever carries support when fielded via jxsi_united_local).
  // Only the currently active ICR party (the one with support > 0) receives
  // the delta. "ciu" is the canonical key for matrix lookups throughout.
  const BCN_ICR_PARTIES = new Set([
    "ciu",
    "cdc",
    "dl",
    "jxcat",
    "junts",
    "pdcat",
    "jxsi",
  ]);
  const BCN_ICR_CANONICAL = "ciu";

  function _bcnMatrixKey(party) {
    return BCN_ICR_PARTIES.has(party) ? BCN_ICR_CANONICAL : party;
  }

  // A "united" Barcelona list (jxsi/jxcat) only contests the city when its
  // *_united_local flag is set; which components it has folded in follows the
  // same parlament membership flags used everywhere else. Returns
  // { carrier, absorbs:[…] } for the active list, or null.
  function bcnUnitedCoalition(Q) {
    if (Q.jxsi_united_local && (Q.jxsi_local_barcelona_support || 0) > 0) {
      const absorbs = [];
      if (Q.erc_in_jxsi) absorbs.push("erc");
      if (Q.cup_in_jxsi) absorbs.push("cup");
      return { carrier: "jxsi", absorbs };
    }
    if (Q.jxcat_united_local && (Q.jxcat_local_barcelona_support || 0) > 0) {
      const absorbs = [];
      if (Q.erc_in_jxcat) absorbs.push("erc");
      if (Q.cup_in_jxcat) absorbs.push("cup");
      return { carrier: "jxcat", absorbs };
    }
    return null;
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

    // United Barcelona list: components folded into it at formation are held at
    // 0 here, and the carrier mean-reverts toward the SUM of their baselines.
    const united = bcnUnitedCoalition(Q);
    const bcnAbsorbed = united ? new Set(united.absorbs) : null;

    for (const party of BCN_PARTIES) {
      // Components folded into an active united list stay at 0 (their support was
      // merged into the carrier at formation); don't let mean-reversion revive them.
      if (bcnAbsorbed && bcnAbsorbed.has(party)) continue;
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

      let baseline = bcnMatrices.BCN_BASELINE[matrixKey] || 0.0;
      // A united carrier reverts toward the combined baseline of its components,
      // so the merged list doesn't decay toward a single party's equilibrium.
      if (united && party === united.carrier) {
        for (const c of united.absorbs)
          baseline += bcnMatrices.BCN_BASELINE[_bcnMatrixKey(c)] || 0.0;
      }
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

  // ===========================================================================
  // Spanish Congreso monthly engine.
  //
  // Ported from simulations/spa_vote_model.py (the calibrated reference), but
  // operates DIRECTLY on the in-game support keys (`{party}_congreso_{c}_support`)
  // defined in root.scene.dry — there is no separate "family" namespace.
  //
  // Behaviour mirrors monthPasses() in cat_engine.js: it runs once per month
  // (called from post_event.scene.dry AFTER window.engineTick), reads the
  // Catalan macro variables on Q, derives Spanish-level deltas, and evolves
  // every constituency's party support, renormalising to 100 (abstain included).
  //
  // Conventions that matter:
  //  - Abstention lives under the `abstain` key (abstain_congreso_{c}_support),
  //    NOT `abs` — matching the resolver in election_algorithm.scene.dry.
  //  - A party is ACTIVE in a constituency iff its support > 0. Formation scenes
  //    inject support to bring a party to life; folded coalition components are
  //    zeroed by their formation scene and then skipped here (so mean-reversion /
  //    noise can't zombie them back — the trap documented in design/LEARNINGS.md).
  //  - Coefficients attach by CANONICAL key (up→podemos, dl/jxsi/…→ciu, etc.).
  //  - Coalition carriers (up / nsuma / jxsi / jxcat) are resolved live: cross-
  //    party effects target whichever key currently carries that bloc's vote.
  // ===========================================================================

  const ABSTAIN = "abstain";
  const URBAN_CONSTITUENCIES = ["catalunya", "euskadi", "valencia", "balears"];

  // CiU-bloc keys, in priority order for "which list is live".
  const CONV_BLOC = ["jxsi", "jxcat", "junts", "pdcat", "dl", "cdc", "ciu"];

  // In-game key -> canonical coefficient key.
  const CANONICAL = {
    up: "podemos",
    sumar: "podemos",
    cdc: "ciu",
    dl: "ciu",
    pdcat: "ciu",
    jxsi: "ciu",
    jxcat: "ciu",
    junts: "ciu",
    amaiur: "ehbildu",
    nos: "bng",
  };

  // Per unit of each driver delta, how much the canonical family shifts.
  // Values carried over verbatim from spa_vote_model.py ECON_BASE_DEFAULT.
  const ECON = {
    //               g(gdp)  u(unemp) w(welfare) d(dissent)
    pp:        { g:  0.06, u: -0.05, w:  0.03, d: -0.04 },
    psoe:      { g:  0.06, u: -0.04, w:  0.04, d: -0.03 },
    psc:       { g:  0.06, u: -0.04, w:  0.04, d: -0.03 }, // PSC mirrors PSOE econ
    podemos:   { g: -0.04, u:  0.06, w: -0.04, d:  0.07 },
    cs:        { g: -0.02, u:  0.03, w: -0.01, d:  0.02 },
    vox:       { g: -0.01, u:  0.01, w: -0.01, d:  0.02 },
    iu:        { g: -0.03, u:  0.04, w: -0.03, d:  0.05 },
    mpais:     { g: -0.02, u:  0.03, w: -0.02, d:  0.04 },
    abstain:   { g: -0.02, u:  0.02, w: -0.02, d:  0.03 },
    nsuma:     { g:  0.05, u: -0.04, w:  0.03, d: -0.03 },
    upn:       { g:  0.01, u:  0.00, w:  0.01, d: -0.01 },
    gbai:      { g:  0.00, u:  0.01, w: -0.01, d:  0.02 },
    pnv:       { g:  0.01, u:  0.00, w:  0.01, d: -0.01 },
    ehbildu:   { g: -0.01, u:  0.01, w: -0.01, d:  0.01 },
    bng:       { g:  0.00, u:  0.01, w: -0.01, d:  0.01 },
    compromis: { g: -0.02, u:  0.03, w: -0.02, d:  0.05 },
    mes:       { g: -0.01, u:  0.02, w: -0.01, d:  0.04 },
    // Catalan independence space — driven by cat_spa, not national economics
    erc:       { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    ciu:       { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    cup:       { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    fr:        { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    // Rest minors — zero econ sensitivity, driven by reversion + noise
    cc:        { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    prc:       { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    te:        { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    fac:       { g:  0.00, u:  0.00, w:  0.00, d:  0.00 },
    // UPyD — collapses over 2012-2015; mild econ, real action is the decay term
    upyd:      { g:  0.02, u: -0.01, w:  0.01, d: -0.02 },
  };

  // Minor "rest" regional parties: mean-revert toward a stable base instead of
  // following national trends, with scaled-down noise so they don't walk to 0.
  const MINOR_REST = new Set(["cc", "prc", "te", "fac"]);
  const MINOR_REST_TARGETS = { cc: 1.0, prc: 0.12, te: 0.08, fac: 0.4 };

  // Named scalar constants (from spa_vote_model.py DEFAULTS).
  const P = {
    gov_gdp_boost: 0.041,
    corr_pp_cs_urban: 0.00075,
    corr_pp_cs_base: 0.00041,
    corr_pp_abs: 0.00031,
    corr_psoe_pod: 0.0007,
    corr_psoe_abs: 0.00031,
    cat_spa_indy: 0.052,
    cat_spa_cs_cat: 0.041,
    cat_spa_pp_psoe: 0.041,
    cat_spa_cs_pod: 0.031,
    dom_momentum: 0.03,
    hold_decay: 0.0088,
    hold_recovery: 0.0051,
    noise_stdev: 0.164,
    noise_stdev_minor: 0.008,
    minor_reversion_rate: 0.008,
    channeling_rate: 0.0024,
    psoe_recover_rate: 0.0027,
    psoe_leadership_rate: 0.0123,
    pp_leadership_rate: 0.0155,
    upyd_decay_rate: 0.035, // UPyD bleed/tick → ~0 by 2015
  };

  // --- UTILS (congreso; gaussianRandom/clamp reused from the Parlament engine above) ---

  function sup(Q, p, c) {
    return Q[p + "_congreso_" + c + "_support"] || 0;
  }
  function setSup(Q, p, c, v) {
    Q[p + "_congreso_" + c + "_support"] = Math.max(0, v);
  }

  function coeffKey(p) {
    return CANONICAL[p] || p;
  }

  // First key in `candidates` that is live (support > 0) in c, else fallback.
  function liveAmong(Q, c, candidates, fallback) {
    for (const p of candidates) if (sup(Q, p, c) > 0) return p;
    return fallback;
  }

  // Live in-game key carrying a given bloc's vote in constituency c.
  function ppKey(Q, c) {
    return liveAmong(Q, c, ["nsuma", "pp"], "pp");
  }
  function podKey(Q, c) {
    return liveAmong(Q, c, ["up", "podemos"], "podemos");
  }
  function psoeKey(Q, c) {
    if (c === "catalunya" && Q.psc_split) return "psc";
    return "psoe";
  }
  function convKey(Q, c) {
    return liveAmong(Q, c, CONV_BLOC, "ciu");
  }
  function ercKey(Q, c) {
    // ERC if it runs standalone, else its vote sits in the live CiU-bloc carrier
    return sup(Q, "erc", c) > 0 ? "erc" : convKey(Q, c);
  }

  function isIncumbent(canonical, Q) {
    const gob = Q.spanish_coalition || [];
    for (const party of gob) {
      const p = ("" + party).toLowerCase();
      if (canonical === "pp" && ["pp", "ppc", "nsuma"].includes(p)) return true;
      if (canonical === "nsuma" && ["nsuma", "pp"].includes(p)) return true;
      if ((canonical === "psoe" || canonical === "psc") &&
          ["psoe", "psc"].includes(p)) return true;
      if (canonical === "podemos" &&
          ["podemos", "up", "unidas_podemos"].includes(p)) return true;
      if (canonical === "iu" && ["iu", "unidas_podemos"].includes(p)) return true;
      if (canonical === "cs" && p === "cs") return true;
      if (canonical === p) return true;
    }
    return false;
  }

  // Active parties (support > 0) in c, abstain included.
  function activeParties(Q, c) {
    const list = (Q["congreso_parties_" + c] || []).concat([ABSTAIN]);
    return list.filter((p) => sup(Q, p, c) > 0);
  }

  // --- DOMINANCE HOLDS (run once per month, before deltas) ---

  function updateHolds(Q, constituencies) {
    for (const c of constituencies) {
      if (c === "navarra") continue; // no clean bipartisan rivalry to track
      const ppS = sup(Q, ppKey(Q, c), c);
      const csS = sup(Q, "cs", c);

      const kPp = "pp_hold_" + c;
      Q[kPp] = Q[kPp] == null ? 1.0 : Q[kPp];
      Q[kPp] = clamp(
        Q[kPp] + (csS > ppS ? -P.hold_decay : P.hold_recovery), 0, 1);

      if (Q.vox_active) {
        const voxS = sup(Q, "vox", c);
        const kV = "pp_vox_hold_" + c;
        Q[kV] = Q[kV] == null ? 1.0 : Q[kV];
        Q[kV] = clamp(
          Q[kV] + (voxS > ppS ? -P.hold_decay : P.hold_recovery), 0, 1);
      }

      const psoeS = sup(Q, psoeKey(Q, c), c);
      const podS = sup(Q, podKey(Q, c), c);
      const kPs = "psoe_hold_" + c;
      Q[kPs] = Q[kPs] == null ? 1.0 : Q[kPs];
      Q[kPs] = clamp(
        Q[kPs] + (podS > psoeS ? -P.hold_decay : P.hold_recovery), 0, 1);
    }
  }

  // --- MAIN MONTHLY TICK ---

  function monthPassesCongreso(Q) {
    console.log("Running congreso engine tick for", Q.month, Q.year);

    const constituencies = Q.congreso_constituencies;
    if (!constituencies) return;

    // 1. Effective Spanish macro variables (Catalan values + scenario offsets).
    const spa_gdp = Q.gdp_growth + (Q.spa_gdp_offset || 0);
    const spa_unemp = Q.unemployment + (Q.spa_unemp_offset || 0);
    const spa_welfare = Q.welfare_index + (Q.spa_welfare_offset || 0);

    const prev_gdp = Q._prev_spa_gdp == null ? spa_gdp : Q._prev_spa_gdp;
    const prev_unemp = Q._prev_spa_unemp == null ? spa_unemp : Q._prev_spa_unemp;
    const prev_welfare =
      Q._prev_spa_welfare == null ? spa_welfare : Q._prev_spa_welfare;
    const prev_dissent =
      Q._prev_spa_dissent == null ? Q.social_dissent : Q._prev_spa_dissent;
    const prev_cat_spa =
      Q._prev_spa_cat_spa == null ? Q.cat_spa_relations : Q._prev_spa_cat_spa;

    const d_gdp = spa_gdp - prev_gdp;
    const d_unemp = spa_unemp - prev_unemp;
    const d_welfare = spa_welfare - prev_welfare;
    const d_dissent = Q.social_dissent - prev_dissent;
    const d_cat_spa = Q.cat_spa_relations - prev_cat_spa;

    Q._prev_spa_gdp = spa_gdp;
    Q._prev_spa_unemp = spa_unemp;
    Q._prev_spa_welfare = spa_welfare;
    Q._prev_spa_dissent = Q.social_dissent;
    Q._prev_spa_cat_spa = Q.cat_spa_relations;

    const channeling = Q.podemos_channeling || 0;

    // 2. Passive corruption decay (decay rates are event-set).
    if (Q.corruption_pp != null) {
      Q.corruption_pp = clamp(
        Q.corruption_pp * (Q.corruption_pp_decay == null ? 1.0 : Q.corruption_pp_decay),
        0, 100);
    }
    if (Q.corruption_psoe != null) {
      Q.corruption_psoe = clamp(
        Q.corruption_psoe * (Q.corruption_psoe_decay == null ? 1.0 : Q.corruption_psoe_decay),
        0, 100);
    }
    const corr_pp = Q.corruption_pp || 0;
    const corr_psoe = Q.corruption_psoe || 0;

    // 3. Dominance holds.
    updateHolds(Q, constituencies);

    // 4. Per-constituency evolution.
    for (const c of constituencies) {
      const fams = activeParties(Q, c);
      if (fams.length === 0) continue;
      const urban = URBAN_CONSTITUENCIES.includes(c);
      const has = (p) => fams.includes(p);

      const deltas = {};
      fams.forEach((p) => (deltas[p] = 0));

      const ppF = ppKey(Q, c);
      const podF = podKey(Q, c);
      const psoeF = psoeKey(Q, c);

      // 4a. Base economic response + incumbent GDP boost.
      for (const p of fams) {
        const coeff = ECON[coeffKey(p)];
        if (!coeff) continue;
        let d =
          coeff.g * d_gdp + coeff.u * d_unemp +
          coeff.w * d_welfare + coeff.d * d_dissent;
        if (d_gdp > 0 && isIncumbent(coeffKey(p), Q)) {
          d += P.gov_gdp_boost * d_gdp;
        }
        deltas[p] += d;
      }

      // 4b. PP corruption bleed → CS + abstain (UPN takes it when run as rival).
      if (corr_pp > 0 && has(ppF)) {
        const to_cs = corr_pp * (urban ? P.corr_pp_cs_urban : P.corr_pp_cs_base);
        const to_abs = corr_pp * P.corr_pp_abs;
        deltas[ppF] -= to_cs + to_abs;
        const upnRival = has("upn") && Q.spa_upn_independent;
        if (upnRival && has("cs")) {
          deltas["upn"] += to_cs * 0.7;
          deltas["cs"] += to_cs * 0.3;
        } else if (upnRival) {
          deltas["upn"] += to_cs;
        } else if (has("cs")) {
          deltas["cs"] += to_cs;
        }
        if (has(ABSTAIN)) deltas[ABSTAIN] += to_abs;
      }

      // 4c. PSOE corruption bleed → Podemos + abstain.
      if (corr_psoe > 0 && has(psoeF)) {
        const to_pod = corr_psoe * P.corr_psoe_pod;
        const to_abs = corr_psoe * P.corr_psoe_abs;
        deltas[psoeF] -= to_pod + to_abs;
        if (has(podF)) deltas[podF] += to_pod;
        if (has(ABSTAIN)) deltas[ABSTAIN] += to_abs;
      }

      // 4d. cat_spa relations effects.
      if (d_cat_spa < 0) {
        const mag = Math.abs(d_cat_spa);
        if (c === "catalunya") {
          const indy_gain = mag * P.cat_spa_indy;
          const cs_gain = mag * P.cat_spa_cs_cat;
          const total = indy_gain + cs_gain;
          const ercF = ercKey(Q, c);
          const convF = convKey(Q, c);
          if (has(ercF)) deltas[ercF] += indy_gain * 0.65;
          if (has(convF)) deltas[convF] += indy_gain * 0.35;
          if (has("cs")) deltas["cs"] += cs_gain;
          if (has(ppF)) deltas[ppF] -= total * 0.4;
          if (has(psoeF)) deltas[psoeF] -= total * 0.6;
        } else if (c !== "navarra") {
          const pp_gain = mag * P.cat_spa_pp_psoe;
          const cs_gain = mag * P.cat_spa_cs_pod;
          if (has(ppF)) deltas[ppF] += pp_gain;
          if (has(psoeF)) deltas[psoeF] -= pp_gain;
          if (has("cs")) deltas["cs"] += cs_gain;
          if (has(podF)) deltas[podF] -= cs_gain;
        }
      }

      // 4e. Dominance momentum.
      const psoeHold = Q["psoe_hold_" + c] == null ? 1.0 : Q["psoe_hold_" + c];
      if (psoeHold < 1.0 && has(psoeF) && has(podF)) {
        const m = P.dom_momentum * (1 - psoeHold);
        deltas[podF] += m;
        deltas[psoeF] -= m;
      }
      const ppHold = Q["pp_hold_" + c] == null ? 1.0 : Q["pp_hold_" + c];
      if (ppHold < 1.0 && has(ppF) && has("cs")) {
        const m = P.dom_momentum * (1 - ppHold);
        deltas["cs"] += m;
        deltas[ppF] -= m;
      }
      if (Q.vox_active) {
        const vH = Q["pp_vox_hold_" + c] == null ? 1.0 : Q["pp_vox_hold_" + c];
        if (vH < 1.0 && has(ppF) && has("vox")) {
          const m = P.dom_momentum * (1 - vH);
          deltas["vox"] += m;
          deltas[ppF] -= m;
        }
      }

      // 4f. Podemos channeling — organic PSOE⇄Podemos flow (cat_engine driven).
      if (has(podF) && has(psoeF)) {
        const net =
          channeling * P.channeling_rate -
          (1 - channeling) * P.psoe_recover_rate;
        let actual;
        if (net > 0) {
          actual = Math.min(net * sup(Q, psoeF, c), sup(Q, psoeF, c) - 1.0);
        } else {
          actual = Math.max(net * sup(Q, podF, c), -(sup(Q, podF, c) - 1.0));
        }
        actual = clamp(actual, -5.0, 5.0);
        deltas[podF] += actual;
        deltas[psoeF] -= actual;
      }

      // 4g. Leadership recovery — sustained monthly pull from abstain.
      const psoeLm = Q.psoe_leadership_mult || 0;
      if (psoeLm > 0 && has(psoeF) && has(ABSTAIN)) {
        const pull = Math.min(P.psoe_leadership_rate * psoeLm, sup(Q, ABSTAIN, c) * 0.02);
        deltas[psoeF] += pull;
        deltas[ABSTAIN] -= pull;
      }
      const ppLm = Q.pp_leadership_mult || 0;
      if (ppLm > 0 && has(ppF) && has(ABSTAIN)) {
        const pull = Math.min(P.pp_leadership_rate * ppLm, sup(Q, ABSTAIN, c) * 0.02);
        deltas[ppF] += pull;
        deltas[ABSTAIN] -= pull;
      }

      // 4h. UPyD collapse — bleeds to CS (where present) and abstain.
      if (has("upyd")) {
        const dec = P.upyd_decay_rate * sup(Q, "upyd", c);
        deltas["upyd"] -= dec;
        const to_cs = has("cs") ? dec * 0.5 : 0;
        if (to_cs) deltas["cs"] += to_cs;
        if (has(ABSTAIN)) deltas[ABSTAIN] += dec - to_cs;
        else if (has("cs")) deltas["cs"] += dec - to_cs;
      }

      // 4i. Minor "rest" regional reversion.
      if (c === "rest") {
        for (const p of fams) {
          if (MINOR_REST.has(p)) {
            deltas[p] += P.minor_reversion_rate * ((MINOR_REST_TARGETS[p] || 0) - sup(Q, p, c));
          }
        }
      }

      // 4j. Gaussian noise (scaled down for minor rest parties).
      for (const p of fams) {
        const sd = c === "rest" && MINOR_REST.has(p) ? P.noise_stdev_minor : P.noise_stdev;
        deltas[p] += gaussianRandom(0, sd);
      }

      // 4k. Apply deltas.
      for (const p of fams) setSup(Q, p, c, sup(Q, p, c) + deltas[p]);

      // 4l. Renormalize constituency to 100 (abstain included).
      let total = 0;
      for (const p of fams) total += sup(Q, p, c);
      if (total > 0) {
        for (const p of fams) setSup(Q, p, c, (sup(Q, p, c) / total) * 100);
      }
    }
  }

  // ===========================================================================
  // SUPPORT INJECTION HELPER (for formation / shock scenes)
  //
  // Mirrors the support_inject semantics from spa_economic_timeline.py: move
  // `delta` percentage points from `from` to `family` in constituency `c`
  // ('all' = every constituency where both keys are part of the lineup),
  // transferring at most 50% of the funding source's current support.
  //
  // `family`/`from` may be a literal in-game key (cs, vox, mes, …) OR a bloc
  // alias (pp / podemos / psoe / ciu), which resolves per-constituency to the
  // live carrier — so a scene can always write `'podemos'` and it lands on `up`
  // once Unidos Podemos exists, regardless of the player's timeline.
  //
  // Usage in a scene's on-arrival block:
  //   window.spaSupportInject(Q, 'cs', 'all', 9.0, 'pp');
  // ===========================================================================

  // Resolve a bloc-alias key to the live carrier in constituency c.
  function resolveBloc(Q, c, key) {
    switch (key) {
      case "pp": return ppKey(Q, c);
      case "podemos": return podKey(Q, c);
      case "psoe": return psoeKey(Q, c);
      case "ciu": return convKey(Q, c);
      default: return key;
    }
  }

  function spaSupportInject(Q, family, c, delta, from) {
    const cs = c === "all" ? Q.congreso_constituencies : [c];
    for (const cc of cs) {
      const toKey = resolveBloc(Q, cc, family);
      const fromKey = resolveBloc(Q, cc, from);
      const lineup = (Q["congreso_parties_" + cc] || []).concat([ABSTAIN]);
      if (!lineup.includes(toKey) || !lineup.includes(fromKey)) continue;
      const fromCur = sup(Q, fromKey, cc);
      const actual = Math.min(delta, fromCur * 0.5);
      if (actual <= 0) continue;
      setSup(Q, fromKey, cc, fromCur - actual);
      setSup(Q, toKey, cc, sup(Q, toKey, cc) + actual);
    }
  }

  window.engineTick = monthPasses;
  window.spaSupportInject = spaSupportInject;
})();
