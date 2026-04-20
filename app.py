import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from main import mark_pdf


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Nikudot")
        self.resizable(False, False)
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # ── Folder selection ─────────────────────────────────────────────
        folder_frame = tk.Frame(self)
        folder_frame.pack(fill="x", **pad)

        tk.Label(folder_frame, text="Folder:").pack(side="left")
        self._folder_var = tk.StringVar()
        tk.Entry(folder_frame, textvariable=self._folder_var, width=52).pack(
            side="left", padx=(6, 6)
        )
        tk.Button(folder_frame, text="Browse…", command=self._browse).pack(side="left")

        # ── Output label ─────────────────────────────────────────────────
        self._out_label = tk.Label(self, text="Output: —", anchor="w", fg="gray")
        self._out_label.pack(fill="x", padx=12, pady=(0, 4))

        # ── Progress bar (shown only while processing) ───────────────────
        self._progress = ttk.Progressbar(self, length=480, mode="determinate")

        # ── Status line ──────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Select a folder to begin.")
        tk.Label(self, textvariable=self._status_var, anchor="w").pack(
            fill="x", padx=12
        )

        # ── Start button (hidden until folder is chosen) ─────────────────
        self._start_btn = tk.Button(
            self, text="Start", width=16, command=self._on_btn
        )

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self._folder_var.set(folder)
        out = Path(folder) / "marked"
        self._out_label.config(text=f"Output: {out}", fg="gray")
        self._status_var.set("Ready.")
        self._start_btn.config(text="Start", state="normal")
        self._start_btn.pack(pady=(8, 12))

    def _on_btn(self):
        if self._start_btn.cget("text") == "Done ✓":
            self.destroy()
        else:
            self._start()

    def _start(self):
        folder = Path(self._folder_var.get())
        if not folder.is_dir():
            self._status_var.set("Invalid folder.")
            return

        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            self._status_var.set("No PDF files found in that folder.")
            return

        self._start_btn.config(state="disabled")
        self._progress["value"] = 0
        self._progress["maximum"] = len(pdfs)
        self._progress.pack(padx=12, pady=6)

        threading.Thread(target=self._process, args=(folder, pdfs), daemon=True).start()

    def _process(self, folder: Path, pdfs: list[Path]):
        out_dir = folder / "marked"
        out_dir.mkdir(exist_ok=True)

        done = 0
        failed: list[Path] = []

        for pdf in pdfs:
            try:
                mark_pdf(str(pdf), str(out_dir / pdf.name))
            except Exception:
                failed.append(pdf)

            done += 1
            self.after(0, self._tick, done, len(pdfs), len(failed))

        if failed:
            err_dir = folder / "errors"
            err_dir.mkdir(exist_ok=True)
            for pdf in failed:
                shutil.copy2(pdf, err_dir / pdf.name)

        self.after(0, self._finish, done, failed)

    # ── UI helpers ───────────────────────────────────────────────────────────

    def _tick(self, done: int, total: int, errors: int):
        self._progress["value"] = done
        self._status_var.set(
            f"Processing… {done}/{total}"
            + (f"  ({errors} error{'s' if errors != 1 else ''})" if errors else "")
        )

    def _finish(self, total: int, failed: list[Path]):
        errors = len(failed)
        ok = total - errors
        self._progress.pack_forget()
        if errors:
            self._status_var.set(
                f"Done. {ok}/{total} marked.  "
                f"{errors} error{'s' if errors != 1 else ''} copied to errors/"
            )
        else:
            self._status_var.set(f"Done. {ok}/{total} files marked.")
        self._start_btn.config(state="normal", text="Done ✓")
        self._start_btn.pack(pady=(8, 12))


if __name__ == "__main__":
    App().mainloop()
