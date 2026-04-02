import tarfile
from pathlib import Path
import io

class TarShardWriter:
    def __init__(self, out_dir: Path, shard_size: int = 10000, prefix: str = "yolo_annos"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.shard_size = int(shard_size)
        self.prefix = prefix

        self._shard_idx = 0
        self._n_in_shard = 0
        self._tar = None  # tarfile.TarFile

        self._open_new()

    def _open_new(self):
        if self._tar is not None:
            self._tar.close()
        shard_name = f"{self.prefix}-{self._shard_idx:06d}.tar"
        self._tar_path = self.out_dir / shard_name
        self._tar = tarfile.open(self._tar_path, mode="w")  # uncompressed tar
        self._n_in_shard = 0
        self._shard_idx += 1

    def write_text(self, rel_path: str, text: str):
        self.write_bytes(rel_path, text.encode("utf-8"))

    def write_bytes(self, rel_path: str, data: bytes):
        if self._n_in_shard >= self.shard_size:
            self._open_new()

        ti = tarfile.TarInfo(name=rel_path)
        ti.size = len(data)
        self._tar.addfile(ti, io.BytesIO(data))
        self._n_in_shard += 1

    def close(self):
        if self._tar is not None:
            self._tar.close()
            self._tar = None

