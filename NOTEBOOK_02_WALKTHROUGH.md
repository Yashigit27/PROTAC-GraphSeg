# Notebook 02 Walkthrough — Cell by Cell (Execution Order)

This guide follows `notebooks/02_baselines.ipynb` in the **same order you should run / read the cells**.

Goal of the notebook:

1. Load data made by Notebook 01
2. Score **Method A: Dictionary** (closed book)
3. Score **Method B: XGBoost** (learned bond cuts)
4. Save `outputs/baselines_metrics.json`

Read order rule used below:

> First see what a cell **defines**, then see **who calls it later**.

---

## Big map (what calls what)

```text
[Setup]
  Paths -> Imports -> Helpers -> Load data

[METHOD A: Dictionary]
  train_only_library
       |
       v
  dictionary_predict  ---> uses best_match (from helpers)
       |
       v
  score_dictionary    ---> calls train_only_library + dictionary_predict + reassembles
       |
       v
  Run loop over all splits -> dict_metrics

[METHOD B: XGBoost]
  bridge_scores + bond_features
       |
       v
  morgan_matrix + morgan_svd_for_split
       |
       v
  build_bond_table    ---> uses bond_features / bridge_scores / boundary_bonds
       |
       v
  cuts_to_labels
       |
       v
  score_xgboost       ---> trains XGB, top-2 cuts, atom_accuracy(swap), pr_auc
       |
       v
  Run loop over all splits -> xgb_metrics

[Save]
  Compare side-by-side -> write baselines_metrics.json
```

---

# PART 0 — Setup (run these first)

## Cell: Intro markdown

Explains the notebook purpose and the four fairness fixes:

1. Train-only dictionary book
2. W/E3 swap when scoring XGBoost atom accuracy
3. Train-only Morgan SVD
4. Metric name `bond_pr_auc`

No code runs here.

---

## Cell: Paths (section 0)

**What to read first**

```python
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
```

**Logic**

- If you launched Jupyter inside `notebooks/`, go one folder up to project root.
- `PROCESSED` = where Notebook 01 saved files.
- `OUT` = where this notebook will save metrics.
- `mkdir(..., exist_ok=True)` creates folders if missing.

**Syntax note**

- `Path / "name"` joins paths in a OS-safe way.

---

## Cell: Imports + labels (section 1)

**What to read first**

```python
WARHEAD, LINKER, E3 = 0, 1, 2
```

**Logic**

- Atom labels are integers: warhead=0, linker=1, E3=2.
- Imports needed later:
  - `json`, `pickle` for loading files
  - `rdkit` for molecules
  - `networkx` for bridge-bond graph
  - `TruncatedSVD` for Morgan compression
  - `XGBClassifier` for Method B
- `RDLogger.DisableLog(...)` hides noisy RDKit warnings.

This cell only **prepares tools**. No prediction yet.

---

## Cell: Shared chemistry helpers (section 2)

This is one big code cell. Read blocks in this order.

### Block 1 — `RefFragment` + `prepare_reference_library`

```python
@dataclass
class RefFragment:
    smiles: str
    mol: Chem.Mol
    n_atoms: int
```

**Logic**

- One recipe page in the dictionary book.
- `prepare_reference_library(smiles_list)`:
  1. parse each SMILES
  2. keep only size range 5–60 heavy atoms
  3. sort largest-first (greedy matching later prefers bigger pieces)

**Called later by:** load cell (to build `all_wh_refs`, `all_e3_refs`).

---

### Block 2 — `best_match`

```python
def best_match(mol, refs, forbidden=None):
```

**Logic**

- Walk recipes in order.
- For each recipe, ask RDKit: does this substructure appear in `mol`?
- Skip matches that overlap `forbidden` atoms.
- Return first valid `(atom_set, recipe_smiles)`.

**Called later by:** `dictionary_predict`.

---

### Block 3 — `boundary_bonds`

```python
def boundary_bonds(mol, labels):
```

