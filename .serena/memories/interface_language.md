# Interface language (added 2026-11-07)
- Source strings in code stay Turkish (keys). mangaeditor/i18n.py: tr(text, **values) returns the English text from mangaeditor/translations.py EN when the language is 'en'; Turkish otherwise. A missing key falls back to Turkish.
- Language: QSettings 'language' ('tr' or 'en'); default from QLocale (tr_* gives Turkish, otherwise English), set in app.main via i18n.init(QSettings()). Changed in Settings -> Dil / Language; applied after restart.
- Every user-visible literal must be wrapped in tr() and added to EN. tests/test_i18n.py enforces this (AST scan of tr() and main_window act() literals, ShortcutDef labels, TOOL_LABELS), checks placeholders and stale keys, and checks that the English window shows no Turkish text.
- Undo labels: commands.py wraps labels with tr() in the constructors. File dialog filters: tr(INPUT_FILTER)/tr(FONT_FILTER) at call time.
- The brand name 'Manga Editör' is intentionally not translated.
- Comments and docstrings in code and tests are English.