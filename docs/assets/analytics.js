/* local-ai-lab — privacy-friendly usage analytics (GoatCounter).
 *
 * Cookieless: no cookies and no persistent identifiers (GoatCounter derives a
 * country from the IP transiently at ingest, then discards it — it is not stored).
 * This file is the ONLY place GoatCounter is wired in: it loads count.js itself,
 * over explicit https, and only on the production Pages host — so local previews
 * (localhost / 127.* / file://) never load the script or send a pageview. On top
 * of the normal pageview it records:
 *   - click tracking: PDF downloads (e.g. the cheat-sheet) and outbound links
 *   - slide depth:    per-lesson `lesson-N/step-K` and a `…/complete` event
 */
(function () {
  "use strict";

  // Scope to this repo's Pages site only. nikolareljin.github.io serves every
  // project site, so the hostname alone isn't enough — also require the
  // /local-ai-lab/ base path.
  var PROD_HOST = "nikolareljin.github.io";
  var PROD_BASE = "/local-ai-lab/";
  if (location.hostname !== PROD_HOST || location.pathname.indexOf(PROD_BASE) !== 0) {
    return; // prod-only: no count.js, no events
  }

  var ENDPOINT = "https://nikolareljin.goatcounter.com/count";
  var MAX_QUEUE = 50; // bound in-memory growth if count.js never loads

  // We control the pageview ourselves, so suppress count.js's own onload hit.
  window.goatcounter = { no_onload: true, endpoint: ENDPOINT };

  var seen = Object.create(null); // de-dupe within a visit (no storage, no id)
  var queue = [];                 // events fired before count.js finishes loading
  var ready = false;
  var failed = false;             // count.js couldn't load — stop queuing

  function send(opts) {
    var g = window.goatcounter;
    if (g && typeof g.count === "function") g.count(opts);
  }

  // Queue until count.js is ready, then flush — so early clicks/slides aren't lost.
  // If loading fails, or the queue hits its cap, drop the event instead of growing
  // memory unbounded.
  function track(opts) {
    if (failed) return;
    if (ready) send(opts);
    else if (queue.length < MAX_QUEUE) queue.push(opts);
  }

  function fire(path, title) {
    if (!path) return;
    if (path.charAt(0) !== "/") path = "/" + path; // GoatCounter paths start with "/"
    if (seen[path]) return;
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
  s.onerror = function () {
    // Network error / blocked: never flips ready, so release the queue and stop.
    failed = true;
    queue.length = 0;
  };
  (document.head || document.documentElement).appendChild(s);

  // --- Click tracking: PDF downloads + outbound links ---
  document.addEventListener(
    "click",
    function (e) {
      var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
      if (!a || !a.href) return;
      // Resolve against the document so query strings / fragments don't leak into
      // the event name (e.g. file.pdf#page=2, file.pdf?dl=1) and break de-dupe.
      var url;
      try {
        url = new URL(a.href, location.href);
      } catch (err) {
        return;
      }
      if (/\.pdf$/i.test(url.pathname)) {
        fire("download/" + url.pathname.split("/").pop(), a.textContent.trim());
      } else if (
        url.hostname &&
        url.hostname !== location.hostname &&
        /^https?:$/i.test(url.protocol)
      ) {
        fire("outbound/" + url.hostname + url.pathname, a.textContent.trim());
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
