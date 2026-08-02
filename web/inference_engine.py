"""PROTAC segmentation engine for the web tool.

Supports:
  - dictionary  (recipe lookup)
  - xgboost     (bond-cut baseline; trained once and cached)
  - gnn         (main model from outputs/gnn_models.pt)
"""
from __future__ import annotations

import io
import json
import pickle
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

WARHEAD, LINKER, E3 = 0, 1, 2
CLASS_NAMES = {WARHEAD: "warhead", LINKER: "linker", E3: "e3_ligand"}
CLASS_COLORS = {
    WARHEAD: (1.0, 0.35, 0.35),
    LINKER: (0.30, 0.55, 1.0),
    E3: (0.30, 0.85, 0.35),
}

ATOM_TYPES = ["C", "N", "O", "S", "F", "Cl", "Br", "I", "P", "B", "Si", "Se", "Other"]
HYBRIDS = [
    Chem.HybridizationType.SP,
    Chem.HybridizationType.SP2,
    Chem.HybridizationType.SP3,
    Chem.HybridizationType.SP3D,
    Chem.HybridizationType.SP3D2,
]
BOND_TYPES = [
    Chem.BondType.SINGLE,
    Chem.BondType.DOUBLE,
    Chem.BondType.TRIPLE,
    Chem.BondType.AROMATIC,
]


@dataclass
class RefFragment:
    smiles: str
    mol: Chem.Mol
    n_atoms: int


def _oh(v, choices):
    x = [0.0] * (len(choices) + 1)
    try:
        x[choices.index(v)] = 1.0
    except ValueError:
        x[-1] = 1.0
    return x


def atom_features(a: Chem.Atom) -> list[float]:
    return (
        _oh(a.GetSymbol(), ATOM_TYPES)
        + _oh(a.GetHybridization(), HYBRIDS)
        + [
            float(a.GetDegree()),
            float(a.GetFormalCharge()),
            float(a.GetTotalNumHs()),
            float(a.GetIsAromatic()),
            float(a.IsInRing()),
        ]
    )


def bond_features_g(b: Chem.Bond) -> list[float]:
    return _oh(b.GetBondType(), BOND_TYPES) + [
        float(b.GetIsConjugated()),
        float(b.IsInRing()),
    ]


ATOM_FEATURE_DIM = len(atom_features(Chem.MolFromSmiles("C").GetAtomWithIdx(0)))
BOND_FEATURE_DIM = len(bond_features_g(Chem.MolFromSmiles("CC").GetBondWithIdx(0)))


def prepare_reference_library(smiles_list, min_atoms=5, max_atoms=60):
    refs = []
    for smi in smiles_list:
        if not isinstance(smi, str) or not smi:
            continue
        m = Chem.MolFromSmiles(smi)
        if m is None:
            continue
        n = m.GetNumHeavyAtoms()
        if min_atoms <= n <= max_atoms:
            refs.append(RefFragment(Chem.MolToSmiles(m), m, n))
    refs.sort(key=lambda r: r.n_atoms, reverse=True)
    return refs


def best_match(mol, refs, forbidden=None):
    forbidden = forbidden or set()
    for ref in refs:
        if ref.n_atoms > mol.GetNumAtoms():
            continue
        for match in mol.GetSubstructMatches(ref.mol, uniquify=True, useChirality=False):
            atoms = set(match)
            if atoms.isdisjoint(forbidden):
                return atoms, ref.smiles
    return None


def boundary_bonds(mol, labels):
    return [
        b.GetIdx()
        for b in mol.GetBonds()
        if labels[b.GetBeginAtomIdx()] != labels[b.GetEndAtomIdx()]
    ]


def reassembles(mol, labels):
    cuts = boundary_bonds(mol, labels)
    if not cuts:
        return False, 1
    frag_mol = Chem.FragmentOnBonds(mol, cuts, addDummies=True)
    frags = Chem.GetMolFrags(frag_mol, asMols=True, sanitizeFrags=False)
    if len(frags) != 3:
        return False, len(frags)
    atoms_seen = 0
    for f in frags:
        try:
            Chem.SanitizeMol(f)
        except Exception:
            return False, len(frags)
        atoms_seen += sum(1 for a in f.GetAtoms() if a.GetAtomicNum() != 0)
    return atoms_seen == mol.GetNumAtoms(), 3


