/* Bankroll tab: calls /api/stake for the entered true count, then re-calls it
   across a TC range client-side to draw the bet ramp -- there's no dedicated
   ramp endpoint, so this is that same Kelly math sampled at several points. */
App.Bankroll = {};

App.Bankroll.readInputs = function () {
    return {
        bankroll: Number(document.getElementById("br-bankroll").value),
        table_min: Number(document.getElementById("br-min").value),
        table_max: Number(document.getElementById("br-max").value),
        chip: Number(document.getElementById("br-chip").value),
        fraction: Number(document.getElementById("br-fraction").value),
        tc: Number(document.getElementById("br-tc").value),
    };
};

App.Bankroll.stakeAt = function (tc, inputs) {
    return App.post("/api/stake", {
        rules: App.state.ruleset,
        system: App.state.system,
        true_count: tc,
        bankroll: inputs.bankroll,
        kelly_fraction: inputs.fraction,
        table_limits: { min: inputs.table_min, max: inputs.table_max, chip: inputs.chip },
    });
};

App.Bankroll.calculate = async function () {
    const status = document.getElementById("bankroll-status");
    status.textContent = "Calculating...";
    status.className = "status-line";
    const inputs = this.readInputs();
    try {
        const data = await this.stakeAt(inputs.tc, inputs);
        document.getElementById("br-bet").textContent = App.fmtMoney(data.bet);
        const edgeEl = document.getElementById("br-edge");
        edgeEl.textContent = App.fmtPct(data.edge);
        edgeEl.className = "metric-value " + (data.edge >= 0 ? "pos" : "neg");
        document.getElementById("br-ror").textContent = App.fmtPct(data.risk_of_ruin);
        document.getElementById("br-nzero").textContent = Number.isFinite(data.n_zero) ? Math.round(data.n_zero).toLocaleString() : "∞";
        status.textContent = data.is_extrapolating ? "Note: this true count is beyond the fitted range -- treat with caution." : "";
        status.className = "status-line" + (data.is_extrapolating ? " error" : "");
        await this.renderRamp(inputs);
    } catch (e) {
        status.textContent = e.message;
        status.className = "status-line error";
        document.getElementById("ramp-status").textContent = "";
        document.getElementById("ramp-chart").innerHTML = "";
    }
};

App.Bankroll.renderRamp = async function (inputs) {
    const chart = document.getElementById("ramp-chart");
    const rampStatus = document.getElementById("ramp-status");
    chart.innerHTML = "";
    rampStatus.textContent = "Loading ramp...";
    const tcRange = [-6, -4, -2, -1, 0, 1, 2, 3, 4, 5, 6, 8, 10];
    try {
        const results = await Promise.all(tcRange.map((tc) => this.stakeAt(tc, inputs)));
        const maxBet = Math.max(...results.map((r) => r.bet), 1);
        results.forEach((r, i) => {
            const tc = tcRange[i];
            const isCurrent = tc === inputs.tc;
            const wrap = document.createElement("div");
            wrap.className = "ramp-bar-wrap";
            const heightPct = Math.max(2, (r.bet / maxBet) * 100);
            wrap.innerHTML = `
                <span class="ramp-val">${App.fmtMoney(r.bet)}</span>
                <div class="ramp-bar${isCurrent ? " current" : ""}" style="height:${heightPct}%"></div>
                <span class="ramp-tc">${tc >= 0 ? "+" : ""}${tc}</span>`;
            chart.appendChild(wrap);
        });
        rampStatus.textContent = "";
    } catch (e) {
        rampStatus.textContent = e.message;
        rampStatus.className = "status-line error";
    }
};

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-stake").addEventListener("click", () => App.Bankroll.calculate());
    const fraction = document.getElementById("br-fraction");
    fraction.addEventListener("input", () => {
        document.getElementById("br-fraction-val").textContent = Number(fraction.value).toFixed(2);
    });
});
