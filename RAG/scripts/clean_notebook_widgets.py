"""Strip un-renderable ipywidgets output from executed notebooks.

Why this is needed
------------------
`sentence-transformers` calls `.encode(show_progress_bar=True)`, and Hugging Face
shows a "Loading weights" bar. Both use tqdm, which renders through *ipywidgets*
inside Jupyter. When a notebook is executed headlessly (`jupyter nbconvert
--execute`), each bar is saved as an `application/vnd.jupyter.widget-view+json`
output that only points at a live widget model -- the model state itself is not
saved. Any viewer opening the file later has nothing to render and shows:

    Could not render content for 'application/vnd.jupyter.widget-view+json'

It is cosmetic: no code failed, and nothing is missing from the results.

What this script does
---------------------
Every such output also carries a `text/plain` fallback (e.g.
"Batches: 0%| | 0/1"). This script drops only the widget MIME entry and the
notebook-level `metadata.widgets` block, keeping that fallback, so viewers show a
harmless one-line progress string instead of an error. The notebook code is left
untouched, so running it live in Jupyter still shows real animated progress bars.

Run it after any `nbconvert --execute`, from the RAG folder:

    python scripts/clean_notebook_widgets.py
"""

import json
from pathlib import Path

WIDGET_MIME = "application/vnd.jupyter.widget-view+json"
NOTEBOOK_DIR = Path(__file__).resolve().parent.parent / "notebooks"


def clean_notebook(path: Path) -> tuple[int, bool]:
    """Remove widget outputs from one notebook, saving only if something changed.

    Returns
    -------
    (outputs_cleaned, metadata_removed)
    """
    nb = json.loads(path.read_text(encoding="utf-8"))
    cleaned = 0

    for cell in nb.get("cells", []):
        kept_outputs = []
        for output in cell.get("outputs", []):
            data = output.get("data")
            if isinstance(data, dict) and WIDGET_MIME in data:
                del data[WIDGET_MIME]
                cleaned += 1
                # An output with no data left has nothing to show at all.
                if not data:
                    continue
            kept_outputs.append(output)
        if "outputs" in cell:
            cell["outputs"] = kept_outputs

    metadata_removed = nb.get("metadata", {}).pop("widgets", None) is not None

    if cleaned or metadata_removed:
        # newline at EOF keeps the file git-friendly
        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return cleaned, metadata_removed


if __name__ == "__main__":
    total = 0
    for notebook in sorted(NOTEBOOK_DIR.glob("*.ipynb")):
        cleaned, meta = clean_notebook(notebook)
        total += cleaned
        state = "unchanged" if not (cleaned or meta) else (
            f"removed {cleaned} widget output(s)"
            + (", dropped metadata.widgets" if meta else "")
        )
        print(f"{notebook.name}: {state}")
    print(f"\nDone. {total} widget output(s) removed in total.")
