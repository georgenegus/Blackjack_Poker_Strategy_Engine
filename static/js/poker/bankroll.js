/* Bankroll tab: POST /api/poker/bankroll. Per the plan's own [!IMPORTANT]
   in Phase 11, the confidence interval around the user's OBSERVED win rate
   is the single most useful number this tab shows -- rendered as its own
   prominent banner, not just another metric card, and deliberately
   compared against the observed rate itself so its width is visible.
*/
PokerApp.Bankroll = (function () {
    function renderDownswing(quantiles) {
        const el = document.getElementById("br-downswing");
        el.innerHTML = "";
        const entries = Object.entries(quantiles).filter(([, v]) => v !== null);
        const maxV = Math.max(...entries.map(([, v]) => v), 1);
        for (const [key, depth] of entries) {
            const wrap = document.createElement("div");
            wrap.className = "bar-wrap";
            const bar = document.createElement("div");
            bar.className = "bar";
            bar.style.height = Math.max(2, (depth / maxV) * 120) + "px";
            const val = document.createElement("div");
            val.className = "bar-val";
            val.textContent = depth.toFixed(0) + " bb";
            const label = document.createElement("div");
            label.className = "bar-label";
            label.textContent = key.replace("p", "") + "% chance";
            wrap.appendChild(bar); wrap.appendChild(val); wrap.appendChild(label);
            el.appendChild(wrap);
        }
    }

    async function run() {
        const status = document.getElementById("br-status");
        status.textContent = "Computing..."; status.className = "status-line";
        try {
            const payload = {
                wr: parseFloat(document.getElementById("br-wr").value),
                sd: parseFloat(document.getElementById("br-sd").value),
                bankroll: parseFloat(document.getElementById("br-bankroll").value),
                n_hands: parseFloat(document.getElementById("br-hands").value),
                observed_wr: parseFloat(document.getElementById("br-observed").value),
                total_bankroll: parseFloat(document.getElementById("br-total").value),
                target_ror: parseFloat(document.getElementById("br-target").value),
            };
            const data = await PokerApp.post("/api/poker/bankroll", payload);

            const metrics = document.getElementById("br-metrics");
            metrics.innerHTML = "";
            const cards = [["Risk of Ruin", PokerApp.fmtPct(data.risk_of_ruin)]];
            if (data.stake_advice) {
                cards.push(["Max Buy-in", "$" + data.stake_advice.max_buyin.toFixed(0)]);
                cards.push(["Required Bankroll", data.stake_advice.required_bankroll_bb.toFixed(0) + " bb"]);
            }
            for (const [title, val] of cards) {
                const card = document.createElement("div");
                card.className = "metric-card";
                card.innerHTML = `<div class="metric-title">${title}</div><div class="metric-value">${val}</div>`;
                metrics.appendChild(card);
            }

            const banner = document.getElementById("br-ci-banner");
            if (data.confidence_interval) {
                banner.style.display = "";
                const lo = data.confidence_interval.low.toFixed(2), hi = data.confidence_interval.high.toFixed(2);
                banner.innerHTML = `<b>95% confidence interval on your observed win rate:</b> ${lo} to ${hi} bb/100 `
                    + `over ${Number(payload.n_hands).toLocaleString()} hands. A sample this size does not distinguish `
                    + `a winning player from a losing one if the interval crosses zero.`;
            } else {
                banner.style.display = "none";
            }

            renderDownswing(data.downswing_quantiles);
            status.textContent = "Done."; status.className = "status-line ok";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
        }
    }

    function init() {
        document.getElementById("br-run").addEventListener("click", run);
        run();
    }

    document.addEventListener("DOMContentLoaded", init);
    return { init, run };
})();
