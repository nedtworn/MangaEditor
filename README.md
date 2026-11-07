# Manga Editör

A simple, fast desktop app for Windows for manga translation and editing: clean up the
original text, add new text (including Turkish), merge the page, export the result.

The interface is available in **English** and **Turkish**. On first start it follows the
Windows language; you can change it in **Settings → Dil / Language…** (the change applies
after a restart).

## Running it

```powershell
# Development
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py            # or: run.py <project folder>

# Standalone application (dist\MangaEditor\MangaEditor.exe)
powershell -ExecutionPolicy Bypass -File build.ps1

# Tests
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests
```

## Usage

1. **New Project** (Ctrl+N): choose a name and a location.
2. **Add Pages** or drag images into the window (PNG, JPG, JPEG, WEBP). The images are copied
   into the project folder; the originals are never modified.
3. **Brush (B)** paints over the original text. **Eyedropper (I)**, or **Alt+click** with the
   brush, picks the color of the single pixel under the cursor. The eyedropper stays selected
   after a pick, so you can try as many points as you like. **Eraser (E)** removes paint and
   reveals the original again.
4. **Clone Stamp (S)**: hold **K** and click a clean area. The source is selected and nothing
   is painted; it is shown as a turquoise cross with a small ring. Release the key and click or
   drag on the target to copy the source pixels exactly. Two modes are available in the panel
   (the choice is remembered; the default is Aligned):
   - **Aligned:** the source-target distance is fixed at the first press and kept between
     strokes; the source marker moves with the cursor.
   - **Non-aligned:** when you pick the source, a square area of the current brush size is
     fixed (its position and content). While painting, the target is tiled with copies of
     this area like a pattern. The same target pixel always gets the same source pixel, so
     there is no shifting, stretching or seams, even when you paint without releasing the
     mouse. Nothing outside the area is read. Picking a new source with K+click replaces it.
   The brush size only sets how much of the target is painted; it does not change the source
   point, the relationship or the source area. `[` and `]` change the size.
5. **Text (Ctrl+T)**: click a speech bubble (the clicked point becomes the center of the box),
   or drag a box, then type. Enter inserts a manual line break; long lines wrap automatically.
   Words are never split: a word that does not fit moves whole to the next line, and a single
   word wider than the box overflows it. Move the box, resize it with the handles, rotate it
   with the round handle (Shift: 15° steps). The side panel sets the font, size, color,
   alignment, spacing, outline, shadow and background. **Load Font** adds a TTF/OTF font and
   copies it into the project's `fonts/` folder.
6. **Merge Page** (Ctrl+M): flattens all texts and the paint of the page into one layer; the
   brush and eraser then also work on the former texts. Undo with Ctrl+Z.
7. **Export** (Ctrl+E): choose pages, PNG (lossless) or JPG (with a quality setting).

## Shortcuts

| Shortcut | Action | Shortcut | Action |
|---|---|---|---|
| Ctrl+N | New project | B | Brush |
| Ctrl+O | Open project | E | Eraser |
| Ctrl+S | Save | I | Eyedropper |
| Ctrl+Z / Ctrl+Y | Undo / Redo | Ctrl+T | Text tool |
| Ctrl+M | Merge page | S | Clone stamp |
| Ctrl+E | Export | K (hold) + click | Pick clone source |
| Ctrl+0 / Ctrl+1 | Fit / 100% | Space + drag | Pan the canvas (middle button works too) |
| Enter (text selected) | Edit text | Mouse wheel | Zoom |
| Delete / Backspace | Delete selected text | [ and ] | Brush / eraser / clone size |
| Esc | Finish editing | Double-click | Edit text |

While editing text, the single-letter shortcuts (B, E, I, S, Space, K…) are typed into the
text and do not change the tool. Ctrl+A/C/X/V/Z/Y, the arrow keys and Home/End always go to
the text.

### Customizing shortcuts (Settings → Shortcuts…)

All shortcuts (menus, tools, canvas keys) are managed from one place
(`mangaeditor/ui/shortcuts.py`). Click the shortcut of an action in the window and press the new
combination, for example `Ctrl+F`, `Shift+E`, `Ctrl+Shift+S`, `Alt+1` or `Ctrl+Alt+Z`. While
capturing, the border turns orange and the held modifiers are shown; **Esc** cancels. Ctrl, Shift
or Alt alone, and Esc, cannot be assigned.
**The same shortcut cannot be assigned to two actions**: on a conflict the message names the
other action, nothing is assigned and the current shortcut stays. ↺ resets one action; **Reset
to Defaults** resets all. Assignments are saved. Hold keys (Space for panning, K for the clone
source) must be single keys. Actions without a shortcut (Add Pages, Remove Page, …) can also get one.

## Project folder

```
My Chapter/
  project.json   page order, texts (with all their styling), page information
  originals/     the copied original images (read-only in practice)
  pages/         the paint layer of each page (<page-id>.png, transparent)
  fonts/         fonts added to the project
  exports/       default export folder
  .recovery/     recovery copy of unsaved changes (deleted on save)
```

The folder can be moved to another computer as it is.

**Saving:** Ctrl+S (and "Save" when closing) saves the project data **and** writes the edited
image of every page changed since the last save to that page's *save target*. The default target
is the source file that was chosen when the page was added, so it is overwritten; the real
original is kept under `originals/`, so erasing and undo are not affected. The target can be
changed by right-clicking the tab and choosing **Change Save Target…**. Safety rules: the project
files (`originals/`, `pages/`, `fonts/`, `project.json`) are never overwritten, two pages cannot
share a target, and a target in a missing folder is not written. If an image cannot be written,
the project data is still saved, a warning is shown and that page is retried on the next save.
If the same source is added twice, the second page writes to `exports/`.

Autosave (can be turned off in the File menu) saves only the project data every 3 minutes and
never overwrites the source images. A recovery copy is written every 30 seconds; when a project
opens after an unexpected shutdown, recovery is offered. Tabs of pages with unsaved changes, or
with an image not yet written, show a **●**. **Export** (Ctrl+E) writes PNG/JPG files to any folder.

## Architecture

```
mangaeditor/core   the data model and operations, independent of the UI (no widgets)
  page.py          page: original (read-only) + paint layer + texts + its own undo stack
  text_data.py     immutable text data
  text_layout.py   line wrapping and drawing (canvas, merge and export use the same code)
  stroke.py        brush / eraser;  clone.py  clone stamp;  commands.py  undoable operations
  compose.py       layer composition;  export.py  export
  project.py       folder-based project, save / open, recovery;  fonts.py  TTF/OTF
mangaeditor/ui     the view: canvas, scene, text box, panels, main window
  shortcuts.py     central shortcut registry (assignment, conflicts, saving)
  shortcuts_dialog.py  Settings → Shortcuts window
mangaeditor/i18n.py  interface language (tr() looks up translations.EN)
mangaeditor/translations.py  English translations of the interface texts
```

Source strings in the code are Turkish; `i18n.tr("...")` returns the English text when the
language is English. To add a text, wrap it with `tr(...)` and add its English translation to
`mangaeditor/translations.py`. `tests/test_i18n.py` checks that every such string has a translation.
