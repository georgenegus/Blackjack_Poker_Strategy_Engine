/* Shared ruleset / counting-system selector bar -- every tab reads
   App.state.ruleset / App.state.system rather than keeping its own copy. */
App.Rules = {};

App.Rules.label = function (r) {
    const parts = [
        `${r.num_decks}D`,
        r.dealer_hits_soft_17 ? "H17" : "S17",
        r.double_after_split ? "DAS" : "no-DAS",
        r.surrender === "none" ? "no surrender" : "late surrender",
    ];
    return parts.join(" · ");
};

App.Rules.populateSelectors = function (data) {
    const rulesetSel = document.getElementById("sel-ruleset");
    rulesetSel.innerHTML = "";
    // Group by deck count for a less overwhelming 32-option list.
    const sorted = [...data.rulesets].sort((a, b) => a.num_decks - b.num_decks || a.key.localeCompare(b.key));
    for (const r of sorted) {
        const opt = document.createElement("option");
        opt.value = r.key;
        opt.textContent = App.Rules.label(r);
        if (r.key === data.defaults.ruleset) opt.selected = true;
        rulesetSel.appendChild(opt);
    }

    const fillSystemSelect = (sel, defaultSlug) => {
        sel.innerHTML = "";
        for (const s of data.systems) {
            const opt = document.createElement("option");
            opt.value = s.slug;
            opt.textContent = `${s.name} (level ${s.level}${s.balanced ? "" : ", unbalanced"})`;
            if (s.slug === defaultSlug) opt.selected = true;
            sel.appendChild(opt);
        }
    };
    fillSystemSelect(document.getElementById("sel-system"), data.defaults.system);
    const bettingSel = document.getElementById("sel-betting-system");
    if (bettingSel) fillSystemSelect(bettingSel, data.defaults.system);

    rulesetSel.addEventListener("change", () => {
        App.state.ruleset = rulesetSel.value;
        App.Rules.updateSummary();
        App.notifyRulesChange();
    });
    document.getElementById("sel-system").addEventListener("change", (e) => {
        App.state.system = e.target.value;
        App.notifyRulesChange();
    });

    App.Rules.updateSummary();
};

App.Rules.currentRuleset = function () {
    return App.state.rulesets.find((r) => r.key === App.state.ruleset);
};

App.Rules.updateSummary = function () {
    const r = App.Rules.currentRuleset();
    const el = document.getElementById("rules-summary");
    if (r) el.textContent = `${r.penetration * 100}% penetration`;
};