**Logic**

- A boundary bond connects two atoms with different labels (e.g. W–L or L–E3).
- Those bonds are the natural “cut places”.

**Called later by:** `reassembles`, and XGBoost table building (`build_bond_table`).

---

### Block 4 — `reassembles`

```python
def reassembles(mol, labels):
```

**Logic**

1. Find boundary bonds
2. Cut them (`FragmentOnBonds`)
3. Success if exactly 3 chemically valid fragments and no atoms lost

**Called later by:** both scoring functions (`score_dictionary`, `score_xgboost`).

---

### Block 5 — `atom_accuracy`

```python
def atom_accuracy(true_labels, pred_labels, allow_we_swap=False):
```

**Logic**

- Normal: fraction of atoms where pred == true.
- If `allow_we_swap=True`: also try swapping warhead <-> E3 in prediction, keep better score.
- This avoids punishing a correct cut that only misnamed the two ends.

**Called later by:** XGBoost scoring (with swap on).

---

### Block 6 — `pr_auc`

```python
def pr_auc(y_true, scores):
```

**Logic**

- Average precision for bond cut ranking.
- This is **not** ROC-AUC (naming fix).

**Called later by:** `score_xgboost` as `bond_pr_auc`.

---

## Cell: Load Notebook 01 outputs (section 3)

**What to read first**

```python
records = [...]
splits = pickle.load(...)
refs_raw = pickle.load(...)
all_wh_refs = prepare_reference_library(refs_raw["warheads"])
all_e3_refs = prepare_reference_library(refs_raw["e3"])
```

**Logic / call order**

1. Load labeled molecules (`records`) from `labeled_protacs.jsonl`
2. Load exam seats (`splits`) from `splits.pkl`
3. Load raw recipe SMILES (`refs_raw`) from `refs.pkl`
4. Call `prepare_reference_library` twice → full books `all_wh_refs`, `all_e3_refs`

**Important**

- These are the **full** books.
- Method A will shrink them per split using train-only filtering.
- Method B mostly uses `records` + `splits` (not recipe lookup).

Now setup is done. Next is Method A.

---

# PART A — METHOD A: Dictionary (closed book)

Read / run in order: A1 -> A2 -> A3 -> A4.

## A1 cell — `train_only_library`

**Function**

```python
def train_only_library(records, train_idx, all_wh, all_e3):
```

**Logic**

1. Collect `wh_ref` / `e3_ref` values from **train molecules only**
2. Keep only recipes whose SMILES appear in that train set
3. Return smaller books `(wh, e3)`

**Why**

- Makes unseen splits fair: held-out recipes are usually missing from the book.

**Demo block in same cell**

```python
_tr = splits["unseen_warhead"]["train"]
_wh, _e3 = train_only_library(records, _tr, all_wh_refs, all_e3_refs)
```

This only prints how much the book shrinks. Real scoring happens in A4.

**Called later by:** `score_dictionary`.

---

## A2 cell — `dictionary_predict`

**Function**

```python
def dictionary_predict(smiles, wh_refs, e3_refs):
```

**Internal call order**

1. `Chem.MolFromSmiles(smiles)`
2. size check (15–120 atoms)
3. `best_match(mol, wh_refs)` -> warhead atoms
4. `best_match(mol, e3_refs, forbidden=wh_atoms)` -> E3 atoms
5. leftover atoms become linker
6. return label list, or `None` if matching failed

**Logic**

- This is inference-time lookup.
- If the needed recipe is not in the (train-only) book, return `None`.

**Called later by:** `score_dictionary`.

---

## A3 cell — `score_dictionary`

**Function**

```python
def score_dictionary(records, train_idx, test_idx, all_wh, all_e3):
```

**Internal call order (this is the Method A engine)**

1. `train_only_library(...)` -> closed book for this split
2. For each test molecule index:
   - `dictionary_predict(...)`
   - if `None`: no coverage credit; atoms counted as wrong
   - else compare pred vs true labels
   - `reassembles(mol, pred)` for exact-3 / reassembly
