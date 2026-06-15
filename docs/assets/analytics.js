/* local-ai-lab — privacy-friendly usage analytics (GoatCounter).
 *
 * Cookieless, no personal data. The GoatCounter count.js script records the
 * normal pageview (path + country); this file adds a few custom events:
 *   - click tracking: PDF downloads (e.g. the cheat-sheet) and outbound links
 *   - slide depth:    per-lesson `lesson-N/step-K` and a `…/complete` event
 *
 * Hard domain guard: nothing is sent unless we're on the real Pages host, so
 * local previews (localhost / 127.* / file://) never pollute the stats.
 */
(function () {
  "use strict";

  var PROD_HOST = "nikolareljin.github.io";
  if (location.hostname !== PROD_HOST) return;

  // De-dupe events within a single visit (no storage, no identifier).
  var seen = Object.create(null);

  function count(opts) {
    var g = window.goatcounter;
    if (g && typeof g.count === "function") g.count(opts);
  }

  function fire(path, title) {
    if (!path || seen[path]) return;
    seen[path] = true;
    count({ path: path, title: title || path, event: true });
  }

  // --- Click tracking: PDF downloads + outbound links ---
  document.addEventListener(
    "click",
    function (e) {
      var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
      if (!a) return;
      var href = a.getAttribute("href") || "";
      if (/\.pdf(\?|#|$)/i.test(href)) {
        fire("download/" + href.split("/").pop(), a.textContent.trim());
      } else if (
        a.hostname &&
        a.hostname !== location.hostname &&
        /^https?:/i.test(a.protocol)
      ) {
        fire("outbound/" + a.hostname + a.pathname, a.textContent.trim());
      }
    },
    true
  );

  // --- Slide depth: lessons deep-link as #step-N (see slider.js) ---
  (function () {
    var slides = document.querySelectorAll(".deck .slide");
    if (!slides.length) return;
    var total = slides.length;
    var slug = (location.pathname.split("/").pop() || "index").replace(/\.html$/, "");
    var last = null;

    function check() {
      var hash = location.hash || "";
      if (hash === last) return;
      last = hash;
      var m = hash.match(/step-(\d+)/);
      if (!m) return;
      var n = parseInt(m[1], 10);
      fire(slug + "/step-" + n);
      if (n >= total) fire(slug + "/complete");
    }

    // slider.js advances via history.replaceState (no hashchange event), so we
    // catch deep links / back-forward via the event and in-page nav via a poll.
    window.addEventListener("hashchange", check);
    setInterval(check, 500);
    check();
  })();
})();
