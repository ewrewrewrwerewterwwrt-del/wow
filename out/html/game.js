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

    // Add your custom code here.
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

  // This function allows you to do something in response to signals.
  window.handleSignal = function (signal, event, scene_id) {};

  // This function runs on a new page. Right now, this auto-saves.
  window.onNewPage = function () {
    var scene = window.dendryUI.dendryEngine.state.sceneId;
    if (scene != "root" && !window.justLoaded) {
      window.dendryUI.autosave();
    }
    if (window.justLoaded) {
      window.justLoaded = false;
    }
    addTooltipEventListeners();
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
    addTooltipEventListeners();
  };

  window.changeTab = function (newTab, tabId) {
    if (
      tabId == "poll_tab" &&
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
  };

  window.onDisplayContent = function () {
    window.updateSidebar();
  };

  /*
   * This function copied from the code for Infinite Space Battle Simulator
   *
   * quality - a number between max and min
   * qualityName - the name of the quality
   * max and min - numbers
   * colors - if true/1, will use some color scheme - green to yellow to red for high to low
   * */
  window.generateBar = function (quality, qualityName, max, min, colors) {
    var bar = document.createElement("div");
    bar.className = "bar";
    var value = document.createElement("div");
    value.className = "barValue";
    var width = (quality - min) / (max - min);
    if (width > 1) {
      width = 1;
    } else if (width < 0) {
      width = 0;
    }
    value.style.width = Math.round(width * 100) + "%";
    if (colors) {
      value.style.backgroundColor = window.probToColor(width * 100);
    }
    bar.textContent = qualityName + ": " + quality;
    if (colors) {
      bar.textContent += "/" + max;
    }
    bar.appendChild(value);
    return bar;
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
