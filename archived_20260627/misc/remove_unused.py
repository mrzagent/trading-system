#!/usr/bin/env python3
"""Remove unused and duplicate strategy files"""
import os
import shutil
from pathlib import Path
from datetime import datetime

# Files to remove (unused or duplicate)
FILES_TO_REMOVE = [
    # Duplicate - momentum_accel is the correct one
    "strategy_momentum_acceleration.py",
    
    # Duplicate - trend_breakout is the correct one  
    "strategy_trend_following_breakout.py",
    
    # Unused - not in orchestrator
    "strategy_mean_reversion_1h.py",
    "strategy_mean_reversion_4h.py",
    
    # Different strategy (momentum_rsi_confluence) - not used
    "strategy_momentum_rsi.py",
]

# Create backup directory
backup_dir = Path(f"archived_strategies_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
backup_dir.mkdir(exist_ok=True)

print("="*80)
print("REMOVING UNUSED/DUPLICATE STRATEGY FILES")
print("="*80)
print(f"\nBackup directory: {backup_dir}")
print()

trading_dir = Path(".")

for filename in FILES_TO_REMOVE:
    filepath = trading_dir / filename
    if filepath.exists():
        # Backup first
        backup_path = backup_dir / filename
        shutil.copy2(filepath, backup_path)
        print(f"[OK] Backed up: {filename}")
        
        # Remove original
        filepath.unlink()
        print(f"[OK] Removed: {filename}")
    else:
        print(f"[--] Not found: {filename}")

print()
print("="*80)
print("CLEANUP COMPLETE")
print("="*80)
print(f"\nArchived files to: {backup_dir}")
print("\nTo restore if needed:")
print(f"  copy {backup_dir}\\* .")

# List remaining strategy files
print("\nRemaining strategy files:")
remaining = sorted(trading_dir.glob("strategy_*.py"))
for f in remaining:
    size = f.stat().st_size / 1024
    print(f"  {f.name:<40} ({size:.1f} KB)")
print(f"\nTotal: {len(remaining)} strategy files")
