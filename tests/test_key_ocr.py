import pytest
from worship_guide.key_ocr import (
    detect_key_candidate,
    normalize_signature,
    extract_chord_roots,
)
from worship_guide.ocr_titles import OCRLine, choose_title


@pytest.mark.parametrize(
    "text,key",
    [
        ("Key: Bb", "Bb"),
        ("F# minor key", "F#m"),
        ("조성: E major", "E"),
        ("G 단조", "Gm"),
        ("C key", "C"),
    ],
)
def test_explicit_key_labels_are_candidates(text, key):
    result = detect_key_candidate([text])
    assert result.key == key and result.method == "printed"
    assert result.evidence()["texts"] == [text]


@pytest.mark.parametrize(
    "texts",
    [
        [],
        ["Kang Score", "Steve Fry"],
        ["F068"],
        ["G"],
        ["C G Am F"],
        ["Key: C", "Key: D"],
    ],
)
def test_ambiguous_or_short_chords_remain_unknown(texts):
    assert detect_key_candidate(texts).key is None


def test_chord_major_minor_and_accidentals():
    assert extract_chord_roots(["CM7 Cmaj7 Cm7 Cmin7 F♯m Bb/D"]) == [
        ("C", False),
        ("C", False),
        ("C", True),
        ("C", True),
        ("F#", True),
        ("Bb", False),
    ]
    assert normalize_signature("f♯m") == "F#m"
    with pytest.raises(ValueError):
        normalize_signature("H")


def test_title_prefers_large_top_heading_over_lyrics_chords_and_author():
    lines = [
        OCRLine("고개 들어", 0.95, [[300, 10], [700, 10], [700, 90], [300, 90]]),
        OCRLine(
            "G GM7 G7 CM7 Am7 D", 0.98, [[20, 160], [980, 160], [980, 200], [20, 200]]
        ),
        OCRLine(
            "내가 원하는 그 모든 것을 주님 앞에 내려놓네",
            0.99,
            [[20, 240], [980, 240], [980, 275], [20, 275]],
        ),
        OCRLine("작곡가", 0.99, [[850, 115], [980, 115], [980, 140], [850, 140]]),
    ]
    assert choose_title(lines, 1000, 300)[0] == "고개 들어"
