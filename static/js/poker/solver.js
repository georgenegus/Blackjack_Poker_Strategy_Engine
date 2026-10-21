/* Solver tab: configures a bounded river spot and runs it through
   POST /api/poker/solve at several increasing iteration counts, plotting
   each run's exploitability as a curve. This is a real trend across
   several independent bounded solves, NOT one continuously-updating solve
   -- src/poker/api.py's /solve route is synchronous and one-shot, so
   there is no server-side streaming of intermediate iterations to poll.
   Documented here rather than left implicit, since a naive reading of
   "watch the exploitability curve fall in real time" (the plan's own
   phrasing) could otherwise be mistaken for a live/incremental solve.
*/
PokerApp.Solver = (function () {
    const ITERATION_STEPS = [500, 1000, 2500, 5000, 10000, 20000];

    function renderCurve(points) {
        const el = document.getElementById("solve-curve");
        el.innerHTML = "";
        if (!points.length) return;
        const maxV = Math.max(...points.map((p) => p.mbb), 0.001);
        const positions = points.map((p, i) => ({
            x: points.length > 1 ? (i / (points.length - 1)) * 92 + 4 : 50,
            y: (p.mbb / maxV) * 85 + 5,
        }));
        positions.forEach((pos, i) => {
            const dot = document.createElement("div");
            dot.className = "point";
            dot.style.left = pos.x + "%";
            dot.style.bottom = pos.y + "%";
            dot.title = `${points[i].iterations.toLocaleString()} iters: ${points[i].mbb.toFixed(1)} mbb/g`;
            el.appendChild(dot);
            if (i > 0) {
                const prev = positions[i - 1];
                const dx = pos.x - prev.x, dy = pos.y - prev.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                const angle = Math.atan2(-dy, dx) * (180 / Math.PI);
                const seg = document.createElement("div");
                seg.className = "seg";
                seg.style.left = prev.x + "%";
                seg.style.bottom = prev.y + "%";
                seg.style.width = len + "%";
                seg.style.transform = `rotate(${angle}deg)`;
                el.appendChild(seg);
            }
        });
        const axisLabel = document.createElement("div");
        axisLabel.className = "axis-label";
        axisLabel.style.left = "4px"; axisLabel.style.top = "4px";
        axisLabel.textContent = `0 – ${maxV.toFixed(0)} mbb/g`;
        el.appendChild(axisLabel);
    }

    function renderStrategyTables(strategy) {
        const el = document.getElementById("solve-strategy-tables");
        el.innerHTML = "";
        const situations = Object.keys(strategy);
        if (!situations.length) { el.textContent = "No infosets reached (try more iterations)."; return; }
        for (const situation of situations.slice(0, 6)) { // cap rendered tables -- avoid an enormous DOM on a wide range
            const wrap = document.createElement("div");
            wrap.className = "strategy-table-wrap";
            const table = document.createElement("table");
            table.className = "strategy-table";
            const caption = document.createElement("caption");
            caption.textContent = situation;
            table.appendChild(caption);
            const hands = Object.entries(strategy[situation]).slice(0, 15); // cap rows too
            for (const [combo, freqs] of hands) {
                const row = document.createElement("tr");
                const th = document.createElement("th");
                th.className = "rowhead"; th.textContent = combo;
                row.appendChild(th);
                const td = document.createElement("td");
                td.textContent = Object.entries(freqs).map(([a, f]) => `${a}:${(f * 100).toFixed(0)}%`).join(" ");
                row.appendChild(td);
                table.appendChild(row);
            }
            wrap.appendChild(table);
            el.appendChild(wrap);
        }
    }

    async function run() {
        const status = document.getElementById("solve-status");
        const runBtn = document.getElementById("solve-run");
        runBtn.disabled = true;
        status.textContent = "Running bounded solves..."; status.className = "status-line";
        const points = [];
        renderCurve(points);
        try {
            const board = document.getElementById("solve-board").value.trim();
            const heroRange = document.getElementById("solve-hero").value.trim();
            const villainRange = document.getElementById("solve-villain").value.trim();
            const pot = parseFloat(document.getElementById("solve-pot").value);
            const stack = parseFloat(document.getElementById("solve-stack").value);

            let lastResult = null;
            for (const iterations of ITERATION_STEPS) {
                status.textContent = `Solving at ${iterations.toLocaleString()} iterations...`;
                const data = await PokerApp.post("/api/poker/solve", {
                    board, hero_range: heroRange, villain_range: villainRange, pot, stack,
                    iterations, max_seconds: 8,
                });
                lastResult = data;
                points.push({ iterations: data.iterations, mbb: data.abstraction_exploitability_mbb });
                renderCurve(points);
            }

            const metrics = document.getElementById("solve-metrics");
            metrics.innerHTML = "";
            const cards = [
                ["Game Value (bb)", PokerApp.fmtNum(lastResult.game_value_bb, 3)],
                ["Std Error", "±" + PokerApp.fmtNum(lastResult.game_value_se_bb, 3)],
                ["Exploitability", PokerApp.fmtNum(lastResult.abstraction_exploitability_mbb, 1) + " mbb/g"],
                ["Iterations", lastResult.iterations.toLocaleString()],
            ];
            for (const [title, val] of cards) {
                const card = document.createElement("div");
                card.className = "metric-card";
                card.innerHTML = `<div class="metric-title">${title}</div><div class="metric-value">${val}</div>`;
                metrics.appendChild(card);
            }
            renderStrategyTables(lastResult.strategy);
            status.textContent = "Done."; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
            PokerApp.toast(e.message, true);
        } finally {
            runBtn.disabled = false;
        }
    }

    function init() {
        document.getElementById("solve-run").addEventListener("click", run);
    }

    document.addEventListener("DOMContentLoaded", init);
    return { init, run };
})();
