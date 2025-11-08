#!/usr/bin/env python3

import run_all_videos

def main():
    vids = sorted(run_all_videos.VIDEO_DIR.rglob("Near.*.mp4"))

    for vid in vids:
        if is_done(vid):
            try:
                vid.unlink()
                print(f"{vid} deleted successfully.")
            except FileNotFoundError:
                print(f"Error: {vid} not found.")
            except Exception as e:
                print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
