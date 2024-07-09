/* local-ai-lab — lesson step slider.
 * Turns a list of <section class="slide"> inside <div class="deck"> into a
 * navigable deck: prev/next buttons, progress bar, clickable dots, arrow-key
 * support, deep-linkable steps (#step-3), and copy buttons on code blocks.
 */
(function () {
  const deck = document.querySelector(".deck");
  if (!deck) return;

  const slides = Array.from(deck.querySelectorAll(".slide"));
  const dotsWrap = document.querySelector(".dots");
  const bar = document.querySelector(".progress > span");
  const prevBtn = document.querySelector("[data-prev]");
  const nextBtn = document.querySelector("[data-next]");
  const counter = document.querySelector(".counter");
  let i = 0;

  // Build clickable dots
  slides.forEach((_, idx) => {
    const b = document.createElement("button");
    b.title = "Step " + (idx + 1);
    b.addEventListener("click", () => go(idx));
    dotsWrap && dotsWrap.appendChild(b);
  });
  const dots = dotsWrap ? Array.from(dotsWrap.children) : [];

  function setHeight() {
    deck.style.height = slides[i].offsetHeight + "px";
  }

  function render() {
    slides.forEach((s, idx) => s.classList.toggle("active", idx === i));
    dots.forEach((d, idx) => d.classList.toggle("on", idx === i));
    if (bar) bar.style.width = ((i + 1) / slides.length) * 100 + "%";
    if (counter) counter.textContent = `Step ${i + 1} of ${slides.length}`;
    if (prevBtn) prevBtn.disabled = i === 0;
    if (nextBtn) nextBtn.disabled = i === slides.length - 1;
    setHeight();
    if (history.replaceState) history.replaceState(null, "", "#step-" + (i + 1));
  }

  function go(n) {
    i = Math.max(0, Math.min(slides.length - 1, n));
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  prevBtn && prevBtn.addEventListener("click", () => go(i - 1));
  nextBtn && nextBtn.addEventListener("click", () => go(i + 1));

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "ArrowRight") go(i + 1);
    if (e.key === "ArrowLeft") go(i - 1);
  });

  // Copy buttons on every <pre>
  document.querySelectorAll("pre").forEach((pre) => {
    const btn = document.createElement("button");
    btn.className = "copy";
    btn.textContent = "Copy";
    btn.addEventListener("click", () => {
      const text = pre.innerText;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = "Copied!";
        btn.classList.add("done");
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.classList.remove("done");
        }, 1400);
      });
    });
    pre.parentElement.appendChild(btn);
  });

  // Deep link: open on the step in the URL hash (#step-N)
  const m = location.hash.match(/step-(\d+)/);
  if (m) i = Math.max(0, Math.min(slides.length - 1, parseInt(m[1], 10) - 1));

  window.addEventListener("resize", setHeight);
  window.addEventListener("load", render);
  render();
})();
