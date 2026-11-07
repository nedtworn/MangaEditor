# Graph Report - MangaEditor  (2026-11-07)

## Corpus Check
- 52 files · ~40,018 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 1277 nodes · 3282 edges · 108 communities (29 shown, 79 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 262 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- pyside6_qtgui
- main_window.py
- CanvasView
- ._build_actions
- ChangeTextCommand
- Text Layout Engine
- Project Persistence
- StrokeSession
- test_v3_clone_core.py
- ExportDialog
- test_phase3_text_ui.py
- test_v3_eyedropper.py
- Misc 8
- TextData
- test_v3_clone_ui.py
- MainWindow
- test_v5_fixed_source_area.py
- TextLayout
- test_v3_shortcuts.py
- app.py
- test_v2_save_output.py
- PageDocument
- project.yml
- ShortcutRegistry
- TextData
- event_sequences
- pyside6_qtgui
- ShortcutCaptureButton
- open_window
- PageScene
- SidePanel
- conftest.py
- test_phase2_tools.py
- ShortcutRegistry
- text_layout.py
- portable
- .__init__
- Manga Editör
- SliderSpin
- .capture_button
- .install
- ToolSettings
- architecture_overview.md
- test_phase8_ui.py
- ColorButton
- ClonePanel
- sources
- shortcuts.py
- test_no_hard_coded_shortcuts_left_in_ui_code

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 96 edges
2. `PageDocument` - 73 edges
3. `CanvasView` - 61 edges
4. `Tool` - 59 edges
5. `TextData` - 59 edges
6. `open_window()` - 51 edges
7. `Project` - 50 edges
8. `TextItemView` - 49 edges
9. `compose_page()` - 45 edges
10. `ShortcutRegistry` - 38 edges

## Surprising Connections (you probably didn't know these)
- `test_bracket_keys_change_size()` --uses--> `Tool`  [INFERRED]
  tests/test_phase2_tools.py → mangaeditor/ui/tools.py
- `test_required_shortcuts_exist_and_do_not_conflict()` --uses--> `Tool`  [INFERRED]
  tests/test_phase8_ui.py → mangaeditor/ui/tools.py
- `test_space_types_while_editing_but_pans_otherwise()` --uses--> `Tool`  [INFERRED]
  tests/test_phase8_ui.py → mangaeditor/ui/tools.py
- `test_typing_in_panel_field_does_not_switch_tools()` --uses--> `Tool`  [INFERRED]
  tests/test_phase8_ui.py → mangaeditor/ui/tools.py
- `test_clone_tool_in_toolbar_and_shortcut()` --uses--> `Tool`  [INFERRED]
  tests/test_v3_clone_ui.py → mangaeditor/ui/tools.py

## Import Cycles
- None detected.

## Communities (108 total, 79 thin omitted)

### Community 1 - "main_window.py"
Cohesion: 0.11
Nodes (7): FontLoadError, export_filename(), export_pages(), is_supported_input(), save_image_atomic(), _safe_stem(), _write_json_atomic()

### Community 3 - "._build_actions"
Cohesion: 0.27
Nodes (7): brush_icon(), _canvas(), clone_icon(), eraser_icon(), eyedropper_icon(), _pen(), text_icon()

### Community 8 - "StrokeSession"
Cohesion: 0.17
Nodes (6): StrokeSession, stroke(), test_paint_and_erase_on_merged_text(), paint(), test_dirty_marker_on_tabs(), window()

### Community 10 - "test_v3_clone_core.py"
Cohesion: 0.16
Nodes (15): dist_to_segment(), page(), painted_count(), pattern(), rgb(), run(), test_brush_size_controls_width(), test_destination_outside_image_is_clipped_safely() (+7 more)

### Community 15 - "ExportDialog"
Cohesion: 0.16
Nodes (3): default_projects_dir(), ExportDialog, NewProjectDialog

### Community 16 - "test_phase3_text_ui.py"
Cohesion: 0.09
Nodes (19): FontManager, make_otf(), create_text(), drag(), handle_view_pos(), test_brush_does_not_touch_texts(), test_create_text_by_typing_and_shortcuts_do_not_fire(), test_editing_backspace_and_inline_undo() (+11 more)

### Community 18 - "test_v3_eyedropper.py"
Cohesion: 0.13
Nodes (13): sample_color(), click(), gradient_page(), rgb(), test_alt_click_with_brush_picks_and_keeps_brush(), test_drag_preview_keeps_tool_and_updates_color(), test_outside_image_returns_none(), test_panel_has_no_size_controls() (+5 more)

### Community 21 - "TextData"
Cohesion: 0.29
Nodes (4): MergePageCommand, max_diff(), test_merge_produces_identical_image(), test_merge_undo_redo()

### Community 22 - "test_v3_clone_ui.py"
Cohesion: 0.09
Nodes (53): offset_between(), assert_cloned_at(), count_color(), cyan(), drag(), hover_at(), make_pattern_png(), orange() (+45 more)

### Community 24 - "test_v5_fixed_source_area.py"
Cohesion: 0.05
Nodes (41): StrokeCommand, CloneSession, PatternCloneSession, SourcePatch, blank_layer(), test_cancel_restores_layer(), assert_tiled_from(), coded_image() (+33 more)

### Community 26 - "TextLayout"
Cohesion: 0.06
Nodes (30): ImageLoadError, load_image(), paint_text(), paint_text_data(), text_transform(), TextLayout, test_actual_size_and_zoom_buttons(), test_load_invalid_file() (+22 more)

### Community 27 - "test_v3_shortcuts.py"
Cohesion: 0.13
Nodes (26): Tool, finish_editing(), make_text(), send_enter(), seq(), start_editing(), test_alt_and_ctrl_alt_shortcuts_do_not_fire_while_editing(), test_assigned_letter_in_panel_field_does_not_fire() (+18 more)

### Community 32 - "test_v2_save_output.py"
Cohesion: 0.17
Nodes (20): compose_page(), write_page_outputs(), test_batch_export_png_matches_canvas(), test_export_jpg_quality_and_subset(), edit(), mean_abs_diff(), rgb32(), sha() (+12 more)

### Community 33 - "PageDocument"
Cohesion: 0.05
Nodes (9): render_for_export(), PageDocument, _is_within(), _norm(), _now(), Project, ProjectError, test_open_invalid_project() (+1 more)

### Community 34 - "project.yml"
Cohesion: 0.08
Nodes (25): activation_command, activation_command_timeout, added_modes, agent_interface, default_modes, encoding, excluded_apis, excluded_tools (+17 more)

### Community 36 - "TextData"
Cohesion: 0.18
Nodes (6): AddTextCommand, TextData, draw_texts(), page(), test_merge_via_ui_then_brush_over_text_and_ctrl_z(), test_pages_are_independent()

### Community 37 - "event_sequences"
Cohesion: 0.27
Nodes (7): _combo(), event_sequences(), _printable_symbol(), key_event(), test_altgr_char_also_matches_real_ctrl_alt_binding(), test_event_to_sequence(), test_modifier_only_events_produce_no_sequence()

### Community 39 - "ShortcutCaptureButton"
Cohesion: 0.15
Nodes (3): _mod_of(), ShortcutCaptureButton, is_modifier_key()

### Community 40 - "open_window"
Cohesion: 0.19
Nodes (17): make_settings(), make_ttf(), open_window(), test_merge_without_texts_is_noop(), build_edited_project(), new_window(), sha(), stroke() (+9 more)

### Community 42 - "SidePanel"
Cohesion: 0.21
Nodes (4): BrushPanel, EraserPanel, EyedropperPanel, SidePanel

### Community 43 - "conftest.py"
Cohesion: 0.12
Nodes (10): dialogs(), make_manga_image(), manga_files(), qapp(), sha(), test_pages_added_as_tabs_and_copied(), test_view_state_per_page(), three_images() (+2 more)

### Community 44 - "test_phase2_tools.py"
Cohesion: 0.21
Nodes (12): drag(), page(), rgb(), stroke(), test_bracket_keys_change_size(), test_brush_opacity_does_not_accumulate(), test_brush_paints_real_pixels(), test_eraser_removes_paint_and_reveals_original() (+4 more)

### Community 46 - "ShortcutRegistry"
Cohesion: 0.15
Nodes (4): AssignResult, native(), ShortcutDef, test_ctrl_a_and_ctrl_alt_z_style_combos_assignable()

### Community 47 - "text_layout.py"
Cohesion: 0.20
Nodes (5): layout_changed(), Line, make_font(), _wrap_paragraph(), wrap_text()

### Community 48 - "portable"
Cohesion: 0.27
Nodes (9): portable(), test_conflicts_detected_across_kinds(), test_corrupt_or_conflicting_saved_data_is_ignored(), test_defaults_are_unique_and_cover_every_action(), test_modifier_alone_and_esc_cannot_be_assigned(), test_reassigning_own_shortcut_is_fine_and_swap_needs_two_steps(), test_required_default_shortcuts_present(), test_reset_one_blocked_when_default_is_taken() (+1 more)

### Community 52 - "Manga Editör"
Cohesion: 0.25
Nodes (7): Kullanım, Kısayollar, Kısayolları özelleştirme (Ayarlar → Kısayollar…), Manga Editör, Mimari, Proje klasörü, Çalıştırma

### Community 53 - "SliderSpin"
Cohesion: 0.18
Nodes (3): _hint(), _panel_layout(), SliderSpin

### Community 54 - ".capture_button"
Cohesion: 0.15
Nodes (12): ShortcutsDialog, dlg(), reg(), test_click_enters_capture_mode_visibly_and_single_key_is_assigned(), test_dialog_changes_persist_to_new_session(), test_dialog_conflict_blocks_assignment_and_names_the_other_action(), test_dialog_esc_cancels_without_changes_and_keeps_dialog_open(), test_dialog_hold_key_with_modifier_is_rejected() (+4 more)

### Community 78 - "test_phase8_ui.py"
Cohesion: 0.17
Nodes (6): test_actions_safe_during_text_editing(), test_required_shortcuts_exist_and_do_not_conflict(), test_space_types_while_editing_but_pans_otherwise(), test_typing_in_panel_field_does_not_switch_tools(), test_welcome_screen_without_project(), window()

## Knowledge Gaps
- **79 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `main_window.py`, `CanvasView`, `._build_actions`, `.add_pages`, `ExportDialog`, `test_phase3_text_ui.py`, `.commit_ui_state`, `test_v3_clone_ui.py`, `test_v5_fixed_source_area.py`, `TextLayout`, `test_v3_shortcuts.py`, `test_v2_save_output.py`, `TextData`, `open_window`, `SidePanel`, `conftest.py`, `test_phase2_tools.py`, `.close_project`, `.__init__`, `._show_page`, `.capture_button`, `.load_fonts`, `.add_pages`, `test_phase8_ui.py`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `MainWindow` (e.g. with `CanvasView` and `SidePanel`) actually correct?**
  _`MainWindow` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `pyside6_qtgui` be split into smaller, more focused modules?**
  _Cohesion score 0.1437908496732026 - nodes in this community are weakly interconnected._
- **Why does `CanvasView` connect `CanvasView` to `main_window.py`, `.close_project`, `.__init__`, `MainWindow`, `test_v5_fixed_source_area.py`, `compose_page`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `PageDocument` (e.g. with `compose_page()` and `sample_color()`) actually correct?**
  _`PageDocument` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Should `main_window.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11397849462365592 - nodes in this community are weakly interconnected._
- **Why does `TextData` connect `TextData` to `pyside6_qtgui`, `main_window.py`, `ChangeTextCommand`, `Text Layout Engine`, `Project Persistence`, `StrokeSession`, `TextLayout`, `test_v3_shortcuts.py`, `compose_page`, `test_v2_save_output.py`, `PageDocument`, `pyside6_qtgui`, `open_window`, `PageScene`, `conftest.py`, `text_layout.py`, `.load_fonts`, `ToolSettings`, `ColorButton`, `.with_`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._