3. Return metrics dict:
   - `coverage`
   - `atom_acc`
   - `exact_3_frag`
   - `reassembly`
   - book sizes used

**Logic**

- One split in, one metrics dict out.
- Does not train anything.

**Called later by:** A4 loop.

---

## A4 cell — Run dictionary on every split

**What to read first**

```python
dict_metrics = {}
for sname, s in splits.items():
    m = score_dictionary(records, s["train"], s["test"], all_wh_refs, all_e3_refs)
    dict_metrics[sname] = m
```

**Call order**

```text
for each split name:
    score_dictionary
        -> train_only_library
        -> dictionary_predict (many times)
            -> best_match
        -> reassembles
```

**What you should see**

- `random` / `fingerprint_ood`: high coverage and atom accuracy
- `unseen_warhead` / `unseen_e3`: coverage collapses (closed book works)

Method A finished. Results live in `dict_metrics`.

---

# PART B — METHOD B: XGBoost (Ayush-style bond cuts)

Read / run in order: B1 -> B2 -> B3 -> B4 -> B5 -> B6.

## B1 cell — `bridge_scores` + `bond_features`

### Function 1 — `bridge_scores(mol)`

**Logic**

1. Build a NetworkX graph of the molecule
2. Find bridge edges (removing them splits the graph)
3. Score each bridge by how balanced the two sides are

**Why**

- Linker attachment bonds are often bridge-like.

**Called later by:** `build_bond_table`.

---

### Function 2 — `bond_features(mol, bond, bc, morgan_vec)`

**Logic**

Builds one numeric row for one bond:

- local chemistry: ring?, sp3?, rotatable?, amide?, ether?, atom numbers, degrees, charges...
- plus `bc` bridge score
- plus `morgan_vec` (whole-molecule context)

**Syntax**

- Local features packed into a NumPy array
- `np.concatenate([local, morgan_vec])` makes the final row

**Called later by:** `build_bond_table`.

---

## B2 cell — Morgan matrix + train-only SVD

### Function 1 — `morgan_matrix(records)`

**Logic**

- For every molecule, compute 256-bit Morgan fingerprint.
- Store as matrix shape `(n_molecules, 256)`.

**Why**

- Raw fingerprints first; compression comes next.

---

### Function 2 — `morgan_svd_for_split(fps, train_idx)`

**Logic (fairness fix)**

1. Fit SVD on **train rows only**
2. Transform **all rows** with that same fit

```python
svd.fit(fps[train_idx])      # no test peeking
return svd.transform(fps)
```

**Why**

- Prevents test molecules from shaping the feature space.

---

### Execution in this cell

```python
FPS = morgan_matrix(records)
```

This computes fingerprints once.  
Per-split SVD happens later inside `score_xgboost`.

---

## B3 cell — `build_bond_table`

**Function**

```python
def build_bond_table(records, indices, morgan_svd_all):
```

**Internal call order for each molecule**

1. `Chem.MolFromSmiles`
2. `bridge_scores(mol)`
3. `boundary_bonds(mol, true_labels)` -> true cut bonds (supervision)
4. For each bond:
   - `bond_features(...)` -> one X row
   - y = 1 if bond is a true cut, else 0
   - remember molecule id in `group`

**Returns**

- `X`: bonds x features
- `y`: cut / not-cut
- `group`: which molecule each bond-row belongs to

**Called later by:** `score_xgboost` for train and test.

---

## B4 cell — `cuts_to_labels`

**Function**

```python
def cuts_to_labels(mol, cut_bond_indices):
```

**Logic**

1. Remove the predicted cut bonds
2. If not exactly 3 fragments -> label everything linker (failure case)
3. Find middle fragment (touches both cuts) -> linker
4. Remaining two ends:
   - larger -> warhead guess
   - smaller -> E3 guess

