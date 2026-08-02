(function () {
  const smilesEl = document.getElementById("smiles");
  const statusEl = document.getElementById("run-status");
  const healthEl = document.getElementById("health-status");
  const outEmpty = document.getElementById("out-empty");
  const outBody = document.getElementById("out-body");
  const imgEl = document.getElementById("out-image");
  const fragBox = document.getElementById("frag-box");
  const metaEl = document.getElementById("out-meta");
  const jsonEl = document.getElementById("out-json");
  const examplesEl = document.getElementById("examples");
  const modelLabels = document.querySelectorAll(".model-picker label");

  function selectedModel() {
    const el = document.querySelector('input[name="model"]:checked');
    return el ? el.value : "gnn";
  }

  function setStatus(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.className = "status-pill" + (kind ? " " + kind : "");
  }

  function refreshModelUI() {
    const m = selectedModel();
    modelLabels.forEach((lab) => {
      const input = lab.querySelector("input");
      lab.classList.toggle("active", input && input.checked);
    });
    document.getElementById("run-btn").textContent =
      m === "gnn" ? "Segment with GNN (main)" : `Segment with ${m}`;
  }

  modelLabels.forEach((lab) => {
    lab.addEventListener("click", () => setTimeout(refreshModelUI, 0));
  });

  async function pollHealth() {
    try {
      const r = await fetch("/api/health");
      const h = await r.json();
      if (h.loading) {
        healthEl.textContent = "Loading models: " + h.status;
        healthEl.className = "status-pill";
        setTimeout(pollHealth, 1500);
        return;
      }
      if (h.error) {
        healthEl.textContent = "Load error: " + h.error;
        healthEl.className = "status-pill err";
        return;
      }
      const ready = Object.entries(h.ready || {})
        .filter(([, v]) => v)
        .map(([k]) => k)
        .join(", ");
      healthEl.textContent = "Ready: " + (ready || "none");
      healthEl.className = "status-pill ok";
    } catch (e) {
      healthEl.textContent =
        "API offline. Start with: python server.py (from Yashi/web)";
      healthEl.className = "status-pill err";
    }
  }

  async function loadExamples() {
    try {
      const r = await fetch("/api/examples");
      const data = await r.json();
      examplesEl.innerHTML = "";
      (data.examples || []).forEach((ex) => {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = `<strong>${ex.name}</strong><br><span style="color:#3d524b;font-size:0.8rem">${ex.note || ""}</span>`;
        b.addEventListener("click", () => {
          smilesEl.value = ex.smiles;
        });
        examplesEl.appendChild(b);
      });
    } catch (_) {
      examplesEl.innerHTML =
        "<p style='color:#3d524b;font-size:0.9rem'>Examples load when the server is running.</p>";
    }
  }

  function copyText(text, btn) {
    navigator.clipboard.writeText(text || "").then(() => {
      const old = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = old), 900);
    });
  }

  function renderResult(data) {
    outEmpty.hidden = true;
    outBody.hidden = false;
    imgEl.src = "data:image/png;base64," + data.image_png_base64;
    const s = data.substructures || {};
    const c = data.counts || {};
    metaEl.innerHTML = `
      <span class="chip gnn">model: ${data.model}</span>
      <span class="chip">atoms: ${data.n_atoms}</span>
      <span class="chip w">W ${c.warhead || 0}</span>
      <span class="chip l">L ${c.linker || 0}</span>
      <span class="chip e">E3 ${c.e3 || 0}</span>
      <span class="chip">${data.reassembly ? "reassembly OK" : "reassembly fail"} · ${data.n_fragments} frags</span>
    `;
    fragBox.innerHTML = `
      <div class="frag w">
        <header><strong>Warhead SMILES</strong><button class="copy-btn" type="button" data-copy="w">Copy</button></header>
        <code id="smiles-w">${s.warhead_smiles || "(none)"}</code>
      </div>
      <div class="frag l">
        <header><strong>Linker SMILES</strong><button class="copy-btn" type="button" data-copy="l">Copy</button></header>
        <code id="smiles-l">${s.linker_smiles || "(none)"}</code>
      </div>
      <div class="frag e">
        <header><strong>E3 ligand SMILES</strong><button class="copy-btn" type="button" data-copy="e">Copy</button></header>
        <code id="smiles-e">${s.e3_smiles || "(none)"}</code>
      </div>
    `;
    fragBox.querySelectorAll(".copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-copy");
        const map = { w: s.warhead_smiles, l: s.linker_smiles, e: s.e3_smiles };
        copyText(map[key] || "", btn);
      });
    });
    jsonEl.value = JSON.stringify(
      {
        model: data.model,
        canonical_smiles: data.canonical_smiles,
        substructures: data.substructures,
        counts: data.counts,
        reassembly: data.reassembly,
        labels: data.labels,
      },
      null,
      2
    );
  }

  document.getElementById("run-btn").addEventListener("click", async () => {
    const smiles = smilesEl.value.trim();
    if (!smiles) {
      setStatus("Paste a PROTAC SMILES first.", "err");
      return;
    }
    setStatus("Running " + selectedModel() + "...");
    try {
      const r = await fetch("/api/segment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ smiles, model: selectedModel() }),
      });
      const data = await r.json();
      if (!data.ok) {
        setStatus(data.error || "Segmentation failed", "err");
        outEmpty.hidden = false;
        outBody.hidden = true;
        outEmpty.textContent = data.error || "Failed";
        return;
      }
      setStatus("Done — substructures ready.", "ok");
      renderResult(data);
    } catch (e) {
      setStatus("Could not reach API. Start python server.py", "err");
    }
  });

  document.getElementById("copy-json")?.addEventListener("click", (e) => {
    copyText(jsonEl.value, e.currentTarget);
  });

  document.getElementById("download-json")?.addEventListener("click", () => {
    const blob = new Blob([jsonEl.value], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "protac_segmentation.json";
    a.click();
  });

  refreshModelUI();
  pollHealth();
  loadExamples();
})();
