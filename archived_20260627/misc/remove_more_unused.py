#!/usr/bin/env python3
"""Remove additional unused files"""
import os
import shutil
from pathlib import Path
from datetime import datetime

# Additional files to remove
FILES_TO_REMOVE = [
    # Unused strategy (vwap_reversion is the correct one)
    "strategy_vwap_mean_reversion.py",
]

# Test/debug scripts that were created during development
# (Keep only the essential audit files)
TEST_SCRIPTS_TO_REMOVE = [
    "audit_naming.py",
    "audit_final.py", 
    "audit_final2.py",
    "debug_registry.py",
    "test_registry.py",
    "remove_unused.py",
    "remove_more_unused.py",
]

# Create backup directory
backup_dir = Path(f"archived_misc_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
backup_dir.mkdir(exist_ok=True)

print("="*80)
print("REMOVING ADDITIONAL UNUSED FILES")
print("="*80)
print(f"\nBackup directory: {backup_dir}")
print()

trading_dir = Path(".")

# Remove unused strategy files
print("Strategy files:")
for filename in FILES_TO_REMOVE:
    filepath = trading_dir / filename
    if filepath.exists():
        backup_path = backup_dir / filename
        shutil.copy2(filepath, backup_path)
        filepath.unlink()
        print(f"  [OK] Removed: {filename}")
    else:
        print(f"  [--] Not found: {filename}")

# Remove test scripts
print("\nTest/debug scripts:")
for filename in TEST_SCRIPTS_TO_REMOVE:
    filepath = trading_dir / filename
    if filepath.exists():
        backup_path = backup_dir / filename
        shutil.copy2(filepath, backup_path)
        filepath.unlink()
        print(f"  [OK] Removed: {filename}")
    else:
        print(f"  [--] Not found: {filename}")

print()
print("="*80)
print("CLEANUP COMPLETE")
print("="*80)
print(f"\nArchived files to: {backup_dir}")

# List remaining files
print("\nRemaining strategy files:")
remaining = sorted(trading_dir.glob("strategy_*.py"))
for f in remaining:
    size = f.stat().st_size / 1024
    print(f"  {f.name:<40} ({size:.1f} KB)")
print(f"\nTotal: {len(remaining)} strategy files")

# Count test files
print("\nRemaining test/audit files:")
test_files = list(trading_dir.glob("test_*.py")) + list(trading_dir.glob("*_test.py")) + list(trading_dir.glob("audit*.py"))
for f in sorted(test_files):
    print(f"  {f.name}")
print(f"Total: {len(test_files)} test files")
