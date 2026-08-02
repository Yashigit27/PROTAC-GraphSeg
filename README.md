# Yashi — PROTAC substructure segmentation (notebooks only)

Research-oriented pipeline: **one major step = one Jupyter notebook**.  
All code lives **inside the notebook cells** (no `src/`, no library package).

## Notebooks (run in order)

| # | Notebook | What it does |
|---|---|---|
| 01 | `notebooks/01_data_and_labels.ipynb` | Load PROTAC-DB → weak labels + reassembly filter → 5 splits → graph tensors |
| 02 | `notebooks/02_baselines.ipynb` | Dictionary + XGBoost baselines on all splits |
| 03 | `notebooks/03_train_gnn.ipynb` | AttrMask pretrain → fine-tune scratch & pretrained GNN (soft reconstruction loss) |
| 04 | `notebooks/04_evaluation.ipynb` | Full metrics table + bar charts |
| 05 | `notebooks/05_inference_demo.ipynb` | Paint W/L/E3 on example molecules |

Each notebook is self-contained: helper functions are defined in early cells, then step-by-step experiment cells follow. Open in Jupyter and run **top → bottom** (or Restart & Run All).

## Environment (do this once)

Dedicated conda env + Jupyter kernel: **`yashi-protac`** / display name **Python (yashi-protac)**.

```bash
# already created on this machine; recreate elsewhere with:
conda env create -f environment.yml
conda activate yashi-protac
python -m ipykernel install --user --name yashi-protac --display-name "Python (yashi-protac)"
```

```bash
# activate every time you work on this project
conda activate yashi-protac
```

In Cursor / VS Code / Jupyter: open a notebook → pick kernel **Python (yashi-protac)**.

## How to run

```bash
cd Yashi
conda activate yashi-protac

# interactive
jupyter lab notebooks/

# or all notebooks in order (uses yashi-protac kernel)
python run_all.py
```

Cached intermediates go to `data/processed/`. Results go to `outputs/`.

## Method (short)

1. Weak labels from dictionary matching (warhead + E3 libraries).  
2. Keep a label only if cutting boundary bonds **reassembles** into 3 valid fragments.  
3. Train a small GIN with atom + bond + smoothness + **soft reconstruction** losses.  
4. Compare scratch vs AttrMask-pretrained encoders.  
5. Evaluate on random, unseen-warhead, unseen-E3, fingerprint-OOD, newer-chemotype splits.

## Results — Notebook 02 baselines (fair evaluation)

Source: `outputs/baselines_metrics.json` (from `notebooks/02_baselines.ipynb`).

Fairness settings used:
- **Dictionary:** train-only recipe book per split (closed book on unseen chemotypes)
- **XGBoost:** train-only Morgan SVD; atom accuracy allows W↔E3 swap; bond metric is `bond_pr_auc`

### Method A — Dictionary (train-only book)

| Split | Coverage | Atom acc | Exact-3 | Reassembly |
|-------|----------|----------|---------|------------|
| random | 0.984 | 0.955 | 0.981 | 0.981 |
| unseen_warhead | 0.062 | 0.057 | 0.000 | 0.000 |
| unseen_e3 | 0.329 | 0.309 | 0.000 | 0.000 |
| fingerprint_ood | 0.932 | 0.891 | 0.930 | 0.930 |
| newer_chemotype | 0.485 | 0.470 | 0.464 | 0.464 |

### Method B — XGBoost bond-cut (Ayush-style)

| Split | Atom acc | Exact-3 | Reassembly | Bond PR-AUC |
|-------|----------|---------|------------|-------------|
| random | 0.840 | 0.853 | 0.853 | 0.750 |
| unseen_warhead | 0.828 | 0.913 | 0.913 | 0.255 |
| unseen_e3 | 0.839 | 0.933 | 0.933 | 0.269 |
| fingerprint_ood | 0.816 | 0.846 | 0.846 | 0.535 |
| newer_chemotype | 0.666 | 0.690 | 0.690 | 0.472 |

### Side-by-side atom accuracy

| Split | Dictionary | XGBoost | Better |
|-------|------------|---------|--------|
| random | **0.955** | 0.840 | Dictionary |
| unseen_warhead | 0.057 | **0.828** | XGBoost |
| unseen_e3 | 0.309 | **0.839** | XGBoost |
| fingerprint_ood | **0.891** | 0.816 | Dictionary |
| newer_chemotype | 0.470 | **0.666** | XGBoost |

### Inference (what these numbers mean)

1. **Dictionary is strong when recipes are known.** On `random` and `fingerprint_ood`, lookup nearly reproduces the teacher labels (high coverage + atom accuracy + reassembly).
2. **Dictionary collapses on true unseen chemotypes.** With a train-only book, `unseen_warhead` coverage falls to ~6% and `unseen_e3` to ~33%. Exact-3 / reassembly go to 0 because most test molecules cannot be matched.
3. **XGBoost still works without the missing recipe.** On unseen warhead/E3 splits it keeps ~0.83 atom accuracy and high reassembly (~0.91–0.93), because it learned cut-bond patterns rather than looking up fragment IDs.
4. **Bond ranking gets harder on unseen splits** (`bond_pr_auc` ~0.25–0.27), but top-2 cuts often still produce three fragments — so molecule-level metrics stay useful.
5. **Takeaway for the GNN (notebooks 03–04):** if recipes are available, dictionary is a tough baseline; if warhead/E3 is unseen, a learned method (XGBoost now, GNN next) is the fair competitor to beat.

Full GNN comparison (scratch vs pretrained vs these baselines) comes from notebooks 03–04 → `outputs/final_results_table.csv`.

## Docs

- `logic.md` — short research logic  
- `STEP_BY_STEP_LAYMAN.md` — deep layman walkthrough  
- `NOTEBOOK_02_WALKTHROUGH.md` — cell-by-cell guide for baselines notebook  
- `Manuscript_PROTAC_Substructure_Segmentation.docx` — paper draft  

## Folder layout

```
Yashi/
├── notebooks/          ← ALL method code lives here (cell by cell)
├── data/processed/     ← cached labels, splits, graphs
├── outputs/            ← metrics, models, figures
├── Protac_4.0_database_files_downloaded/
├── run_all.py
├── requirements.txt
├── logic.md
├── STEP_BY_STEP_LAYMAN.md
├── NOTEBOOK_02_WALKTHROUGH.md
└── README.md
```
