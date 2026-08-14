#!/usr/bin/env python3
"""
A'levels Past Paper Downloader
==============================
Modern desktop GUI tool built with CustomTkinter for bulk-downloading 
CAIE AS & A Level past papers from PapaCambridge with organized directories.

Requirements:
    pip install customtkinter cloudscraper beautifulsoup4

Run:
    python alevel_downloader.py
"""

import os
import re
import sys
import queue
import threading
import subprocess
import tkinter as tk
from datetime import datetime
from urllib.parse import urljoin

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import cloudscraper
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit(
        "Missing dependencies. Install them first with:\n"
        "    pip install customtkinter cloudscraper beautifulsoup4"
    )


# --------------------------------------------------------------------------
# Resource Path Helper (PyInstaller & Dev Support)
# --------------------------------------------------------------------------
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# --------------------------------------------------------------------------
# Global CustomTkinter Configuration
# --------------------------------------------------------------------------
ctk.set_appearance_mode("Dark")       # Modes: "System", "Dark", "Light"
ctk.set_default_color_theme("blue")   # Themes: "blue", "green", "dark-blue"

# --------------------------------------------------------------------------
# Configuration & Constants
# --------------------------------------------------------------------------
PAPACAMBRIDGE_BASE = "https://pastpapers.papacambridge.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://pastpapers.papacambridge.com/"
}

REQUEST_TIMEOUT = 25
CURRENT_YEAR = datetime.now().year

CAIE_PAPER_REGEX = re.compile(
    r'(\d{4})[_\-]([a-z]\d{2})[_\-](qp|ms|er|gt|ci|in)(?:[_\-](\d+))?',
    re.IGNORECASE
)

SEASON_MAP = {
    's': 'Summer',  # May/June
    'w': 'Winter',  # Oct/Nov
    'm': 'Spring',  # Feb/March
}

DOC_FOLDER_MAP = {
    "qp": "Question Papers",
    "ms": "Mark Schemes",
    "er": "Examiner Reports",
    "gt": "Grade Thresholds",
    "ci": "Confidential Instructions",
    "in": "Inserts",
}

SUBJECTS = {
    "Mathematics": ("9709", "mathematics-9709"),
    "Physics": ("9702", "physics-9702"),
    "Chemistry": ("9701", "chemistry-9701"),
    "Biology": ("9700", "biology-9700"),
    "Economics": ("9708", "economics-9708"),
    "Business": ("9609", "business-9609"),
    "Accounting": ("9706", "accounting-9706"),
    "Computer Science": ("9618", "computer-science-9618"),
    "Psychology": ("9990", "psychology-9990"),
    "English Language": ("9093", "english-language-9093"),
    "Further Mathematics": ("9231", "further-mathematics-9231"),
}

DOC_TYPES = {
    "qp": "Question Papers (qp)",
    "ms": "Mark Schemes (ms)",
    "er": "Examiner Reports (er)",
    "gt": "Grade Thresholds (gt)",
    "ci": "Confidential Instructions (ci)",
    "in": "Inserts (in)",
}


