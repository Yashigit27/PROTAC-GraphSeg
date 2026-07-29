# Yashi — research logic (notebooks-only)

## Design choice

This project is organised for a **researcher**, not a software library:

- **One major experimental step → one notebook**
- Helper functions live **in the same notebook** (early cells)
- No `src/` package, no importable library

Run notebooks **01 → 05** in order. Intermediate files are cached so you can re-run later steps without repeating labelling.

## Pipeline

```
PROTAC-DB Excel files
        │
        ▼
[01_data_and_labels.ipynb]
  • load / filter SMILES
  • dictionary weak labels
  • reassembly filter (must cut to 3 valid fragments)
  • 5 splits + graph tensors → data/processed/
        │
        ▼
[02_baselines.ipynb]
  • dictionary baseline
  • XGBoost bond-cut baseline → outputs/baselines_metrics.json
        │
        ▼
[03_train_gnn.ipynb]
  • AttrMask pretrain
  • fine-tune scratch + pretrained GIN
  • losses: atom + bond + smoothness + soft reconstruction
  • → outputs/gnn_models.pt
        │
        ▼
[04_evaluation.ipynb]
  • metrics on all splits
  • comparison table + figures
        │
        ▼
[05_inference_demo.ipynb]
  • coloured molecule drawings
```

## Why exit bonds still matter

Boundary (exit) bonds = bonds whose two atoms have different W/L/E3 labels.

They are used when:
1. filtering weak labels (`reassembles` cuts them),
2. training the bond head (boundary CE),
3. scoring exact-3 / reassembly at evaluation.

Final GNN inference mainly uses **atom** predictions; cut bonds are then implied by atom-class changes.

## Reading order for understanding

1. Open `01_data_and_labels.ipynb` — read markdown cells, then helper cells, then experiment cells  
2. Skim `03_train_gnn.ipynb` for the loss and AttrMask story  
3. Read `04_evaluation.ipynb` results table  

For a long prose explanation, see `STEP_BY_STEP_LAYMAN.md`.
