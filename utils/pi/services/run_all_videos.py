#!/usr/bin/env python3

import contextlib, os, time, json, subprocess
from pathlib import Path

VIDEO_DIR = Path("/media/hdd/ADFG/chignik/")
STATE_DIR = VIDEO_DIR / ".state"   # keep markers together
STATE_DIR.mkdir(exist_ok=True)

def file_sig(p: Path) -> dict:
    st = p.stat()
    return {"size": st.st_size, "mtime": st.st_mtime}

def marker_paths(p: Path):
    base = STATE_DIR / (p.name + ".json")  # store metadata
    lock = STATE_DIR / (p.name + ".lock")
    return base, lock

def is_done(p: Path) -> bool:
    meta_path, _ = marker_paths(p)
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
        return meta.get("status") == "done" and meta.get("sig") == file_sig(p)
    except Exception:
        return False

def mark_status(p: Path, status: str, note: str = ""):
    meta_path, _ = marker_paths(p)
    tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    data = {"status": status, "sig": file_sig(p), "note": note, "ts": time.time()}
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, meta_path)  # atomic

def process_video(vid: Path, flags, device_id, fps, drive):
    cmd = [
        "python3", "training/tools/run_motion_detect_rtsp.py",
        flags, device_id, "--fps", fps, str(vid), drive
    ]
    subprocess.run(cmd, check=True)

def run_all(flags="", device_id="", fps="30", drive="/media/local_hdd"):
    vids = sorted(VIDEO_DIR.rglob("Near.*.mp4"))
    for vid in vids:
        meta_path, lock_path = marker_paths(vid)

        if is_done(vid):
            print(f"[skip] {vid.name} (already done)")
            continue

        # lock (best-effort)
        try:
            lock_path.write_text(str(os.getpid()))
        except Exception:
            pass

        try:
            print(f"[run]  {vid.name}")
            mark_status(vid, "running")
            process_video(vid, flags, device_id, fps, drive)
            mark_status(vid, "done")
            print(f"[done] {vid.name}")
        except subprocess.CalledProcessError as e:
            mark_status(vid, "failed", note=str(e))
            print(f"[fail] {vid.name}: {e}")
        finally:
            with contextlib.suppress(Exception):
                lock_path.unlink()

if __name__ == "__main__":
    FLAGS     = os.getenv("FLAGS", "")
    DEVICE_ID = os.getenv("DEVICE_ID", "")
    FPS       = os.getenv("FPS", "30")
    DRIVE     = os.getenv("DRIVE", "/media/local_hdd")
    run_all(FLAGS, DEVICE_ID, FPS, DRIVE)
