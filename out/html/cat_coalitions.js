/**
 * cat_coalitions.js
 * Route to Ítaca — Coalition visualisation helper
 *
 * ── Usage ────────────────────────────────────────────────────────────────────
 *
 *   on-arrival:
 *   {!
 *     window._cvParlement = {
 *       totalSeats:        135,
 *       majoritySeats:     Q.parlament_s_majority || 68,
 *       majorityMarkAt:    0.6,    // 0–1, where the majority line sits in the bar
 *       nearMissThreshold: 10,     // seats within which a short coalition still shows
 *       seatsKey:          "{party}_parlament_s",
 *       partyAliases: {
 *         "ciu_alias": Q.parlament_current_ciu,
 *         "icv_alias": Q.parlament_current_icv
 *       },
 *       coalitions: [
 *         {
 *           label:      "Sovereignty Government",
 *           alwaysShow: true,          // show even if far short (default: false)
 *           condition:  function(s) { return s("ciu_alias") > s("erc"); },
 *           members: [
 *             { party: "ciu_alias", type: "government", label: "CiU" },
 *             { party: "erc",       type: "government", label: "ERC" },
 *             { party: "cup",       type: "abstain",    label: "CUP" }
 *           ]
 *         }
 *       ]
 *     };
 *   !}
 *
 *   scene body:
 *   {!<div id="parlament-coalition-widget"></div>!}
 *
 *   game.js:
 *   initCatCoalitions("parlament-coalition-widget", window._cvParlement,
 *                     dendryUI.dendryEngine.state.qualities);
 *
 * ── Member types ─────────────────────────────────────────────────────────────
 *   "government"  solid bar — party IS in government
 *   "support"     solid bar, 60% opacity — gives assent/yes but outside govt
 *   "abstain"     striped bar — tolerates; prevents a blocking no
 *   Default: "government"
 *
 * ── Visibility ───────────────────────────────────────────────────────────────
 *   A row renders when ANY of:
 *     effectiveSeats >= majority
 *     delta >= -nearMissThreshold
 *     def.alwaysShow === true
 */