def scatter_sum(src, index, n):
    out = torch.zeros(n, src.size(-1), device=src.device, dtype=src.dtype)
    out.index_add_(0, index, src)
    return out


class GINLayer(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.eps = nn.Parameter(torch.zeros(1))
        self.mlp = nn.Sequential(nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, dim))
        self.bn = nn.BatchNorm1d(dim)

    def forward(self, x, edge_index):
        src, dst = edge_index[0], edge_index[1]
        agg = scatter_sum(x[src], dst, n=x.size(0))
        return self.bn(self.mlp((1.0 + self.eps) * x + agg))


class ProtacSegGNN(nn.Module):
    def __init__(self, atom_dim: int, hidden: int = 64, n_layers: int = 4, dropout: float = 0.0):
        super().__init__()
        self.encoder = nn.Linear(atom_dim, hidden)
        self.layers = nn.ModuleList([GINLayer(hidden) for _ in range(n_layers)])
        self.dropout = nn.Dropout(dropout)
        self.atom_head = nn.Linear(hidden, 3)
        self.bond_head = nn.Sequential(
            nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 2)
        )
        self.frag_proj = nn.Linear(hidden, hidden)
        self.attrmask_head = nn.Linear(hidden, len(ATOM_TYPES) + 1)

    def encode(self, x, edge_index):
        h = F.relu(self.encoder(x))
        for layer in self.layers:
            h = F.relu(layer(h, edge_index))
            h = self.dropout(h)
        return h

    def forward(self, x, edge_index):
        h = self.encode(x, edge_index)
        atom_logits = self.atom_head(h)
        src, dst = edge_index[0], edge_index[1]
        bond_logits = self.bond_head(torch.cat([h[src], h[dst]], dim=-1))
        return atom_logits, bond_logits, h


def smiles_to_graph(smiles: str) -> Optional[dict]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    n = mol.GetNumAtoms()
    x = torch.tensor([atom_features(a) for a in mol.GetAtoms()], dtype=torch.float32)
    src, dst, eattr = [], [], []
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        f = bond_features_g(b)
        src += [i, j]
        dst += [j, i]
        eattr += [f, f]
    ei = torch.tensor([src, dst], dtype=torch.long) if src else torch.zeros(2, 0, dtype=torch.long)
    ea = (
        torch.tensor(eattr, dtype=torch.float32)
        if eattr
        else torch.zeros(0, BOND_FEATURE_DIM)
    )
    return {"x": x, "edge_index": ei, "edge_attr": ea, "n_atoms": n, "smiles": smiles}


def largest_cc_per_class(mol: Chem.Mol, labels: list[int]) -> list[int]:
    n = mol.GetNumAtoms()
    adj = [[] for _ in range(n)]
    for b in mol.GetBonds():
        adj[b.GetBeginAtomIdx()].append(b.GetEndAtomIdx())
        adj[b.GetEndAtomIdx()].append(b.GetBeginAtomIdx())
    seen = [False] * n
    ccs = []
    for i in range(n):
        if seen[i]:
            continue
        cls = labels[i]
        comp = []
        q = deque([i])
        seen[i] = True
        while q:
            u = q.popleft()
            comp.append(u)
            for v in adj[u]:
                if not seen[v] and labels[v] == cls:
                    seen[v] = True
                    q.append(v)
        ccs.append((cls, comp))
    keep = set()
    for cls in (WARHEAD, LINKER, E3):
        cands = [c for c in ccs if c[0] == cls]
        if cands:
            keep.update(max(cands, key=lambda c: len(c[1]))[1])
    if not keep:
        return list(labels)
    new = [-1] * n
    q = deque()
    for a in keep:
        new[a] = labels[a]
        q.append(a)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if new[v] == -1:
                new[v] = new[u]
                q.append(v)
    return new


def fragment_smiles(mol: Chem.Mol, labels: list[int], cls: int) -> Optional[str]:
    atoms = [i for i, lab in enumerate(labels) if lab == cls]
    if not atoms:
        return None
    try:
        return Chem.MolFragmentToSmiles(mol, atomsToUse=atoms, canonical=True)
    except Exception:
        return None


