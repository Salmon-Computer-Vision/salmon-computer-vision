from object_detection.utils.utils import (
    parse_video_stem,
)


def test_parse_video_stem_happy_path():
    got = parse_video_stem("HIRMD-tankeeah-jetson-0_20250714_012827_M")
    assert got == {
        "org": "HIRMD",
        "site": "tankeeah",
        "device": "jetson-0",
        "date": "20250714",
        "time": "012827",
        "suffix": "M",
    }


def test_parse_video_stem_invalid():
    assert parse_video_stem("not_a_valid_stem") is None

