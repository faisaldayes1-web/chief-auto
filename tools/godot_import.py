"""Headless Godot import with a crash retry, for fresh checkouts and build machines.

Godot 4.3's headless --import has segfaulted intermittently on this project (exit 139 / -11): 4 times in about
30 runs on desktop1 on 2026-10-21/22, each time while several textures re-imported in parallel; 13 deliberate
repro runs (fresh worktrees, fresh profiles, modified textures, new class_name scripts) all passed. No backtrace was
ever printed, and the import resumes cleanly on the next run (the partially written .godot cache is reused).
The only importer warning is the non-finite normal in assets/cars3d_hd/forde_mustank.glb's LOD generation,
the code path PR #38 flagged; its LODs are now off (generate_lods=false: it is only seen up close).
project.godot now sets editor/import/use_multiple_threads=false (serial import). This wrapper also re-runs the import (up to 3 tries) when Godot dies on a signal, and fails on a real error exit.

Usage:  python tools/godot_import.py [godot_exe] [project_dir]
"""
import subprocess
import sys

GODOT = sys.argv[1] if len(sys.argv) > 1 else "C:/Tools/Godot/Godot_v4.3-stable_win64_console.exe"
PROJECT = sys.argv[2] if len(sys.argv) > 2 else "."


def main() -> int:
    for attempt in range(1, 4):
        code = subprocess.call([GODOT, "--headless", "--path", PROJECT, "--import"])
        if code == 0:
            print(f"import ok (attempt {attempt})")
            return 0
        crashed = code < 0 or code >= 128 or code in (0xC0000005, -1073741819)
        print(f"import attempt {attempt} exited {code}" + (" (crash), retrying" if crashed else ""))
        if not crashed:
            return code
    return 1


if __name__ == "__main__":
    sys.exit(main())
