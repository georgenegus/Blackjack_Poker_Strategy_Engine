/* Preflop tab: renders the solved strategy (GET /api/poker/preflop) as a
   169-grid. Scoped to the OPEN situation only (position BTN or BB, no
   facing-a-raise navigation) -- a deliberate, documented simplification:
   full action-history navigation (breadcrumbs through 3-bet/4-bet lines)
   is real additional UI work this phase's effort budget doesn't stretch
   to, and "open" is the single most commonly consulted chart anyway.

   Mixed cells render as SPLIT cells with their real per-action frequencies
   -- never collapsed to the most-frequent action alone, per Phase 13's own
   [!NOTE] (the single most important UI decision in this plan). The
   "simplified" toggle rounds to the pure (most-frequent) action for
   memorisation, but does NOT claim an EV cost for doing so: advisor.py's
   Advice/advise() only ever returns action FREQUENCIES, never per-action
   EV (see src/poker/advisor.py's Advice dataclass) -- so the simplified
   view's warning banner says exactly that, rather than fabricating a
   number the backend has never computed.
*/
PokerApp.Preflop = (function () {
    let strategyData = null;

    const ACTION_CLASS = (action) => {
        if (action === "fold") return "seg-fold";
        if (action === "check") return "seg-check";
        if (action === "call") return "seg-call";
        return "seg-raise"; // bet_*/raise_*/allin_*
    };

    function renderLegend() {
        const el = document.getElementById("pf-legend");
        el.innerHTML = "";
        const items = [["seg-fold", "Fold"], ["seg-check", "Check/Limp"], ["seg-call", "Call"], ["seg-raise", "Bet/Raise"]];
        for (const [cls, name] of items) {
            const chip = document.createElement("span");
            chip.className = "legend-chip";
            chip.innerHTML = `<span class="legend-swatch ${cls}"></span>${name}`;
            el.appendChild(chip);
        }
    }

    function renderCell(cell, label) {
        cell.querySelectorAll(".split").forEach((n) => n.remove());
        const freqs = strategyData ? strategyData[label] : null;
        if (!freqs) { cell.title = ""; return; }

        const simplified = document.getElementById("pf-simplify").value === "simplified";
        const split = document.createElement("div");
        split.className = "split";

        if (simplified) {
            const best = Object.entries(freqs).sort((a, b) => b[1] - a[1])[0];
            const seg = document.createElement("div");
            seg.className = "seg " + ACTION_CLASS(best[0]);
            seg.style.width = "100%";
            split.appendChild(seg);
        } else {
            for (const [action, freq] of Object.entries(freqs)) {
                const seg = document.createElement("div");
                seg.className = "seg " + ACTION_CLASS(action);
                seg.style.width = (freq * 100).toFixed(2) + "%";
                split.appendChild(seg);
            }
        }
        cell.insertBefore(split, cell.firstChild);
        cell.title = Object.entries(freqs).map(([a, f]) => `${a}: ${(f * 100).toFixed(1)}%`).join("\n");
    }

    function renderAll() {
        document.querySelectorAll("#pf-grid .hand-cell").forEach((cell) => renderCell(cell, cell.dataset.hand));
    }

    async function load() {
        const spec = document.getElementById("pf-spec").value;
        const position = document.getElementById("pf-position").value;
        const status = document.getElementById("pf-status");
        const warning = document.getElementById("pf-warning");
        status.textContent = "Loading..."; status.className = "status-line";
        try {
            const data = await PokerApp.get(`/api/poker/preflop?spec=${encodeURIComponent(spec)}`);
            strategyData = data.strategy[`${position}:open`] || {};
            const nHands = Object.keys(strategyData).length;
            warning.textContent = `Abstraction exploitability: ${PokerApp.fmtNum(data.abstraction_exploitability_mbb, 1)} `
                + `± ${PokerApp.fmtNum(data.abstraction_exploitability_se_mbb, 1)} mbb/g over ${data.iterations.toLocaleString()} iterations `
                + `-- this is an equilibrium of an ABSTRACTED game, not real play (see the banner above). `
                + `Simplified view rounds to the most-frequent action; per-action EV isn't available from this solver's output, `
                + `so no EV cost is shown for doing so.`;
            renderAll();
            status.textContent = `${nHands} hands loaded.`; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
            PokerApp.toast(e.message, true);
        }
    }

    function buildGrid() {
        const container = document.getElementById("pf-grid");
        PokerApp.buildHandGrid(container, () => {});
    }

    function init() {
        renderLegend();
        buildGrid();
        document.getElementById("pf-spec").addEventListener("change", load);
        document.getElementById("pf-position").addEventListener("change", load);
        document.getElementById("pf-simplify").addEventListener("change", renderAll);
        if (PokerApp.state.solvedSpecs.length) load();
    }

    return { init, load, getStrategyData: () => strategyData };
})();