# --------------------------------------------------------------------------
# Download Engine
# --------------------------------------------------------------------------
class DownloadWorker(threading.Thread):
    def __init__(self, jobs, dest_root, allowed_doc_types, log_queue, stop_event, progress_queue):
        super().__init__(daemon=True)
        self.jobs = jobs
        self.dest_root = dest_root
        self.allowed_doc_types = allowed_doc_types
        self.log_queue = log_queue
        self.stop_event = stop_event
        self.progress_queue = progress_queue

        self.session = cloudscraper.create_scraper()
        self.session.headers.update(HEADERS)

    def log(self, msg):
        self.log_queue.put(msg)

    def run(self):
        total_files = 0
        downloaded_files = 0
        failed_files = 0

        self.log(f"[*] Starting download across {len(self.jobs)} year task(s)...")

        for job_index, (subject_name, code, slug, year) in enumerate(self.jobs, start=1):
            if self.stop_event.is_set():
                self.log("[!] Operation cancelled by user.")
                break

            self.log(f"[{job_index}/{len(self.jobs)}] Scanning {subject_name} ({code}) - Year {year}...")
            
            subject_url = f"{PAPACAMBRIDGE_BASE}/papers/caie/as-and-a-level-{slug}"

            try:
                pdf_entries = self._get_papers_for_year(subject_url, code, year)
            except Exception as exc:
                self.log(f"  ! Error scanning {subject_name} {year}: {exc}")
                continue

            if not pdf_entries:
                self.log(f"  - No matching papers found for {year}.")
                continue

            subject_folder = f"{code}_{self._safe(subject_name)}"
            total_files += len(pdf_entries)

            for clean_filename, viewer_or_direct_url, doc_type, season_code in pdf_entries:
                if self.stop_event.is_set():
                    break

                season_folder = SEASON_MAP.get(season_code, "Other")
                doc_type_folder = DOC_FOLDER_MAP.get(doc_type, doc_type.upper())

                dest_dir = os.path.join(
                    self.dest_root,
                    subject_folder,
                    str(year),
                    season_folder,
                    doc_type_folder
                )
                os.makedirs(dest_dir, exist_ok=True)

                out_path = os.path.join(dest_dir, clean_filename)

                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    self.log(f"  [=] Exist: {season_folder}/{doc_type_folder}/{clean_filename}")
                    downloaded_files += 1
                    self.progress_queue.put((downloaded_files, failed_files, total_files))
                    continue

                download_url = self._resolve_pdf_url(viewer_or_direct_url)
                if not download_url:
                    failed_files += 1
                    self.log(f"  [!] Missing Link: {clean_filename}")
                    self.progress_queue.put((downloaded_files, failed_files, total_files))
                    continue

                ok = self._download_file(download_url, out_path)
                if ok:
                    downloaded_files += 1
                    self.log(f"  [+] Saved: {season_folder}/{doc_type_folder}/{clean_filename}")
                else:
                    failed_files += 1
                    self.log(f"  [!] Failed: {clean_filename}")

                self.progress_queue.put((downloaded_files, failed_files, total_files))

        self.log("=" * 60)
        self.log(f"Finished. Saved: {downloaded_files} | Failed/Skipped: {failed_files} | Total: {total_files}")
        self.log_queue.put("__DONE__")

    @staticmethod
    def _safe(name):
        return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

    def _parse_caie_filename(self, text, expected_code):
        match = CAIE_PAPER_REGEX.search(text)
        if not match:
            return None, None, None

        code, session, doc_type, component = match.groups()
        if code != expected_code:
            return None, None, None

        doc_type = doc_type.lower()
        if self.allowed_doc_types and doc_type not in self.allowed_doc_types:
            return None, None, None

        session = session.lower()
        if component:
            clean_name = f"{code}_{session}_{doc_type}_{component}.pdf"
        else:
            clean_name = f"{code}_{session}_{doc_type}.pdf"

        season_code = session[0]
        return clean_name, doc_type, season_code

    def _get_papers_for_year(self, subject_url, code, year):
        resp = self.session.get(subject_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        year_str = str(year)
        short_year = year_str[-2:]

        urls_to_scan = [subject_url]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if year_str in href or f"-{short_year}-" in href:
                full_url = urljoin(PAPACAMBRIDGE_BASE, href)
                if full_url not in urls_to_scan and not full_url.endswith(".pdf"):
                    urls_to_scan.append(full_url)

        found_entries = {}

        for scan_url in urls_to_scan:
            if self.stop_event.is_set():
                break

            try:
                if scan_url == subject_url:
                    page_soup = soup
                else:
                    r = self.session.get(scan_url, timeout=REQUEST_TIMEOUT)
                    if r.status_code != 200:
                        continue
                    page_soup = BeautifulSoup(r.text, "html.parser")

                for a in page_soup.find_all("a", href=True):
                    href = a["href"]
                    clean_name, doc_type, season_code = self._parse_caie_filename(href, code)
                    if not clean_name:
                        clean_name, doc_type, season_code = self._parse_caie_filename(a.text, code)

                    if clean_name:
                        session_part = clean_name.split("_")[1]
                        if session_part.endswith(short_year):
                            full_link = urljoin(PAPACAMBRIDGE_BASE, href)
                            found_entries[clean_name] = (full_link, doc_type, season_code)

            except Exception:
                continue

        return [(clean_name, meta[0], meta[1], meta[2]) for clean_name, meta in found_entries.items()]

    def _resolve_pdf_url(self, url):
        if url.endswith(".pdf") and "/viewer/" not in url:
            return url

        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            iframe = soup.find("iframe", src=True)
            if iframe and "pdf" in iframe["src"].lower():
                return urljoin(PAPACAMBRIDGE_BASE, iframe["src"])

            embed = soup.find("embed", src=True)
            if embed and "pdf" in embed["src"].lower():
                return urljoin(PAPACAMBRIDGE_BASE, embed["src"])

            matches = re.findall(r'https?://[^\s"\']+\.pdf', resp.text)
            if matches:
                return matches[0]

        except Exception:
            pass

        return None

    def _download_file(self, url, out_path):
        for attempt in range(2):
            if self.stop_event.is_set():
                return False
            try:
                with self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True) as r:
                    r.raise_for_status()
                    tmp_path = out_path + ".part"
                    with open(tmp_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if self.stop_event.is_set():
                                f.close()
                                if os.path.exists(tmp_path):
                                    os.remove(tmp_path)
                                return False
                            if chunk:
                                f.write(chunk)
                    os.replace(tmp_path, out_path)
                    return True
            except Exception:
                if attempt == 0:
                    continue
                return False
        return False


# --------------------------------------------------------------------------
# Custom Tkinter Desktop GUI
# --------------------------------------------------------------------------
class PastPaperApp(ctk.CTk):
    def __init__(self):
        # className replaces default "Tk" in OS window managers (e.g. GNOME top bar)
        super().__init__(className="A'levels Past Paper Downloader")

        self.title("A'levels Past Paper Downloader")
        self.geometry("1000x720")
        self.minsize(920, 650)

        # ------------------------------------------------------------------
        # Set Window Icon (stored on self._icon_img to prevent Garbage Collection)
        # ------------------------------------------------------------------
        icon_path = get_resource_path("icon.png")
        if os.path.exists(icon_path):
            try:
                self._icon_img = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self._icon_img)
            except Exception as e:
                print(f"[!] Could not load icon: {e}")

        self.stop_event = threading.Event()
        self.worker = None
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.subject_vars = {}
        self.doc_type_vars = {}

        self._build_layout()
        self._poll_queues()

    def _build_layout(self):
        # Header Banner
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="A'levels Past Paper Downloader",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="POWERED BY PAPACAMBRIDGE ENGINE",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#3b82f6"
        ).pack(anchor="w")

        # Central Split View (Grid)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=5)
        body.columnconfigure(0, weight=1, uniform="group1")
        body.columnconfigure(1, weight=1, uniform="group1")
        body.rowconfigure(0, weight=1)

        self._build_subject_panel(body)
        self._build_options_panel(body)

        # Bottom Section: Dashboard, Progress & Log
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(5, 15))
        self._build_dashboard_and_log(bottom)

    def _build_subject_panel(self, parent):
        panel = ctk.CTkFrame(parent, corner_radius=10)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(
            panel, text="Select Subjects", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(12, 6))

        # Search Bar
        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.pack(fill="x", padx=15, pady=(0, 8))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_subject_list())
        
        entry = ctk.CTkEntry(search_row, placeholder_text="Search subjects or codes...", textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)

        # Quick Selection Buttons
        select_row = ctk.CTkFrame(panel, fg_color="transparent")
        select_row.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkButton(
            select_row, text="Select All", width=80, height=26,
            fg_color="#334155", hover_color="#475569",
            command=lambda: self._set_all_visible(True)
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            select_row, text="Clear", width=60, height=26,
            fg_color="#334155", hover_color="#475569",
            command=lambda: self._set_all_visible(False)
        ).pack(side="left")

        # Scrollable Subjects List
        self.subj_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.subj_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for name in SUBJECTS:
            self.subject_vars[name] = ctk.BooleanVar(value=False)

        self._refresh_subject_list()

    def _refresh_subject_list(self):
        for child in self.subj_scroll.winfo_children():
            child.destroy()

        query = self.search_var.get().strip().lower()
        for name, (code, slug) in SUBJECTS.items():
            if query and query not in name.lower() and query not in code:
                continue

            row = ctk.CTkFrame(self.subj_scroll, fg_color="#1e293b", corner_radius=6)
            row.pack(fill="x", pady=2)

            # Code Badge
            badge = ctk.CTkLabel(
                row, text=code, fg_color="#3b82f6", text_color="#ffffff",
                corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"),
                width=42, height=20
            )
            badge.pack(side="left", padx=8, pady=6)

            cb = ctk.CTkCheckBox(row, text=name, variable=self.subject_vars[name])
            cb.pack(side="left", padx=4, pady=6)

    def _set_all_visible(self, value):
        query = self.search_var.get().strip().lower()
        for name, (code, slug) in SUBJECTS.items():
            if not query or query in name.lower() or query in code:
                self.subject_vars[name].set(value)

    def _build_options_panel(self, parent):
        panel = ctk.CTkFrame(parent, corner_radius=10)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(
            panel, text="Download Configuration", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(12, 10))

        # Year Range
        ctk.CTkLabel(panel, text="Year Range", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(4, 2))
        
        year_row = ctk.CTkFrame(panel, fg_color="transparent")
        year_row.pack(fill="x", padx=15, pady=(0, 12))

        years = [str(y) for y in range(CURRENT_YEAR, CURRENT_YEAR - 21, -1)]
        self.year_from_var = ctk.StringVar(value="2022")
        self.year_to_var = ctk.StringVar(value=str(CURRENT_YEAR))

        ctk.CTkLabel(year_row, text="From", text_color="#94a3b8").pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(year_row, values=years, variable=self.year_from_var, width=90).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(year_row, text="To", text_color="#94a3b8").pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(year_row, values=years, variable=self.year_to_var, width=90).pack(side="left")

        # Document Types
        ctk.CTkLabel(panel, text="Document Types", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(4, 2))
        
        doc_card = ctk.CTkFrame(panel, fg_color="#1e293b", corner_radius=8)
        doc_card.pack(fill="x", padx=15, pady=(0, 12))

        for code, label in DOC_TYPES.items():
            var = ctk.BooleanVar(value=code in ("qp", "ms", "er", "in"))
            self.doc_type_vars[code] = var
            cb = ctk.CTkCheckBox(doc_card, text=label, variable=var)
            cb.pack(anchor="w", padx=10, pady=5)

        # Output Folder
        ctk.CTkLabel(panel, text="Save Destination", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(4, 2))
        
        dest_row = ctk.CTkFrame(panel, fg_color="transparent")
        dest_row.pack(fill="x", padx=15, pady=(0, 10))

        default_dir = os.path.join(os.path.expanduser("~"), "ALevelPastPapers")
        self.dest_var = ctk.StringVar(value=default_dir)

        ctk.CTkEntry(dest_row, textvariable=self.dest_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            dest_row, text="Browse", width=70, fg_color="#334155", hover_color="#475569",
            command=self._browse_dest
        ).pack(side="left")

    def _browse_dest(self):
        # Attempt GTK/Zenity dialog first on Linux systems for native GTK folder picker
        try:
            cmd = ["zenity", "--file-selection", "--directory", "--title=Select Download Directory"]
            chosen = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
            if chosen:
                self.dest_var.set(chosen)
                return
        except Exception:
            pass  # Fallback if Zenity isn't installed or running on non-Linux OS

        # Standard Fallback
        chosen = filedialog.askdirectory()
        if chosen:
            self.dest_var.set(chosen)

    def _build_dashboard_and_log(self, parent):
        # Action Bar & Counters
        control_card = ctk.CTkFrame(parent, corner_radius=10)
        control_card.pack(fill="x", pady=(0, 8))

        c_inner = ctk.CTkFrame(control_card, fg_color="transparent")
        c_inner.pack(fill="x", padx=12, pady=10)

        # Buttons
        self.start_btn = ctk.CTkButton(
            c_inner, text="▶  START DOWNLOAD", font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10b981", hover_color="#059669", height=36,
            command=self._start
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            c_inner, text="■  STOP", font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#ef4444", hover_color="#dc2626", height=36, width=80,
            state="disabled", command=self._stop
        )
        self.stop_btn.pack(side="left")

        # Stats Counters
        stats_box = ctk.CTkFrame(c_inner, fg_color="transparent")
        stats_box.pack(side="right")

        self.lbl_saved = self._stat_badge(stats_box, "SAVED", "0", "#10b981")
        self.lbl_failed = self._stat_badge(stats_box, "FAILED/SKIPPED", "0", "#ef4444")
        self.lbl_total = self._stat_badge(stats_box, "QUEUED", "0", "#3b82f6")

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(parent, height=14)
        self.progress_bar.pack(fill="x", pady=(0, 8))
        self.progress_bar.set(0)

        # Log Box
        self.log_text = ctk.CTkTextbox(
            parent, height=110, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#070a12", text_color="#38bdf8", corner_radius=8
        )
        self.log_text.pack(fill="x")
        self.log_text.configure(state="disabled")

    def _stat_badge(self, parent, title, value, color):
        card = ctk.CTkFrame(parent, fg_color="#1e293b", corner_radius=6, width=90)
        card.pack(side="left", padx=4)

        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=8, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=6, pady=(3, 0))
        lbl = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=13, weight="bold"), text_color=color)
        lbl.pack(anchor="w", padx=6, pady=(0, 3))
        return lbl

    def _selected_subjects(self):
        return [(name, SUBJECTS[name][0], SUBJECTS[name][1]) for name, var in self.subject_vars.items() if var.get()]

    def _selected_doc_types(self):
        return {code for code, var in self.doc_type_vars.items() if var.get()}

    def _start(self):
        subjects = self._selected_subjects()
        if not subjects:
            messagebox.showwarning("No subjects selected", "Please select at least one subject from the list.")
            return

        try:
            y_from = int(self.year_from_var.get())
            y_to = int(self.year_to_var.get())
        except ValueError:
            messagebox.showerror("Invalid year", "Please choose valid years.")
            return

        if y_from > y_to:
            y_from, y_to = y_to, y_from
        years = list(range(y_from, y_to + 1))

        dest_root = self.dest_var.get().strip()
        if not dest_root:
            messagebox.showwarning("No destination", "Please choose a target folder.")
            return
        os.makedirs(dest_root, exist_ok=True)

        allowed_doc_types = self._selected_doc_types()

        jobs = []
        for name, code, slug in subjects:
            for year in years:
                jobs.append((name, code, slug, year))

        self.stop_event.clear()
        self._clear_log()
        self._log_line(f"[*] Queued {len(jobs)} year task(s) to scan...")
        self.progress_bar.set(0)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.lbl_saved.configure(text="0")
        self.lbl_failed.configure(text="0")
        self.lbl_total.configure(text="0")

        self.worker = DownloadWorker(jobs, dest_root, allowed_doc_types, self.log_queue, self.stop_event, self.progress_queue)
        self.worker.start()

    def _stop(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.stop_btn.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _log_line(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queues(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "__DONE__":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                else:
                    self._log_line(msg)
        except queue.Empty:
            pass

        try:
            while True:
                saved, failed, total = self.progress_queue.get_nowait()
                self.lbl_saved.configure(text=str(saved))
                self.lbl_failed.configure(text=str(failed))
                self.lbl_total.configure(text=str(total))
                if total > 0:
                    self.progress_bar.set((saved + failed) / total)
        except queue.Empty:
            pass

        self.after(100, self._poll_queues)


if __name__ == "__main__":
    app = PastPaperApp()
    app.mainloop()
