/* Equity tab: hand vs hand (POST /api/poker/equity) or range vs range
   (POST /api/poker/range/equity). See markdowns/poker/poker_build_plan_v1.md
   Phase 13's Equity tab spec: exact-vs-sampled badge, runout count, and the
   equity DISTRIBUTION histogram as the headline chart (not just the mean).
*/
PokerApp.Equity = (function () {
    let mode = "hands";

    function setMode(m) {
        mode = m;
        document.getElementById("eq-mode-hands").classList.toggle("btn-alt", m === "hands");
        document.getElementById("eq-mode-ranges").classList.toggle("btn-alt", m === "ranges");
        document.getElementById("eq-a").placeholder = m === "hands" ? "AsAh" : "AA";
        document.getElementById("eq-b").placeholder = m === "hands" ? "KsKh" : "KK";
    }

    function renderHistogram(distribution) {
        const wrap = document.getElementById("eq-hist-wrap");
        const el = document.getElementById("eq-hist");
        if (!distribution) { wrap.style.display = "none"; return; }
        wrap.style.display = "";
        el.innerHTML = "";
        // distribution[0] is hero's {value: probability} dict, e.g. {"0.0":.17,"0.5":.005,"1.0":.82}
        const dist = distribution[0];
        const order = ["1.0", "0.5", "0.0"];
        const names = { "1.0": "Win", "0.5": "Tie", "0.0": "Lose" };
        const maxP = Math.max(...order.map((k) => dist[k] || 0), 0.001);
        for (const key of order) {
            const p = dist[key] || 0;
            const wrapEl = document.createElement("div");
            wrapEl.className = "bar-wrap";
            const bar = document.createElement("div");
            bar.className = "bar";
            bar.style.height = Math.max(2, (p / maxP) * 120) + "px";
            const val = document.createElement("div");
            val.className = "bar-val";
            val.textContent = PokerApp.fmtPct(p);
            const label = document.createElement("div");
            label.className = "bar-label";
            label.textContent = names[key];
            wrapEl.appendChild(bar); wrapEl.appendChild(val); wrapEl.appendChild(label);
            el.appendChild(wrapEl);
        }
    }

    function renderMetrics(data) {
        const el = document.getElementById("eq-metrics");
        el.innerHTML = "";
        const labels = mode === "hands" ? ["Hero", "Villain"] : ["Range A", "Range B"];
        const equities = mode === "hands" ? data.equities : [data.equity_a, data.equity_b];
        equities.forEach((eq, i) => {
            const card = document.createElement("div");
            card.className = "metric-card";
            card.innerHTML = `<div class="metric-title">${labels[i]}</div><div class="metric-value">${PokerApp.fmtPct(eq)}</div>`;
            el.appendChild(card);
        });
    }

    async function run() {
        const status = document.getElementById("eq-status");
        const badge = document.getElementById("eq-badge");
        status.textContent = "Computing..."; status.className = "status-line";
        badge.style.display = "none";
        try {
            const a = document.getElementById("eq-a").value.trim();
            const b = document.getElementById("eq-b").value.trim();
            const board = document.getElementById("eq-board").value.trim();
            if (!a || !b) throw new Error("both hero and villain are required");

            if (mode === "hands") {
                const data = await PokerApp.post("/api/poker/equity", { hands: [a, b], board });
                renderMetrics(data);
                renderHistogram(data.distribution || null);
                badge.style.display = "";
                badge.className = "badge " + (data.method === "exact" ? "exact" : "sampled");
                badge.textContent = data.method === "exact"
                    ? `exact / ${data.runouts.toLocaleString()} runouts`
                    : `sampled (±${PokerApp.fmtPct((data.standard_error || [0])[0], 2)})`;
                status.textContent = "Done."; status.className = "status-line ok";
            } else {
                const data = await PokerApp.post("/api/poker/range/equity", { range_a: a, range_b: b, board });
                renderMetrics(data);
                renderHistogram(null);
                badge.style.display = "";
                badge.className = "badge exact";
                badge.textContent = "joint combo-weighted";
                status.textContent = "Done."; status.className = "status-line ok";
            }
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
            PokerApp.toast(e.message, true);
        }
    }

    function init() {
        document.getElementById("eq-mode-hands").addEventListener("click", () => setMode("hands"));
        document.getElementById("eq-mode-ranges").addEventListener("click", () => setMode("ranges"));
        document.getElementById("eq-run").addEventListener("click", run);
        setMode("hands");
    }

    document.addEventListener("DOMContentLoaded", init);
    return { init, run };
})();
