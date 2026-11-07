# MangaEditor mimarisi (PySide6, Python 3.11, .venv)
- core/ (QtWidgets YOK): page.py PageDocument (original salt-okunur + paint ARGB katmanı + texts + kendi QUndoStack),
  text_data.py TextData (frozen; '\n' = manuel satır sonu), text_layout.py (wrap_text, TextLayout, paint_text, text_transform),
  stroke.py StrokeSession (fırça tampona çizilir, bitince opaklıkla birleşir), commands.py (Stroke/Add/Remove/ChangeText(merge)/MergePage),
  compose.py compose_page (tuval=birleştirme=dışa aktarma), project.py Project (klasör, kaydet/yükle, .recovery), export.py, fonts.py FontManager.
- ui/: canvas_view.py CanvasView (zoom/pan/araçlar, ShortcutOverride ile düzenlemede kısayolları engeller), page_scene.py PageScene
  (model<->öğe eşitleme, düzenleme başlat/bitir, apply_style), text_item.py TextItemView (taşı/boyutlandır/döndür/yerinde düzenleme),
  text_panel.py, panels.py, dialogs.py, main_window.py MainWindow (proje, sekmeler, autosave/recovery, export).
- Testler: tests/ (pytest, offscreen; QT_QPA_FONTDIR conftest'te). QTest.keyClicks ASCII dışı karakterde çöker → type_unicode yardımcısı.
  conftest open_window(tmp_path, images) geçici proje kurar; QMessageBox otomatik yanıtlanır.
- Paketleme: build.ps1 (PyInstaller onedir).
- v2 (2026-11-07): wrap_text kelimeleri ASLA bölmez (uzun kelime taşar). Kaydet (Ctrl+S / çıkışta Kaydet) =
  export.write_page_outputs: output_stale sayfaları Project.output_target'a (varsayılan: eklenen kaynak dosya)
  yazar; Project.check_output_target korunan proje klasörlerini/çakışan hedefleri reddeder; json'da
  output/output_pending. Otomatik kaydetme görsel yazmaz. Damlalık: yalnızca TEK piksel
  (compose.sample_color(page, point); örnekleme boyutu özelliği v3'te kaldırıldı); renk alınca araç seçili kalır.
- v3 (2026-11-07): Klonlama = core/clone.py CloneSession (offset=kaynak-hedef tamsayı, kaynak=orijinal+darbe başı boya,
  kapsül maskesi, görsel dışı atlanır, StrokeCommand ile undo); PageScene.clone_source/clone_offset sayfaya özel;
  canvas._clone_press: K basılıysa yalnızca kaynak seçer, kaynak yoksa çizmez. v4: ToolSettings.clone_aligned
  (QSettings 'clone_aligned', varsayılan True). Hizalı: scene.clone_offset ilk basışta sabitlenir, darbeler arası kalır.
  Hizalı değil (v6, kullanıcı onaylı: 'desen gibi döşensin'): K+tıklamada SourcePatch.capture = fırça boyutunda KARE,
  koordinat+içerik dondurulur (scene.clone_patch). PatternCloneSession hedefi q <- origin + ((q-origin) mod size) ile döşer
  (QBrush texture, ızgara görsele sabit), keskin kapsül maskesi. Bırakmadan sürükleme = tek tek tıklama, birebir aynı.
  Hizalı mod CloneSession ile aynen kalır. Test görseli: renk = (x,y) kodu (test_v5_fixed_source_area). Kaynak = (nokta, offset);
  fırça boyutu yalnızca hedef maskesidir. Kaynak göstergesi SABİT ekran boyutlu (CLONE_MARK_ARM/RING), fırça boyutuyla
  ölçeklenmez. Mod değişince MainWindow._on_clone_mode_changed offset'leri sıfırlar, kaynak noktası kalır.
  Merkezi kısayollar = ui/shortcuts.py ShortcutRegistry (kinds: action/local/hold; çakışma engeli, QSettings JSON
  'shortcuts/overrides', bind_action, matches, is_held) + ui/shortcuts_dialog.py. Tuvalde sabit tuş kontrolü YOK
  (test_no_hard_coded_shortcuts_left_in_ui_code bunu denetler). Hold tuşları (Space,K) canvas keyPress/Release ->
  registry.note_key_press; app-wide eventFilter KULLANMA (yavaşlatıyor). Düzenleme tuşları (Ctrl+A/C/X/V/Z/Y, oklar)
  text_item.handle_key + canvas ShortcutOverride ile sabit.