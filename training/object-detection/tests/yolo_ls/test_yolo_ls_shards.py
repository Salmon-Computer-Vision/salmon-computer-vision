import tarfile
from pathlib import Path

from object_detection.yolo_ls.shards import TarShardWriter


def test_tar_shard_writer_writes_member(tmp_path: Path):
    out_dir = tmp_path / "shards"
    writer = TarShardWriter(out_dir, shard_size=10, prefix="test")
    writer.write_text("video/frame_000001.txt", "hello\n")
    writer.close()

    tar_path = out_dir / "test-000000.tar"
    assert tar_path.exists()

    with tarfile.open(tar_path, "r") as tf:
        assert tf.getnames() == ["video/frame_000001.txt"]
        content = tf.extractfile("video/frame_000001.txt").read().decode("utf-8")
        assert content == "hello\n"


def test_tar_shard_writer_rotates(tmp_path: Path):
    out_dir = tmp_path / "shards"
    writer = TarShardWriter(out_dir, shard_size=1, prefix="test")
    writer.write_text("a.txt", "a")
    writer.write_text("b.txt", "b")
    writer.close()

    assert (out_dir / "test-000000.tar").exists()
    assert (out_dir / "test-000001.tar").exists()
