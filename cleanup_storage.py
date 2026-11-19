"""
Storage Cleanup Script for @OtakuSnapster repository.
Preserves:
- The 4 active scheduled master videos & their metadata in output/
- Code, configs, assets, and state files
Deletes:
- All old test outputs in output/
- All temporary segments in temp/
- All harvested raw inputs in input/
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
INPUT_DIR = ROOT / "input"
TEMP_DIR = ROOT / "temp"

# Master files to strictly KEEP in output/
KEEP_PATTERNS = [
    "edit_ranking_the_mentalist_ep03_master",
    "song_ranking_paparazzi_master",
    "edit_ranking_ramayana_master",
    "edit_ranking_my_demon_ep_6_master",
]

def clean_output():
    if not OUTPUT_DIR.exists():
        return
    deleted_count = 0
    bytes_freed = 0
    for item in list(OUTPUT_DIR.iterdir()):
        if item.is_dir():
            import shutil
            shutil.rmtree(item, ignore_errors=True)
            print(f"Removed directory: {item.name}")
            continue
        
        # Check if file belongs to any KEEP pattern
        keep = any(item.name.startswith(p) for p in KEEP_PATTERNS)
        if not keep:
            sz = item.stat().st_size
            item.unlink()
            deleted_count += 1
            bytes_freed += sz
    print(f"[Cleanup] Output cleaned: {deleted_count} files removed ({bytes_freed / (1024*1024):.2f} MB freed).")

def clean_input():
    if not INPUT_DIR.exists():
        return
    deleted_count = 0
    bytes_freed = 0
    for item in list(INPUT_DIR.iterdir()):
        if item.is_dir():
            import shutil
            shutil.rmtree(item, ignore_errors=True)
            continue
        sz = item.stat().st_size
        item.unlink()
        deleted_count += 1
        bytes_freed += sz
    print(f"[Cleanup] Input cleaned: {deleted_count} raw clips removed ({bytes_freed / (1024*1024):.2f} MB freed).")

def clean_temp():
    if not TEMP_DIR.exists():
        return
    deleted_count = 0
    bytes_freed = 0
    for item in list(TEMP_DIR.iterdir()):
        if item.is_dir():
            import shutil
            shutil.rmtree(item, ignore_errors=True)
            continue
        sz = item.stat().st_size
        item.unlink()
        deleted_count += 1
        bytes_freed += sz
    print(f"[Cleanup] Temp cleaned: {deleted_count} temporary files removed ({bytes_freed / (1024*1024):.2f} MB freed).")

if __name__ == "__main__":
    clean_output()
    clean_input()
    clean_temp()
