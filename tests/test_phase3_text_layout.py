"""Phase 3a: line wrapping engine (distinguishing manual and automatic line breaks)."""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter

from mangaeditor.core.text_data import TextData
from mangaeditor.core.text_layout import TextLayout, paint_text_data, text_transform


def lines_of(data):
    lay = TextLayout(data)
    return [lay.line_text(i).rstrip() for i in range(len(lay.lines))], lay


def make(text, width=1000.0, **kw):
    return TextData(id="t", text=text, width=width, height=300, font_family="Arial", font_size=32, **kw)


def test_manual_breaks_preserved_when_widened(qapp):
    lines, _ = lines_of(make("Bu bir\nmanga", width=2000))
    assert lines == ["Bu bir", "manga"]  # not merged even in a wide box


def test_auto_wrap_and_reflow_on_widen(qapp):
    text = "Bu uzun bir manga cümlesidir"
    narrow, lay = lines_of(make(text, width=150))
    assert len(narrow) >= 3
    assert all(not ln.hard for ln in lay.lines)  # hepsi otomatik
    assert all(ln.width <= 150 + 0.01 for ln in lay.lines)
    wide, _ = lines_of(make(text, width=2000))
    assert wide == [text]  # when the box widens, words move back up
    assert "\n" not in text  # no automatic line break was written into the text


def test_mixed_manual_and_auto(qapp):
    text = "Merhaba dünya nasılsın\nİyiyim"
    narrow, lay = lines_of(make(text, width=170))
    assert narrow[-1] == "İyiyim"
    hard = [ln.hard for ln in lay.lines]
    assert hard.count(True) == 1 and hard[len(narrow) - 2] is True
    wide, _ = lines_of(make(text, width=3000))
    assert wide == ["Merhaba dünya nasılsın", "İyiyim"]


def test_long_word_is_never_split_and_may_overflow(qapp):
    # A single word wider than the box is not split; it overflows the box on its own line.
    lines, lay = lines_of(make("Şşşşşşşşşşşşşşşşşşşş", width=100))
    assert lines == ["Şşşşşşşşşşşşşşşşşşşş"]
    assert lay.lines[0].width > 100


def test_word_moves_whole_to_next_line(qapp):
    # When "Kemalettin" does not fit, it moves whole to the next line instead of "Kemal / ettin".
    probe = TextLayout(make("Merhaba Kemalettin"))
    width = probe.measure("Merhaba Kemal")  # "Merhaba Kemal" fits but "Merhaba Kemalettin" does not
    lines, _ = lines_of(make("Merhaba Kemalettin", width=width))
    assert lines == ["Merhaba", "Kemalettin"]


@pytest.mark.parametrize("width", [40, 80, 120, 160, 200, 260, 330, 420, 600])
def test_no_word_is_ever_split(qapp, width):
    text = "Bu bir manga Kemalettin çok uzunkelimelerdenoluşan Türkçe cümlelerle dolu\nİkinci satır elle eklendi"
    lines, lay = lines_of(make(text, width=width))
    words = text.split()
    assert " ".join(" ".join(lines).split()) == " ".join(words)  # same order and content
    for ln in lines:
        for w in ln.split():
            assert w in words  # every piece is a whole word
    # The manual line break is kept at every width
    hard = [i for i, ln in enumerate(lay.lines) if ln.hard]
    assert len(hard) == 1 and lines[hard[0] + 1].startswith("İkinci")


def test_overflowing_word_with_manual_breaks_and_caret(qapp):
    data = make("Kısa\nUzunnnnnnnnnnnnnkelime\nSon", width=60, align_h="left", align_v="top")
    lines, lay = lines_of(data)
    assert lines == ["Kısa", "Uzunnnnnnnnnnnnnkelime", "Son"]
    for idx in range(len(data.text) + 1):
        r = lay.caret_rect(idx)
        assert lay.hit_test(QPointF(r.x(), r.center().y())) == idx


def test_empty_lines_kept(qapp):
    lines, _ = lines_of(make("A\n\nB"))
    assert lines == ["A", "", "B"]


def test_caret_and_hit_test_roundtrip(qapp):
    data = make("Bu bir\nmanga", width=400, align_h="left", align_v="top")
    lay = TextLayout(data)
    for idx in range(len(data.text) + 1):
        r = lay.caret_rect(idx)
        assert lay.hit_test(QPointF(r.x(), r.center().y())) == idx


def test_line_spacing_and_vertical_align(qapp):
    d1 = make("A\nB", line_spacing=1.0, align_v="top")
    d2 = make("A\nB", line_spacing=2.0, align_v="top")
    l1, l2 = TextLayout(d1), TextLayout(d2)
    assert l2.baseline(1) - l2.baseline(0) == pytest.approx(2 * (l1.baseline(1) - l1.baseline(0)))
    mid = TextLayout(make("A", align_v="middle"))
    bot = TextLayout(make("A", align_v="bottom"))
    assert mid.top == pytest.approx((300 - mid.block_height) / 2)
    assert bot.top == pytest.approx(300 - bot.block_height)


def test_letter_spacing_widens(qapp):
    a = TextLayout(make("MANGA", letter_spacing=0))
    b = TextLayout(make("MANGA", letter_spacing=10))
    assert b.lines[0].width == pytest.approx(a.lines[0].width + 40, abs=0.5)


def test_horizontal_alignment(qapp):
    left = TextLayout(make("Hi", align_h="left"))
    right = TextLayout(make("Hi", align_h="right"))
    center = TextLayout(make("Hi", align_h="center"))
    w = left.lines[0].width
    assert left.line_x[0] == 0
    assert right.line_x[0] == pytest.approx(1000 - w)
    assert center.line_x[0] == pytest.approx((1000 - w) / 2)


def render(data, size=(400, 400)):
    img = QImage(*size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    paint_text_data(p, data)
    p.end()
    return img


def count_color(img, pred):
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if pred(img.pixelColor(x, y)):
                n += 1
    return n


def test_render_fill_stroke_shadow_background(qapp):
    base = TextData(id="t", text="MANGA", x=50, y=100, width=300, height=100, font_size=60,
                    color="#ff000000")
    plain = render(base)
    assert count_color(plain, lambda c: c.red() < 40) > 50  # black text was drawn
    stroked = render(base.with_(stroke_enabled=True, stroke_width=4, stroke_color="#ffff0000"))
    assert count_color(stroked, lambda c: c.red() > 200 and c.green() < 60) > 50  # red outline
    shadowed = render(base.with_(shadow_enabled=True, shadow_color="#ff0000ff", shadow_dx=6, shadow_dy=6))
    assert count_color(shadowed, lambda c: c.blue() > 200 and c.red() < 60) > 20  # blue shadow
    bg = render(base.with_(bg_enabled=True, bg_color="#ff00ff00"))
    assert bg.pixelColor(60, 110) == QColor(0, 255, 0)  # box background


def test_rotation_transform(qapp):
    d = TextData(id="t", x=100, y=100, width=200, height=100, rotation=90)
    t = text_transform(d)
    c = t.map(QPointF(100, 50))  # the box center stays in place
    assert (c.x(), c.y()) == pytest.approx((200, 150))
    corner = t.map(QPointF(0, 0))
    assert (corner.x(), corner.y()) == pytest.approx((250, 50))
