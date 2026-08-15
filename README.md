# A'levels Past Paper Downloader

A modern desktop GUI tool for bulk-downloading CAIE (Cambridge International) AS & A Level past papers from [PapaCambridge](https://pastpapers.papacambridge.com), with results automatically sorted into clean, organized folders.

Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for a clean, modern dark-themed interface.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- 🎨 **Modern dark UI** — built with CustomTkinter, not a bare Tkinter window
- 📚 **11 built-in subjects** — Mathematics, Physics, Chemistry, Biology, Economics, Business, Accounting, Computer Science, Psychology, English Language, Further Mathematics
- 🔍 **Searchable subject list** with quick "Select All" / "Clear" controls
- 📅 **Year range selection** — pick any span of exam years to download
- 📄 **Document type filters** — Question Papers, Mark Schemes, Examiner Reports, Grade Thresholds, Confidential Instructions, and Inserts
- 📁 **Automatic organization** — files are saved into a clean hierarchy:
  ```
  <destination>/
    └── <subject_code>_<subject_name>/
        └── <year>/
            └── <Season>/
                └── <Document Type>/
                    └── <code>_<session>_<type>_<component>.pdf
  ```
- ⏸️ **Start/Stop controls** with a live log and progress bar
- ♻️ **Skips already-downloaded files** so you can safely re-run a job
- 🛡️ Uses `cloudscraper` to get past basic anti-bot protection on the source site

## Requirements

- Python 3.8+
- [`customtkinter`](https://pypi.org/project/customtkinter/)
- [`cloudscraper`](https://pypi.org/project/cloudscraper/)
- [`beautifulsoup4`](https://pypi.org/project/beautifulsoup4/)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/zaydbhai/alevels-past-paper-downloader.git
   cd alevels-past-paper-downloader
   ```

2. Install the dependencies:
   ```bash
   pip install customtkinter cloudscraper beautifulsoup4
   ```

## Usage

Run the application:

```bash
python alevel_downloader.py
```

Then, in the GUI:

1. **Select subjects** — search or scroll the subject list and tick the ones you want.
2. **Set the year range** — choose a "From" and "To" year.
3. **Choose document types** — Question Papers, Mark Schemes, and Examiner Reports/Inserts are selected by default.
4. **Pick a save destination** — defaults to `~/ALevelPastPapers`, or browse for a custom folder.
5. Click **▶ START DOWNLOAD** to begin. Progress, live logs, and saved/failed/queued counts appear at the bottom.
6. Click **■ STOP** at any time to cancel an in-progress download safely.

## How it works

For each selected subject and year, the tool:

1. Scrapes the subject's PapaCambridge listing page (and related linked pages) for that year.
2. Parses file/link names against the standard CAIE naming pattern (e.g. `9709_s22_qp_11.pdf`) to identify subject code, session (summer/winter/spring), document type, and component number.
3. Resolves the actual PDF download link (following viewer/iframe pages where needed).
4. Downloads the file into the correct `subject/year/season/document-type` folder, skipping files that already exist.

## Supported Subjects

| Subject | Code |
|---|---|
| Mathematics | 9709 |
| Physics | 9702 |
| Chemistry | 9701 |
| Biology | 9700 |
| Economics | 9708 |
| Business | 9609 |
| Accounting | 9706 |
| Computer Science | 9618 |
| Psychology | 9990 |
| English Language | 9093 |
| Further Mathematics | 9231 |

## Disclaimer

This tool downloads publicly available past papers hosted on PapaCambridge for personal study and educational use. It is not affiliated with Cambridge Assessment International Education (CAIE) or PapaCambridge. Please respect the source website's terms of service and use responsibly.

## License

This project is licensed under the MIT License.
