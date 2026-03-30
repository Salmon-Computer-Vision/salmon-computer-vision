def safe_float(x: str, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


_STEM_RE = re.compile(
    r"""
    ^
    (?P<prefix>.+?)
    _
    (?P<date>\d{8})
    _
    (?P<time>\d{6})
    _
    (?P<suffix>.+)
    $
    """,
    re.VERBOSE,
)

def parse_video_stem(video_stem: str) -> Optional[Dict[str, str]]:
    """
    Example:
      HIRMD-tankeeah-jetson-0_20250714_012827_M
    ->
      {
        "org": "HIRMD",
        "site": "tankeeah",
        "device": "jetson-0",
        "date": "20250714",
        "time": "012827",
        "suffix": "M",
      }
    """
    m = _STEM_RE.match(video_stem)
    if not m:
        return None

    prefix = m.group("prefix")
    parts = prefix.split("-")
    if len(parts) < 3:
        return None

    return {
        "org": parts[0],
        "site": parts[1],
        "device": "-".join(parts[2:]),
        "date": m.group("date"),
        "time": m.group("time"),
        "suffix": m.group("suffix"),
    }
