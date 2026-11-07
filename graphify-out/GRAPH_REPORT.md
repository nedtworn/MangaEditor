# Graph Report - MangaEditor  (2026-11-07)

## Corpus Check
- 55 files · ~45,874 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 1346 nodes · 3630 edges · 140 communities (30 shown, 110 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 374 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- test_i18n.py
- CanvasView
- ._build_actions
- RemoveTextCommand
- TextItemView
- StrokeSession
- test_v3_clone_core.py
- ExportDialog
- test_phase3_text_ui.py
- test_v3_eyedropper.py
- PaintLayerItem
- test_phase4_merge.py
- test_v3_clone_ui.py
- .open_project
- test_v5_fixed_source_area.py
- test_phase3_text_layout.py
- seq
- CloneSession
- app.py
- main_window.py
- test_v2_save_output.py
- PageDocument
- project.yml
- parse
- paint_text_data
- PageDocument
- TextData
- ShortcutCaptureButton
- open_window
- PageScene
- ToolSettings
- conftest.py
- test_phase2_tools.py
- ShortcutRegistry
- text_layout.py
- portable
- TextLayout
- pytest
- Manga Editör
- test_v3_shortcuts.py
- MainWindow
- .install
- tr
- architecture_overview.md
- test_phase8_ui.py
- NewProjectDialog
- conftest.py
- .from_image
- test_dialog_conflict_blocks_assignment_and_names_the_other_action
- ChangeTextCommand

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 118 edges
2. `PageDocument` - 102 edges
3. `tr()` - 100 edges
4. `CanvasView` - 67 edges
5. `Tool` - 67 edges
6. `TextData` - 65 edges
7. `Project` - 52 edges
8. `TextItemView` - 52 edges
9. `open_window()` - 51 edges
10. `compose_page()` - 45 edges

## Surprising Connections (you probably didn't know these)
- `test_settings_menu_opens_dialog()` --uses--> `ShortcutsDialog`  [INFERRED]
  tests/test_v3_shortcuts.py → mangaeditor/ui/shortcuts_dialog.py
- `test_bracket_keys_change_size()` --uses--> `Tool`  [INFERRED]
  tests/test_phase2_tools.py → mangaeditor/ui/tools.py
- `test_clone_tool_in_toolbar_and_shortcut()` --uses--> `Tool`  [INFERRED]
  tests/test_v3_clone_ui.py → mangaeditor/ui/tools.py
- `test_panel_has_no_size_controls()` --uses--> `Tool`  [INFERRED]
  tests/test_v3_eyedropper.py → mangaeditor/ui/tools.py
- `test_offset_between_rounds_to_nearest()` --calls--> `offset_between()`  [EXTRACTED]
  tests/test_v3_clone_core.py → mangaeditor/core/clone.py

## Import Cycles
- None detected.

## Communities (140 total, 110 thin omitted)

### Community 0 - "test_i18n.py"
Cohesion: 0.08
Nodes (21): current(), detect_language(), force(), init(), _load_table(), saved_language(), set_language(), tr_in() (+13 more)

### Community 3 - "._build_actions"
Cohesion: 0.27
Nodes (8): brush_icon(), _canvas(), clone_icon(), eraser_icon(), eyedropper_icon(), _pen(), text_icon(), act()

### Community 8 - "StrokeSession"
Cohesion: 0.17
Nodes (5): StrokeCommand, StrokeSession, stroke(), window(), test_source_includes_existing_paint()

### Community 10 - "test_v3_clone_core.py"
Cohesion: 0.16
Nodes (14): dist_to_segment(), page(), painted_count(), pattern(), rgb(), run(), test_brush_size_controls_width(), test_destination_outside_image_is_clipped_safely() (+6 more)

### Community 16 - "test_phase3_text_ui.py"
Cohesion: 0.09
Nodes (20): FontLoadError, FontManager, make_otf(), create_text(), drag(), handle_view_pos(), test_brush_does_not_touch_texts(), test_create_text_by_typing_and_shortcuts_do_not_fire() (+12 more)

### Community 18 - "test_v3_eyedropper.py"
Cohesion: 0.12
Nodes (13): sample_color(), click(), gradient_page(), rgb(), test_alt_click_with_brush_picks_and_keeps_brush(), test_drag_preview_keeps_tool_and_updates_color(), test_outside_image_returns_none(), test_panel_has_no_size_controls() (+5 more)

### Community 21 - "test_phase4_merge.py"
Cohesion: 0.17
Nodes (7): AddTextCommand, MergePageCommand, max_diff(), test_merge_produces_identical_image(), test_merge_undo_redo(), test_merge_via_ui_then_brush_over_text_and_ctrl_z(), test_paint_and_erase_on_merged_text()

### Community 22 - "test_v3_clone_ui.py"
Cohesion: 0.09
Nodes (53): offset_between(), assert_cloned_at(), count_color(), cyan(), drag(), hover_at(), make_pattern_png(), orange() (+45 more)

### Community 24 - "test_v5_fixed_source_area.py"
Cohesion: 0.09
Nodes (35): PatternCloneSession, SourcePatch, assert_tiled_from(), coded_image(), coded_png(), cyan(), decode(), diff_bbox() (+27 more)

### Community 26 - "test_phase3_text_layout.py"
Cohesion: 0.22
Nodes (17): count_color(), lines_of(), make(), render(), test_auto_wrap_and_reflow_on_widen(), test_caret_and_hit_test_roundtrip(), test_empty_lines_kept(), test_horizontal_alignment() (+9 more)

### Community 27 - "seq"
Cohesion: 0.14
Nodes (16): finish_editing(), seq(), start_editing(), test_alt_and_ctrl_alt_shortcuts_do_not_fire_while_editing(), test_assigned_letter_in_panel_field_does_not_fire(), test_brush_size_keys_follow_assignment(), test_clone_source_key_follows_assignment(), test_conflicts_detected_across_kinds() (+8 more)

### Community 29 - "CloneSession"
Cohesion: 0.14
Nodes (3): CloneSession, blank_layer(), test_cancel_restores_layer()

### Community 31 - "main_window.py"
Cohesion: 0.11
Nodes (4): new_page_id(), new_text_id(), sequence_from_event(), double_spin()

### Community 32 - "test_v2_save_output.py"
Cohesion: 0.16
Nodes (21): compose_page(), test_batch_export_png_matches_canvas(), test_export_jpg_quality_and_subset(), edit(), mean_abs_diff(), rgb32(), sha(), sources() (+13 more)

### Community 33 - "PageDocument"
Cohesion: 0.05
Nodes (18): export_filename(), export_pages(), render_for_export(), write_page_outputs(), ImageLoadError, is_supported_input(), load_image(), save_image_atomic() (+10 more)

### Community 34 - "project.yml"
Cohesion: 0.08
Nodes (25): activation_command, activation_command_timeout, added_modes, agent_interface, default_modes, encoding, excluded_apis, excluded_tools (+17 more)

### Community 36 - "paint_text_data"
Cohesion: 0.16
Nodes (3): draw_texts(), paint_text(), paint_text_data()

### Community 38 - "TextData"
Cohesion: 0.18
Nodes (4): TextData, layout_changed(), text_transform(), test_rotation_transform()

### Community 39 - "ShortcutCaptureButton"
Cohesion: 0.18
Nodes (3): _mod_of(), ShortcutCaptureButton, is_modifier_key()

### Community 40 - "open_window"
Cohesion: 0.26
Nodes (12): make_ttf(), build_edited_project(), new_window(), sha(), stroke(), test_autosave(), test_cancel_close_keeps_window(), test_crash_recovery() (+4 more)

### Community 42 - "ToolSettings"
Cohesion: 0.05
Nodes (12): BrushPanel, ClonePanel, EraserPanel, EyedropperPanel, _hint(), _panel_layout(), SidePanel, _color_str() (+4 more)

### Community 43 - "conftest.py"
Cohesion: 0.14
Nodes (9): make_manga_image(), paint(), sha(), test_dirty_marker_on_tabs(), test_pages_added_as_tabs_and_copied(), test_pages_are_independent(), three_images(), window() (+1 more)

### Community 44 - "test_phase2_tools.py"
Cohesion: 0.21
Nodes (12): drag(), page(), rgb(), stroke(), test_bracket_keys_change_size(), test_brush_opacity_does_not_accumulate(), test_brush_paints_real_pixels(), test_eraser_removes_paint_and_reveals_original() (+4 more)

### Community 47 - "text_layout.py"
Cohesion: 0.28
Nodes (4): Line, make_font(), _wrap_paragraph(), wrap_text()

### Community 48 - "portable"
Cohesion: 0.16
Nodes (15): AssignResult, _combo(), native(), portable(), ShortcutDef, test_corrupt_or_conflicting_saved_data_is_ignored(), test_ctrl_a_and_ctrl_alt_z_style_combos_assignable(), test_defaults_are_unique_and_cover_every_action() (+7 more)

### Community 51 - "pytest"
Cohesion: 0.25
Nodes (6): test_actual_size_and_zoom_buttons(), test_load_invalid_file(), test_space_drag_pans(), test_wheel_zoom_keeps_point_under_mouse(), window(), test_view_state_per_page()

### Community 52 - "Manga Editör"
Cohesion: 0.25
Nodes (7): Architecture, Customizing shortcuts (Settings → Shortcuts…), Manga Editör, Project folder, Running it, Shortcuts, Usage

### Community 54 - "test_v3_shortcuts.py"
Cohesion: 0.08
Nodes (25): capture_prompt(), event_sequences(), _printable_symbol(), dlg(), key_event(), make_text(), reg(), send_enter() (+17 more)

### Community 78 - "test_phase8_ui.py"
Cohesion: 0.14
Nodes (14): Tool, make_settings(), open_window(), test_merge_without_texts_is_noop(), test_actions_safe_during_text_editing(), test_required_shortcuts_exist_and_do_not_conflict(), test_space_types_while_editing_but_pans_otherwise(), test_typing_in_panel_field_does_not_switch_tools() (+6 more)

### Community 94 - "conftest.py"
Cohesion: 0.60
Nodes (3): dialogs(), manga_files(), qapp()

## Knowledge Gaps
- **110 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `test_i18n.py`, `CanvasView`, `._build_actions`, `.add_pages`, `ExportDialog`, `test_phase3_text_ui.py`, `.commit_ui_state`, `test_phase4_merge.py`, `test_v3_clone_ui.py`, `.open_project`, `test_v5_fixed_source_area.py`, `app.py`, `main_window.py`, `test_v2_save_output.py`, `PageDocument`, `PageDocument`, `TextData`, `open_window`, `PageScene`, `ToolSettings`, `test_phase2_tools.py`, `.close_project`, `ShortcutRegistry`, `pytest`, `test_v3_shortcuts.py`, `tr`, `test_phase8_ui.py`, `NewProjectDialog`, `conftest.py`?**
  _High betweenness centrality (0.165) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `MainWindow` (e.g. with `MergePageCommand` and `FontLoadError`) actually correct?**
  _`MainWindow` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_i18n.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08108108108108109 - nodes in this community are weakly interconnected._
- **Why does `PageDocument` connect `PageDocument` to `RemoveTextCommand`, `.add_pages`, `StrokeSession`, `test_v3_clone_core.py`, `ExportDialog`, `.commit_ui_state`, `test_v3_eyedropper.py`, `PaintLayerItem`, `test_phase4_merge.py`, `.open_project`, `test_v5_fixed_source_area.py`, `CloneSession`, `main_window.py`, `test_v2_save_output.py`, `PageDocument`, `TextData`, `PageScene`, `test_phase2_tools.py`, `MainWindow`, `tr`, `.__init__`, `.__init__`, `.from_image`, `ChangeTextCommand`?**
  _High betweenness centrality (0.150) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `PageDocument` (e.g. with `CloneSession` and `PatternCloneSession`) actually correct?**
  _`PageDocument` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Should `CanvasView` be split into smaller, more focused modules?**
  _Cohesion score 0.06606990622335891 - nodes in this community are weakly interconnected._
- **Why does `tr()` connect `tr` to `test_i18n.py`, `CanvasView`, `._build_actions`, `RemoveTextCommand`, `TextItemView`, `.add_pages`, `ExportDialog`, `test_phase3_text_ui.py`, `.commit_ui_state`, `test_phase4_merge.py`, `.open_project`, `CloneSession`, `main_window.py`, `PageDocument`, `parse`, `PageDocument`, `PageScene`, `ToolSettings`, `.close_project`, `ShortcutRegistry`, `portable`, `test_v3_shortcuts.py`, `MainWindow`, `NewProjectDialog`, `.__init__`, `ChangeTextCommand`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._