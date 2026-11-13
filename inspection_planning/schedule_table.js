// Each row keeps both drafts, but only the selected schedule provides an input.
export default function scheduleTable({ parentElement, data, setStateValue }) {
    const container = parentElement.querySelector(".schedule-table");
    const { prior, horizon, defaultInterval } = data;
    const identity = prior ? "Cracked joint" : "Plan name";
    const manual = prior ? "Manual excavation years" : "Manual inspection years";
    const interval = "Interval (years)";
    const kind = "Schedule type";

    // Keep the live fields and keyboard focus through Streamlit reruns.
    // Python supplies the latest saved rows on mount (including when reopening a draft).
    if (container.instance !== data.instance) {
        container.instance = data.instance;
        container.model = data.rows.map(row => ({ ...row }));
        container.config = null;
    }
    const rows = container.model;
    const types = prior ? ["Fixed interval", "Manual years", "No excavation"] : ["Fixed interval", "Manual years"];
    const publish = () => setStateValue("rows", rows.map(row => ({ ...row })));

    function element(tag, text) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function select(label, options, selected) {
        const node = element("select");
        node.setAttribute("aria-label", label);
        for (const [value, text] of options) node.add(new Option(text, value));
        node.value = selected;
        return node;
    }

    function showValue(td, row, rowLabel) {
        td.replaceChildren();
        if (row[kind] === "No excavation") {
            const dash = element("span", "—");
            dash.setAttribute("aria-label", "No excavation scheduled");
            td.append(dash);
            return;
        }
        const fixed = row[kind] === "Fixed interval";
        const field = fixed ? interval : manual;
        const label = element("label");
        label.append(element("span", field));
        const input = element("input");
        input.type = fixed ? "number" : "text";
        input.setAttribute("aria-label", field + " for " + rowLabel);
        if (fixed) {
            input.min = "1";
            input.max = String(horizon);
            input.step = "1";
        } else {
            input.placeholder = "e.g. 2, 10, 15";
        }
        input.value = row[field] ?? "";
        input.oninput = () => {
            row[field] = fixed ? (Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : null) : input.value;
        };
        input.onchange = publish;
        input.onkeydown = event => { if (event.key === "Enter") input.blur(); };
        label.append(input);
        td.append(label);
    }

    function uniqueName(base, firstNumber) {
        const used = new Set(rows.map(row => String(row[identity] ?? "").trim().toLowerCase()));
        if (firstNumber === 2 && !used.has(base.toLowerCase())) return base;
        let number = firstNumber;
        while (used.has((base + " " + number).toLowerCase())) number += 1;
        return base + " " + number;
    }

    function draw() {
        const grid = element("table");
        grid.setAttribute("aria-label", prior ? "Prior excavation schedules" : "ILI schedules");
        const header = grid.createTHead().insertRow();
        for (const title of (prior ? [identity, kind, "Schedule"] : ["Actions", identity, kind, "Schedule"])) {
            const th = element("th", title);
            th.scope = "col";
            header.append(th);
        }
        const body = grid.createTBody();
        rows.forEach((row, index) => {
            const tr = body.insertRow();
            const rowLabel = prior ? row[identity] : "ILI row " + (index + 1);
            if (!prior) {
                const actions = select("Actions for " + rowLabel, [["", "⋯"], ["Duplicate", "Duplicate"], ["Delete", "Delete"]], "");
                actions.className = "actions";
                actions.onchange = () => {
                    if (actions.value === "Duplicate") {
                        const base = String(row[identity] || "ILI plan").trim() + " copy";
                        rows.splice(index + 1, 0, { ...row, [identity]: uniqueName(base, 2) });
                    } else if (actions.value === "Delete") {
                        rows.splice(index, 1);
                    } else {
                        return;
                    }
                    draw();
                    publish();
                };
                tr.insertCell().append(actions);
            }
            const idCell = tr.insertCell();
            if (prior) {
                idCell.textContent = row[identity];
            } else {
                const name = element("input");
                name.setAttribute("aria-label", "Plan name for " + rowLabel);
                name.value = row[identity] ?? "";
                name.oninput = () => { row[identity] = name.value; };
                name.onchange = publish;
                name.onkeydown = event => { if (event.key === "Enter") name.blur(); };
                idCell.append(name);
            }
            const modeCell = tr.insertCell();
            const valueCell = tr.insertCell();
            const mode = select("Schedule type for " + rowLabel, types.map(type => [type, type]), row[kind]);
            mode.onchange = () => {
                row[kind] = mode.value;
                showValue(valueCell, row, rowLabel);
                publish();
            };
            modeCell.append(mode);
            showValue(valueCell, row, rowLabel);
        });
        const scroll = element("div");
        scroll.className = "scroll";
        scroll.append(grid);
        container.replaceChildren(scroll);
        if (!prior) {
            const add = element("button", "Add ILI plan");
            add.type = "button";
            add.onclick = () => {
                rows.push({ [identity]: uniqueName("Pre-posterior plan", 1), [kind]: "Fixed interval",
                            [interval]: defaultInterval, [manual]: "" });
                draw();
                publish();
                container.querySelector("tbody tr:last-child td:nth-child(2) input")?.focus();
            };
            container.append(add);
        }
    }
    const config = JSON.stringify([prior, horizon, defaultInterval]);
    if (container.config !== config) {
        draw();
        container.config = config;
    }
}
