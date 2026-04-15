(function () {
  "use strict";

  const STORAGE = "colorDotsLocaleV1";

  /** @type {Record<string, Record<string, string>>} */
  const S = {
    en: {
      meta_description: "Color Dots — connect matching dots, fill the grid, lines can't cross.",
      page_title: "Color Dots",
      home_subtitle: "Connect the colors. Fill the grid.",
      home_plaque_play_hint: "Levels & classic flow",
      home_plaque_daily_hint: "2026 · 3 puzzles per day",
      aria_main_tabs: "Main sections",
      tab_game: "Game",
      tab_daily: "Daily Challenge",
      tagline:
        "Connect, think, and glow. Match pairs of colored dots to fill the grid — lines can't cross. Every move lights up the board and your brain.",
      btn_play: "Play",
      btn_levels: "Levels",
      howto_title: "How to play",
      howto_li1: "Connect matching dots of the same color.",
      howto_li2: "When every pair is linked, the level clears — cover all squares for a perfect fill.",
      howto_li3: "Lines cannot overlap — plan your path carefully.",
      feat_1: "Hundreds of levels to master",
      feat_2: "Progressive difficulty",
      feat_3: "Hints when you're stuck",
      feat_4: "Smooth neon visuals",
      footer_strong: "Light up the grid",
      footer_span: "Relax at home or train logic on the go — endless satisfaction.",
      daily_title: "Daily",
      daily_lead: "2026 · 3 puzzles per day · tap a date",
      daily_year: "2026",
      daily_legend_ring: "ring = progress · ★ = all 3 done",
      wd0: "M",
      wd1: "T",
      wd2: "W",
      wd3: "T",
      wd4: "F",
      wd5: "S",
      wd6: "S",
      levels_title: "Levels",
      aria_back: "Back",
      aria_settings: "Settings",
      label_moves: "Moves",
      label_lines: "Lines",
      label_fill: "Fill",
      ctrl_restart: "Restart",
      ctrl_hint: "Hint",
      ctrl_undo: "Undo",
      settings_title: "Settings",
      home_menu_title: "Menu",
      dialog_close: "Close",
      settings_language: "Language",
      lang_en: "English",
      lang_ru: "Русский",
      lang_es: "Español",
      win_level_complete: "Level complete",
      win_puzzle_clear: "Puzzle clear",
      win_day_complete: "Day complete",
      win_replay: "Replay",
      win_home: "Home",
      win_next_level: "Next level",
      win_next_puzzle: "Next puzzle",
      win_calendar: "Calendar",
      win_choose_level: "Choose level",
      win_moves_campaign: "You completed the level in ___MOVES___ moves!",
      win_moves_partial: "You cleared puzzle {done} in ___MOVES___ moves!",
      win_moves_last: "You finished the last puzzle in ___MOVES___ moves!",
      win_meta_next: "Next: puzzle {next} of {total} · {stats}",
      win_opt_fill_optional: " · 100% fill optional.",
      win_meta_day: "{d}.{m} — all {total} cleared · {stats}",
      win_opt_replay_cal: " · Replay from the calendar anytime.",
      win_fill_hint: " · Cover all cells for 100% fill.",
      stats_line: "Moves {moves} · Lines {locked}/{total} · Fill {fp}%",
      game_title_level: "LEVEL {n}",
      game_title_daily: "Daily {d}.{m} · {sub}/3",
      aria_prev_month: "Previous month",
      aria_next_month: "Next month",
      aria_replay: "Replay level",
      daily_aria_done: "{month} {day}, complete",
      daily_aria_prog: "{month} {day}, {prog} of {total}",
      puzzle_grid: "Puzzle grid",
    },
    ru: {
      meta_description: "Color Dots — соединяй точки одного цвета, заполняй поле, линии не должны пересекаться.",
      page_title: "Color Dots",
      home_subtitle: "Соединяй цвета. Заполняй поле.",
      home_plaque_play_hint: "Уровни и классический режим",
      home_plaque_daily_hint: "2026 · 3 головоломки в день",
      aria_main_tabs: "Основные разделы",
      tab_game: "Игра",
      tab_daily: "Ежедневный вызов",
      tagline:
        "Соединяй пары цветных точек и заполняй сетку — линии не пересекаются. Каждый ход подсвечивает поле и заставляет думать.",
      btn_play: "Играть",
      btn_levels: "Уровни",
      howto_title: "Как играть",
      howto_li1: "Соединяй точки одного цвета.",
      howto_li2: "Когда все пары соединены, уровень пройден — закрась все клетки для идеального заполнения.",
      howto_li3: "Линии не должны накладываться друг на друга — планируй путь.",
      feat_1: "Сотни уровней",
      feat_2: "Растущая сложность",
      feat_3: "Подсказки, если застрял",
      feat_4: "Плавный неоновый визуал",
      footer_strong: "Зажги поле",
      footer_span: "Дома в спокойном темпе или тренировка логики в дороге.",
      daily_title: "Ежедневно",
      daily_lead: "2026 · 3 головоломки в день · нажми на дату",
      daily_year: "2026",
      daily_legend_ring: "кольцо = прогресс · ★ = все 3 пройдены",
      wd0: "Пн",
      wd1: "Вт",
      wd2: "Ср",
      wd3: "Чт",
      wd4: "Пт",
      wd5: "Сб",
      wd6: "Вс",
      levels_title: "Уровни",
      aria_back: "Назад",
      aria_settings: "Настройки",
      label_moves: "Ходы",
      label_lines: "Линии",
      label_fill: "Заполнение",
      ctrl_restart: "Заново",
      ctrl_hint: "Подсказка",
      ctrl_undo: "Отмена",
      settings_title: "Настройки",
      home_menu_title: "Меню",
      dialog_close: "Закрыть",
      settings_language: "Язык",
      lang_en: "English",
      lang_ru: "Русский",
      lang_es: "Español",
      win_level_complete: "Уровень пройден",
      win_puzzle_clear: "Головоломка пройдена",
      win_day_complete: "День завершён",
      win_replay: "Ещё раз",
      win_home: "Домой",
      win_next_level: "Следующий уровень",
      win_next_puzzle: "Следующая",
      win_calendar: "Календарь",
      win_choose_level: "К уровням",
      win_moves_campaign: "Уровень пройден за ___MOVES___ ходов!",
      win_moves_partial: "Головоломка {done} пройдена за ___MOVES___ ходов!",
      win_moves_last: "Последняя головоломка дня за ___MOVES___ ходов!",
      win_meta_next: "Далее: {next} из {total} · {stats}",
      win_opt_fill_optional: " · 100% заполнения не обязательно.",
      win_meta_day: "{d}.{m} — все {total} пройдены · {stats}",
      win_opt_replay_cal: " · Повтор в любое время из календаря.",
      win_fill_hint: " · Закрась все клетки для 100% заполнения.",
      stats_line: "Ходы {moves} · Линии {locked}/{total} · Заполнение {fp}%",
      game_title_level: "УРОВЕНЬ {n}",
      game_title_daily: "День {d}.{m} · {sub}/3",
      aria_prev_month: "Предыдущий месяц",
      aria_next_month: "Следующий месяц",
      aria_replay: "Переиграть уровень",
      daily_aria_done: "{month} {day}, всё пройдено",
      daily_aria_prog: "{month} {day}, {prog} из {total}",
      puzzle_grid: "Игровое поле",
    },
    es: {
      meta_description: "Color Dots — conecta puntos del mismo color, rellena la cuadrícula, las líneas no pueden cruzarse.",
      page_title: "Color Dots",
      home_subtitle: "Conecta colores. Rellena la cuadrícula.",
      home_plaque_play_hint: "Niveles y modo clásico",
      home_plaque_daily_hint: "2026 · 3 puzles al día",
      aria_main_tabs: "Secciones principales",
      tab_game: "Juego",
      tab_daily: "Reto diario",
      tagline:
        "Conecta parejas de puntos del mismo color y rellena la cuadrícula — las líneas no se cruzan. Cada movimiento ilumina el tablero y entrena la lógica.",
      btn_play: "Jugar",
      btn_levels: "Niveles",
      howto_title: "Cómo jugar",
      howto_li1: "Conecta puntos del mismo color.",
      howto_li2: "Cuando todas las parejas estén unidas, el nivel se completa — cubre todas las casillas para un relleno perfecto.",
      howto_li3: "Las líneas no pueden superponerse — planifica el camino.",
      feat_1: "Cientos de niveles",
      feat_2: "Dificultad progresiva",
      feat_3: "Pistas si te atascas",
      feat_4: "Estética neón fluida",
      footer_strong: "Ilumina la cuadrícula",
      footer_span: "Relájate en casa o entrena la lógica donde vayas.",
      daily_title: "Diario",
      daily_lead: "2026 · 3 puzles al día · toca una fecha",
      daily_year: "2026",
      daily_legend_ring: "anillo = progreso · ★ = los 3 hechos",
      wd0: "L",
      wd1: "M",
      wd2: "X",
      wd3: "J",
      wd4: "V",
      wd5: "S",
      wd6: "D",
      levels_title: "Niveles",
      aria_back: "Atrás",
      aria_settings: "Ajustes",
      label_moves: "Mov.",
      label_lines: "Líneas",
      label_fill: "Relleno",
      ctrl_restart: "Reiniciar",
      ctrl_hint: "Pista",
      ctrl_undo: "Deshacer",
      settings_title: "Ajustes",
      home_menu_title: "Menú",
      dialog_close: "Cerrar",
      settings_language: "Idioma",
      lang_en: "English",
      lang_ru: "Русский",
      lang_es: "Español",
      win_level_complete: "Nivel completado",
      win_puzzle_clear: "Puzle hecho",
      win_day_complete: "Día completado",
      win_replay: "Repetir",
      win_home: "Inicio",
      win_next_level: "Siguiente nivel",
      win_next_puzzle: "Siguiente puzle",
      win_calendar: "Calendario",
      win_choose_level: "Elegir nivel",
      win_moves_campaign: "¡Completaste el nivel en ___MOVES___ movimientos!",
      win_moves_partial: "¡Completaste el puzle {done} en ___MOVES___ movimientos!",
      win_moves_last: "¡Último puzle del día en ___MOVES___ movimientos!",
      win_meta_next: "Siguiente: puzle {next} de {total} · {stats}",
      win_opt_fill_optional: " · Rellenar al 100% es opcional.",
      win_meta_day: "{d}.{m} — los {total} hechos · {stats}",
      win_opt_replay_cal: " · Repite cuando quieras desde el calendario.",
      win_fill_hint: " · Cubre todas las casillas para 100% de relleno.",
      stats_line: "Mov. {moves} · Líneas {locked}/{total} · Relleno {fp}%",
      game_title_level: "NIVEL {n}",
      game_title_daily: "Día {d}.{m} · {sub}/3",
      aria_prev_month: "Mes anterior",
      aria_next_month: "Mes siguiente",
      aria_replay: "Repetir nivel",
      daily_aria_done: "{month} {day}, completado",
      daily_aria_prog: "{month} {day}, {prog} de {total}",
      puzzle_grid: "Cuadrícula del puzle",
    },
  };

  const MONTHS_SHORT = {
    en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    ru: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    es: ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
  };

  const MONTHS_LONG = {
    en: [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ],
    ru: [
      "Январь",
      "Февраль",
      "Март",
      "Апрель",
      "Май",
      "Июнь",
      "Июль",
      "Август",
      "Сентябрь",
      "Октябрь",
      "Ноябрь",
      "Декабрь",
    ],
    es: [
      "enero",
      "febrero",
      "marzo",
      "abril",
      "mayo",
      "junio",
      "julio",
      "agosto",
      "septiembre",
      "octubre",
      "noviembre",
      "diciembre",
    ],
  };

  let loc = "en";

  function detectInitial() {
    try {
      const s = localStorage.getItem(STORAGE);
      if (s === "en" || s === "ru" || s === "es") return s;
    } catch (_) {}
    const n = (navigator.language || "en").slice(0, 2).toLowerCase();
    if (n === "ru") return "ru";
    if (n === "es") return "es";
    return "en";
  }

  function tr(key, vars) {
    let str = (S[loc] && S[loc][key]) || S.en[key] || key;
    if (vars) {
      for (const k in vars) {
        str = str.split("{" + k + "}").join(String(vars[k]));
      }
    }
    return str;
  }

  function applyDom() {
    document.querySelectorAll("[data-i18n]").forEach(function (node) {
      const k = node.getAttribute("data-i18n");
      if (!k) return;
      node.textContent = tr(k);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (node) {
      const k = node.getAttribute("data-i18n-aria");
      if (!k) return;
      node.setAttribute("aria-label", tr(k));
    });
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", tr("meta_description"));
    const title = document.querySelector("title");
    if (title) title.textContent = tr("page_title");

    document.querySelectorAll(".lang-option").forEach(function (btn) {
      const l = btn.getAttribute("data-locale");
      const on = l === loc;
      btn.classList.toggle("lang-option--active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function monthShort(monthIndex1to12) {
    const arr = MONTHS_SHORT[loc] || MONTHS_SHORT.en;
    return arr[monthIndex1to12 - 1] || "";
  }

  function monthLong(monthIndex1to12) {
    const arr = MONTHS_LONG[loc] || MONTHS_LONG.en;
    return arr[monthIndex1to12 - 1] || "";
  }

  function setLocale(code) {
    if (code !== "en" && code !== "ru" && code !== "es") return;
    loc = code;
    try {
      localStorage.setItem(STORAGE, code);
    } catch (_) {}
    document.documentElement.lang = code === "en" ? "en" : code === "ru" ? "ru" : "es";
    applyDom();
    window.dispatchEvent(new CustomEvent("colorDotsLocaleChange", { detail: { locale: code } }));
  }

  function getLocale() {
    return loc;
  }

  loc = detectInitial();
  document.documentElement.lang = loc === "en" ? "en" : loc === "ru" ? "ru" : "es";

  function formatWinMovesHtml(key, movesNum, vars) {
    const b = '<b class="win-moves-num" id="win-moves-num">' + movesNum + "</b>";
    let s = tr(key, vars || {});
    return s.split("___MOVES___").join(b);
  }

  window.COLOR_DOTS_I18N = {
    getLocale: getLocale,
    setLocale: setLocale,
    tr: tr,
    applyDom: applyDom,
    monthShort: monthShort,
    monthLong: monthLong,
    formatWinMovesHtml: formatWinMovesHtml,
  };
})();
