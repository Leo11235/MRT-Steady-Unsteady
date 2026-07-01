# MRT Steady-Unsteady Simulator — GUI (skeleton)

This is the skeleton of the desktop UI. It exists to prove the architecture
end-to-end before we invest in filling out every form.

What you can do with it today:

- Open the main menu (big **Steady** / **Unsteady** buttons).
- Navigate to either configuration page; see the side-bar action buttons and
  the placeholder form layout.
- Use **Browse saved results…** to pick a previously-saved unsteady simulation
  JSON and pop up the full matplotlib visualization
  (`display_unsteady_results`) on it.
- Use the **⌂ Home** button in the top-left of every non-main page to return.

What's deliberately *not* in yet:

- The Load Preset / Save Preset / Run Simulation buttons are wired to
  no-op "coming soon" dialogs.
- The Steady page shows three demo form rows; the full form follows after you
  approve the visual shape.
- The Unsteady page is a pure placeholder.
- No icons; the home button uses the `⌂` Unicode glyph.
- No threading around `display_unsteady_results` — while matplotlib windows
  are open the UI is briefly unresponsive. (Acceptable for the skeleton.)

---

## How to run the UI

From the project root (the folder that contains `src/`, `user_data/`, etc.):

```bash
# one-time install of GUI deps (skip if already done)
pip install -r src/ui/requirements-ui.txt

# launch
python -m src.ui.main
```

That's it. The window should appear within a second or two.

---

## How to build a standalone executable

PyInstaller bundles the Python interpreter, the simulator code, customtkinter,
matplotlib, numpy/scipy, and everything they pull in into one binary you can
double-click.

From the project root:

```bash
pyinstaller src/ui/build.spec
```

You'll find the result at `dist/MRT-Sim` (or `MRT-Sim.exe` on Windows).

**Cross-platform notes** (these *all* apply to every Python packager, not just
PyInstaller):

| Target OS | Where you have to run the build |
|---|---|
| Windows `.exe` | A Windows machine |
| macOS `.app`  | A macOS machine (and ideally code-sign + notarize for distribution) |
| Linux ELF     | A Linux machine (or WSL2) |

The same `pyinstaller src/ui/build.spec` command works on all three; only
the host OS changes. When we're ready to ship to multiple OSes from one
push, see the §"GitHub Actions" stub below.

---

## File layout

```
src/ui/
├── README.md                  ← this file
├── requirements-ui.txt        ← extra deps just for the GUI
├── build.spec                 ← PyInstaller config
├── main.py                    ← entry point — creates the AppShell
├── assets/                    ← (icons, theme JSON, etc — empty for now)
└── app/
    ├── theme.py               ← design tokens (colors, sizes, padding)
    ├── shell.py               ← persistent chrome + page stack
    ├── backend_bridge.py      ← thin wrapper around src.backend.*
    ├── widgets/               ← reusable widget classes (empty for now)
    └── pages/
        ├── main_menu.py
        ├── steady_page.py
        ├── unsteady_page.py
        └── results_browser.py
```

Adding a new page is:

1. Write a class in `app/pages/<name>.py` that extends `ctk.CTkFrame`,
   with a `TITLE` class attribute and a constructor `(master, on_navigate)`.
   Optionally define `on_show(self)` for per-show refresh logic.
2. Import it in `app/shell.py` and add it to the `PAGES` dict.

That's the entire navigation contract.

---

## GitHub Actions cross-OS build (future)

When we want Windows + Mac + Linux binaries built automatically on every
push, add a `.github/workflows/build.yml` that uses a matrix:

```yaml
strategy:
  matrix:
    os: [windows-latest, macos-latest, ubuntu-latest]
runs-on: ${{ matrix.os }}
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: '3.13' }
  - run: pip install -r requirements.txt -r src/ui/requirements-ui.txt
  - run: pyinstaller src/ui/build.spec
  - uses: actions/upload-artifact@v4
    with:
      name: MRT-Sim-${{ matrix.os }}
      path: dist/MRT-Sim*
```

About 30 minutes of one-time setup; after that every push produces three
downloadable binaries.

---

## Troubleshooting

**`ModuleNotFoundError: customtkinter`** — you skipped the
`pip install -r src/ui/requirements-ui.txt` step.

**Window opens then closes immediately** — usually a Python exception in a
page's `__init__`. Run from a terminal so you can see the traceback:
`python -m src.ui.main`.

**`display_unsteady_results` errors out** — the underlying analysis function
is unchanged from the simulator; verify it works in isolation by running
`python -m src.backend.unsteady.analysis.unsteady_results` and picking the
same file.

**Built `MRT-Sim.exe` says "Failed to load Python DLL" or similar** — usually a
mismatch between the Python you used to build and the Python on the target
machine. The binary embeds the interpreter, so this should not happen if you
build on the same machine you run on. If it does, rebuild with
`pyinstaller --clean src/ui/build.spec`.
