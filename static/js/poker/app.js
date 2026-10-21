/* Poker app shell: tab navigation, fetch helper, toasts, formatters. Every
   other js/poker/*.js file attaches to the shared `PokerApp` namespace
   rather than declaring its own globals -- mirrors static/js/app.js's own
   pattern on the blackjack side exactly. */
const PokerApp = {
    state: {
        spec: null,           // currently selected spec key, e.g. "hu-100bb-r5c3-s5"
        solvedSpecs: [],       // spec keys with a solved preflop strategy on disk
    },
};

PokerApp.api = async function (path, options = {}) {
    const opts = { headers: { "Content-Type": "application/json" }, ...options };
    const res = await fetch(path, opts);
    let body = null;
    try { body = await res.json(); } catch (e) { /* no JSON body */ }
    if (!res.ok) {
        const msg = (body && body.error) ? body.error : `${res.status} ${res.statusText}`;
        throw new Error(msg);
    }
    return body;
};

PokerApp.get = (path) => PokerApp.api(path, { method: "GET" });
PokerApp.post = (path, data) => PokerApp.api(path, { method: "POST", body: JSON.stringify(data) });

PokerApp.toast = function (message, isError = false) {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 5000);
};

PokerApp.fmtPct = (x, d = 1) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : (x * 100).toFixed(d) + "%";
PokerApp.fmtNum = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : Number(x).toFixed(d);

// The 13 ranks, high to low -- used by every 169-grid renderer (Ranges,
// Preflop, Push/Fold tabs) so there is exactly one definition of the grid's
// row/column order in the whole app.
PokerApp.RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];

PokerApp.handLabel = function (rowRank, colRank) {
    // Upper-right triangle (row < col index, i.e. row rank > col rank in our
    // high-to-low order) is suited; lower-left is offsuit; diagonal is a pair --
    // the standard 169-grid convention every published chart uses.
    const ri = PokerApp.RANKS.indexOf(rowRank), ci = PokerApp.RANKS.indexOf(colRank);
    if (ri === ci) return rowRank + colRank;
    if (ri < ci) return PokerApp.RANKS[Math.min(ri, ci)] + PokerApp.RANKS[Math.max(ri, ci)] + "s";
    return PokerApp.RANKS[Math.min(ri, ci)] + PokerApp.RANKS[Math.max(ri, ci)] + "o";
};

// n_combos for a 169-class label, from its own notation -- pairs have 6,
// suited 4, offsuit 12 -- derivable client-side with no server round trip.
PokerApp.classCombos = function (label) {
    if (label.length === 2) return 6;
    return label.endsWith("s") ? 4 : 12;
};

/* Builds an empty 13x13 .hand-grid inside `container`, calling
   `onCell(cellEl, label)` once per cell for the caller to populate/attach
   listeners to -- the one grid-construction routine every tab's JS reuses,
   so the row/column order is never redefined per-tab. */
PokerApp.buildHandGrid = function (container, onCell) {
    container.innerHTML = "";
    for (const rowRank of PokerApp.RANKS) {
        for (const colRank of PokerApp.RANKS) {
            const label = PokerApp.handLabel(rowRank, colRank);
            const cell = document.createElement("div");
            cell.className = "hand-cell" + (rowRank === colRank ? " pair" : "");
            cell.dataset.hand = label;
            const labelEl = document.createElement("span");
            labelEl.className = "label";
            labelEl.textContent = label;
            cell.appendChild(labelEl);
            container.appendChild(cell);
            onCell(cell, label);
        }
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const tabButtons = document.querySelectorAll(".tab-btn");
    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            tabButtons.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
            document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        });
    });

    PokerApp.init().catch((e) => PokerApp.toast("Failed to load /api/poker/spec: " + e.message, true));
});

PokerApp.init = async function () {
    const data = await PokerApp.get("/api/poker/spec");
    PokerApp.state.spec = data.default_key;
    PokerApp.state.solvedSpecs = data.solved_preflop_specs;

    for (const sel of [document.getElementById("pf-spec"), document.getElementById("trainer-spec")]) {
        if (!sel) continue;
        sel.innerHTML = "";
        for (const key of data.solved_preflop_specs) {
            const opt = document.createElement("option");
            opt.value = key; opt.textContent = key;
            sel.appendChild(opt);
        }
        if (data.solved_preflop_specs.includes(data.default_key)) sel.value = data.default_key;
    }

    PokerApp.Ranges.init();
    PokerApp.Preflop.init();
    PokerApp.PushFold.init();
    PokerApp.Trainer.init();
};
