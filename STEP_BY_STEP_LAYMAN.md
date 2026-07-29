#50. Yashi pipeline — deep, layman-language walkthrough

This document explains every step of the **Yashi** project in simple words, end-to-end.
If you want to explain your work to a reviewer or a labmate, you can use this as your “story”.

The goal of Yashi is:

> Given a **PROTAC molecule** (a long SMILES string), automatically split its atoms into 3 roles:
> **Warhead**, **Linker**, and **E3 ligand**.

We do it using a small **graph neural network (GNN)** trained on **weak labels**.
Then we evaluate how well it really did using a **chemistry-aware reassembly check**.

---

## 0) What a “step” means in this project

You will see **5 notebooks only**. Each notebook is one major stage.
**All code for that stage lives inside that notebook** (helper cells first,
then experiment cells). There is **no `src/` library**.

1. `01_data_and_labels.ipynb` — data, weak labels, splits, graphs  
2. `02_baselines.ipynb` — dictionary + XGBoost  
3. `03_train_gnn.ipynb` — AttrMask + GNN training  
4. `04_evaluation.ipynb` — metrics and tables  
5. `05_inference_demo.ipynb` — drawings  

How to read a notebook:
* Markdown cells = the story  
* Early code cells = helper functions for this step  
* Later code cells = run the experiment  

Cached data: `data/processed/`  
Results / figures: `outputs/`

---

## 1) Understanding the “weak supervision” idea (labels without human annotation)

In an ideal world, a chemist would label every atom in every PROTAC:

* “this atom is part of the warhead”
* “this atom is part of the linker”
* “this atom is part of the E3 ligand”

But manually labeling thousands of PROTACs is hard.

So Yashi uses a trick:

### 1.1 Dictionary-style matching (no deep learning yet)

We collect reference fragment libraries:

* a library of possible **warheads**
* a library of possible **E3 ligands**

For each PROTAC, we try to “find” which reference fragments appear inside it.
That gives us *initial guesses* for warhead atoms and E3 atoms.

Everything else becomes **linker** by default.

This is why the labels are called **weak**:
they come from matching, so they can be wrong sometimes.

---

## 2) Why the reassembly filter exists (the biggest improvement)

The weak labels can still be messy.
So we add a chemistry sanity check that acts like a gatekeeper.

### 2.1 How we define the split points (boundaries)

After we have an atom label list (W/L/E3), we “cut” the molecule:

* we cut every bond that connects atoms of different classes
  (for example W–L, L–E3, or W–E3)

This produces multiple disconnected pieces (fragments).

### 2.2 What we want (exactly 3 fragments)

For PROTAC splitting, the ideal result is:

* exactly **3 fragments**:
  warhead fragment
  linker fragment
  E3 fragment

So we keep only those labelings where the molecule breaks into exactly 3 pieces.

### 2.3 What we also require (reassembly must recover the original)

We also require that those 3 fragments can be reassembled back into the original molecule.

So if the labeling suggests a chemically inconsistent split, we drop that PROTAC from training.

### 2.4 Why this matters

This step does two huge things:

1. It removes noisy pseudo-labels early (training becomes easier).
2. It makes our evaluation meaningful: we’re training for something chemistry-aware, not just “classification accuracy”.

This reassembly check is inspired by the “curation” concept in Ribes-style PROTAC splitting.

---

## 3) How the project creates train/val/test splits (including “hard generalization”)

If you randomly split PROTACs, the test set still contains many similar warheads/E3 motifs seen in training.
That makes the task easier than it really is.

So we build 3 split types:

### 3.1 Random split
Standard split:

* Train = 80%
* Val = 10%
* Test = 10%

This measures normal performance.

### 3.2 Unseen-warhead split
Here we intentionally hide some warhead families from training.

The test molecules contain warheads that the model likely never saw.

This tests generalization on the **warhead** side.

### 3.3 Unseen-E3 split
Same idea but for E3 ligands:

* E3 motifs are kept out of training
* test includes previously unseen E3 chemotypes

This is typically the hardest split for segmentation.

---

## 4) Graph construction (turning a molecule into something the GNN can read)

