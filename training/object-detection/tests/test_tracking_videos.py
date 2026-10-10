from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from object_detection.tracking_eval import videos as v


def write_eval_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["split", "video_stem", "s3_key", "s3_uri", "local_video_path"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_read_video_requests_builds_s3_uri(tmp_path):
    csv_path = tmp_path / "val.csv"
    local = tmp_path / "videos" / "v.mp4"
    write_eval_csv(csv_path, [{
        "split": "val",
        "video_stem": "v",
        "s3_key": "ORG/site/device/motion_vids/v.mp4",
        "s3_uri": "",
        "local_video_path": str(local),
    }])
    got = v.read_video_requests(csv_path, bucket="bucket", expected_split="val")
    assert got[0].s3_uri == "s3://bucket/ORG/site/device/motion_vids/v.mp4"
    assert got[0].local_path == local


def test_read_video_requests_prefers_s3_uri(tmp_path):
    csv_path = tmp_path / "test.csv"
    write_eval_csv(csv_path, [{
        "split": "test",
        "video_stem": "v",
        "s3_key": "wrong.mp4",
        "s3_uri": "s3://other/right.mp4",
        "local_video_path": str(tmp_path / "v.mp4"),
    }])
    got = v.read_video_requests(csv_path, bucket="bucket", expected_split="test")
    assert got[0].s3_uri == "s3://other/right.mp4"


def test_read_video_requests_rejects_split_mismatch(tmp_path):
    csv_path = tmp_path / "x.csv"
    write_eval_csv(csv_path, [{
        "split": "test",
        "video_stem": "v",
        "s3_key": "v.mp4",
        "s3_uri": "",
        "local_video_path": str(tmp_path / "v.mp4"),
    }])
    with pytest.raises(ValueError, match="Split mismatch"):
        v.read_video_requests(csv_path, bucket="bucket", expected_split="val")


def test_existing_nonempty_file_is_reused(tmp_path, monkeypatch):
    local = tmp_path / "v.mp4"
    local.write_bytes(b"abc")
    req = v.VideoRequest("val", "v", "s3://bucket/v.mp4", local)

    def boom(*args, **kwargs):
        raise AssertionError("aws should not run")
    monkeypatch.setattr(v.subprocess, "run", boom)

    result = v._download_one(req)
    assert result.status == "existing"
    assert result.size_bytes == 3


def test_successful_download_uses_partial_then_renames(tmp_path, monkeypatch):
    local = tmp_path / "v.mp4"
    req = v.VideoRequest("val", "v", "s3://bucket/v.mp4", local)

    class Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        partial = Path(cmd[4])
        assert partial.name.endswith(".partial")
        partial.write_bytes(b"video")
        return Proc()

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    result = v._download_one(req)
    assert result.status == "downloaded"
    assert local.read_bytes() == b"video"
    assert not Path(str(local) + ".partial").exists()


def test_glacier_download_is_classified(tmp_path, monkeypatch):
    local = tmp_path / "v.mp4"
    req = v.VideoRequest("val", "v", "s3://bucket/path/v.mp4", local)

    class Proc:
        returncode = 2
        stdout = ""
        stderr = (
            "warning: Skipping file s3://bucket/path/v.mp4. "
            "Object is of storage class GLACIER. Unable to perform download operations."
        )

    monkeypatch.setattr(v.subprocess, "run", lambda *a, **k: Proc())
    result = v._download_one(req)
    assert result.status == "archived"
    assert result.archive_class == "GLACIER"


def test_deep_archive_download_is_classified(tmp_path, monkeypatch):
    local = tmp_path / "v.mp4"
    req = v.VideoRequest("val", "v", "s3://bucket/path/v.mp4", local)

    class Proc:
        returncode = 2
        stdout = ""
        stderr = "Object is of storage class DEEP_ARCHIVE"

    monkeypatch.setattr(v.subprocess, "run", lambda *a, **k: Proc())
    result = v._download_one(req)
    assert result.status == "archived"
    assert result.archive_class == "DEEP_ARCHIVE"


def test_missing_download_is_classified(tmp_path, monkeypatch):
    req = v.VideoRequest("test", "v", "s3://bucket/v.mp4", tmp_path / "v.mp4")

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "fatal error: An error occurred (404) when calling the HeadObject operation: Key does not exist"

    monkeypatch.setattr(v.subprocess, "run", lambda *a, **k: Proc())
    result = v._download_one(req)
    assert result.status == "missing"


def test_unknown_failure_is_error(tmp_path, monkeypatch):
    req = v.VideoRequest("test", "v", "s3://bucket/v.mp4", tmp_path / "v.mp4")

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "Could not connect to endpoint URL"

    monkeypatch.setattr(v.subprocess, "run", lambda *a, **k: Proc())
    result = v._download_one(req)
    assert result.status == "error"


def test_glacier_log_is_compatible_with_restore_script_regex(tmp_path):
    path = tmp_path / "glacier.log"
    uri = "s3://bucket/path/video.mp4"
    results = [v.VideoDownloadResult(
        split="val", video_stem="video", s3_uri=uri,
        local_video_path="video.mp4", status="archived", size_bytes=0,
        archive_class="GLACIER",
    )]
    v.write_glacier_log(results, path)
    text = path.read_text()
    pattern = re.compile(r".*Skipping file (s3://[^ ]*)\. Object is of storage class.*")
    match = pattern.match(text.strip())
    assert match is not None
    assert match.group(1) == uri


def test_glacier_log_deduplicates_urls(tmp_path):
    path = tmp_path / "glacier.log"
    uri = "s3://bucket/path/video.mp4"
    results = [
        v.VideoDownloadResult("val", "a", uri, "a", "archived", 0, "GLACIER"),
        v.VideoDownloadResult("val", "b", uri, "b", "archived", 0, "GLACIER"),
    ]
    v.write_glacier_log(results, path)
    assert len(path.read_text().strip().splitlines()) == 1


def test_status_csv_marks_only_present_videos_eligible(tmp_path):
    path = tmp_path / "status.csv"
    results = [
        v.VideoDownloadResult("val", "a", "s3://b/a", "a", "existing", 10),
        v.VideoDownloadResult("val", "b", "s3://b/b", "b", "downloaded", 20),
        v.VideoDownloadResult("val", "c", "s3://b/c", "c", "missing", 0),
    ]
    v.write_status_csv(results, path)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["eligible_for_tracking"] for r in rows] == ["true", "true", "false"]


def test_summary_counts_all_statuses():
    results = [
        v.VideoDownloadResult("val", "a", "a", "a", "existing", 10),
        v.VideoDownloadResult("val", "b", "b", "b", "downloaded", 20),
        v.VideoDownloadResult("val", "c", "c", "c", "archived", 0),
        v.VideoDownloadResult("val", "d", "d", "d", "missing", 0),
        v.VideoDownloadResult("val", "e", "e", "e", "error", 0),
    ]
    stats = v.summarize(results)
    assert stats.videos_total == 5
    assert stats.existing == 1
    assert stats.downloaded == 1
    assert stats.archived == 1
    assert stats.missing == 1
    assert stats.errors == 1
    assert stats.bytes_present == 30


def test_download_tracking_videos_rejects_bad_workers():
    with pytest.raises(ValueError, match="workers"):
        v.download_tracking_videos([], workers=0)
