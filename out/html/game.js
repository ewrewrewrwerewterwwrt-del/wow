(function () {
  var game;
  var ui;

  var DateOptions = {
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
    year: "numeric",
    month: "short",
    day: "numeric",
  };

  var main = function (dendryUI) {
    ui = dendryUI;
    game = ui.game;

    // I want these settings on by default, but the engine does not have a way to set them and I don't fancy touching that sht.
    if (!window.dendryUI.dendryEngine.touchedSettings) {
      window.dendryUI.animate = true;
      window.dendryUI.show_portraits = true;
      window.dendryUI.dark_mode = false;
      window.dendryUI.saveSettings();
    }
  };

  var TITLE =
    "Route to Ítaca - An Alternate History" +
    "_" +
    "BrokenArrow, modded from Autumn Chen's work";

  window.showStats = function () {
    if (window.dendryUI.dendryEngine.state.sceneId.startsWith("library")) {
      window.dendryUI.dendryEngine.goToScene("backSpecialScene");
    } else {
      window.dendryUI.dendryEngine.goToScene("library");
    }
    addTooltipEventListeners();
  };

  window.showOptions = function () {
    var save_element = document.getElementById("options");
    window.populateOptions();
    window.dendryUI.dendryEngine.touchedSettings = true;
    save_element.style.display = "block";
    if (!save_element.onclick) {
      save_element.onclick = function (evt) {
        var target = evt.target;
        var save_element = document.getElementById("options");
        if (target == save_element) {
          window.hideOptions();
        }
      };
    }
  };

  window.hideOptions = function () {
    var save_element = document.getElementById("options");
    save_element.style.display = "none";
  };

  window.disableBg = function () {
    window.dendryUI.disable_bg = true;
    document.body.style.backgroundImage = "none";
    window.dendryUI.saveSettings();
  };

  window.enableBg = function () {
    window.dendryUI.disable_bg = false;
    window.dendryUI.setBg(window.dendryUI.dendryEngine.state.bg);
    window.dendryUI.saveSettings();
  };

  window.disableAnimate = function () {
    window.dendryUI.animate = false;
    window.dendryUI.saveSettings();
  };

  window.enableAnimate = function () {
    window.dendryUI.animate = true;
    window.dendryUI.saveSettings();
  };

  window.disableAnimateBg = function () {
    window.dendryUI.animate_bg = false;
    window.dendryUI.saveSettings();
  };

  window.enableAnimateBg = function () {
    window.dendryUI.animate_bg = true;
    window.dendryUI.saveSettings();
  };

  window.disableAudio = function () {
    window.dendryUI.toggle_audio(false);
    window.dendryUI.saveSettings();
  };

  window.enableAudio = function () {
    window.dendryUI.toggle_audio(true);
    window.dendryUI.saveSettings();
  };

  window.enableImages = function () {
    window.dendryUI.show_portraits = true;
    window.dendryUI.saveSettings();
  };

  window.disableImages = function () {
    window.dendryUI.show_portraits = false;
    window.dendryUI.saveSettings();
  };

  window.enableLightMode = function () {
    window.dendryUI.dark_mode = false;
    document.body.classList.remove("dark-mode");
    window.dendryUI.saveSettings();
  };
  window.enableDarkMode = function () {
    window.dendryUI.dark_mode = true;
    document.body.classList.add("dark-mode");
    window.dendryUI.saveSettings();
  };

  // populates the checkboxes in the options view
  window.populateOptions = function () {
    var disable_bg = window.dendryUI.disable_bg;
    var animate = window.dendryUI.animate;
    var disable_audio = true; // TODO: enable on adding music!
    // var disable_audio = window.dendryUI.disable_audio;
    var show_portraits = window.dendryUI.show_portraits;
    if (disable_bg) {
      $("#backgrounds_no")[0].checked = true;
    } else {
      $("#backgrounds_yes")[0].checked = true;
    }
    if (animate) {
      $("#animate_yes")[0].checked = true;
    } else {
      $("#animate_no")[0].checked = true;
    }
    if (disable_audio) {
      $("#audio_no")[0].checked = true;
    } else {
      $("#audio_yes")[0].checked = true;
    }
    if (show_portraits) {
      $("#images_yes")[0].checked = true;
    } else {
      $("#images_no")[0].checked = true;
    }
    if (window.dendryUI.dark_mode) {
      $("#dark_mode")[0].checked = true;
    } else {
      $("#light_mode")[0].checked = true;
    }
  };

  // This function allows you to modify the text before it's displayed.
  // E.g. wrapping chat-like messages in spans.
  window.displayText = function (text) {
    return applyWholesome(text);
  };

  function applyWholesome(str) {
    const allWords = new Set([
      ...tooltipList.map((t) => t.searchString).flat(),
      ...colourList.map((c) => c.words).flat(),
    ]);

    const regex = new RegExp(`\\b(${[...allWords].join("|")})\\b`, "g");

    return str.replace(
      /(<(?:span|strong)[^>]*>.*?<\/(?:span|strong)>|<[^>]+>|[^<]+)/g,
      (segment) => {
        if (segment.startsWith("<")) return segment;

        return segment.replace(regex, (match) => {
          const tooltip = tooltipList.find((t) =>
            t.searchString.includes(match),
          );
          const colour = colourList.find((c) => c.words.includes(match));
          let textColor;
          if (colour && colour.colour) {
            textColor = colour.colour;
          } else {
            textColor = "inherit";
          }

          // skip if preceded by zero-width space
          const zwspIndex = segment.indexOf("\u200B" + match);
          if (zwspIndex !== -1) {
            return match;
          }

          // find if just before the match there was "--"
          const matchStart = segment.lastIndexOf(
            "--",
            segment.indexOf(match) - 2,
          );
          if (matchStart !== -1 && matchStart === segment.indexOf(match) - 2) {
            return match;
          }

          let style = colour && colour.style ? colour.style : "";
          let innerText = match;

          if (tooltip) {
            const imgHtml = tooltip.img
              ? `<img src='${tooltip.img}' alt='${innerText} image'/>`
              : "";
            const subText = tooltip.subText
              ? `<br/><span class='mytooltip-sub-text'>${tooltip.subText}</span>`
              : "";
            let ledBy = "";
            let ideology = "";
            let allegiances = "";
            if (
              tooltip.ledBy &&
              window.dendryUI.dendryEngine.state.qualities.hasOwnProperty(
                tooltip.ledBy,
              )
            ) {
              ledBy = `<br/>Leader: <span class='mytooltip-ledby'>${window.dendryUI.dendryEngine.state.qualities[tooltip.ledBy]}</span>`;
            }
            if (tooltip.ideology) {
              ideology = `<br/><span class='mytooltip-ideology'>${
                window.dendryUI.dendryEngine.state.qualities.hasOwnProperty(
                  tooltip.ideology,
                )
                  ? window.dendryUI.dendryEngine.state.qualities[
                      tooltip.ideology
                    ]
                  : tooltip.ideology
              }</span>`;
            }
            if (tooltip.allegiances) {
              allegiances = `<br/><span class='mytooltip-allegiances'>`;
              allegiances +=
                tooltip.allegiances(
                  window.dendryUI.dendryEngine.state.qualities,
                ).length > 1
                  ? "Allegiances: "
                  : "Allegiance: ";
              allegiances += tooltip
                .allegiances(window.dendryUI.dendryEngine.state.qualities)
                .join(", ");
              allegiances += `</span>`;
            }

            return `<span class='mytooltip' style='--mytooltip-color:${textColor}; ${style}' data-tooltip-id='${tooltip.searchString}'>${colour.transform ? colour.transform : innerText}<span class='mytooltiptext'><span class='mytooltip-content'>${imgHtml}<span class='mytooltip-text'><span class='mytooltip-main-text'>${tooltip.mainText}</span>${subText}${ledBy}${ideology}${allegiances}</span></span></span></span>`;
          } else if (colour) {
            return `<span style='color: ${textColor}; ${style}'>${colour.transform ? colour.transform : innerText}</span>`;
          }

          return match;
        });
      },
    );
  }

  window.applyWholesome = applyWholesome;

  // This function allows you to do something in response to signals.
  window.handleSignal = function (signal, event, scene_id) {};

  // This function runs on a new page
  window.onNewPage = function () {
    var scene = window.dendryUI.dendryEngine.state.sceneId;
    console.log("New page: " + scene);
    initCataloniaPolls(
      "cat-polls-widget",
      dendryUI.dendryEngine.state.qualities,
    );
    initCataloniaPolls(
      "cat-polls-widget-wide",
      dendryUI.dendryEngine.state.qualities,
      true,
    );
    initCatLocalMap(
      "catalonia-local-map",
      dendryUI.dendryEngine.state.qualities,
    );
    initCatCoalitions(
      "parlament-coalition-widget",
      window._cvParlement,
      dendryUI.dendryEngine.state.qualities,
    );
    addTooltipEventListeners();
    if (scene != "root" && !window.justLoaded) {
      window.dendryUI.autosave();
    }
    if (window.justLoaded) {
      window.justLoaded = false;
    }
  };

  // tabbed browsing
  window.updateSidebar = function () {
    $("#qualities").empty();
    var scene = dendryUI.game.scenes[window.statusTab];
    dendryUI.dendryEngine._runActions(scene.onArrival);
    var displayContent = dendryUI.dendryEngine._makeDisplayContent(
      scene.content,
      true,
    );
    $("#qualities").append(dendryUI.contentToHTML.convert(displayContent));
    initCataloniaPolls(
      "cat-polls-widget",
      dendryUI.dendryEngine.state.qualities,
    );
    initCataloniaPolls(
      "cat-polls-widget-wide",
      dendryUI.dendryEngine.state.qualities,
      true,
    );
    initCatLocalMap(
      "catalonia-local-map",
      dendryUI.dendryEngine.state.qualities,
    );
    initCatCoalitions(
      "parlament-coalition-widget",
      window._cvParlement,
      dendryUI.dendryEngine.state.qualities,
    );
    addTooltipEventListeners();
  };

  window.changeTab = function (newTab, tabId) {
    if (
      tabId == "polls_tab" &&
      dendryUI.dendryEngine.state.qualities.historical_mode
    ) {
      window.alert("Polls are not available in historical mode.");
      return;
    }
    var tabButton = document.getElementById(tabId);
    var tabButtons = document.getElementsByClassName("tab_button");
    for (i = 0; i < tabButtons.length; i++) {
      tabButtons[i].className = tabButtons[i].className.replace(" active", "");
    }
    tabButton.className += " active";
    window.statusTab = newTab;
    window.updateSidebar();
    initCataloniaPolls(
      "cat-polls-widget",
      dendryUI.dendryEngine.state.qualities,
    );
    initCataloniaPolls(
      "cat-polls-widget-wide",
      dendryUI.dendryEngine.state.qualities,
      true,
    );
    initCatLocalMap(
      "catalonia-local-map",
      dendryUI.dendryEngine.state.qualities,
    );
    initCatCoalitions(
      "parlament-coalition-widget",
      window._cvParlement,
      dendryUI.dendryEngine.state.qualities,
    );
    addTooltipEventListeners();
  };

  window.onDisplayContent = function () {
    window.updateSidebar();
    initCataloniaPolls(
      "cat-polls-widget",
      dendryUI.dendryEngine.state.qualities,
    );
    initCataloniaPolls(
      "cat-polls-widget-wide",
      dendryUI.dendryEngine.state.qualities,
      true,
    );
    initCatLocalMap(
      "catalonia-local-map",
      dendryUI.dendryEngine.state.qualities,
    );
    initCatCoalitions(
      "parlament-coalition-widget",
      window._cvParlement,
      dendryUI.dendryEngine.state.qualities,
    );
    addTooltipEventListeners();
  };

  window._achievementStack = [];
  window._achievementLabel = null;

  function updateLabel() {
    if (!window._achievementLabel) return;
    const n = window._achievementStack.length;
    window._achievementLabel.textContent =
      n === 1 ? "Achievement Unlocked" : "Achievements Unlocked";
  }

  function getOrCreateLabel() {
    if (!window._achievementLabel) {
      const label = document.createElement("div");
      label.style.cssText = `
      position: fixed; right: 24px; z-index: 9999;
      background: var(--card-bg-color);
      border-radius: 8px; padding: 8px 14px;
      font-family: 'UbuntuCustom', system-ui, -apple-system, BlinkMacSystemFont, Ubuntu, Cantarell, sans-serif;
      font-size: .72em; font-weight: 700; letter-spacing: .14em;
      color: var(--text-color); text-transform: uppercase;
      width: fit-content; white-space: nowrap;
      transition: bottom .35s cubic-bezier(.16,1,.3,1), transform .45s cubic-bezier(.16,1,.3,1);
      transform: translateX(0);
    `;
      document.body.appendChild(label);
      window._achievementLabel = label;
    }
    return window._achievementLabel;
  }

  function restack() {
    const GAP = 12;
    let bottom = 24;
    for (let i = window._achievementStack.length - 1; i >= 0; i--) {
      window._achievementStack[i].style.bottom = bottom + "px";
      bottom += window._achievementStack[i].offsetHeight + GAP;
    }
    if (window._achievementLabel) {
      window._achievementLabel.style.bottom = bottom + "px";
    }
  }

  window.achievementNotif = function (title, img, stars) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const beat = 60 / 180;
    [
      { freq: 293.66, delay: 0, dur: beat * 1.5 },
      { freq: 329.63, delay: beat * 1.5, dur: beat * 0.5 },
      { freq: 349.23, delay: beat * 2, dur: beat * 2.0 },
    ].forEach(({ freq, delay, dur }) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = freq;
      const t = ctx.currentTime + delay;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.25, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
      osc.start(t);
      osc.stop(t + dur);
    });

    const el = document.createElement("div");
    el.className = "achievement achievement--unlocked";
    el.style.cssText = `
    position: fixed; right: 24px; z-index: 9999;
    flex-direction: column; align-items: stretch;
    gap: 10px; padding: 12px 14px;
    border-top: none; border-radius: 8px;
    background: var(--card-bg-color);
    box-shadow:
      0 0 0 1px rgba(220,150,0,.4),
      0 0 14px rgba(220,150,0,.5),
      0 0 28px rgba(220,150,0,.2);
    width: 18em;
    transform: translateX(calc(100% + 32px));
    transition: transform .45s cubic-bezier(.16,1,.3,1), bottom .35s cubic-bezier(.16,1,.3,1);
  `;

    el.innerHTML = `
    <div style="display: flex; align-items: center; gap: 12px;">
      <div class="achievement-image achievement-image--unlocked" style="flex: 1 0 0; height: auto; aspect-ratio: 3/2; box-shadow: none;">
        <img src="${img}" style="width:100%;height:100%;object-fit:cover;">
      </div>
      <div class="achievement-body" style="flex: 2 0 0; min-width: 0;">
        <div class="achievement-title achievement-title--unlocked" style="display: block; margin-bottom: 6px;">${title}</div>
        <div class="achievement-stars">
          ${Array.from(
            { length: 5 },
            (_, i) =>
              `<span class="${i < stars ? "star--filled" : "star--empty"}">★</span>`,
          ).join("")}
        </div>
      </div>
    </div>
  `;

    document.body.appendChild(el);
    window._achievementStack.push(el);
    getOrCreateLabel();
    updateLabel();
    restack();

    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        el.style.transform = "translateX(0)";
      }),
    );

    setTimeout(() => {
      window._achievementStack = window._achievementStack.filter(
        (e) => e !== el,
      );

      // if last card, slide label out together
      if (window._achievementStack.length === 0 && window._achievementLabel) {
        window._achievementLabel.style.transform =
          "translateX(calc(100% + 32px))";
        window._achievementLabel.addEventListener(
          "transitionend",
          () => {
            window._achievementLabel?.remove();
            window._achievementLabel = null;
          },
          { once: true },
        );
      } else {
        updateLabel();
        restack();
      }

      el.style.transform = "translateX(calc(100% + 32px))";
      el.addEventListener(
        "transitionend",
        () => {
          el.remove();
        },
        { once: true },
      );
    }, 4500);
  };

  window.justLoaded = true;
  window.statusTab = "status";
  window.dendryModifyUI = main;
  console.log("Modifying stats: see dendryUI.dendryEngine.state.qualities");

  window.onload = function () {
    window.dendryUI.loadSettings({ show_portraits: false });
    if (window.dendryUI.dark_mode) {
      document.body.classList.add("dark-mode");
    }
    window.pinnedCardsDescription =
      "Advisor cards - actions are only usable once per 6 months.";

    initCataloniaPolls(
      "cat-polls-widget",
      dendryUI.dendryEngine.state.qualities,
    );
    initCataloniaPolls(
      "cat-polls-widget-wide",
      dendryUI.dendryEngine.state.qualities,
      true,
    );
    initCatLocalMap(
      "catalonia-local-map",
      dendryUI.dendryEngine.state.qualities,
    );
    initCatCoalitions(
      "parlament-coalition-widget",
      window._cvParlement,
      dendryUI.dendryEngine.state.qualities,
    );
    addTooltipEventListeners();
  };

  // Tooltip event listeners
  function addTooltipEventListeners() {
    const tooltips = document.querySelectorAll(".mytooltip");

    tooltips.forEach((tooltip) => {
      const tooltipText = tooltip.querySelector(".mytooltiptext");

      // Click event to toggle tooltip
      tooltip.addEventListener("click", function (e) {
        e.stopPropagation();

        // Close all other tooltips
        document.querySelectorAll(".mytooltiptext.active").forEach((t) => {
          if (t !== tooltipText) t.classList.remove("active");
        });

        tooltipText.classList.toggle("active");
      });
    });

    // Close tooltip when clicking outside
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".mytooltip")) {
        document.querySelectorAll(".mytooltiptext.active").forEach((t) => {
          t.classList.remove("active");
        });
      }
    });
  }
})();