def draw_labeled_png(smiles: str, labels: list[int]) -> bytes:
    mol = Chem.MolFromSmiles(smiles)
    atom_colors = {i: CLASS_COLORS[l] for i, l in enumerate(labels)}
    bond_colors = {}
    for b in mol.GetBonds():
        li, lj = labels[b.GetBeginAtomIdx()], labels[b.GetEndAtomIdx()]
        bond_colors[b.GetIdx()] = CLASS_COLORS[li] if li == lj else (0.15, 0.15, 0.15)
    d = rdMolDraw2D.MolDraw2DCairo(720, 480)
    d.drawOptions().highlightRadius = 0.35
    d.drawOptions().fillHighlights = True
    rdMolDraw2D.PrepareAndDrawMolecule(
        d,
        mol,
        highlightAtoms=list(atom_colors),
        highlightAtomColors=atom_colors,
        highlightBonds=list(bond_colors),
        highlightBondColors=bond_colors,
    )
    d.FinishDrawing()
    return d.GetDrawingText()


def pack_result(smiles: str, labels: list[int], model: str, extra: Optional[dict] = None) -> dict:
    mol = Chem.MolFromSmiles(smiles)
    canon = Chem.MolToSmiles(mol)
    ok, nfrag = reassembles(mol, labels)
    wh = fragment_smiles(mol, labels, WARHEAD)
    li = fragment_smiles(mol, labels, LINKER)
    e3 = fragment_smiles(mol, labels, E3)
    import base64

    png = draw_labeled_png(canon, labels)
    out = {
        "ok": True,
        "model": model,
        "input_smiles": smiles,
        "canonical_smiles": canon,
        "labels": labels,
        "n_atoms": mol.GetNumAtoms(),
        "counts": {
            "warhead": labels.count(WARHEAD),
            "linker": labels.count(LINKER),
            "e3": labels.count(E3),
        },
        "substructures": {
            "warhead_smiles": wh,
            "linker_smiles": li,
            "e3_smiles": e3,
        },
        "reassembly": ok,
        "n_fragments": nfrag,
        "image_png_base64": base64.b64encode(png).decode("ascii"),
        "note": "Colors: coral=warhead, blue=linker, green=E3",
    }
    if extra:
        out.update(extra)
    return out


# ---- XGBoost helpers (simplified tool version) --------------------------------

def bridge_scores(mol):
    G = nx.Graph()
    for a in mol.GetAtoms():
        G.add_node(a.GetIdx())
    for b in mol.GetBonds():
        G.add_edge(b.GetBeginAtomIdx(), b.GetEndAtomIdx())
    n = G.number_of_nodes()
    out = {}
    if n < 2:
        return out
    denom = n * (n - 1) / 2
    bridges = set(nx.bridges(G))
    for b in mol.GetBonds():
        u, v = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if (u, v) not in bridges and (v, u) not in bridges:
            continue
        H = G.copy()
        H.remove_edge(u, v)
        comps = list(nx.connected_components(H))
        if len(comps) == 2:
            a, bsz = len(comps[0]), len(comps[1])
            out[b.GetIdx()] = (a * bsz) / denom
    return out


def bond_feat_row(mol, bond, bc, morgan_vec):
    i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
    a1, a2 = mol.GetAtomWithIdx(i), mol.GetAtomWithIdx(j)
    is_ring = int(bond.IsInRing())
    sp3 = 0.5 * (
        int(a1.GetHybridization() == Chem.HybridizationType.SP3)
        + int(a2.GetHybridization() == Chem.HybridizationType.SP3)
    )
    rotatable = int(
        (not is_ring)
        and bond.GetBondType() == Chem.BondType.SINGLE
        and a1.GetDegree() > 1
        and a2.GetDegree() > 1
    )
    bond_type = {
        Chem.BondType.SINGLE: 1.0,
        Chem.BondType.DOUBLE: 2.0,
        Chem.BondType.TRIPLE: 3.0,
        Chem.BondType.AROMATIC: 1.5,
    }.get(bond.GetBondType(), 1.0)
    local = np.array(
        [
            is_ring,
            sp3,
            rotatable,
            bc.get(bond.GetIdx(), 0.0),
            a1.GetAtomicNum(),
            a2.GetAtomicNum(),
            bond_type,
            int(a1.GetAtomicNum() == 8 or a2.GetAtomicNum() == 8),
            int(a1.IsInRing()),
            int(a2.IsInRing()),
            int(a1.GetIsAromatic()),
            int(a2.GetIsAromatic()),
            int(bond.GetIsAromatic()),
            a1.GetDegree(),
            a2.GetDegree(),
        ],
        dtype=np.float32,
    )
    return np.concatenate([local, morgan_vec])


