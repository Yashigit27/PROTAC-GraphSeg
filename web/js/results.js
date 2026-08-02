(function () {
  const { splits, dictionary, xgboost, gnn_scratch, gnn_pretrained, splitExplain } = window.YASHI;
  const splitSel = document.getElementById("split-select");
  const metricSel = document.getElementById("metric-select");
  const bars = document.getElementById("bar-chart");
  const tableBody = document.querySelector("#results-table tbody");
  const insight = document.getElementById("insight");

  if (!splitSel) return;

  splits.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    splitSel.appendChild(opt);
  });

  function val(model, split, metric) {
    const m = window.YASHI[model][split];
    if (!m) return 0;
    if (metric === "atom_acc") return m.atom_acc || 0;
    if (metric === "exact_3") return m.exact_3 || 0;
    if (metric === "reassembly") return m.reassembly || 0;
    if (metric === "coverage") return m.coverage || 0;
    return 0;
  }

  function render() {
    const split = splitSel.value;
    const metric = metricSel.value;
    const rows = [
      { key: "dictionary", label: "Dictionary", color: "#d65a45" },
      { key: "xgboost", label: "XGBoost", color: "#3d7ea6" },
      { key: "gnn_scratch", label: "GNN scratch (main)", color: "#0b6e4f", gnn: true },
      { key: "gnn_pretrained", label: "GNN pretrained (main)", color: "#1f8a7a", gnn: true },
    ];

    const max = 1;
    bars.innerHTML = "";
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 640 240");
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");

    rows.forEach((r, i) => {
      const v = val(r.key, split, metric);
      const y = 28 + i * 50;
      const w = Math.max(4, 480 * (v / max));
      const bg = document.createElementNS(svgNS, "rect");
      bg.setAttribute("x", "140");
      bg.setAttribute("y", String(y));
      bg.setAttribute("width", "480");
      bg.setAttribute("height", "28");
      bg.setAttribute("rx", "8");
      bg.setAttribute("fill", "#e7f0eb");
      svg.appendChild(bg);

      const bar = document.createElementNS(svgNS, "rect");
      bar.setAttribute("x", "140");
      bar.setAttribute("y", String(y));
      bar.setAttribute("width", String(w));
      bar.setAttribute("height", "28");
      bar.setAttribute("rx", "8");
      bar.setAttribute("fill", r.color);
      svg.appendChild(bar);

      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", "8");
      label.setAttribute("y", String(y + 19));
      label.setAttribute("fill", "#14241f");
      label.setAttribute("font-size", "13");
      label.setAttribute("font-family", "Sora, sans-serif");
      label.textContent = r.label;
      svg.appendChild(label);

      const num = document.createElementNS(svgNS, "text");
      num.setAttribute("x", String(150 + w));
      num.setAttribute("y", String(y + 19));
      num.setAttribute("fill", "#14241f");
      num.setAttribute("font-size", "13");
      num.setAttribute("font-family", "Sora, sans-serif");
      num.textContent = " " + (v * 100).toFixed(1) + "%";
      svg.appendChild(num);
    });
    bars.appendChild(svg);

    tableBody.innerHTML = "";
    rows.forEach((r) => {
      const m = window.YASHI[r.key][split];
      const tr = document.createElement("tr");
      if (r.gnn) tr.className = "gnn-row";
      tr.innerHTML = `
        <td>${r.label}</td>
        <td class="metric">${m.coverage != null ? pct(m.coverage) : "—"}</td>
        <td class="metric">${pct(m.atom_acc)}</td>
        <td class="metric">${pct(m.exact_3)}</td>
        <td class="metric">${pct(m.reassembly)}</td>
      `;
      tableBody.appendChild(tr);
    });

    const d = dictionary[split].atom_acc;
    const x = xgboost[split].atom_acc;
    const g = gnn_scratch[split].atom_acc;
    let text = splitExplain[split] + " ";
    if (split.startsWith("unseen")) {
      text += `Closed-book dictionary drops hard (${pct(d)} atom acc), while GNN scratch stays high (${pct(g)}), beating XGBoost (${pct(x)}).`;
    } else if (split === "random") {
      text += `Dictionary leads when recipes are available (${pct(d)}). GNN remains strong (${pct(g)}) without needing lookup at inference.`;
    } else {
      text += `Compare generalization: dictionary ${pct(d)}, XGBoost ${pct(x)}, GNN scratch ${pct(g)}.`;
    }
    insight.textContent = text;
  }

  splitSel.addEventListener("change", render);
  metricSel.addEventListener("change", render);
  render();
})();
