// Small progressive enhancements. Everything works without JavaScript.
(function () {
  "use strict";

  // Submit filter forms when a select changes.
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });

  // Live SMS segment count for message boxes (mirrors docketbell/sms/segments.py).
  var GSM = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?" +
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà";
  var GSM_EXT = "^{}\\[~]|€\f";

  function analyze(text) {
    var gsm = true, units = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (GSM.indexOf(ch) !== -1) { units += 1; }
      else if (GSM_EXT.indexOf(ch) !== -1) { units += 2; }
      else { gsm = false; break; }
    }
    if (!gsm) { units = text.length; }
    var single = gsm ? 160 : 70, multi = gsm ? 153 : 67;
    var segments = units === 0 ? 0 : (units <= single ? 1 : Math.ceil(units / multi));
    return { units: units, segments: segments, encoding: gsm ? "GSM-7" : "UCS-2" };
  }

  document.querySelectorAll("textarea[data-segment-counter]").forEach(function (area) {
    var output = area.form && area.form.querySelector("[data-segment-output]");
    if (!output) { return; }
    function update() {
      var info = analyze(area.value);
      output.textContent = info.units
        ? info.units + " · " + info.segments + " SMS · " + info.encoding
        : "";
    }
    area.addEventListener("input", update);
    update();
  });

  // Close the account menu when clicking elsewhere.
  document.addEventListener("click", function (event) {
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      if (!menu.contains(event.target)) { menu.removeAttribute("open"); }
    });
  });
})();