def cuts_to_labels(mol, cut_bond_indices):
    n = mol.GetNumAtoms()
    if not cut_bond_indices:
        return [LINKER] * n
    rw = Chem.RWMol(mol)
    for bidx in cut_bond_indices:
        try:
            bond = mol.GetBondWithIdx(bidx)
            rw.RemoveBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        except Exception:
            pass
    frags = Chem.GetMolFrags(rw.GetMol(), asMols=False)
    if len(frags) != 3:
        return [LINKER] * n
    frag_sets = [set(f) for f in frags]
    cut_pairs = []
    for bidx in cut_bond_indices:
        bond = mol.GetBondWithIdx(bidx)
        cut_pairs.append((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
    linker_idx = -1
    for k, s in enumerate(frag_sets):
        if all(any(a in s for a in pair) for pair in cut_pairs):
            linker_idx = k
            break
    if linker_idx < 0:
        linker_idx = min(range(3), key=lambda k: len(frag_sets[k]))
    ends = [k for k in range(3) if k != linker_idx]
    ends.sort(key=lambda k: -len(frag_sets[k]))
    labels = [LINKER] * n
    for a in frag_sets[ends[0]]:
        labels[a] = WARHEAD
    for a in frag_sets[ends[1]]:
        labels[a] = E3
    return labels


class Segmenter:
    def __init__(self):
        self.ready = {"dictionary": False, "xgboost": False, "gnn": False}
        self.wh_refs = []
        self.e3_refs = []
        self.gnn = None
        self.xgb = None
        self.svd = None
        self.status = "not loaded"

    def load(self):
        self.status = "loading dictionary..."
        refs = pickle.load(open(PROCESSED / "refs.pkl", "rb"))
        self.wh_refs = prepare_reference_library(refs["warheads"])
        self.e3_refs = prepare_reference_library(refs["e3"])
        self.ready["dictionary"] = True

        self.status = "loading GNN..."
        ckpt_path = OUT / "gnn_models.pt"
        if not ckpt_path.exists():
            raise FileNotFoundError(
                f"Missing {ckpt_path}. Run notebook 03_train_gnn.ipynb first."
            )
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        atom_dim = ckpt.get("atom_dim", ATOM_FEATURE_DIM)
        self.gnn = ProtacSegGNN(atom_dim=atom_dim, hidden=64, n_layers=4, dropout=0.0)
        # Prefer scratch/random as default main model
        sd = ckpt["state_dicts"]["scratch"].get("random") or next(
            iter(ckpt["state_dicts"]["scratch"].values())
        )
        self.gnn.load_state_dict(sd)
        self.gnn.eval()
        self.ready["gnn"] = True

        self.status = "preparing XGBoost (may take ~1 min first time)..."
        self._ensure_xgb()
        self.status = "ready"

    def _ensure_xgb(self):
        cache = OUT / "xgb_tool.pkl"
        if cache.exists():
            blob = pickle.load(open(cache, "rb"))
            self.xgb = blob["clf"]
            self.svd = blob["svd"]
            self.ready["xgboost"] = True
            return

        from sklearn.decomposition import TruncatedSVD
        from xgboost import XGBClassifier

        records = [json.loads(l) for l in open(PROCESSED / "labeled_protacs.jsonl")]
        splits = pickle.load(open(PROCESSED / "splits.pkl", "rb"))
        train_idx = splits["random"]["train"]

        fps = np.zeros((len(records), 256), dtype=np.float32)
        for i, rec in enumerate(records):
            mol = Chem.MolFromSmiles(rec["smiles"])
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=3, nBits=256)
            arr = np.zeros(256, dtype=np.int8)
            DataStructs.ConvertToNumpyArray(fp, arr)
            fps[i] = arr.astype(np.float32)

        svd = TruncatedSVD(n_components=min(32, len(train_idx) - 1), random_state=0)
        svd.fit(fps[train_idx])
        morgan = svd.transform(fps)

        X_rows, y_rows = [], []
        # subsample train for faster tool startup
        use = train_idx[::2] if len(train_idx) > 800 else train_idx
        for idx in use:
            rec = records[idx]
            mol = Chem.MolFromSmiles(rec["smiles"])
            bc = bridge_scores(mol)
            cuts = set(boundary_bonds(mol, rec["labels"]))
            mvec = morgan[idx]
            for b in mol.GetBonds():
                X_rows.append(bond_feat_row(mol, b, bc, mvec))
                y_rows.append(1 if b.GetIdx() in cuts else 0)
        X = np.stack(X_rows)
        y = np.array(y_rows)
        pos = max(int(y.sum()), 1)
        neg = max(int((y == 0).sum()), 1)
        clf = XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            tree_method="hist",
            scale_pos_weight=float(neg) / pos,
            n_jobs=-1,
            verbosity=0,
            random_state=0,
        )
        clf.fit(X, y)
        pickle.dump({"clf": clf, "svd": svd}, open(cache, "wb"))
        self.xgb = clf
        self.svd = svd
        self.ready["xgboost"] = True

    def segment_dictionary(self, smiles: str) -> dict:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"ok": False, "error": "Invalid SMILES"}
        n = mol.GetNumAtoms()
        if not (10 <= n <= 150):
            return {"ok": False, "error": f"Unusual size ({n} atoms). Expected ~15–120."}
        wh = best_match(mol, self.wh_refs)
        if wh is None:
            return {"ok": False, "error": "No warhead recipe matched in the dictionary."}
        e3 = best_match(mol, self.e3_refs, forbidden=wh[0])
        if e3 is None:
            return {"ok": False, "error": "No E3 recipe matched in the dictionary."}
        labels = [LINKER] * n
        for a in wh[0]:
            labels[a] = WARHEAD
        for a in e3[0]:
            labels[a] = E3
        if LINKER not in labels:
            return {"ok": False, "error": "No linker atoms left after matching."}
        return pack_result(
            smiles,
            labels,
            "dictionary",
            extra={"matched_warhead_ref": wh[1], "matched_e3_ref": e3[1]},
        )

    def segment_xgboost(self, smiles: str) -> dict:
        if not self.ready["xgboost"]:
            return {"ok": False, "error": "XGBoost model not ready"}
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"ok": False, "error": "Invalid SMILES"}
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=3, nBits=256)
        arr = np.zeros(256, dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        mvec = self.svd.transform(arr.astype(np.float32).reshape(1, -1))[0]
        bc = bridge_scores(mol)
        rows = []
        for b in mol.GetBonds():
            rows.append(bond_feat_row(mol, b, bc, mvec))
        if not rows:
            return {"ok": False, "error": "Molecule has no bonds"}
        X = np.stack(rows)
        scores = self.xgb.predict_proba(X)[:, 1]
        top2 = list(np.argsort(-scores)[:2])
        labels = cuts_to_labels(mol, top2)
        return pack_result(smiles, labels, "xgboost", extra={"top_cut_bonds": top2})

    @torch.no_grad()
    def segment_gnn(self, smiles: str) -> dict:
        if not self.ready["gnn"]:
            return {"ok": False, "error": "GNN model not ready. Train notebook 03 first."}
        g = smiles_to_graph(smiles)
        if g is None:
            return {"ok": False, "error": "Invalid SMILES"}
        al, _, _ = self.gnn(g["x"], g["edge_index"])
        raw = al.argmax(-1).tolist()
        mol = Chem.MolFromSmiles(smiles)
        labels = largest_cc_per_class(mol, raw)
        return pack_result(
            smiles,
            labels,
            "gnn",
            extra={"variant": "scratch/random", "is_main_model": True},
        )

    def segment(self, smiles: str, model: str = "gnn") -> dict:
        model = (model or "gnn").lower().strip()
        if model in ("gnn", "gnn_scratch", "main"):
            return self.segment_gnn(smiles)
        if model in ("dictionary", "dict"):
            return self.segment_dictionary(smiles)
        if model in ("xgboost", "xgb"):
            return self.segment_xgboost(smiles)
        return {"ok": False, "error": f"Unknown model: {model}"}


ENGINE = Segmenter()
