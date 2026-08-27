(function () {
  "use strict";
  var I18N = __I18N__;
  var STORE = "iirdsv.page";

  function remembered() {
    // localStorage throws outright in some privacy configurations, so every
    // read and write is guarded and the page works with nothing stored.
    try { return JSON.parse(localStorage.getItem(STORE) || "{}"); }
    catch (e) { return {}; }
  }
  function remember(patch) {
    try {
      var next = remembered();
      for (var k in patch) { next[k] = patch[k]; }
      localStorage.setItem(STORE, JSON.stringify(next));
    } catch (e) { /* a preference nobody can store is still a preference */ }
  }

  function pickLanguage() {
    var saved = remembered().lang;
    if (saved && I18N.strings[saved]) { return saved; }
    var offered = (navigator.languages || [navigator.language || "en"]);
    for (var i = 0; i < offered.length; i++) {
      var tag = String(offered[i] || "").toLowerCase().split("-")[0];
      if (I18N.strings[tag]) { return tag; }
    }
    return "en";
  }

  var el = {
    title: document.getElementById("title"),
    lead: document.getElementById("lead"),
    drop: document.getElementById("drop"),
    file: document.getElementById("file"),
    note: document.getElementById("note"),
    out: document.getElementById("out"),
    save: document.getElementById("save"),
    foot: document.getElementById("foot"),
    lang: document.getElementById("lang"),
    theme: document.getElementById("theme")
  };
  var lang = pickLanguage();
  var latest = null;
  var lastName = null;

  function t(key) { return I18N.strings[lang][key]; }

  function paint() {
    document.documentElement.lang = lang;
    document.title = t("title");
    el.title.textContent = t("title");
    el.lead.textContent = t("lead");
    el.drop.textContent = t("drop");
    el.note.textContent = t("reportNote");
    el.save.textContent = t("save");
    el.foot.textContent = document.body.dataset.version + " · " + t("footer");
    el.lang.setAttribute("aria-label", t("language"));
    el.theme.setAttribute("aria-label", t("theme"));
    var labels = { system: t("system"), light: t("light"), dark: t("dark") };
    for (var i = 0; i < el.theme.options.length; i++) {
      el.theme.options[i].textContent = labels[el.theme.options[i].value];
    }
  }

  function applyTheme(choice) {
    if (choice === "system") { document.documentElement.removeAttribute("data-theme"); }
    else { document.documentElement.setAttribute("data-theme", choice); }
  }

  I18N.order.forEach(function (code) {
    var option = document.createElement("option");
    option.value = code;
    option.textContent = I18N.names[code];
    el.lang.appendChild(option);
  });
  el.lang.value = lang;
  el.theme.value = remembered().theme || "system";
  applyTheme(el.theme.value);
  paint();

  el.lang.addEventListener("change", function () {
    lang = el.lang.value; remember({ lang: lang }); paint();
    if (lastName) { document.title = lastName + " · " + t("title"); }
  });
  el.theme.addEventListener("change", function () {
    applyTheme(el.theme.value); remember({ theme: el.theme.value });
  });

  function show(text) { el.out.hidden = false; el.out.textContent = text; }

  function send(chosen) {
    if (!chosen) { return; }
    lastName = chosen.name;
    el.note.hidden = false;
    show(t("checking") + " " + chosen.name + "…");
    el.save.hidden = true;
    var body = new FormData();
    body.append("package", chosen, chosen.name);
    fetch("/check", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (payload) {
        show(payload.text);
        latest = payload.report;
        el.save.hidden = latest === null;
        document.title = (payload.exit === 0 ? "PASS" : "FAIL") + " · " + chosen.name;
      })
      .catch(function (err) { show(t("failed") + ": " + err); });
  }

  el.drop.addEventListener("click", function () { el.file.click(); });
  el.drop.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.file.click(); }
  });
  el.file.addEventListener("change", function () { send(el.file.files[0]); });
  ["dragenter", "dragover"].forEach(function (name) {
    el.drop.addEventListener(name, function (e) { e.preventDefault(); el.drop.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    el.drop.addEventListener(name, function (e) { e.preventDefault(); el.drop.classList.remove("over"); });
  });
  el.drop.addEventListener("drop", function (e) { send(e.dataTransfer.files[0]); });

  el.save.addEventListener("click", function () {
    var blob = new Blob([JSON.stringify(latest, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = "iirds-report.json"; a.click();
    // Released on the next turn of the loop: revoking synchronously after
    // click() cancels the download in some browsers.
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  });
})();
