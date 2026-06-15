/* local-ai-lab — privacy-friendly usage analytics (GoatCounter).
 *
 * Cookieless, no personal data. This file is the ONLY place GoatCounter is
 * wired in: it loads count.js itself, over explicit https, and only on the
 * production Pages host — so local previews (localhost / 127.* / file://) never
 * load the script or send a pageview. On top of the normal pageview it records:
 *   - click tracking: PDF downloads (e.g. the cheat-sheet) and outbound links
 *   - slide depth:    per-lesson `lesson-N/step-K` and a `…/complete` event
 */
(function () {
  "use strict";

  var PROD_HOST = "nikolareljin.github.io";
  if (location.hostname !== PROD_HOST) return; // prod-only: no count.js, no events

  var ENDPOINT = "https://nikolareljin.goatcounter.com/count";

  // We control the pageview ourselves, so suppress count.js's own onload hit.
  window.goatcounter = { no_onload: true, endpoint: ENDPOINT };

  var seen = Object.create(null); // de-dupe within a visit (no storage, no id)
  var queue = [];                 // events fired before count.js finishes loading
  var ready = false;

  function send(opts) {
    var g = window.goatcounter;
    if (g && typeof g.count === "function") g.count(opts);
  }

  // Queue until count.js is ready, then flush — so early clicks/slides aren't lost.
  function track(opts) {
    if (ready) send(opts);
    else queue.push(opts);
  }

  function fire(path, title) {
    if (!path || seen[path]) return;
    seen[path] = true;
    track({ path: path, title: title || path, event: true });
  }

  // Load count.js explicitly over https, prod-only. Fire the pageview and drain
  // the queue once it's actually available.
  var s = document.createElement("script");
  s.async = true;
  s.src = "https://gc.zgo.at/count.js";
  s.setAttribute("data-goatcounter", ENDPOINT);
  s.onload = function () {
    ready = true;
    send({}); // normal pageview (path + country)
    while (queue.length) send(queue.shift());
  };
  (document.head || document.documentElement).appendChild(s);

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

    function check() {
      var m = (location.hash || "").match(/step-(\d+)/);
      if (!m) return;
      var n = parseInt(m[1], 10);
      fire(slug + "/step-" + n);
      if (n >= total) fire(slug + "/complete");
    }

    // slider.js advances via history.replaceState (which fires no event), so wrap
    // it to run check() exactly when navigation happens — no polling. popstate /
    // hashchange cover back-forward and deep links.
    var replace = history.replaceState;
    if (typeof replace === "function") {
      history.replaceState = function () {
        var r = replace.apply(this, arguments);
        check();
        return r;
      };
    }
    window.addEventListener("popstate", check);
    window.addEventListener("hashchange", check);
    check();
  })();
})();
