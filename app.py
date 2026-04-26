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

        # ── File selection ────────────────────────────────────────────────
        file_frame = tk.Frame(self)
        file_frame.pack(fill="x", **pad)

        tk.Label(file_frame, text="File:").pack(side="left")
        self._file_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self._file_var, width=52).pack(
            side="left", padx=(6, 6)
        )
        tk.Button(file_frame, text="Browse…", command=self._browse).pack(side="left")

        # ── Output label ─────────────────────────────────────────────────
        self._out_label = tk.Label(self, text="Output: —", anchor="w", fg="gray")
        self._out_label.pack(fill="x", padx=12, pady=(0, 4))

        # ── Progress bar (shown only while processing) ───────────────────
        self._progress = ttk.Progressbar(self, length=480, mode="determinate")

        # ── Status line ──────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Select a PDF file to begin.")
        tk.Label(self, textvariable=self._status_var, anchor="w").pack(
            fill="x", padx=12
        )

        # ── Start button (hidden until file is chosen) ───────────────────
        self._start_btn = tk.Button(
            self, text="Start", width=16, command=self._on_btn
        )

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not path:
            return
        self._file_var.set(path)
        p = Path(path)
        out = p.parent / "marked" / p.name
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
        pdf_path = Path(self._file_var.get())
        if not pdf_path.is_file():
            self._status_var.set("Invalid file.")
            return

        import fitz
        try:
            page_count = len(fitz.open(str(pdf_path)))
        except Exception:
            self._status_var.set("Could not open PDF.")
            return

        self._start_btn.config(state="disabled")
        self._progress["value"] = 0
        self._progress["maximum"] = page_count
        self._progress.pack(padx=12, pady=6)

        threading.Thread(
            target=self._process, args=(pdf_path, page_count), daemon=True
        ).start()

    def _process(self, pdf_path: Path, total_pages: int):
        out_path = pdf_path.parent / "marked" / pdf_path.name
        out_path.parent.mkdir(exist_ok=True)

        error: str | None = None

        def on_progress(done: int, total: int):
            self.after(0, self._tick, done, total)

        try:
            mark_pdf(str(pdf_path), str(out_path), progress_cb=on_progress)
        except Exception as e:
            error = str(e)

        self.after(0, self._finish, total_pages, error)

    # ── UI helpers ───────────────────────────────────────────────────────────

    def _tick(self, done: int, total: int):
        self._progress["value"] = done
        self._status_var.set(f"Processing… page {done}/{total}")

    def _finish(self, total: int, error: str | None):
        self._progress.pack_forget()
        if error:
            self._status_var.set(f"Error: {error}")
            self._start_btn.config(state="normal", text="Start")
        else:
            self._status_var.set(f"Done. {total} page{'s' if total != 1 else ''} marked.")
            self._start_btn.config(state="normal", text="Done ✓")
        self._start_btn.pack(pady=(8, 12))


if __name__ == "__main__":
    App().mainloop()
