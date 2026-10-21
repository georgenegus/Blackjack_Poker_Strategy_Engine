/* Ranges tab: the 169-grid editor. Click-drag to select/deselect a block,
   right-click a selected cell to set its weight (a lightweight prompt()
   dialog stands in for a slider popup here -- same practical effect, a
   0-1 weight per combo, without building custom popup-positioning
   machinery this phase's effort budget doesn't stretch to). The notation
   box is synced both ways via /api/poker/range/parse (server-side, so the
   grid never re-implements the notation parser's own combo-expansion
   rules -- src.poker.ranges.Range stays the single source of truth for
   what a token like "A5s+" expands to).
*/
PokerApp.Ranges = (function () {
    let weights = {}; // label -> weight, greater than 0 and at most 1
    let dragging = false;
    let dragSelecting = true; // whether the current drag is selecting or deselecting

    function cellFill(cell, label) {
        const fillEl = cell.querySelector(".fill");
        const w = weights[label];
        if (!w) {
            if (fillEl) fillEl.remove();
            cell.classList.remove("selected");
            return;
        }
        cell.classList.add("selected");
        let f = fillEl;
        if (!f) {
            f = document.createElement("div");
            f.className = "fill";
            cell.insertBefore(f, cell.firstChild);
        }
        f.style.opacity = String(0.35 + 0.65 * w);
    }

    function toggleCell(label, forceState) {
        const nowSet = weights[label] !== undefined;
        const shouldSet = forceState !== undefined ? forceState : !nowSet;
        if (shouldSet) weights[label] = weights[label] || 1.0;
        else delete weights[label];
        const cell = document.querySelector(`#range-grid .hand-cell[data-hand="${label}"]`);
        if (cell) cellFill(cell, label);
    }

    function toNotation() {
        const parts = Object.entries(weights).map(([label, w]) =>
            w >= 1.0 ? label : `${label}:${w.toFixed(2)}`
        );
        return parts.join(",");
    }

    async function refreshMetrics() {
        const notation = toNotation();
        document.getElementById("range-notation").value = notation;
        if (!notation) {
            document.getElementById("range-combos").textContent = "0";
            document.getElementById("range-pct").textContent = "0%";
            return;
        }
        try {
            const data = await PokerApp.post("/api/poker/range/parse", { notation });
            document.getElementById("range-combos").textContent = data.n_combos;
            document.getElementById("range-pct").textContent = data.percent_of_hands.toFixed(2) + "%";
        } catch (e) {
            document.getElementById("range-status").textContent = e.message;
            document.getElementById("range-status").className = "status-line error";
        }
    }

    async function applyNotation() {
        const notation = document.getElementById("range-notation").value.trim();
        const status = document.getElementById("range-status");
        try {
            const data = notation ? await PokerApp.post("/api/poker/range/parse", { notation }) : { combos: {} };
            // data.combos is keyed by concrete combo (e.g. "AsAh"), not by
            // 169-class label -- collapse back to a per-label weight by
            // re-deriving each combo's class from its two ranks and whether
            // its suits match, taking the max weight seen per label (a
            // notation token always applies the SAME weight to every combo
            // it covers, so max == the token's weight).
            const byLabel = {};
            for (const [comboStr, w] of Object.entries(data.combos)) {
                const r1 = comboStr[0], s1 = comboStr[1], r2 = comboStr[2], s2 = comboStr[3];
                let label;
                if (r1 === r2) label = r1 + r2;
                else {
                    const suited = s1 === s2;
                    const ri = PokerApp.RANKS.indexOf(r1), rj = PokerApp.RANKS.indexOf(r2);
                    const hi = PokerApp.RANKS[Math.min(ri, rj)], lo = PokerApp.RANKS[Math.max(ri, rj)];
                    label = hi + lo + (suited ? "s" : "o");
                }
                byLabel[label] = Math.max(byLabel[label] || 0, w);
            }
            weights = byLabel;
            document.querySelectorAll("#range-grid .hand-cell").forEach((cell) => cellFill(cell, cell.dataset.hand));
            await refreshMetrics();
            status.textContent = "Applied."; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
        }
    }

    function clearAll() {
        weights = {};
        document.querySelectorAll("#range-grid .hand-cell").forEach((cell) => cellFill(cell, cell.dataset.hand));
        refreshMetrics();
    }

    function buildGrid() {
        const container = document.getElementById("range-grid");
        PokerApp.buildHandGrid(container, (cell, label) => {
            cell.addEventListener("mousedown", (ev) => {
                ev.preventDefault();
                dragging = true;
                dragSelecting = weights[label] === undefined;
                toggleCell(label, dragSelecting);
                refreshMetrics();
            });
            cell.addEventListener("mouseenter", () => {
                if (dragging) { toggleCell(label, dragSelecting); refreshMetrics(); }
            });
            cell.addEventListener("contextmenu", (ev) => {
                ev.preventDefault();
                if (weights[label] === undefined) return;
                const input = prompt(`Weight for ${label} (0-1):`, String(weights[label]));
                if (input === null) return;
                const w = Math.max(0, Math.min(1, parseFloat(input)));
                if (Number.isNaN(w)) return;
                if (w === 0) delete weights[label]; else weights[label] = w;
                cellFill(cell, label);
                refreshMetrics();
            });
        });
        document.addEventListener("mouseup", () => { dragging = false; });
    }

    function init() {
        buildGrid();
        document.getElementById("range-apply").addEventListener("click", applyNotation);
        document.getElementById("range-clear").addEventListener("click", clearAll);
    }

    return { init };
})();