(function (global) {
  "use strict";

  // ── helpers ────────────────────────────────────────────────────────────────

  function getPartyColor(party) {
    var val = getComputedStyle(document.documentElement)
      .getPropertyValue("--" + party)
      .trim();
    return val || "#888";
  }

  function makeSeatsResolver(config, Q) {
    var aliases = config.partyAliases || {};
    var template = config.seatsKey || "{party}_s";
    return function (partyKey) {
      var realKey = aliases[partyKey] || partyKey;
      var qKey = template.replace("{party}", realKey);
      return Q && Q[qKey] ? +Q[qKey] : 0;
    };
  }

  // ── styles (injected once) ─────────────────────────────────────────────────

  var _stylesInjected = false;
  function injectStyles() {
    if (_stylesInjected) return;
    _stylesInjected = true;
    var el = document.createElement("style");
    el.textContent = [
      ".cv-wrap{width:100%}",

      /* one row = label line + bar line stacked */
      ".cv-entry{margin-bottom:.9em}",

      /* label row */
      ".cv-label-row{display:flex;align-items:baseline;gap:.4em;margin-bottom:.3em}",
      ".cv-entry-name{color:var(--text-color,#ddd); font-weight:bold}",
      ".cv-entry-members{white-space:nowrap}",
      ".cv-entry-count{margin-left:auto;white-space:nowrap}",
      ".cv-count-ok{color:var(--success-color,#4caf50)}",
      ".cv-count-warn{color:var(--warning-color,#ff9800)}",
      ".cv-count-info{color:var(--info-color,#2196f3)}",
      ".cv-count-muted{color:var(--muted-color,#888)}",

      /* bar track */
      ".cv-track{position:relative;height:2em;border-radius:3px;",
      "background:var(--bar-track-bg,rgba(128,128,128,.15));overflow:visible}",

      /* segments sit inside a flex fill div */
      ".cv-fill{position:absolute;left:0;top:0;height:100%;width:100%;display:flex;",
      "border-radius:3px;overflow:hidden}",
      ".cv-seg{height:100%;flex-shrink:0;min-width:1px; display:flex;align-items:center;justify-content:center;color:#fff;font-weight:bold;}",
      ".cv-seg-support{opacity:.6}",
      ".cv-seg-abstain{position:relative}",
      ".cv-seg-abstain::after{content:'';position:absolute;inset:0;",
      "background:repeating-linear-gradient(-45deg,",
      "transparent 0,transparent 3px,rgba(0,0,0,.3) 3px,rgba(0,0,0,.3) 6px)}",

      /* majority line */
      ".cv-line{position:absolute;top:-3px;bottom:-3px;width:2px;",
      "background:var(--text-color,#ccc);z-index:2}",
      ".cv-line-label{position:absolute;top:-1.5em;left:50%;transform:translateX(-50%);",
      "font-size:.8em;white-space:nowrap;color:var(--muted-color,#888)}",
    ].join("");
    document.head.appendChild(el);
  }

  // ── render one coalition entry ─────────────────────────────────────────────

  function renderEntry(def, config, seats, Q) {
    // condition gate
    var condOk =
      def.condition == null
        ? true
        : typeof def.condition === "function"
          ? def.condition(seats)
          : !!def.condition;
    if (!condOk) return null;

    var majority = +config.majoritySeats;
    var near =
      config.nearMissThreshold != null ? +config.nearMissThreshold : 12;
    var markAt = config.majorityMarkAt != null ? +config.majorityMarkAt : 0.55;
    var aliases = config.partyAliases || {};

    // resolve members
    var members = (def.members || []).map(function (m) {
      var realKey = aliases[m.party] || m.party;
      return {
        party: realKey,
        label: m.label != null ? m.label : realKey,
        seats: m.seats != null ? +m.seats : seats(m.party),
        type: m.type || "government",
      };
    });

    // tally
    var govSeats = 0,
      supportSeats = 0,
      abstainSeats = 0;
    members.forEach(function (m) {
      if (m.type === "government") govSeats += m.seats;
      if (m.type === "support") supportSeats += m.seats;
      if (m.type === "abstain") abstainSeats += m.seats;
    });
    var yesSeats = govSeats + supportSeats;
    var effectiveSeats = Math.floor(yesSeats + abstainSeats / 2);
    var delta = effectiveSeats - majority;

    var alwaysShow = !!def.alwaysShow || !!Q.debug;

    // visibility gate
    if (!alwaysShow && effectiveSeats < majority && delta < -near) return null;

    // status
    var countClass, countText;
    if (govSeats >= majority) {
      countClass = "cv-count-ok";
      countText = `<strong> ${govSeats} </strong> / ${majority}`;
    } else if (yesSeats >= majority) {
      countClass = "cv-count-ok";
      countText = `<strong> ${yesSeats} </strong> / ${majority}`;
    } else if (abstainSeats > 0 && effectiveSeats >= majority) {
      countClass = "cv-count-info";
      countText = `${yesSeats} / ${majority} (tolerated)`;
    } else {
      countClass = "cv-count-muted";
      countText = `${yesSeats} / <strong>${majority}</strong>`;
    }

    // ── DOM construction ───────────────────────────────────────────────────

    var entry = document.createElement("div");
    entry.className = "cv-entry";

    // label row
    var labelRow = document.createElement("div");
    labelRow.className = "cv-label-row";

    var name = document.createElement("span");
    name.className = "cv-entry-name";
    name.innerHTML = window.applyWholesome(def.label) + ":" || "";

    var memberSpan = document.createElement("span");
    memberSpan.className = "cv-entry-members";
    memberSpan.innerHTML = members
      .filter(function (m) {
        return m.seats > 0;
      })
      .map(function (m) {
        var suffix =
          m.type === "support"
            ? " <span style='opacity:.6'>(support)</span>"
            : m.type === "abstain"
              ? " <span style='opacity:.6'>(abst.)</span>"
              : "";
        return window.applyWholesome(m.label) + suffix;
      })
      .join(" + ");

    var countSpan = document.createElement("span");
    countSpan.className = "cv-entry-count " + countClass;
    countSpan.innerHTML = countText;

    labelRow.appendChild(name);
    labelRow.appendChild(memberSpan);
    labelRow.appendChild(countSpan);

    // bar
    // Scale: `majority` seats maps to `markAt` fraction of bar width.
    // Segments beyond markAt are allowed to overflow up to 100%.
    var scale = markAt / majority; // track-fraction per seat

    var track = document.createElement("div");
    track.className = "cv-track";

    var fill = document.createElement("div");
    fill.className = "cv-fill";

    var runPct = 0;
    members.forEach(function (m) {
      if (m.seats <= 0) return;
      var pct = Math.min(m.seats * scale * 100, 100 - runPct);
      runPct += pct;
      var seg = document.createElement("div");
      seg.className =
        "cv-seg" +
        (m.type === "support" ? " cv-seg-support" : "") +
        (m.type === "abstain" ? " cv-seg-abstain" : "");
      seg.style.width = pct.toFixed(3) + "%";
      seg.style.background = getPartyColor(m.party);
      // abstain stripe needs the color for the ::after pseudo-element too
      if (m.type === "abstain") {
        seg.style.setProperty("--seg-color", getPartyColor(m.party));
      }
      seg.title = m.label + ": " + m.seats + " seats";
      seg.textContent = m.seats;
      fill.appendChild(seg);
    });

    // majority line
    var line = document.createElement("div");
    line.className = "cv-line";
    line.style.left = (markAt * 100).toFixed(3) + "%";

    // Label to display the needed majority seats. Currently disabled.
    // var lineLabel = document.createElement("span");
    // lineLabel.className = "cv-line-label";
    // lineLabel.textContent = majority;

    // line.appendChild(lineLabel);
    track.appendChild(fill);
    track.appendChild(line);

    entry.appendChild(labelRow);
    entry.appendChild(track);
    return entry;
  }

  // ── main render ────────────────────────────────────────────────────────────

  function render(config, Q) {
    if (!config) return document.createDocumentFragment();
    injectStyles();
    var seats = makeSeatsResolver(config, Q);
    var wrap = document.createElement("div");
    wrap.className = "cv-wrap";
    (config.coalitions || []).forEach(function (def) {
      var el = renderEntry(def, config, seats, Q);
      if (el) wrap.appendChild(el);
    });
    return wrap;
  }

  function initCatCoalitions(target, config, Q) {
    var el =
      typeof target === "string" ? document.getElementById(target) : target;
    if (!el || !config) return;
    el.innerHTML = "";
    el.appendChild(render(config, Q));
  }

  global.CatCoalitionViz = { render: render };
  global.initCatCoalitions = initCatCoalitions;
})(typeof window !== "undefined" ? window : this);
