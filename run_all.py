"""Re-execute every notebook in order using the yashi-protac env if available."""

import shutil
import subprocess
import sys
from pathlib import Path

NB_DIR = Path(__file__).parent / "notebooks"
NOTEBOOKS = sorted(NB_DIR.glob("0?_*.ipynb"))


def python_exe() -> str:
    """Prefer conda env yashi-protac; else current interpreter."""
    conda = shutil.which("conda")
    if conda:
        try:
            out = subprocess.check_output(
                ["conda", "run", "-n", "yashi-protac", "python", "-c",
                 "import sys; print(sys.executable)"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip().splitlines()[-1]
            if out and Path(out).exists():
                return out
        except Exception:
            pass
    return sys.executable


def main() -> int:
    py = python_exe()
    print("using Python:", py)
    for nb in NOTEBOOKS:
        print(f"\n>>> executing {nb.name}")
        r = subprocess.run([
            py, "-m", "jupyter", "nbconvert",
            "--to", "notebook", "--execute", "--inplace",
            "--ExecutePreprocessor.kernel_name=yashi-protac",
            "--ExecutePreprocessor.timeout=3600",
            str(nb),
        ])
        if r.returncode != 0:
            print(f"!!! {nb.name} failed")
            return r.returncode
    print("\nall notebooks completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
