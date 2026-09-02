(() => {
  const submissionLocks = new Map();
  let pointerReorder = null;
  let reorderHold = null;
  let reorderHoldTimer = null;
  let reorderHintTimer = null;
  let suppressEntityClickUntil = 0;
  const HOLD_TO_REORDER_MS = 500;

  function reorderPositionLabel(item) {
    const position = Number(item.dataset.reorderPosition);
    const direction = item.dataset.reorderLevel === "box" ? "bottom" : "left";
    return position === 0 ? `0 · ${direction}-most` : `${position} from ${direction}`;
  }

  function showReorderHint(item, target = null) {
    let hint = document.getElementById("reorder-position-hint");
    if (!hint) {
      hint = document.createElement("div");
      hint.id = "reorder-position-hint";
      hint.className = "reorder-position-hint";
      hint.setAttribute("role", "status");
      document.body.appendChild(hint);
    }
    hint.textContent = target ? `${reorderPositionLabel(item)} → ${reorderPositionLabel(target)}` : reorderPositionLabel(item);
    hint.hidden = false;
    window.clearTimeout(reorderHintTimer);
    reorderHintTimer = window.setTimeout(() => { hint.hidden = true; }, 1800);
  }

  function updateFullscreenButton() {
    document.querySelectorAll("[data-fullscreen-toggle]").forEach((button) => {
      const label = document.fullscreenElement ? "Exit fullscreen" : "Enter fullscreen";
      button.setAttribute("aria-label", label);
      button.title = label;
    });
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-fullscreen-toggle]");
    if (!button) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    } catch (error) {
      if (window.Shiny) Shiny.setInputValue("fullscreen_error", String(error), { priority: "event" });
    }
  });
  document.addEventListener("fullscreenchange", updateFullscreenButton);
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".submit-once");
    if (!button) return;
    const lockKey = button.id || button.name;
    const now = Date.now();
    if (button.dataset.submitting === "true" || now - (submissionLocks.get(lockKey) || 0) < 900) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    submissionLocks.set(lockKey, now);
    button.dataset.submitting = "true";
    // Let Shiny receive the first click before changing its interactive state.
    window.setTimeout(() => {
      if (button.dataset.submitting !== "true") return;
      button.classList.add("is-submitting");
      button.setAttribute("aria-disabled", "true");
      if (button.classList.contains("measurement-save")) button.textContent = "Saving…";
    }, 0);
    window.setTimeout(() => {
      if (submissionLocks.get(lockKey) === now) submissionLocks.delete(lockKey);
      if (!button.isConnected) return;
      delete button.dataset.submitting;
      button.classList.remove("is-submitting");
      button.removeAttribute("aria-disabled");
    }, 900);
  }, true);

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-submit]");
    if (!button || !window.Shiny) return;
    const controls = button.closest(".modal-body").querySelectorAll("input[id],select[id]");
    const fields = Object.fromEntries([...controls]
      .filter((control) => control.type !== "radio" || control.checked)
      .map((control) => [control.id, control.value]));
    Shiny.setInputValue("edit_save_payload", JSON.stringify({ fields, nonce: `${Date.now()}-${Math.random()}` }), { priority: "event" });
  });

  function setMeasurementValue(input, value) {
    const minimum = Number(input.min || 0);
    const maximum = Number(input.max || 100);
    input.value = Math.min(maximum, Math.max(minimum, Number(value) || 0));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.addEventListener("input", (event) => {
    const slider = event.target.closest(".measurement-slider");
    if (!slider) return;
    const input = document.getElementById(slider.dataset.measurementInput);
    if (input) setMeasurementValue(input, slider.value);
  });

  document.addEventListener("input", (event) => {
    const input = event.target.closest(".measurement-control input[type=number]");
    if (!input) return;
    const slider = document.getElementById(`${input.id}_slider`);
    if (slider) slider.value = input.value;
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-position-input]");
    if (!button) return;
    const input = document.getElementById(button.dataset.positionInput);
    if (input) setMeasurementValue(input, Number(input.value) + Number(button.dataset.positionDelta));
  });

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-chart-series]");
    const reset = event.target.closest("[data-chart-reset]");
    if (!toggle && !reset) return;
    const box = event.target.closest(".hive-box-report");
    if (!box) return;
    if (reset) {
      box.querySelectorAll("[data-chart-series]").forEach((button) => {
        button.setAttribute("aria-pressed", "true");
        button.classList.add("is-active");
      });
      box.querySelectorAll(".stacked-frame-track .stacked-segment").forEach((segment) => { segment.hidden = false; });
      return;
    }
    const active = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", String(active));
    toggle.classList.toggle("is-active", active);
    box.querySelectorAll(`.stacked-frame-track .segment-${toggle.dataset.chartSeries}`).forEach((segment) => { segment.hidden = !active; });
  });

  function clearPointerReorder() {
    window.clearTimeout(reorderHoldTimer);
    reorderHoldTimer = null;
    reorderHold = null;
    document.querySelectorAll(".is-dragging, .is-drop-target").forEach((item) => item.classList.remove("is-dragging", "is-drop-target"));
    pointerReorder = null;
  }

  document.addEventListener("pointerdown", (event) => {
    const item = event.target.closest("[data-reorder-level]");
    if (!item || event.button !== 0) return;
    reorderHold = { item, id: item.dataset.id, level: item.dataset.reorderLevel, parent: item.dataset.reorderParent, startX: event.clientX, startY: event.clientY };
    reorderHoldTimer = window.setTimeout(() => {
      if (!reorderHold) return;
      pointerReorder = { ...reorderHold, target: null };
      pointerReorder.item.setPointerCapture?.(event.pointerId);
      pointerReorder.item.classList.add("is-dragging");
      showReorderHint(pointerReorder.item);
      reorderHold = null;
      reorderHoldTimer = null;
    }, HOLD_TO_REORDER_MS);
  });

  document.addEventListener("pointermove", (event) => {
    if (reorderHold && Math.hypot(event.clientX - reorderHold.startX, event.clientY - reorderHold.startY) > 8) {
      clearPointerReorder();
      return;
    }
    if (!pointerReorder || Math.hypot(event.clientX - pointerReorder.startX, event.clientY - pointerReorder.startY) < 5) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-reorder-level]");
    document.querySelectorAll(".is-drop-target").forEach((item) => item.classList.remove("is-drop-target"));
    if (!target || target.dataset.id === pointerReorder.id || target.dataset.reorderLevel !== pointerReorder.level || target.dataset.reorderParent !== pointerReorder.parent) {
      pointerReorder.target = null;
      return;
    }
    pointerReorder.target = target;
    target.classList.add("is-drop-target");
    showReorderHint(pointerReorder.item, target);
  });

  document.addEventListener("pointerup", (event) => {
    if (!pointerReorder) {
      clearPointerReorder();
      return;
    }
    const { id, level, parent, target } = pointerReorder;
    suppressEntityClickUntil = Date.now() + 500;
    if (target && window.Shiny) Shiny.setInputValue("reorder_request", JSON.stringify({ id, level, parent, target: target.dataset.id }), { priority: "event" });
    clearPointerReorder();
    event.preventDefault();
  });
  document.addEventListener("pointercancel", clearPointerReorder);

  document.addEventListener("click", (event) => {
    const typeButton = event.target.closest("[data-search-type]");
    if (!typeButton) return;
    const active = typeButton.getAttribute("aria-pressed") !== "true";
    typeButton.setAttribute("aria-pressed", String(active));
    typeButton.classList.toggle("is-active", active);
    filterEntities(typeButton);
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-level][data-id]");
    if (!button || !window.Shiny) return;
    if (Date.now() < suppressEntityClickUntil && button.matches("[data-reorder-level]")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    Shiny.setInputValue("entity_selection", JSON.stringify({
      level: button.dataset.level,
      id: button.dataset.id,
      source: button.classList.contains("search-result") ? "search" : "hierarchy",
    }), { priority: "event" });
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-note-id]");
    if (!button || !window.Shiny) return;
    Shiny.setInputValue("note_action", button.dataset.noteId, { priority: "event" });
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-grid-column][data-grid-row]");
    if (!button || button.disabled || !window.Shiny) return;
    button.closest(".apiary-grid").querySelectorAll(".grid-editor-cell.is-selected").forEach((cell) => cell.classList.remove("is-selected"));
    button.classList.add("is-selected");
    Shiny.setInputValue("hive_grid_point", JSON.stringify({
      grid_column: Number(button.dataset.gridColumn),
      grid_row: Number(button.dataset.gridRow),
    }), { priority: "event" });
  });
  document.addEventListener("click", (event) => {
    const option = event.target.closest("[data-move-id]");
    if (!option || !window.Shiny) return;
    option.classList.toggle("is-selected");
    const selected = [...option.closest(".move-results").querySelectorAll(".move-option.is-selected")].map((item) => item.dataset.moveId);
    Shiny.setInputValue("move_selection", JSON.stringify(selected), { priority: "event" });
  });

  function filterEntities(input) {
    const modal = input.closest(".modal-body");
    const normalize = (value) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(/\s+/).filter(Boolean);
    const query = normalize(modal.querySelector("#entity-search-filter").value);
    const status = modal.querySelector("#search-status-filter").value;
    const types = new Set([...modal.querySelectorAll("[data-search-type][aria-pressed=true]")].map((button) => button.dataset.searchType));
    const results = [...modal.querySelectorAll(".search-result")];
    results.forEach((result) => {
      const matchesStatus = status === "all" || (status === "archived") === (result.dataset.entityArchived === "true");
      const matchesType = types.has(result.dataset.entityType);
      const terms = normalize(result.dataset.searchText);
      const matchesQuery = query.every((queryTerm) => terms.some((term) => term.startsWith(queryTerm) || queryTerm.startsWith(term)));
      result.hidden = !matchesQuery || !matchesStatus || !matchesType;
    });
    modal.querySelector(".search-empty").hidden = results.some((result) => !result.hidden);
  }

  function filterMove(input) {
    const query = input.value.trim().toLowerCase();
    input.closest(".modal-body").querySelectorAll(".move-option").forEach((option) => {
      option.hidden = !option.dataset.moveSearch.includes(query);
    });
  }

  function filterNotes(control) {
    const modal = control.closest(".modal-body");
    const query = modal.querySelector("#notes-table-filter")?.value.trim().toLowerCase() || "";
    const scope = modal.querySelector("#notes-scope-filter")?.value || "all";
    const rows = [...modal.querySelectorAll("[data-note-search]")];
    rows.forEach((row) => { row.hidden = !row.dataset.noteSearch.includes(query) || (scope === "current" && row.dataset.noteCurrent !== "true"); });
    const empty = modal.querySelector(".notes-empty");
    if (empty) empty.hidden = rows.some((row) => !row.hidden);
  }

  document.addEventListener("input", (event) => {
    if (event.target.id === "entity-search-filter") filterEntities(event.target);
    if (event.target.id === "move-search-filter") filterMove(event.target);
    if (event.target.id === "notes-table-filter") filterNotes(event.target);
  });
  document.addEventListener("change", (event) => {
    if (event.target.id === "notes-scope-filter") filterNotes(event.target);
    if (event.target.id === "search-status-filter") filterEntities(event.target);
  });
  document.addEventListener("shown.bs.modal", (event) => {
    const filter = event.target.querySelector("#notes-table-filter");
    if (filter) filterNotes(filter);
    const entityFilter = event.target.querySelector("#entity-search-filter");
    if (entityFilter) { filterEntities(entityFilter); entityFilter.focus(); }
    event.target.querySelector("#move-search-filter")?.focus();
  });
})();
