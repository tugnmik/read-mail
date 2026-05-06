"""
UI don gian de doc inbox Hotmail/Outlook tu refresh_token.

Input moi dong:
email|password|refresh_token|client_id
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from read_mail_from_refresh import (
    exchange_refresh_token,
    parse_input_lines,
    read_latest_subjects,
)


class ReadMailApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Doc Inbox Outlook tu Refresh Token")
        self.geometry("980x620")

        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._rows: list[dict] = []

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Nhap du lieu (email|pass|refresh_token|client_id):").pack(anchor="w")
        self.txt_input = scrolledtext.ScrolledText(top, height=8, font=("Consolas", 9))
        self.txt_input.pack(fill="x", pady=(4, 0))

        bar = ttk.Frame(self, padding=(8, 2))
        bar.pack(fill="x")

        ttk.Button(bar, text="Import TXT", command=self._import_txt).pack(side="left", padx=(0, 8))

        ttk.Label(bar, text="So mail moi nhat:").pack(side="left")
        self.spin_limit = tk.Spinbox(bar, from_=1, to=50, width=5)
        self.spin_limit.delete(0, "end")
        self.spin_limit.insert(0, "5")
        self.spin_limit.pack(side="left", padx=(6, 12))

        self.btn_run = ttk.Button(bar, text="Doc Inbox", command=self._start)
        self.btn_run.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(bar, text="Dung", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))

        ttk.Button(bar, text="Xoa ket qua", command=self._clear_results).pack(side="left")

        self.lbl_status = ttk.Label(bar, text="San sang")
        self.lbl_status.pack(side="right")

        middle = ttk.Frame(self, padding=(8, 2))
        middle.pack(fill="both", expand=True)

        cols = ("email", "status", "subjects")
        self.tree = ttk.Treeview(middle, columns=cols, show="headings")
        self.tree.heading("email", text="Email")
        self.tree.heading("status", text="Status")
        self.tree.heading("subjects", text="Subjects")

        self.tree.column("email", width=220, minwidth=120)
        self.tree.column("status", width=160, minwidth=100)
        self.tree.column("subjects", width=560, minwidth=200)

        y_scroll = ttk.Scrollbar(middle, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(middle, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=y_scroll.set, xscroll=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        middle.rowconfigure(0, weight=1)
        middle.columnconfigure(0, weight=1)

        bottom = ttk.Frame(self, padding=(8, 2, 8, 8))
        bottom.pack(fill="x")

        ttk.Label(bottom, text="Log:").pack(anchor="w")
        self.txt_log = scrolledtext.ScrolledText(bottom, height=7, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="x")

    def _log(self, msg: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _import_txt(self):
        path = filedialog.askopenfilename(
            title="Chon file txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().strip()
            self.txt_input.delete("1.0", "end")
            self.txt_input.insert("1.0", content)
            self._log(f"Da import file: {path}")
        except Exception as exc:
            messagebox.showerror("Loi", str(exc))

    def _clear_results(self):
        self._rows.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._log("Da xoa ket qua")

    def _start(self):
        raw = self.txt_input.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("Canh bao", "Ban chua nhap du lieu")
            return

        accounts = parse_input_lines(raw)
        if not accounts:
            messagebox.showwarning("Canh bao", "Khong co dong hop le")
            return

        try:
            limit = int(self.spin_limit.get())
        except ValueError:
            limit = 5
        limit = max(1, limit)

        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status.configure(text=f"Dang chay {len(accounts)} account...")

        self._clear_results()
        t = threading.Thread(target=self._worker, args=(accounts, limit), daemon=True)
        t.start()

    def _stop(self):
        self._running = False
        self.lbl_status.configure(text="Dang dung...")

    def _worker(self, accounts: list[dict], limit: int):
        total = len(accounts)
        for idx, acc in enumerate(accounts, start=1):
            if not self._running:
                self._queue.put(("log", "Da dung boi nguoi dung"))
                break

            email = acc["email"]
            self._queue.put(("log", f"[{idx}/{total}] Dang xu ly {email}"))

            ok_token, token_or_err = exchange_refresh_token(acc["refresh_token"], acc["client_id"])
            if not ok_token:
                self._queue.put(("row", email, "FAIL token", token_or_err))
                continue

            ok_read, data_or_err = read_latest_subjects(email, token_or_err, limit=limit)
            if not ok_read:
                self._queue.put(("row", email, "FAIL inbox", data_or_err))
                continue

            subjects = " | ".join(data_or_err)
            self._queue.put(("row", email, "OK", subjects))

        self._queue.put(("done",))

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                cmd = msg[0]

                if cmd == "log":
                    self._log(msg[1])
                elif cmd == "row":
                    _, email, status, subjects = msg
                    self.tree.insert("", "end", values=(email, status, subjects))
                elif cmd == "done":
                    self._running = False
                    self.btn_run.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.lbl_status.configure(text="Hoan thanh")
                    self._log("Xong")
        except queue.Empty:
            pass

        self.after(100, self._poll_queue)


if __name__ == "__main__":
    app = ReadMailApp()
    app.mainloop()
