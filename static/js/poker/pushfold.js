/* Push/Fold & ICM tab. Jam/call ranges via GET /api/poker/pushfold?stack=,
   rendered on two 169-grids (fill opacity = weight, matching the Ranges
   tab's own visual language for "this hand is in the range at this
   frequency" -- weighted cells render as partially-filled, never on/off).
   ICM calculator via POST /api/poker/icm.
*/
PokerApp.PushFold = (function () {
    function fillGrid(containerId, weights) {
        document.querySelectorAll(`#${containerId} .hand-cell`).forEach((cell) => {
            const label = cell.dataset.hand;
            const w = weights[label];
            const existing = cell.querySelector(".fill");
            if (existing) existing.remove();
            if (!w) return;
            const fill = document.createElement("div");
            fill.className = "fill";
            fill.style.opacity = String(0.3 + 0.7 * w);
            cell.insertBefore(fill, cell.firstChild);
            cell.title = `${label}: ${(w * 100).toFixed(1)}%`;
        });
    }

    async function loadPushfold() {
        const stack = parseFloat(document.getElementById("pfold-stack").value);
        document.getElementById("pfold-stack-val").textContent = stack.toFixed(1) + " bb";
        const status = document.getElementById("pfold-status");
        status.textContent = "Solving..."; status.className = "status-line";
        try {
            const data = await PokerApp.get(`/api/poker/pushfold?stack=${stack}`);
            document.getElementById("pfold-jam-pct").textContent = data.jam_pct.toFixed(1) + "%";
            document.getElementById("pfold-call-pct").textContent = data.call_pct.toFixed(1) + "%";
            fillGrid("pfold-jam-grid", data.jam);
            fillGrid("pfold-call-grid", data.call);
            status.textContent = `${data.iterations} fictitious-play iterations.`; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
        }
    }

    function renderPerChipBar(equities, stacks) {
        const el = document.getElementById("icm-per-chip");
        el.innerHTML = "";
        const totalChips = stacks.reduce((a, b) => a + b, 0);
        const totalEquity = equities.reduce((a, b) => a + b, 0);
        const ratios = equities.map((e, i) => (e / totalEquity) / (stacks[i] / totalChips));
        const maxR = Math.max(...ratios, 0.001);
        ratios.forEach((r, i) => {
            const wrap = document.createElement("div");
            wrap.className = "bar-wrap";
            const bar = document.createElement("div");
            bar.className = "bar";
            bar.style.height = Math.max(2, (r / maxR) * 120) + "px";
            if (r < 1.0) bar.style.background = "var(--danger-grad)";
            const val = document.createElement("div");
            val.className = "bar-val";
            val.textContent = r.toFixed(2) + "x";
            const label = document.createElement("div");
            label.className = "bar-label";
            label.textContent = "P" + i;
            wrap.appendChild(bar); wrap.appendChild(val); wrap.appendChild(label);
            el.appendChild(wrap);
        });
    }

    async function runIcm() {
        const status = document.getElementById("icm-status");
        try {
            const stacks = document.getElementById("icm-stacks").value.split(",").map((s) => parseFloat(s.trim()));
            const payouts = document.getElementById("icm-payouts").value.split(",").map((s) => parseFloat(s.trim()));
            const player = parseInt(document.getElementById("icm-player").value, 10);
            const opponent = parseInt(document.getElementById("icm-opponent").value, 10);
            const riskAmount = parseFloat(document.getElementById("icm-risk").value);

            const data = await PokerApp.post("/api/poker/icm", {
                stacks, payouts, player, opponent, risk_amount: riskAmount,
            });

            const el = document.getElementById("icm-equities");
            el.innerHTML = "";
            data.equities.forEach((eq, i) => {
                const card = document.createElement("div");
                card.className = "metric-card";
                card.innerHTML = `<div class="metric-title">Player ${i}</div><div class="metric-value">${eq.toFixed(2)}</div>`;
                el.appendChild(card);
            });
            if (data.bubble_factor !== undefined) {
                const card = document.createElement("div");
                card.className = "metric-card";
                card.innerHTML = `<div class="metric-title">Bubble Factor</div><div class="metric-value">${data.bubble_factor.toFixed(2)}</div>`;
                el.appendChild(card);
            }
            renderPerChipBar(data.equities, stacks);
            status.textContent = "Done."; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
        }
    }

    function init() {
        PokerApp.buildHandGrid(document.getElementById("pfold-jam-grid"), () => {});
        PokerApp.buildHandGrid(document.getElementById("pfold-call-grid"), () => {});
        document.getElementById("pfold-stack").addEventListener("input", loadPushfold);
        document.getElementById("icm-run").addEventListener("click", runIcm);
        loadPushfold();
        runIcm();
    }

    return { init };
})();
