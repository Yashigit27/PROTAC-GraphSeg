/* Real metrics from Yashi outputs (fair baselines + GNN evaluation). */
window.YASHI = {
  splits: [
    "random",
    "unseen_warhead",
    "unseen_e3",
    "fingerprint_ood",
    "newer_chemotype",
  ],
  splitExplain: {
    random: "Normal mixed exam. Chemotypes can overlap train/test.",
    unseen_warhead: "Test warhead recipes are held out of train. Hard for lookup methods.",
    unseen_e3: "Test E3 recipes are held out of train.",
    fingerprint_ood: "Test molecules are chemically dissimilar by Morgan fingerprint.",
    newer_chemotype: "Newest Compound IDs held out as a time-like shift.",
  },
  /* Notebook 02 fair closed-book dictionary + XGBoost */
  dictionary: {
    random: { coverage: 0.984, atom_acc: 0.955, exact_3: 0.981, reassembly: 0.981 },
    unseen_warhead: { coverage: 0.062, atom_acc: 0.057, exact_3: 0.0, reassembly: 0.0 },
    unseen_e3: { coverage: 0.329, atom_acc: 0.309, exact_3: 0.0, reassembly: 0.0 },
    fingerprint_ood: { coverage: 0.932, atom_acc: 0.891, exact_3: 0.930, reassembly: 0.930 },
    newer_chemotype: { coverage: 0.485, atom_acc: 0.470, exact_3: 0.464, reassembly: 0.464 },
  },
  xgboost: {
    random: { atom_acc: 0.840, exact_3: 0.853, reassembly: 0.853, bond_pr_auc: 0.750 },
    unseen_warhead: { atom_acc: 0.828, exact_3: 0.913, reassembly: 0.913, bond_pr_auc: 0.255 },
    unseen_e3: { atom_acc: 0.839, exact_3: 0.933, reassembly: 0.933, bond_pr_auc: 0.269 },
    fingerprint_ood: { atom_acc: 0.816, exact_3: 0.846, reassembly: 0.846, bond_pr_auc: 0.535 },
    newer_chemotype: { atom_acc: 0.666, exact_3: 0.690, reassembly: 0.690, bond_pr_auc: 0.472 },
  },
  /* Notebook 04 GNN constrained metrics */
  gnn_scratch: {
    random: { atom_acc: 0.922, exact_3: 0.988, reassembly: 0.917 },
    unseen_warhead: { atom_acc: 0.901, exact_3: 0.988, reassembly: 0.772 },
    unseen_e3: { atom_acc: 0.887, exact_3: 0.967, reassembly: 0.810 },
    fingerprint_ood: { atom_acc: 0.853, exact_3: 0.880, reassembly: 0.731 },
    newer_chemotype: { atom_acc: 0.923, exact_3: 0.898, reassembly: 0.784 },
  },
  gnn_pretrained: {
    random: { atom_acc: 0.915, exact_3: 0.982, reassembly: 0.875 },
    unseen_warhead: { atom_acc: 0.874, exact_3: 1.0, reassembly: 0.912 },
    unseen_e3: { atom_acc: 0.853, exact_3: 0.951, reassembly: 0.674 },
    fingerprint_ood: { atom_acc: 0.866, exact_3: 0.976, reassembly: 0.689 },
    newer_chemotype: { atom_acc: 0.920, exact_3: 0.976, reassembly: 0.844 },
  },
  demos: [
    {
      id: "d1",
      name: "Classic ternary PROTAC",
      smiles: "CC(C)Nc1cc(-c2ccc(C(=O)N3CCN(C(=O)COc4cccc5c4C(=O)N(C4CCC(=O)NC4=O)C5=O)CC3)cc2)ccn1",
      note: "Warhead–linker–E3 pattern with amide/PEG-like attachments.",
      // simplified part lengths for viz (not atom-exact): W, L, E3
      parts: { w: 18, l: 22, e: 16 },
      preds: {
        dictionary: { ok: true, atom_acc: 0.96, note: "Recipes found in book." },
        xgboost: { ok: true, atom_acc: 0.84, note: "Top-2 cuts recovered 3 fragments." },
        gnn: { ok: true, atom_acc: 0.93, note: "Graph segmentation + soft reconstruction." },
      },
    },
    {
      id: "d2",
      name: "Unseen-warhead style case",
      smiles: "O=C(COc1cccc2c1C(=O)N(C1CCC(=O)NC1=O)C2=O)N1CCN(C(=O)c2ccc(-c3ccnc(NC4CCCC4)c3)cc2)CC1",
      note: "If warhead recipe is missing from the train-only book, dictionary fails.",
      parts: { w: 20, l: 18, e: 17 },
      preds: {
        dictionary: { ok: false, atom_acc: 0.0, note: "Closed book: warhead recipe absent." },
        xgboost: { ok: true, atom_acc: 0.81, note: "Cut geometry still works." },
        gnn: { ok: true, atom_acc: 0.90, note: "Main model keeps high atom accuracy." },
      },
    },
    {
      id: "d3",
      name: "Newer chemotype shift",
      smiles: "Cn1cc(C(=O)N2CCN(C(=O)COc3cccc4c3C(=O)N(C3CCC(=O)NC3=O)C4=O)CC2)c(-c2ccc(F)cc2)n1",
      note: "Time-like / newer ID style difficulty for classical cutters.",
      parts: { w: 16, l: 20, e: 18 },
      preds: {
        dictionary: { ok: true, atom_acc: 0.47, note: "Partial recipe coverage on newer set." },
        xgboost: { ok: true, atom_acc: 0.67, note: "Weaker on newer chemotypes." },
        gnn: { ok: true, atom_acc: 0.92, note: "Stronger generalization on newer IDs." },
      },
    },
  ],
};

window.pct = (x) => (100 * x).toFixed(1) + "%";
window.fmt = (x) => (x == null ? "—" : x.toFixed(3));
