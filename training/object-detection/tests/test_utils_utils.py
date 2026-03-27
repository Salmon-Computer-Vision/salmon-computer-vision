from object_detection.utils.utils import safe_float
import pytest

def test_safe_float():
    assert safe_float("1.25") == 1.25
    assert safe_float("bad", 7.0) == 7.0


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("1.5", 0.0, 1.5),
        (2, 0.0, 2.0),
        (None, 7.0, 7.0),
        ("abc", -1.0, -1.0),
    ],
)
def test_safe_float(value, default, expected):
    assert safe_float(value, default) == expected
