(function () {
  "use strict";

  /**
   * false = level clears when every color pair is connected (matches player expectation).
   * true = must also cover every cell (classic Flow-style).
   * Per-level: set requireFullFill: true in level JSON to override.
   */
  const WIN_REQUIRES_FULL_GRID_DEFAULT = false;

  const STORAGE_HINTS = "colorDotsHintsV1";
  const STORAGE_DONE = "colorDotsDoneV1";
  const STORAGE_DAILY_LEGACY = "colorDotsDailyV1";
  const STORAGE_DAILY_PROGRESS = "colorDotsDailyV2";

  const DAILY_YEAR = 2026;
  const DAILY_SUBLEVELS = 3;

  function I() {
    return window.COLOR_DOTS_I18N;
  }

  /** @type {"campaign" | "daily"} */
  let gameMode = "campaign";
  /** @type {"levels" | "home-game" | "home-daily"} */
  let gameBackTarget = "home-game";
  /** 1–12 month currently shown in daily calendar */
  let dailyViewMonth = 1;
  /** @type {{ y: number; m: number; d: number; sub: number } | null} */
  let dailyContext = null;

  /** @type {any[]} */
  let levels = [];
  let levelIndex = 0;
  /** @type {any} */
  let level = null;
  let n = 0;
  /** @type {{ locked: boolean; cells: string[] }[]} */
  let paths = [];
  /** @type {{ pairIndex: number; cells: string[] } | null} */
  let active = null;
  let moves = 0;
  /** @type {string} */
  let history = [];
  let hintTimer = 0;
  let hintCellKey = "";
  let layoutLinesRaf = 0;
  let resizeTimer = 0;
  let confettiRaf = 0;
  /** @type {CanvasRenderingContext2D | null} */
  let confettiCtx = null;
  /** @type {any[]} */
  let confettiParticles = [];
  let confettiRunning = false;
  /** @type {number[]} */
  let winConfettiSpawnTimers = [];
  let winDismissTimer = 0;
  let confettiBurstUntil = 0;

  const el = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";

  function cellKey(r, c) {
    return r + "," + c;
  }

  function parseKey(k) {
    const p = k.split(",");
    return [Number(p[0]), Number(p[1])];
  }

  function adj(r1, c1, r2, c2) {
    return Math.abs(r1 - r2) + Math.abs(c1 - c2) === 1;
  }

  function neighbors(r, c) {
    const o = [];
    if (r > 0) o.push([r - 1, c]);
    if (r < n - 1) o.push([r + 1, c]);
    if (c > 0) o.push([r, c - 1]);
    if (c < n - 1) o.push([r, c + 1]);
    return o;
  }

  function loadLevels() {
    if (typeof window.COLOR_DOTS_LEVELS !== "undefined" && Array.isArray(window.COLOR_DOTS_LEVELS)) {
      levels = window.COLOR_DOTS_LEVELS;
    } else {
      levels = [];
    }
  }

  function loadHints() {
    const raw = localStorage.getItem(STORAGE_HINTS);
    const v = raw == null ? 3 : Number(raw);
    return Number.isFinite(v) ? Math.max(0, Math.min(99, v)) : 3;
  }

  function saveHints(h) {
    localStorage.setItem(STORAGE_HINTS, String(h));
  }

  function loadDone() {
    try {
      const raw = localStorage.getItem(STORAGE_DONE);
      if (!raw) return new Set();
      const arr = JSON.parse(raw);
      return new Set(Array.isArray(arr) ? arr.map(String) : []);
    } catch {
      return new Set();
    }
  }

  function saveDone(set) {
    localStorage.setItem(STORAGE_DONE, JSON.stringify([...set]));
  }

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function dailyDateKeyFull(y, m, d) {
    return y + "-" + pad2(m) + "-" + pad2(d);
  }

  function daysInMonth(y, m) {
    return new Date(y, m, 0).getDate();
  }

  function loadDailyProgressMap() {
    try {
      const raw = localStorage.getItem(STORAGE_DAILY_PROGRESS);
      if (raw) {
        const o = JSON.parse(raw);
        if (o && typeof o === "object" && !Array.isArray(o)) return o;
      }
      const leg = localStorage.getItem(STORAGE_DAILY_LEGACY);
      if (!leg) return {};
      const o1 = JSON.parse(leg);
      const out = {};
      if (o1 && typeof o1 === "object" && !Array.isArray(o1)) {
        Object.keys(o1).forEach(function (k) {
          if (o1[k]) out[k] = DAILY_SUBLEVELS;
        });
      }
      if (Object.keys(out).length) localStorage.setItem(STORAGE_DAILY_PROGRESS, JSON.stringify(out));
      return out;
    } catch {
      return {};
    }
  }

  function saveDailyProgressMap(map) {
    localStorage.setItem(STORAGE_DAILY_PROGRESS, JSON.stringify(map));
  }

  function getDailyProgress(key) {
    const map = loadDailyProgressMap();
    const v = map[key];
    const n = Number(v);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(DAILY_SUBLEVELS, Math.floor(n)));
  }

  function setDailyProgress(key, n) {
    const map = loadDailyProgressMap();
    map[key] = Math.max(0, Math.min(DAILY_SUBLEVELS, n));
    saveDailyProgressMap(map);
  }

  function startOfDay(ts) {
    const x = new Date(ts);
    x.setHours(0, 0, 0, 0);
    return x.getTime();
  }

  function isDayUnlocked2026(y, m, d) {
    if (y !== DAILY_YEAR) return false;
    const cell = new Date(y, m - 1, d).getTime();
    const now = new Date();
    const ny = now.getFullYear();
    if (ny > DAILY_YEAR) return true;
    if (ny < DAILY_YEAR) return false;
    return cell <= startOfDay(now.getTime());
  }

  function isToday2026(y, m, d) {
    const n = new Date();
    return n.getFullYear() === y && n.getMonth() + 1 === m && n.getDate() === d;
  }

  function dailyThreeIndices(y, m, d) {
    const L = levels.length;
    if (L < 1) return [0, 0, 0];
    const seed = y * 10000 + m * 100 + d;
    const out = [];
    for (let k = 0; k < DAILY_SUBLEVELS; k++) {
      let v = (seed * (7919 + k * 131) + k * 17 + 5) % L;
      let guard = 0;
      while (out.indexOf(v) >= 0 && guard < L + 8) {
        v = (v + 1) % L;
        guard++;
      }
      out.push(v);
    }
    return out;
  }

  function isEndpoint(pi, r, c) {
    const p = level.pairs[pi];
    return (p.start[0] === r && p.start[1] === c) || (p.end[0] === r && p.end[1] === c);
  }

  function endpointPairIndex(r, c) {
    for (let i = 0; i < level.pairs.length; i++) {
      if (isEndpoint(i, r, c)) return i;
    }
    return -1;
  }

  function isForeignEndpoint(r, c, activePi) {
    for (let j = 0; j < level.pairs.length; j++) {
      if (j === activePi) continue;
      if (isEndpoint(j, r, c)) return true;
    }
    return false;
  }

  function occupiedByLockedOther(pi, r, c) {
    const k = cellKey(r, c);
    for (let j = 0; j < paths.length; j++) {
      if (j === pi) continue;
      if (!paths[j].locked) continue;
      if (paths[j].cells.includes(k)) return true;
    }
    return false;
  }

  function snapshotPaths() {
    return JSON.stringify(paths.map((p) => ({ locked: p.locked, cells: [...p.cells] })));
  }

  function applySnapshot(s) {
    const data = JSON.parse(s);
    paths = data.map((p) => ({ locked: p.locked, cells: [...p.cells] }));
  }

  function fillPercent() {
    const s = new Set();
    for (const p of paths) {
      for (const k of p.cells) s.add(k);
    }
    if (active) {
      for (const k of active.cells) s.add(k);
    }
    return Math.round((s.size / (n * n)) * 100);
  }

  function lockedLines() {
    return paths.filter((p) => p.locked).length;
  }

  function levelRequiresFullGrid() {
    if (level && typeof level.requireFullFill === "boolean") return level.requireFullFill;
    return WIN_REQUIRES_FULL_GRID_DEFAULT;
  }

  function checkWin() {
    if (!level.pairs.every((_, i) => paths[i].locked)) return false;
    const covered = new Set();
    for (let i = 0; i < paths.length; i++) {
      for (const k of paths[i].cells) {
        if (covered.has(k)) return false;
        covered.add(k);
      }
    }
    if (levelRequiresFullGrid()) return covered.size === n * n;
    return true;
  }

  function orderedSolutionCells(pi) {
    const sol = level.solution;
    const allow = new Set();
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        if (sol[r][c] === pi) allow.add(cellKey(r, c));
      }
    }
    const targetEnd = cellKey(level.pairs[pi].end[0], level.pairs[pi].end[1]);
    const start = cellKey(level.pairs[pi].start[0], level.pairs[pi].start[1]);
    const prev = new Map();
    prev.set(start, null);
    const q = [start];
    let found = null;
    for (let qi = 0; qi < q.length; qi++) {
      const cur = q[qi];
      if (cur === targetEnd) {
        found = cur;
        break;
      }
      const [r, c] = parseKey(cur);
      for (const [nr, nc] of neighbors(r, c)) {
        const nk = cellKey(nr, nc);
        if (!allow.has(nk) || prev.has(nk)) continue;
        prev.set(nk, cur);
        q.push(nk);
      }
    }
    if (!found) return [];
    const out = [];
    let x = found;
    while (x) {
      out.push(x);
      x = prev.get(x);
    }
    out.reverse();
    return out;
  }

  function pulseStat(id) {
    const node = el(id);
    if (!node) return;
    node.classList.remove("pop");
    void node.offsetWidth;
    node.classList.add("pop");
    window.setTimeout(() => node.classList.remove("pop"), 500);
  }

  function updateStats(opts) {
    el("stat-moves").textContent = String(moves);
    el("stat-lines").textContent = lockedLines() + "/" + level.pairs.length;
    el("stat-fill").textContent = fillPercent() + "%";
    if (opts && opts.pulseMoves) pulseStat("stat-moves");
    if (opts && opts.pulseLines) pulseStat("stat-lines");
    if (opts && opts.pulseFill) pulseStat("stat-fill");
  }

  function colorAtCell(r, c) {
    const k = cellKey(r, c);
    if (active && active.cells.includes(k)) {
      return level.pairs[active.pairIndex].color;
    }
    for (let i = 0; i < paths.length; i++) {
      if (paths[i].cells.includes(k)) return level.pairs[i].color;
    }
    return null;
  }

  function ensureBoardSvgDefs() {
    const svg = el("board-svg");
    if (!svg || svg.querySelector("defs")) return;
    const defs = document.createElementNS(SVG_NS, "defs");
    const filter = document.createElementNS(SVG_NS, "filter");
    filter.setAttribute("id", "neon-glow");
    filter.setAttribute("x", "-80%");
    filter.setAttribute("y", "-80%");
    filter.setAttribute("width", "260%");
    filter.setAttribute("height", "260%");
    const blur = document.createElementNS(SVG_NS, "feGaussianBlur");
    blur.setAttribute("in", "SourceGraphic");
    blur.setAttribute("stdDeviation", "2.1");
    blur.setAttribute("result", "blur");
    const merge = document.createElementNS(SVG_NS, "feMerge");
    const mn1 = document.createElementNS(SVG_NS, "feMergeNode");
    mn1.setAttribute("in", "blur");
    const mn2 = document.createElementNS(SVG_NS, "feMergeNode");
    mn2.setAttribute("in", "SourceGraphic");
    merge.appendChild(mn1);
    merge.appendChild(mn2);
    filter.appendChild(blur);
    filter.appendChild(merge);
    defs.appendChild(filter);
    svg.appendChild(defs);
  }

  function cellCenterPx(r, c) {
    const stack = el("board-stack");
    const cellsRoot = el("board-cells");
    if (!stack || !cellsRoot) return null;
    const cell = cellsRoot.querySelector('.cell[data-r="' + r + '"][data-c="' + c + '"]');
    if (!cell) return null;
    const br = cell.getBoundingClientRect();
    const sr = stack.getBoundingClientRect();
    return {
      x: br.left + br.width / 2 - sr.left,
      y: br.top + br.height / 2 - sr.top,
    };
  }

  function keysToPathD(keys) {
    const pts = [];
    for (let i = 0; i < keys.length; i++) {
      const [r, c] = parseKey(keys[i]);
      const p = cellCenterPx(r, c);
      if (p) pts.push(p);
    }
    if (pts.length < 2) return "";
    let d = "M " + pts[0].x + " " + pts[0].y;
    for (let i = 1; i < pts.length; i++) {
      d += " L " + pts[i].x + " " + pts[i].y;
    }
    return d;
  }

  function layoutBoardLines() {
    const svg = el("board-svg");
    const stack = el("board-stack");
    if (!svg || !stack || !level) return;
    ensureBoardSvgDefs();

    svg.querySelectorAll("g.board-line-root").forEach((g) => g.remove());

    const w = stack.clientWidth;
    const h = stack.clientHeight;
    if (w < 2 || h < 2) return;
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");

    const cellPx = Math.min(w, h) / n;
    const strokeBase = Math.max(2.8, cellPx * 0.24);
    const glowWidth = strokeBase * 2.35;

    function appendPathGroup(d, color, draft) {
      if (!d) return;
      const coreStroke = mixTowardWhite(color, 0.52);
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", "board-line-root" + (draft ? " board-lines-group--draft" : ""));

      const glow = document.createElementNS(SVG_NS, "path");
      glow.setAttribute("d", d);
      glow.setAttribute("fill", "none");
      glow.setAttribute("stroke", color);
      glow.setAttribute("stroke-width", String(glowWidth));
      glow.setAttribute("stroke-linecap", "round");
      glow.setAttribute("stroke-linejoin", "round");
      glow.setAttribute("opacity", draft ? "0.22" : "0.28");
      glow.setAttribute("filter", "url(#neon-glow)");

      const core = document.createElementNS(SVG_NS, "path");
      core.setAttribute("d", d);
      core.setAttribute("fill", "none");
      core.setAttribute("stroke", coreStroke);
      core.setAttribute("stroke-width", String(draft ? strokeBase * 0.92 : strokeBase));
      core.setAttribute("stroke-linecap", "round");
      core.setAttribute("stroke-linejoin", "round");
      core.setAttribute("opacity", draft ? "0.88" : "0.98");

      g.appendChild(glow);
      g.appendChild(core);
      svg.appendChild(g);
    }

    for (let i = 0; i < paths.length; i++) {
      if (!paths[i].locked || paths[i].cells.length < 2) continue;
      const d = keysToPathD(paths[i].cells);
      appendPathGroup(d, level.pairs[i].color, false);
    }

    if (active && active.cells.length >= 2) {
      const d = keysToPathD(active.cells);
      appendPathGroup(d, level.pairs[active.pairIndex].color, true);
    }
  }

  function scheduleLayoutLines() {
    if (layoutLinesRaf) cancelAnimationFrame(layoutLinesRaf);
    layoutLinesRaf = requestAnimationFrame(() => {
      layoutLinesRaf = 0;
      layoutBoardLines();
      requestAnimationFrame(layoutBoardLines);
    });
  }

  function renderBoard() {
    const cellsRoot = el("board-cells");
    if (!cellsRoot) return;
    ensureBoardSvgDefs();

    cellsRoot.innerHTML = "";
    cellsRoot.style.gridTemplateColumns = "repeat(" + n + ", 1fr)";
    cellsRoot.style.gridTemplateRows = "repeat(" + n + ", 1fr)";

    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        const cell = document.createElement("div");
        cell.className = "cell";
        cell.dataset.r = String(r);
        cell.dataset.c = String(c);
        if ((r + c) % 2 === 1) cell.classList.add("cell--alt");
        const col = colorAtCell(r, c);
        if (col) {
          cell.classList.add("path");
          cell.style.background = hexToRgba(col, 0.17);
          cell.style.boxShadow = "inset 0 0 16px " + hexToRgba(col, 0.24);
        } else {
          cell.style.background = "";
          cell.style.boxShadow = "";
        }
        if (hintCellKey === cellKey(r, c)) cell.classList.add("hint-pulse");
        cellsRoot.appendChild(cell);

        const ep = endpointPairIndex(r, c);
        if (ep >= 0) {
          const dot = document.createElement("div");
          dot.className = "dot";
          const hue = level.pairs[ep].color;
          const hi = mixTowardWhite(hue, 0.38);
          const lo = mixTowardBlack(hue, 0.38);
          const ring = mixTowardWhite(hue, 0.12);
          dot.style.color = hue;
          dot.style.borderColor = ring;
          dot.style.background =
            "radial-gradient(circle at 34% 28%, " +
            hi +
            " 0%, " +
            hue +
            " 48%, " +
            lo +
            " 92%)";
          dot.style.boxShadow =
            "0 0 0 1px rgba(255,255,255,0.88), 0 0 0 3px " +
            hexToRgba(hue, 0.55) +
            ", 0 0 22px " +
            hexToRgba(hue, 0.65) +
            ", 0 3px 10px rgba(0,0,0,0.45), inset 0 2px 12px rgba(255,255,255,0.42)";
          cell.appendChild(dot);
        }
      }
    }
    scheduleLayoutLines();
  }

  function hexToRgba(hex, a) {
    const h = hex.replace("#", "");
    const bigint = parseInt(h, 16);
    const r = (bigint >> 16) & 255;
    const g = (bigint >> 8) & 255;
    const b = bigint & 255;
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  }

  function mixTowardWhite(hex, t) {
    const h = hex.replace("#", "");
    if (h.length !== 6) return hex;
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    const R = Math.round(r + (255 - r) * t);
    const G = Math.round(g + (255 - g) * t);
    const B = Math.round(b + (255 - b) * t);
    return "#" + [R, G, B].map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  function mixTowardBlack(hex, t) {
    const h = hex.replace("#", "");
    if (h.length !== 6) return hex;
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    const k = 1 - t;
    const R = Math.round(r * k);
    const G = Math.round(g * k);
    const B = Math.round(b * k);
    return "#" + [R, G, B].map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  function showScreen(id) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
    el(id).classList.add("active");
  }

  function showHomeHub() {
    const hub = el("home-hub");
    const panelD = el("home-panel-daily");
    if (hub) hub.hidden = false;
    if (panelD) panelD.hidden = true;
  }

  function showHomeDaily() {
    const hub = el("home-hub");
    const panelD = el("home-panel-daily");
    if (hub) hub.hidden = true;
    if (panelD) panelD.hidden = false;
    buildDailyCalendar();
  }

  function openHomeMenu() {
    const o = el("overlay-home-menu");
    if (!o) return;
    o.classList.add("sheet-overlay--open");
    o.setAttribute("aria-hidden", "false");
    I().applyDom();
  }

  function closeHomeMenu() {
    const o = el("overlay-home-menu");
    if (!o) return;
    o.classList.remove("sheet-overlay--open");
    o.setAttribute("aria-hidden", "true");
  }

  function openHowtoDialog() {
    const o = el("overlay-howto");
    if (!o) return;
    closeHomeMenu();
    o.classList.add("sheet-overlay--open");
    o.setAttribute("aria-hidden", "false");
    I().applyDom();
  }

  function closeHowtoDialog() {
    const o = el("overlay-howto");
    if (!o) return;
    o.classList.remove("sheet-overlay--open");
    o.setAttribute("aria-hidden", "true");
  }

  function buildMonthStripOnce() {
    const strip = el("daily-month-strip");
    if (!strip || strip.dataset.built === "1") return;
    strip.dataset.built = "1";
    strip.innerHTML = "";
    for (let mi = 1; mi <= 12; mi++) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "daily-month-chip";
      b.dataset.month = String(mi);
      b.textContent = I().monthShort(mi);
      b.setAttribute("role", "tab");
      (function (m) {
        b.addEventListener("click", function () {
          dailyViewMonth = m;
          updateMonthStripActive();
          buildDailyCalendar();
        });
      })(mi);
      strip.appendChild(b);
    }
    updateMonthStripActive();
  }

  function updateMonthStripActive() {
    const strip = el("daily-month-strip");
    if (!strip) return;
    strip.querySelectorAll(".daily-month-chip").forEach(function (btn) {
      const mi = Number(btn.dataset.month);
      const on = mi === dailyViewMonth;
      btn.classList.toggle("daily-month-chip--active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function buildDailyCalendar() {
    const root = el("daily-calendar");
    const label = el("daily-month-label");
    const prev = el("daily-prev-month");
    const next = el("daily-next-month");
    if (!root) return;
    if (label) label.textContent = I().monthLong(dailyViewMonth);
    if (prev) prev.disabled = dailyViewMonth <= 1;
    if (next) next.disabled = dailyViewMonth >= 12;
    updateMonthStripActive();

    root.innerHTML = "";
    const y = DAILY_YEAR;
    const m = dailyViewMonth;
    const dim = daysInMonth(y, m);
    const first = new Date(y, m - 1, 1);
    const mondayFirstOffset = (first.getDay() + 6) % 7;

    for (let i = 0; i < 42; i++) {
      const slot = document.createElement("div");
      slot.className = "daily-cal-slot";
      if (i < mondayFirstOffset || i >= mondayFirstOffset + dim) {
        slot.classList.add("daily-cal-slot--empty");
        root.appendChild(slot);
        continue;
      }
      const d = i - mondayFirstOffset + 1;
      const key = dailyDateKeyFull(y, m, d);
      const unlocked = isDayUnlocked2026(y, m, d);
      const prog = getDailyProgress(key);
      const pct = prog / DAILY_SUBLEVELS;
      const isToday = isToday2026(y, m, d);
      const isStar = prog >= DAILY_SUBLEVELS;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "daily-day";
      if (isStar) btn.classList.add("daily-day--star");
      if (isToday) btn.classList.add("daily-day--today");
      btn.disabled = !unlocked;
      btn.style.setProperty("--daily-pct", String(pct));

      const ring = document.createElement("span");
      ring.className = "daily-day-ring";
      ring.setAttribute("aria-hidden", "true");
      const inner = document.createElement("span");
      inner.className = "daily-day-inner";
      if (isStar) {
        inner.textContent = "★";
      } else {
        inner.appendChild(document.createTextNode(String(d)));
        const sub = document.createElement("span");
        sub.className = "daily-day-sub";
        sub.textContent = prog + "/" + DAILY_SUBLEVELS;
        inner.appendChild(sub);
      }
      btn.appendChild(ring);
      btn.appendChild(inner);
      btn.setAttribute(
        "aria-label",
        isStar
          ? I().tr("daily_aria_done", { month: I().monthLong(m), day: d })
          : I().tr("daily_aria_prog", {
              month: I().monthLong(m),
              day: d,
              prog: prog,
              total: DAILY_SUBLEVELS,
            }),
      );
      (function (yy, mm, dd) {
        btn.addEventListener("click", function () {
          if (!isDayUnlocked2026(yy, mm, dd)) return;
          startDailyChallenge(yy, mm, dd);
        });
      })(y, m, d);

      slot.appendChild(btn);
      root.appendChild(slot);
    }
  }

  function applyLevelState(idx) {
    levelIndex = idx;
    level = levels[idx];
    n = level.size;
    paths = level.pairs.map(() => ({ locked: false, cells: [] }));
    active = null;
    moves = 0;
    history = [];
    hintCellKey = "";
    updateStats();
    renderBoard();
    updateHintBadge();
  }

  function startDailyChallenge(y, m, d, forceSub) {
    if (!levels.length || !isDayUnlocked2026(y, m, d)) return;
    closeWin();
    const key = dailyDateKeyFull(y, m, d);
    const prog = getDailyProgress(key);
    let sub =
      forceSub !== undefined && forceSub !== null
        ? forceSub
        : prog >= DAILY_SUBLEVELS
          ? 0
          : prog;
    sub = Math.max(0, Math.min(DAILY_SUBLEVELS - 1, sub));
    const triple = dailyThreeIndices(y, m, d);
    const idx = triple[sub];
    gameMode = "daily";
    dailyContext = { y: y, m: m, d: d, sub: sub };
    gameBackTarget = "home-daily";
    applyLevelState(idx);
    el("game-title").textContent = I().tr("game_title_daily", {
      d: pad2(d),
      m: pad2(m),
      sub: sub + 1,
    });
    showScreen("screen-game");
  }

  function buildLevelGrid() {
    const grid = el("level-grid");
    grid.innerHTML = "";
    const done = loadDone();
    levels.forEach((L, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "level-tile" + (done.has(String(i)) ? " done" : "");
      b.innerHTML = "<span>" + (i + 1) + "</span><small>" + escapeHtml(L.name) + "</small>";
      b.addEventListener("click", function () {
        startGame(i, { from: "levels" });
      });
      grid.appendChild(b);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function startGame(idx, opts) {
    closeWin();
    gameMode = "campaign";
    dailyContext = null;
    if (opts && opts.from === "home") gameBackTarget = "home-game";
    else if (opts && opts.from === "levels") gameBackTarget = "levels";
    applyLevelState(idx);
    el("game-title").textContent = I().tr("game_title_level", { n: idx + 1 });
    showScreen("screen-game");
  }

  function updateHintBadge() {
    el("hint-badge").textContent = String(loadHints());
  }

  function clientToCell(clientX, clientY) {
    const cellsRoot = el("board-cells");
    if (!cellsRoot) return null;
    const cells = cellsRoot.querySelectorAll(".cell");
    for (let i = 0; i < cells.length; i++) {
      const node = cells[i];
      const r = node.getBoundingClientRect();
      if (clientX >= r.left && clientX < r.right && clientY >= r.top && clientY < r.bottom) {
        return [Number(node.dataset.r), Number(node.dataset.c)];
      }
    }
    return null;
  }

  function onPointerDown(ev) {
    if (!level) return;
    const hit = clientToCell(ev.clientX, ev.clientY);
    if (!hit) return;
    const [r, c] = hit;
    const pi = endpointPairIndex(r, c);
    if (pi < 0) return;
    paths[pi].locked = false;
    paths[pi].cells = [];
    active = { pairIndex: pi, cells: [cellKey(r, c)] };
    try {
      el("board").setPointerCapture(ev.pointerId);
    } catch (_) {}
    renderBoard();
    updateStats();
  }

  function onPointerMove(ev) {
    if (!active || !level) return;
    const hit = clientToCell(ev.clientX, ev.clientY);
    if (!hit) return;
    const [r, c] = hit;
    const pi = active.pairIndex;
    const last = active.cells[active.cells.length - 1];
    const [lr, lc] = parseKey(last);
    if (lr === r && lc === c) return;

    const k = cellKey(r, c);
    const idxInTrail = active.cells.indexOf(k);
    if (idxInTrail >= 0) {
      active.cells = active.cells.slice(0, idxInTrail + 1);
      renderBoard();
      updateStats();
      return;
    }

    if (!adj(lr, lc, r, c)) return;

    if (occupiedByLockedOther(pi, r, c)) return;

    if (isForeignEndpoint(r, c, pi)) return;

    const isMineEnd = isEndpoint(pi, r, c);
    const startK = cellKey(level.pairs[pi].start[0], level.pairs[pi].start[1]);
    const endK = cellKey(level.pairs[pi].end[0], level.pairs[pi].end[1]);
    const otherEnd = active.cells[0] === startK ? endK : startK;

    if (isMineEnd && k === otherEnd && active.cells.length >= 1) {
      active.cells.push(k);
      history.push(snapshotPaths());
      paths[pi].cells = active.cells.slice();
      paths[pi].locked = true;
      active = null;
      moves += 1;
      renderBoard();
      updateStats({ pulseMoves: true, pulseLines: true, pulseFill: true });
      if (checkWin()) onWin();
      return;
    }

    if (!isMineEnd && !occupiedByLockedOther(pi, r, c)) {
      active.cells.push(k);
      renderBoard();
      updateStats();
    }
  }

  function onPointerUp(ev) {
    if (!level) return;
    if (active) {
      active = null;
      renderBoard();
      updateStats();
    }
    try {
      el("board").releasePointerCapture(ev.pointerId);
    } catch (_) {}
  }

  function clearWinConfettiSpawns() {
    winConfettiSpawnTimers.forEach((t) => clearTimeout(t));
    winConfettiSpawnTimers = [];
  }

  function stopWinConfetti() {
    confettiRunning = false;
    clearWinConfettiSpawns();
    if (confettiRaf) {
      cancelAnimationFrame(confettiRaf);
      confettiRaf = 0;
    }
    confettiParticles = [];
    confettiBurstUntil = 0;
    const canvas = el("win-confetti");
    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    confettiCtx = null;
  }

  function confettiTick() {
    if (!confettiRunning || !confettiCtx) return;
    const canvas = el("win-confetti");
    if (!canvas) return;
    const w = window.innerWidth;
    const h = window.innerHeight;
    const ctx = confettiCtx;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    for (let i = confettiParticles.length - 1; i >= 0; i--) {
      const p = confettiParticles[i];
      p.vy += p.gravity;
      p.vx *= p.drag;
      p.vy *= 0.9985;
      p.x += p.vx;
      p.y += p.vy;
      p.rotation += p.spin;
      p.alpha -= p.decay;
      if (p.alpha < 0.02 || p.y > h + 80 || p.x < -100 || p.x > w + 100) {
        confettiParticles.splice(i, 1);
        continue;
      }
      ctx.save();
      ctx.globalAlpha = Math.min(1, p.alpha);
      ctx.fillStyle = p.color;
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    }

    const t = Date.now();
    if (confettiRunning && (confettiParticles.length > 0 || t < confettiBurstUntil)) {
      confettiRaf = requestAnimationFrame(confettiTick);
    } else {
      confettiRaf = 0;
    }
  }

  function spawnConfettiFan(cx, cy, count, baseAngle) {
    const colors = [
      "#FF2D95",
      "#00E5FF",
      "#B388FF",
      "#69F0AE",
      "#FFEA00",
      "#FF5252",
      "#FFFFFF",
      "#FF9100",
    ];
    for (let i = 0; i < count; i++) {
      const ang = baseAngle + (Math.random() - 0.5) * Math.PI * 1.2;
      const sp = 7 + Math.random() * 17;
      confettiParticles.push({
        x: cx + (Math.random() - 0.5) * 48,
        y: cy + (Math.random() - 0.5) * 36,
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp - 3,
        w: 4 + Math.random() * 8,
        h: 5 + Math.random() * 11,
        color: colors[(Math.random() * colors.length) | 0],
        rotation: Math.random() * Math.PI * 2,
        spin: (Math.random() - 0.5) * 0.38,
        gravity: 0.1 + Math.random() * 0.15,
        drag: 0.9935,
        alpha: 1,
        decay: 0.0012 + Math.random() * 0.0022,
      });
    }
  }

  function startWinConfetti() {
    const canvas = el("win-confetti");
    if (!canvas) return;
    stopWinConfetti();
    confettiRunning = true;
    const w = window.innerWidth;
    const h = window.innerHeight;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    confettiCtx = canvas.getContext("2d");
    if (!confettiCtx) return;
    confettiCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    confettiBurstUntil = Date.now() + 6400;

    const cx = w / 2;
    const cy = h * 0.38;
    spawnConfettiFan(cx, cy, 118, -Math.PI / 2);
    winConfettiSpawnTimers.push(
      window.setTimeout(function () {
        spawnConfettiFan(cx * 0.42, cy + 40, 38, -Math.PI / 2 + 0.45);
      }, 110),
    );
    winConfettiSpawnTimers.push(
      window.setTimeout(function () {
        spawnConfettiFan(cx * 1.58, cy + 40, 38, -Math.PI / 2 - 0.45);
      }, 200),
    );
    winConfettiSpawnTimers.push(
      window.setTimeout(function () {
        spawnConfettiFan(cx, cy - 20, 48, -Math.PI / 2);
      }, 360),
    );

    if (!confettiRaf) confettiRaf = requestAnimationFrame(confettiTick);
  }

  function onWin() {
    const ov0 = el("win-overlay");
    if (ov0 && ov0.classList.contains("show")) return;

    if (gameMode === "daily" && dailyContext) {
      const key = dailyDateKeyFull(dailyContext.y, dailyContext.m, dailyContext.d);
      const p = getDailyProgress(key);
      setDailyProgress(key, Math.min(DAILY_SUBLEVELS, p + 1));
      buildDailyCalendar();
    } else if (gameMode === "campaign") {
      const done = loadDone();
      done.add(String(levelIndex));
      saveDone(done);
      buildLevelGrid();
    }

    const fp = fillPercent();
    const statsLine = I().tr("stats_line", {
      moves: moves,
      locked: lockedLines(),
      total: level.pairs.length,
      fp: fp,
    });

    if (gameMode === "daily" && dailyContext) {
      const key = dailyDateKeyFull(dailyContext.y, dailyContext.m, dailyContext.d);
      const doneN = getDailyProgress(key);
      if (doneN < DAILY_SUBLEVELS) {
        el("win-heading-3d").textContent = I().tr("win_puzzle_clear");
        el("win-moves-line").innerHTML = I().formatWinMovesHtml("win_moves_partial", moves, { done: doneN });
        let meta = I().tr("win_meta_next", {
          next: doneN + 1,
          total: DAILY_SUBLEVELS,
          stats: statsLine,
        });
        if (fp < 100) meta += I().tr("win_opt_fill_optional");
        el("win-meta").textContent = meta;
        el("win-next-label").textContent = I().tr("win_next_puzzle");
        el("btn-next-level").dataset.winAction = "daily-next";
      } else {
        el("win-heading-3d").textContent = I().tr("win_day_complete");
        el("win-moves-line").innerHTML = I().formatWinMovesHtml("win_moves_last", moves);
        let meta = I().tr("win_meta_day", {
          d: pad2(dailyContext.d),
          m: pad2(dailyContext.m),
          total: DAILY_SUBLEVELS,
          stats: statsLine,
        });
        if (fp < 100) meta += I().tr("win_opt_replay_cal");
        el("win-meta").textContent = meta;
        el("win-next-label").textContent = I().tr("win_calendar");
        el("btn-next-level").dataset.winAction = "daily-home";
      }
    } else {
      const hasNext = levelIndex + 1 < levels.length;
      el("win-heading-3d").textContent = I().tr("win_level_complete");
      el("win-moves-line").innerHTML = I().formatWinMovesHtml("win_moves_campaign", moves);
      let meta = statsLine;
      if (level.name) meta = level.name + " · " + meta;
      if (fp < 100) meta += I().tr("win_fill_hint");
      el("win-meta").textContent = meta;
      el("win-next-label").textContent = hasNext ? I().tr("win_next_level") : I().tr("win_choose_level");
      el("btn-next-level").dataset.winAction = hasNext ? "next" : "levels";
    }

    const ov = el("win-overlay");
    if (winDismissTimer) {
      clearTimeout(winDismissTimer);
      winDismissTimer = 0;
    }
    ov.classList.remove("win-overlay--out");
    ov.classList.add("show");
    ov.setAttribute("aria-hidden", "false");

    requestAnimationFrame(function () {
      startWinConfetti();
    });
  }

  function closeWin() {
    if (winDismissTimer) {
      clearTimeout(winDismissTimer);
      winDismissTimer = 0;
    }
    stopWinConfetti();
    const ov = el("win-overlay");
    ov.classList.remove("show", "win-overlay--out");
    ov.setAttribute("aria-hidden", "true");
  }

  function dismissWinAndGo(action) {
    const ov = el("win-overlay");
    if (!ov.classList.contains("show")) return;
    if (winDismissTimer) {
      clearTimeout(winDismissTimer);
      winDismissTimer = 0;
    }
    stopWinConfetti();
    ov.classList.add("win-overlay--out");
    winDismissTimer = window.setTimeout(function () {
      winDismissTimer = 0;
      ov.classList.remove("show", "win-overlay--out");
      ov.setAttribute("aria-hidden", "true");
      if (action === "next") startGame(levelIndex + 1);
      else if (action === "levels") {
        buildLevelGrid();
        showScreen("screen-levels");
      } else if (action === "daily-next" && dailyContext) {
        startDailyChallenge(dailyContext.y, dailyContext.m, dailyContext.d);
      } else if (action === "daily-home") {
        showScreen("screen-home");
        showHomeDaily();
      } else if (action === "replay") {
        restartLevel();
      } else {
        showScreen("screen-home");
        if (gameMode === "daily") showHomeDaily();
        else showHomeHub();
      }
    }, 300);
  }

  function restartLevel() {
    if (!level) return;
    closeWin();
    if (gameMode === "daily" && dailyContext) {
      startDailyChallenge(dailyContext.y, dailyContext.m, dailyContext.d, dailyContext.sub);
    } else startGame(levelIndex);
  }

  function undoMove() {
    if (!history.length) return;
    const snap = history.pop();
    applySnapshot(snap);
    if (moves > 0) moves -= 1;
    active = null;
    renderBoard();
    updateStats();
  }

  function useHint() {
    let hints = loadHints();
    if (hints <= 0) return;
    const incomplete = paths.findIndex((p) => !p.locked);
    if (incomplete < 0) return;
    const order = orderedSolutionCells(incomplete);
    const cur = new Set(paths[incomplete].cells);
    let pick = "";
    for (const k of order) {
      if (!cur.has(k)) {
        pick = k;
        break;
      }
    }
    if (!pick) return;
    hints -= 1;
    saveHints(hints);
    updateHintBadge();
    hintCellKey = pick;
    renderBoard();
    if (hintTimer) clearTimeout(hintTimer);
    hintTimer = window.setTimeout(() => {
      hintCellKey = "";
      renderBoard();
    }, 2200);
  }

  function refreshAfterLocaleChange() {
    const strip = el("daily-month-strip");
    if (strip && strip.dataset.built === "1") {
      strip.querySelectorAll(".daily-month-chip").forEach(function (btn) {
        const mi = Number(btn.dataset.month);
        if (mi >= 1 && mi <= 12) btn.textContent = I().monthShort(mi);
      });
    }
    const ml = el("daily-month-label");
    if (ml) ml.textContent = I().monthLong(dailyViewMonth);
    const panelD = el("home-panel-daily");
    if (panelD && !panelD.hidden && el("screen-home") && el("screen-home").classList.contains("active")) {
      buildDailyCalendar();
    }
    const gameScr = el("screen-game");
    if (gameScr && gameScr.classList.contains("active") && level) {
      if (gameMode === "daily" && dailyContext) {
        const dc = dailyContext;
        el("game-title").textContent = I().tr("game_title_daily", {
          d: pad2(dc.d),
          m: pad2(dc.m),
          sub: dc.sub + 1,
        });
      } else {
        el("game-title").textContent = I().tr("game_title_level", { n: levelIndex + 1 });
      }
    }
  }

  function wireUi() {
    el("btn-play").addEventListener("click", function () {
      startGame(0, { from: "home" });
    });
    el("btn-home-daily").addEventListener("click", function () {
      showHomeDaily();
    });
    el("btn-daily-back").addEventListener("click", function () {
      showHomeHub();
    });
    el("btn-home-settings").addEventListener("click", function () {
      openHomeMenu();
    });
    el("btn-home-menu-close").addEventListener("click", closeHomeMenu);
    el("home-menu-backdrop").addEventListener("click", closeHomeMenu);
    el("btn-menu-howto").addEventListener("click", function () {
      openHowtoDialog();
    });
    el("btn-howto-close").addEventListener("click", closeHowtoDialog);
    el("howto-backdrop").addEventListener("click", closeHowtoDialog);
    el("btn-menu-levels").addEventListener("click", function () {
      closeHomeMenu();
      buildLevelGrid();
      showScreen("screen-levels");
    });
    document.querySelectorAll(".lang-option--sheet").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const lc = btn.getAttribute("data-locale");
        if (lc) I().setLocale(lc);
      });
    });
    el("btn-levels-back").addEventListener("click", function () {
      showScreen("screen-home");
      showHomeHub();
    });
    el("btn-game-back").addEventListener("click", function () {
      if (gameMode === "daily" || gameBackTarget === "home-daily") {
        showScreen("screen-home");
        showHomeDaily();
      } else if (gameBackTarget === "home-game") {
        showScreen("screen-home");
        showHomeHub();
      } else {
        showScreen("screen-levels");
      }
    });
    el("btn-game-settings").addEventListener("click", function () {
      showScreen("screen-settings");
    });
    el("btn-settings-back").addEventListener("click", function () {
      showScreen("screen-game");
    });
    ["lang-en", "lang-ru", "lang-es"].forEach(function (id) {
      const btn = el(id);
      if (!btn) return;
      btn.addEventListener("click", function () {
        const lc = btn.getAttribute("data-locale");
        if (lc) I().setLocale(lc);
      });
    });
    const prevM = el("daily-prev-month");
    const nextM = el("daily-next-month");
    if (prevM) {
      prevM.addEventListener("click", function () {
        if (dailyViewMonth > 1) {
          dailyViewMonth -= 1;
          updateMonthStripActive();
          buildDailyCalendar();
        }
      });
    }
    if (nextM) {
      nextM.addEventListener("click", function () {
        if (dailyViewMonth < 12) {
          dailyViewMonth += 1;
          updateMonthStripActive();
          buildDailyCalendar();
        }
      });
    }
    el("btn-restart").addEventListener("click", restartLevel);
    el("btn-undo").addEventListener("click", undoMove);
    el("btn-hint").addEventListener("click", useHint);
    el("btn-next-level").addEventListener("click", function () {
      const act = el("btn-next-level").dataset.winAction || "next";
      if (act === "daily-home") dismissWinAndGo("daily-home");
      else if (act === "daily-next") dismissWinAndGo("daily-next");
      else if (act === "levels") dismissWinAndGo("levels");
      else dismissWinAndGo("next");
    });
    el("btn-win-replay").addEventListener("click", function () {
      dismissWinAndGo("replay");
    });
    el("btn-win-home").addEventListener("click", function () {
      dismissWinAndGo("home");
    });

    const board = el("board");
    board.addEventListener("pointerdown", onPointerDown);
    board.addEventListener("pointermove", onPointerMove);
    board.addEventListener("pointerup", onPointerUp);
    board.addEventListener("pointercancel", onPointerUp);

    window.addEventListener(
      "resize",
      function () {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(scheduleLayoutLines, 80);
      },
      { passive: true },
    );
  }

  function init() {
    loadLevels();
    if (!levels.length) {
      el("btn-play").disabled = true;
      const ml = el("btn-menu-levels");
      if (ml) ml.disabled = true;
      return;
    }
    const n0 = new Date();
    if (n0.getFullYear() === DAILY_YEAR) dailyViewMonth = n0.getMonth() + 1;
    else dailyViewMonth = 1;
    I().applyDom();
    window.addEventListener("colorDotsLocaleChange", refreshAfterLocaleChange);
    wireUi();
    updateHintBadge();
    buildMonthStripOnce();
    showHomeHub();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