Neural networks don’t directly understand SMILES.
So we convert each PROTAC into a **graph**:

* **nodes** = atoms
* **edges** = bonds

### 4.1 Node features (what we store for each atom)

For each atom we store a small set of features, such as:

* atom element type (C/N/O/Cl/Br/etc.)
* hybridization
* degree (how many neighbors)
* aromaticity / ring membership
* charge / number of attached hydrogens

The exact features are designed to be:

* simple
* fast to compute
* sufficient to learn roles (W/L/E3)

### 4.2 Edge features (what we store for each bond)

For each bond we store:

* bond type (single/double/triple/aromatic)
* conjugation (yes/no)
* ring membership

### 4.3 Batching many graphs at once

To train efficiently, we combine multiple molecular graphs into one “big graph” for one forward pass.

We carefully track which atom belongs to which molecule using a `batch` vector.

---

## 5) The model: what the GNN is doing

The model is called `ProtacSegGNN`.

You can think of it in layers:

### 5.1 Encoder (start)

We start by mapping each atom feature vector into a learned embedding space.

### 5.2 GIN message passing (the “chemistry propagation” part)

Each GIN layer updates each atom embedding by collecting information from its neighbors.

After several layers, an atom embedding “knows” about its local chemical neighborhood.

That’s important because:

* warhead atoms tend to live in particular substructures
* E3 ligand atoms tend to live in different substructures
* linker atoms often appear as repeated chain-like chemistry connecting them

So neighborhood context helps classification.

### 5.3 Heads (what outputs it predicts)

The network has multiple “heads”:

1. **Atom head**: predicts class for each atom (W/L/E3)
2. **Bond head**: predicts whether a bond is a boundary
   (boundary = connects two different classes)
3. (internally) a fragment embedding / pooling mechanism to support constraints

---

## 6) Training losses (how we force the model to learn a useful split)

Instead of only training on atom classification, we add multiple losses.

Think of it like:

> “Not only should each atom get the right label, but the whole split should look like 3 connected fragments.”

### 6.1 Atom loss (main task)

We compute cross-entropy between predicted atom class and weak-label atom class.

We also use **class weighting**:

* linker is the smallest class in many molecules
* without weighting, the network often collapses to “predict mostly warhead and E3”
* that would break reassembly

So we boost linker importance.

### 6.2 Bond boundary loss (auxiliary chemistry consistency)

We also train the bond head to detect boundary bonds:

* boundary bond = bond connects different atom classes

This helps the model learn where the “cut” should happen,
not just what each side should be labeled.

### 6.3 Smoothness loss (soft contiguity prior)

Atoms that are neighbors and should belong to the same fragment
should not strongly disagree.

Smoothness loss penalizes prediction differences along edges
where the weak labels say the atoms should be in the same class.

This nudges the model toward coherent fragment regions.

### 6.4 Linker-attachment loss (soft reconstruction proxy)

Exact reassembly is hard to differentiate directly.

So we use a proxy that captures an intuition:

> In a typical PROTAC split into 3 fragments,
> the linker should touch the rest of the molecule at about 2 places:
> linker-warhead boundary and linker-E3 boundary.

The model computes a soft estimate of how many “linker boundary-like” edges it predicts.
We penalize it when that soft count is far from 2.

This is the reconstruction-flavored part of training.

---

## 7) What “raw” vs “chemistry-constrained” predictions mean

When the model predicts labels per atom, you can still get:

* multiple disconnected pieces of the same class
* tiny isolated linker atoms scattered around

Even if atom accuracy is decent, the final “split into 3 connected fragments” may fail.

So for **constrained decoding**, we do:

1. For each class (W, L, E3), find the largest connected component in the predicted labels.
2. Keep that component and remove other small components.
3. Reassign removed atoms to the nearest kept neighbor class.

This forces the predicted segmentation to become 3 meaningful fragments.

That’s why you always see:

* `exact_3_frag_cst` and `reassembly_cst`
* alongside their raw versions

---

## 8) How evaluation works (the metrics in human terms)

### 8.1 Atom accuracy / macro-F1