**Important**

- End naming is a guess.
- That is why scoring later allows W/E3 swap.

**Called later by:** `score_xgboost`.

---

## B5 cell — `score_xgboost` (Method B engine)

**Function**

```python
def score_xgboost(records, train_idx, test_idx, fps):
```

**Internal call order (read this carefully)**

1. `morgan_svd_for_split(fps, train_idx)`  
   -> train-only SVD features
2. `build_bond_table(..., train_idx, ...)`  
   -> `X_tr`, `y_tr`
3. `build_bond_table(..., test_idx, ...)`  
   -> `X_te`, `y_te`, `grp_te`
4. Create `XGBClassifier(...)` and `clf.fit(X_tr, y_tr)`
5. `scores = clf.predict_proba(X_te)[:, 1]`  
   -> probability that each test bond is a cut
6. For each test molecule:
   - gather that molecule’s bond rows
   - pick top-2 highest scores
   - `cuts_to_labels(mol, top2)`
   - `atom_accuracy(..., allow_we_swap=True)`
   - `reassembles(mol, pred)`
7. Compute `bond_pr_auc = pr_auc(y_te, scores)`
8. Return metrics dict

**Logic summary**

- Learns cut bonds from train.
- Predicts cuts on test.
- Converts cuts to atom labels.
- Scores fairly with W/E3 swap + PR-AUC.

**Called later by:** B6 loop.

---

## B6 cell — Run XGBoost on every split

**What to read first**

```python
xgb_metrics = {}
for sname, s in splits.items():
    m = score_xgboost(records, s["train"], s["test"], FPS)
    xgb_metrics[sname] = m
```

**Call order**

```text
for each split:
    score_xgboost
        -> morgan_svd_for_split
        -> build_bond_table (train)
            -> bridge_scores, boundary_bonds, bond_features
        -> build_bond_table (test)
        -> XGBClassifier.fit / predict_proba
        -> cuts_to_labels
        -> atom_accuracy(allow_we_swap=True)
        -> reassembles
        -> pr_auc
```

Method B finished. Results live in `xgb_metrics`.

---

# PART C — Compare and save

## Compare cell

**What it does**

- Prints side-by-side `atom_acc` for dictionary vs XGBoost
- Prints dictionary `coverage` per split

**Why**

- Easy check that unseen splits hurt dictionary more than XGBoost.

---

## Save cell

**What to read first**

```python
out = {
    "dictionary": dict_metrics,
    "xgboost": xgb_metrics,
    "notes": {...},
}
json.dump(out, open(OUT / "baselines_metrics.json", "w"), indent=2)
```

**Logic**

- Keeps the two methods in **separate** blocks.
- Notebook 04 later loads this file for the final comparison table.

---

# Recommended reading path for a new person

If someone is confused, tell them to read in this exact order:

1. Paths + Imports
2. Helpers: only `best_match`, `boundary_bonds`, `reassembles`
3. Load cell
4. Method A: `train_only_library` -> `dictionary_predict` -> `score_dictionary` -> run loop
5. Method B: `bond_features` -> `morgan_svd_for_split` -> `build_bond_table` -> `cuts_to_labels` -> `score_xgboost` -> run loop
6. Save cell

Do **not** jump into XGBoost before understanding Method A call chain.

---

# One-page memory

| Piece | Role |
|-------|------|
| `train_only_library` | Close the dictionary book to train recipes |
| `dictionary_predict` | Lookup-based atom painting |
| `score_dictionary` | Evaluate Method A on one split |
| `bond_features` | Turn one bond into numbers |
| `morgan_svd_for_split` | Molecule context without test leakage |
| `build_bond_table` | Make supervised cut/non-cut table |
| `cuts_to_labels` | Top cuts -> W/L/E3 labels |
| `score_xgboost` | Train + evaluate Method B on one split |

**Method A = look up recipes.  
Method B = learn where to cut.**
