/* Trainer tab: deals a random hand at the BTN open decision (the same
   single, well-defined situation the Preflop tab itself is scoped to --
   see preflop.js's own docstring for why full action-history navigation is
   out of scope for this phase), the user picks an action, and the score is
   FREQUENCY-LOSS in percentage points (best action's frequency minus the
   chosen action's frequency) -- NOT bb EV, which advisor.py's solver
   output has never computed or persisted (see preflop.js's docstring on
   the same gap). This is a real, honestly-scoped implementation of the
   plan's own core idea ("scoring against frequencies rather than a single
   right answer... picking the 30% action is not an error") even though it
   isn't literally bb-denominated.
*/
PokerApp.Trainer = (function () {
    let currentStrategy = null; // {hand: {action: freq}} for BTN:open, cached per spec
    let currentSpec = null;
    let currentHand = null;
    let history = []; // [{hand, chosen, loss}]

    // A fixed, deterministic suit assignment per 169-class label, purely for
    // visual card display -- the solved strategy itself is suit-agnostic
    // (that's the whole point of the 169-class abstraction), so any legal
    // representative combo is equally correct to show.
    function comboForLabel(label) {
        const r1 = label[0], r2 = label[1], suited = label[2] === "s";
        if (r1 === r2) return [r1 + "s", r2 + "h"];
        return suited ? [r1 + "s", r2 + "s"] : [r1 + "s", r2 + "d"];
    }

    function renderCard(rankSuit) {
        const rank = rankSuit[0], suit = rankSuit[1];
        const red = suit === "h" || suit === "d";
        const suitChar = { s: "♠", h: "♥", d: "♦", c: "♣" }[suit];
        const el = document.createElement("div");
        el.className = "playing-card" + (red ? " red" : "");
        el.innerHTML = `<span class="pc-top">${rank}${suitChar}</span><span class="pc-bottom">${rank}${suitChar}</span>`;
        return el;
    }

    async function ensureStrategy() {
        const spec = document.getElementById("trainer-spec").value;
        if (currentSpec === spec && currentStrategy) return;
        const data = await PokerApp.get(`/api/poker/preflop?spec=${encodeURIComponent(spec)}`);
        currentStrategy = data.strategy["BTN:open"] || {};
        currentSpec = spec;
    }

    function dealHand() {
        const labels = Object.keys(currentStrategy);
        const weights = labels.map(PokerApp.classCombos);
        const total = weights.reduce((a, b) => a + b, 0);
        let r = Math.random() * total;
        for (let i = 0; i < labels.length; i++) {
            r -= weights[i];
            if (r <= 0) return labels[i];
        }
        return labels[labels.length - 1];
    }

    function renderActions(hand) {
        const el = document.getElementById("trainer-actions");
        el.innerHTML = "";
        const freqs = currentStrategy[hand];
        const actions = Object.keys(freqs);
        for (const action of actions) {
            const btn = document.createElement("button");
            btn.className = "glow-btn btn-ghost";
            btn.textContent = action;
            btn.addEventListener("click", () => choose(hand, action));
            el.appendChild(btn);
        }
    }

    function choose(hand, action) {
        const freqs = currentStrategy[hand];
        const best = Math.max(...Object.values(freqs));
        const chosen = freqs[action] || 0;
        const loss = (best - chosen) * 100;
        history.push({ hand, chosen: action, loss });

        const status = document.getElementById("trainer-status");
        status.textContent = `${hand} -> ${action}: solved frequency ${(chosen * 100).toFixed(1)}% `
            + `(best was ${(best * 100).toFixed(1)}%), frequency-loss ${loss.toFixed(1)}pp.`;
        status.className = "status-line " + (loss < 5 ? "ok" : "error");

        document.getElementById("trainer-n").textContent = history.length;
        const avgLoss = history.reduce((a, h) => a + h.loss, 0) / history.length;
        document.getElementById("trainer-avg-loss").textContent = avgLoss.toFixed(1) + "pp";

        const dot = document.createElement("div");
        dot.className = "trainer-chip " + (loss < 5 ? "good" : "bad");
        dot.title = `${hand} -> ${action} (${loss.toFixed(1)}pp)`;
        document.getElementById("trainer-history").appendChild(dot);

        document.getElementById("trainer-actions").innerHTML = "";
    }

    async function deal() {
        const status = document.getElementById("trainer-status");
        try {
            await ensureStrategy();
            currentHand = dealHand();
            const [c1, c2] = comboForLabel(currentHand);
            const cardsRow = document.getElementById("trainer-cards");
            cardsRow.innerHTML = "";
            cardsRow.appendChild(renderCard(c1));
            cardsRow.appendChild(renderCard(c2));
            document.getElementById("trainer-situation").textContent = `BTN open -- ${currentHand}`;
            renderActions(currentHand);
            status.textContent = "Pick an action."; status.className = "status-line";
        } catch (e) {
            status.textContent = e.message; status.className = "status-line error";
        }
    }

    function init() {
        document.getElementById("trainer-deal").addEventListener("click", deal);
    }

    return { init };
})();
