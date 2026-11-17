/* Short version first: long pages show a heading for each section, and a tap opens the section.
   Without JavaScript everything simply stays open.

   ylhCollapse({
     cards:  ".system-card",          // each section is one card: the head stays, everything else folds away
     head:   ".system-header",        // the head inside each card (default: the card's first child)
     pairs:  false,                   // true: each head is followed by a sibling body instead (head = cards selector, body = bodySel)
     body:   ".templates-grid",       // pairs mode: the sibling that folds away
     open:   "first" | "none" | "all",// which sections start open (a section named in the URL # always opens)
     toolbar: true                    // add "Open all / Close all"
   })
*/
(function () {
  var css = ".ylh-cl-hidden{display:none !important;}" +
    ".ylh-cl-head{cursor:pointer;display:flex !important;align-items:center;justify-content:space-between;gap:.75rem;-webkit-tap-highlight-color:transparent;}" +
    ".ylh-cl-head:focus-visible{outline:2px solid #8F6244;outline-offset:2px;border-radius:6px;}" +
    ".ylh-cl-chev{flex:0 0 auto;width:.6rem;height:.6rem;border-right:2px solid #8F6244;border-bottom:2px solid #8F6244;transform:rotate(45deg);transition:transform .2s;margin:0 .35rem .2rem .5rem;}" +
    ".ylh-cl-head[aria-expanded=true] .ylh-cl-chev{transform:rotate(-135deg);margin-bottom:-.2rem;}" +
    ".ylh-cl-bar{display:flex;gap:1rem;justify-content:flex-end;margin:0 0 .6rem;font-size:.85rem;}" +
    ".ylh-cl-bar button{all:unset;cursor:pointer;color:#8F6244;font-weight:700;text-decoration:underline;padding:.35rem .2rem;min-height:24px;}" +
    "@media (prefers-reduced-motion: reduce){.ylh-cl-chev{transition:none;}}";

  function addCss() {
    if (document.getElementById("ylh-cl-css")) return;
    var s = document.createElement("style");
    s.id = "ylh-cl-css";
    s.textContent = css;
    document.head.appendChild(s);
  }

  window.ylhCollapse = function (cfg) {
    try {
      build(cfg);
    } catch (e) {   // never leave anything hidden if something goes wrong
      Array.prototype.forEach.call(document.querySelectorAll(".ylh-cl-hidden"), function (n) { n.classList.remove("ylh-cl-hidden"); });
      if (window.console) console.warn("collapsible: showing everything", e);
    }
  };

  function build(cfg) {
    addCss();
    var nodes = Array.prototype.slice.call(document.querySelectorAll(cfg.cards));
    var startOpen = function (card, i) {
      if (cfg.open === "all") return true;
      if (cfg.open === "none") return false;
      if (cfg.open === "first" || !cfg.open) return i === 0;
      return card.matches(cfg.open);   // any other value is a CSS selector for the sections that start open
    };
    var groups = [];
    nodes.forEach(function (card) {
      var head, body = [];
      if (cfg.pairs) {
        head = card;
        var n = card.nextElementSibling;
        while (n && !n.matches(cfg.body) && !n.matches(cfg.cards)) n = n.nextElementSibling;
        if (n && n.matches(cfg.body)) body = [n];
      } else {
        head = cfg.head ? card.querySelector(":scope > " + cfg.head) : card.firstElementChild;
        if (!head) return;
        Array.prototype.forEach.call(card.children, function (c) { if (c !== head) body.push(c); });
      }
      if (!body.length) return;
      groups.push({ card: card, head: head, body: body });
    });
    if (groups.length < 2) return;

    function setOpen(g, open) {
      g.head.setAttribute("aria-expanded", open ? "true" : "false");
      g.body.forEach(function (b) { b.classList.toggle("ylh-cl-hidden", !open); });
    }
    groups.forEach(function (g, i) {
      g.head.classList.add("ylh-cl-head");
      g.head.setAttribute("role", "button");
      g.head.setAttribute("tabindex", "0");
      var chev = document.createElement("span");
      chev.className = "ylh-cl-chev";
      chev.setAttribute("aria-hidden", "true");
      g.head.appendChild(chev);
      setOpen(g, startOpen(g.card, i));
      function toggle() { setOpen(g, g.head.getAttribute("aria-expanded") !== "true"); }
      g.head.addEventListener("click", function (e) { if (e.target.closest("a, button, input, select, textarea")) return; toggle(); });
      g.head.addEventListener("keydown", function (e) {
        if ((e.key === "Enter" || e.key === " ") && e.target === g.head) { e.preventDefault(); toggle(); }
      });
    });

    function openFromHash() {
      var id = (location.hash || "").slice(1);
      if (!id) return;
      groups.forEach(function (g) {
        var hit = g.card.id === id || (document.getElementById(id) && g.card.contains(document.getElementById(id)));
        if (hit) {
          setOpen(g, true);
          setTimeout(function () { g.card.scrollIntoView({ behavior: "smooth", block: "start" }); }, 30);
        }
      });
    }
    window.addEventListener("hashchange", openFromHash);
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      if (a && a.getAttribute("href").length > 1) setTimeout(openFromHash, 0);
    });
    openFromHash();

    if (cfg.toolbar !== false) {
      var bar = document.createElement("div");
      bar.className = "ylh-cl-bar";
      [["Open all", true], ["Close all", false]].forEach(function (x) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = x[0];
        b.addEventListener("click", function () { groups.forEach(function (g) { setOpen(g, x[1]); }); });
        bar.appendChild(b);
      });
      var first = groups[0].card;
      first.parentNode.insertBefore(bar, first);
    }
  }
})();
