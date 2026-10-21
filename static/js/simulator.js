/* Simulator tab: a bounded Monte Carlo battery via /api/simulate, plus the
   edge-vs-true-count curve read off the locked edge model via repeated
   /api/stake calls (edge itself doesn't depend on stake's bankroll/kelly
   inputs -- only ruleset/system/true_count -- so any fixed values work). */
App.Simulator = {};

App.Simulator.run = async function () {
    const status = document.getElementById("sim-status");
    status.textContent = "Running battery -- this can take a while for large hand counts...";
    status.className = "status-line";
    const hands = Number(document.getElementById("sim-hands").value);
    const otherPlayers = Number(document.getElementById("sim-other").value);
    const useDeviations = document.getElementById("sim-deviations").checked;
    try {
        const data = await App.post("/api/simulate", {
            rules: App.state.ruleset,
            system: App.state.system,
            n_hands: hands,
            other_players: otherPlayers,
            use_deviations: useDeviations,
        });
        document.getElementById("sim-mean").textContent = App.fmtPct(data.mean);
        document.getElementById("sim-se").textContent = "±" + App.fmtPct(data.stderr);
        document.getElementById("sim-var").textContent = App.fmtNum(data.variance, 3);
        document.getElementById("sim-doubled").textContent = data.n_doubled.toLocaleString();
        document.getElementById("sim-splits").textContent = data.n_split_rounds.toLocaleString();
        document.getElementById("sim-seconds").textContent = data.seconds.toFixed(1) + "s";
        status.textContent = `${data.n_hands.toLocaleString()} hands simulated.`;
        status.className = "status-line ok";
    } catch (e) {
        status.textContent = e.message;
        status.className = "status-line error";
    }
};

App.Simulator.loadEdgeCurve = async function () {
    const chart = document.getElementById("edge-chart");
    const status = document.getElementById("edge-status");
    chart.innerHTML = "";
    status.textContent = "Loading...";
    status.className = "status-line";
    const tcRange = [-6, -4, -2, -1, 0, 1, 2, 3, 4, 5, 6, 8, 10];
    try {
        const results = await Promise.all(tcRange.map((tc) => App.post("/api/stake", {
            rules: App.state.ruleset, system: App.state.system, true_count: tc,
            bankroll: 10000, kelly_fraction: 0.5,
        })));
        const maxAbs = Math.max(0.01, ...results.map((r) => Math.abs(r.edge)));
        results.forEach((r, i) => {
            const tc = tcRange[i];
            const wrap = document.createElement("div");
            wrap.className = "ramp-bar-wrap";
            const heightPct = Math.max(2, (Math.abs(r.edge) / maxAbs) * 100);
            wrap.innerHTML = `
                <span class="ramp-val">${App.fmtPct(r.edge)}</span>
                <div class="ramp-bar${r.is_extrapolating ? "" : " current"}" style="height:${heightPct}%"></div>
                <span class="ramp-tc">${tc >= 0 ? "+" : ""}${tc}</span>`;
            chart.appendChild(wrap);
        });
        status.textContent = "Highlighted bars are within the edge model's fitted TC range.";
    } catch (e) {
        chart.innerHTML = "";
        status.textContent = e.message;
        status.className = "status-line error";
    }
};

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-simulate").addEventListener("click", () => App.Simulator.run());
    App.onRulesChange(() => App.Simulator.loadEdgeCurve());
});
