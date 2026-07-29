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

## Results

See `outputs/final_results_table.csv` and `README` table from the last full run (or regenerate with notebooks 02–04).

## Docs

- `logic.md` — short research logic  
- `STEP_BY_STEP_LAYMAN.md` — deep layman walkthrough  
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
└── README.md
```
