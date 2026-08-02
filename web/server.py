"""Yashi PROTAC segmentation web tool.

Run:
  conda activate yashi-protac
  cd Yashi/web
  python server.py

Then open http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from inference_engine import ENGINE, OUT, ROOT

WEB = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(WEB), static_url_path="")

_load_error = None
_loading = False


def _load_async():
    global _load_error, _loading
    _loading = True
    try:
        ENGINE.load()
        _load_error = None
    except Exception as e:
        _load_error = str(e)
    finally:
        _loading = False


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": ENGINE.status,
            "loading": _loading,
            "error": _load_error,
            "ready": ENGINE.ready,
        }
    )


@app.get("/api/metrics")
def metrics():
    path = OUT / "baselines_metrics.json"
    final = OUT / "final_results.json"
    data = {}
    if path.exists():
        data["baselines"] = json.loads(path.read_text(encoding="utf-8"))
    if final.exists():
        data["gnn"] = json.loads(final.read_text(encoding="utf-8"))
    return jsonify(data)


@app.post("/api/segment")
def segment():
    if _loading or ENGINE.status != "ready":
        return jsonify(
            {
                "ok": False,
                "error": _load_error or f"Models still loading ({ENGINE.status}). Retry shortly.",
            }
        ), 503
    body = request.get_json(force=True, silent=True) or {}
    smiles = (body.get("smiles") or "").strip()
    model = (body.get("model") or "gnn").strip().lower()
    if not smiles:
        return jsonify({"ok": False, "error": "Please paste a PROTAC SMILES."}), 400
    result = ENGINE.segment(smiles, model=model)
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


@app.get("/api/examples")
def examples():
    # A few usable demo SMILES from labeled set (short list)
    examples = [
        {
            "name": "Example PROTAC A",
            "smiles": "CC(C)(C)OC(=O)N1CCN(C(=O)COc2cccc3c2C(=O)N(C2CCC(=O)NC2=O)C3=O)CC1",
            "note": "Try with GNN first, then compare dictionary / XGBoost.",
        }
    ]
    try:
        import itertools

        records = [json.loads(l) for l in open(ROOT / "data" / "processed" / "labeled_protacs.jsonl")]
        picks = []
        for rec in itertools.islice(records, 0, None, max(len(records) // 5, 1)):
            picks.append(
                {
                    "name": f"PROTAC-DB id {rec.get('compound_id', '?')}",
                    "smiles": rec["smiles"],
                    "note": "From your labeled dataset",
                }
            )
            if len(picks) >= 4:
                break
        if picks:
            examples = picks
    except Exception:
        pass
    return jsonify({"examples": examples})


if __name__ == "__main__":
    threading.Thread(target=_load_async, daemon=True).start()
    print("Yashi segmentation tool")
    print("Open: http://127.0.0.1:5000")
    print("Models load in the background on first start...")
    app.run(host="127.0.0.1", port=5000, debug=False)