How often the atom labels match the weak labels (and macro-F1 checks class balance).

If your macro-F1 is low, the model may be missing the linker class.

### 8.2 Exact-3-fragment rate

If we cut along predicted boundaries, do we get 3 connected fragments?

This is about topology.

### 8.3 Reassembly accuracy

This is the chemistry check:

Do the 3 fragments reassemble to the original PROTAC?

This is the most “scientific” metric because it ensures the split is chemically consistent.

---

## 9) Baselines: dictionary and XGBoost (why we include them)

We include baselines so the reviewer sees:

* you didn’t invent a random metric
* you compared against reasonable published-style methods

### 9.1 Dictionary baseline (Ribes-style)

At inference time, we re-run the dictionary matching against warhead and E3 libraries.

This produces labels directly from substructure matching.

Important caveat:

Because the dictionary is the same kind of tool used to generate weak labels,
the dictionary baseline naturally gets very high reassembly on dictionary-generated labels.

That is circular, and we explicitly acknowledge it.

### 9.2 XGBoost baseline (Ayush-style)

Ayush’s idea is to predict which bonds to cut.

We train an XGBoost classifier that scores bonds as “cut or not cut” using engineered features
(bridge-betweenness-like proxy, some chemistry flags, and fingerprint-context features).

Then we select top bonds to create 3 fragments and convert that into W/L/E3 labels for evaluation.

This baseline is strong for bond cutting,
but it doesn’t learn a deep representation like the GNN does.

---

## 10) Interpreting the final results (plain language)

The project outputs results in `outputs/final_results.json`.

The key takeaway:

### 10.1 Yashi GNN beats XGBoost clearly

Example highlights from your final run:

* Random split: GNN atom accuracy is higher than XGBoost.
* Unseen warhead split: GNN stays high; XGBoost drops a lot.

This suggests the GNN representation generalizes better.

### 10.2 Dictionary looks perfect, but that’s expected

Dictionary gets ~1.0 reassembly almost everywhere.

That doesn’t mean the GNN is worse;
it means the dictionary is basically reproducing its own label source.

This is why we still keep it as a baseline:
it’s a sanity check, not a fair “competition”.

### 10.3 Unseen E3 is the hardest and shows where to improve

The GNN reassembly on unseen-E3 is lower than on other splits.

This is the honest OOD failure case:

* E3 recognition depends on specific chemotypes
* the model likely hasn’t seen enough variety during training

So in “future work” you can propose:

* more E3 reference variety
* better learned chemotype encoders
* more robust label generation and/or gold anchors

---

## 11) How to run the whole thing

Recommended:

1. Install dependencies: `pip install -r requirements.txt`
2. Open notebooks in order, or run: `python run_all.py`

Artifacts appear under:

* `data/processed/` (cached graphs and labels)
* `outputs/` (metrics, figures, trained models)

**Tip for researchers:** always *Restart Kernel & Run All* before trusting final numbers.

---

---

## 13) The three final methodology upgrades (post-review)

### 13.1 Pretrained encoder (AttrMask)

Instead of only training the GIN from scratch, we first run a
self-supervised **AttrMask** stage:

* randomly zero out some atom features
* ask the network to predict the atom type from its neighbours

This is the same family of idea used in Mole-BERT / Hu et al. molecular
pretraining, but implemented on our lightweight backbone so it runs on
CPU without PyTorch Geometric. We then fine-tune two models per split
(scratch vs pretrained) and report both.

### 13.2 Reconstruction inside training

Reassembly is no longer “only a test metric”. During training we add a
**soft reconstruction loss**:

* linker should attach at ~2 places
* all three classes (W, L, E3) must remain present in the soft prediction

That is why unseen-E3 reassembly improved a lot after this change.

### 13.3 Stronger OOD benchmark

Beyond random / unseen-warhead / unseen-E3 we also evaluate:

* **fingerprint_ood** — molecules least similar (Morgan fingerprint) to
  the training pool (proxy for a different chemical source)
* **newer_chemotype** — highest PROTAC-DB Compound IDs (proxy for newer
  chemotypes entering the literature later)

These are the splits that show whether the method generalises for real.
