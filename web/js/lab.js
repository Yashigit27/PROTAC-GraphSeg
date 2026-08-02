(function () {
  const demos = window.YASHI.demos;
  const list = document.getElementById("demo-list");
  const smiles = document.getElementById("smiles-box");
  const note = document.getElementById("demo-note");
  const viz = document.getElementById("protac-viz");
  const board = document.getElementById("pred-board");
  const modelTabs = document.querySelectorAll("[data-model-tab]");
  let active = demos[0];
  let focusModel = "gnn";

  if (!list) return;

  function paint() {
    list.querySelectorAll("button").forEach((b) => {
      b.classList.toggle("active", b.dataset.id === active.id);
    });
    smiles.value = active.smiles;
    note.textContent = active.note;
    const { w, l, e } = active.parts;
    const total = w + l + e;
    viz.innerHTML = `
      <div class="seg-w" style="flex:${w / total}">Warhead</div>
      <div class="seg-l" style="flex:${l / total}">Linker</div>
      <div class="seg-e" style="flex:${e / total}">E3</div>
    `;

    const order = [
      ["dictionary", "Dictionary"],
      ["xgboost", "XGBoost"],
      ["gnn", "GNN (main)"],
    ];
    board.innerHTML = order
      .map(([key, label]) => {
        const p = active.preds[key];
        const hi = key === focusModel ? "gnn-pred" : "";
        const status = p.ok
          ? `<span class="ok">OK · ${pct(p.atom_acc)}</span>`
          : `<span class="fail">FAIL · ${pct(p.atom_acc)}</span>`;
        return `
          <div class="pred-row ${key === "gnn" || hi ? "gnn-pred" : ""}" data-key="${key}">
            <strong>${label}</strong>
            <span>${p.note}</span>
            ${status}
          </div>
        `;
      })
      .join("");

    // emphasize selected tab row
    board.querySelectorAll(".pred-row").forEach((row) => {
      if (row.dataset.key === focusModel) row.style.outline = "2px solid #0b6e4f";
      else row.style.outline = "none";
    });
  }

  demos.forEach((d) => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.id = d.id;
    b.innerHTML = `<strong>${d.name}</strong><br><span style="color:#3d524b;font-size:0.85rem">${d.note}</span>`;
    b.addEventListener("click", () => {
      active = d;
      paint();
    });
    list.appendChild(b);
  });

  modelTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      focusModel = tab.dataset.modelTab;
      modelTabs.forEach((t) => t.classList.toggle("active", t === tab));
      paint();
    });
  });

  document.getElementById("run-demo")?.addEventListener("click", () => {
    paint();
    const el = document.getElementById("run-status");
    if (el) {
      el.textContent =
        "Demo prediction loaded from curated cases. Live RDKit/GNN API can be plugged into this workbench later.";
    }
  });

  paint();
})();
