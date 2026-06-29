#!/usr/bin/env python3
"""Audit naming consistency across trading system files"""
import os
import re
from pathlib import Path

def extract_strategy_keys_from_orchestrator():
    """Extract strategy keys from STRATEGY_CONFIG in orchestrator.py"""
    with open('orchestrator.py', 'r') as f:
        content = f.read()
    
    # Find STRATEGY_CONFIG dictionary
    pattern = r'"([a-z_]+)":\s*\{'
    matches = re.findall(pattern, content)
    return matches

def extract_strategy_names_from_files():
    """Extract STRATEGY constants from all strategy files"""
    strategies = {}
    for file in Path('.').glob('strategy_*.py'):
        with open(file, 'r') as f:
            content = f.read()
        
        # Find STRATEGY = "..."
        match = re.search(r'STRATEGY\s*=\s*"([^"]+)"', content)
        if match:
            strategy_name = match.group(1)
            strategies[file.name] = strategy_name
    return strategies

def extract_allowed_strategies():
    """Extract ALLOWED_STRATEGIES from signal_integrator.py"""
    with open('signal_integrator.py', 'r') as f:
        content = f.read()
    
    # Find the list
    pattern = r"ALLOWED_STRATEGIES\s*=\s*\[([^\]]+)\]"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        list_content = match.group(1)
        # Extract quoted strings
        strategies = re.findall(r"'([^']+)'", list_content)
        return strategies
    return []

def extract_risk_config_strategies():
    """Extract strategy keys from strategy_risk_config.py"""
    with open('strategy_risk_config.py', 'r') as f:
        content = f.read()
    
    # Find STRATEGY_RISK_PARAMS keys
    pattern = r"'([a-z_]+)':\s*StrategyRiskParams"
    matches = re.findall(pattern, content)
    return matches

def extract_registry_modules():
    """Extract STRATEGY_MODULES from strategy_registry.py"""
    with open('strategy_registry.py', 'r') as f:
        content = f.read()
    
    # Find the list
    pattern = r"STRATEGY_MODULES:\s*list\[str\]\s*=\s*\[([^\]]+)\]"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        list_content = match.group(1)
        # Extract quoted strings
        modules = re.findall(r'"([^"]+)"', list_content)
        return modules
    return []

print("="*80)
print("TRADING SYSTEM NAMING CONSISTENCY AUDIT")
print("="*80)

print("\n1. STRATEGY_CONFIG keys in orchestrator.py:")
print("-" * 50)
orchestrator_keys = extract_strategy_keys_from_orchestrator()
for key in sorted(orchestrator_keys):
    print(f"  - {key}")

print("\n2. STRATEGY constants in strategy_*.py files:")
print("-" * 50)
file_strategies = extract_strategy_names_from_files()
for filename, strategy in sorted(file_strategies.items()):
    print(f"  {filename:<40} -> {strategy}")

print("\n3. ALLOWED_STRATEGIES in signal_integrator.py:")
print("-" * 50)
allowed = extract_allowed_strategies()
for s in sorted(allowed):
    print(f"  - {s}")

print("\n4. STRATEGY_RISK_PARAMS keys:")
print("-" * 50)
risk_keys = extract_risk_config_strategies()
for key in sorted(risk_keys):
    print(f"  - {key}")

print("\n5. STRATEGY_MODULES in strategy_registry.py:")
print("-" * 50)
registry_modules = extract_registry_modules()
for mod in sorted(registry_modules):
    print(f"  - {mod}")

# Check for inconsistencies
print("\n" + "="*80)
print("CONSISTENCY CHECKS")
print("="*80)

# Check 1: orchestrator keys vs file STRATEGY constants
print("\nCheck 1: STRATEGY_CONFIG vs File STRATEGY constants")
print("-" * 50)
file_strategy_values = set(file_strategies.values())
orchestrator_set = set(orchestrator_keys)
missing_in_files = orchestrator_set - file_strategy_values
extra_in_files = file_strategy_values - orchestrator_set
if missing_in_files:
    print(f"  WARNING: In orchestrator but no file has STRATEGY={missing_in_files}")
if extra_in_files:
    print(f"  WARNING: Files have STRATEGY not in orchestrator: {extra_in_files}")
if not missing_in_files and not extra_in_files:
    print("  ✓ All STRATEGY constants match STRATEGY_CONFIG keys")

# Check 2: orchestrator keys vs ALLOWED_STRATEGIES
print("\nCheck 2: STRATEGY_CONFIG vs ALLOWED_STRATEGIES")
print("-" * 50)
allowed_set = set(allowed)
missing_allowed = orchestrator_set - allowed_set
if missing_allowed:
    print(f"  WARNING: In orchestrator but not in ALLOWED_STRATEGIES: {missing_allowed}")
else:
    print("  ✓ All orchestrator strategies are in ALLOWED_STRATEGIES")

# Check 3: orchestrator keys vs RISK_PARAMS
print("\nCheck 3: STRATEGY_CONFIG vs STRATEGY_RISK_PARAMS")
print("-" * 50)
risk_set = set(risk_keys)
missing_risk = orchestrator_set - risk_set
if missing_risk:
    print(f"  WARNING: In orchestrator but no risk params: {missing_risk}")
else:
    print("  ✓ All orchestrator strategies have risk params")

# Check 4: File naming vs STRATEGY constant
print("\nCheck 4: Filename vs STRATEGY constant naming")
print("-" * 50)
for filename, strategy in sorted(file_strategies.items()):
    # Extract base name (remove strategy_ prefix and .py suffix)
    base_name = filename.replace('strategy_', '').replace('.py', '')
    # Check if strategy constant matches or is related
    if strategy.replace('_', '') != base_name.replace('_', ''):
        # Check for common patterns
        if 'momentum' in base_name and 'momentum' in strategy:
            continue
        if 'mean_reversion' in base_name and 'mean_reversion' in strategy:
            continue
        print(f"  NOTE: {filename} has STRATEGY='{strategy}' (filename='{base_name}')")

# Check 5: Registry modules vs actual files
print("\nCheck 5: STRATEGY_MODULES vs actual files")
print("-" * 50)
actual_files = set(f.stem for f in Path('.').glob('strategy_*.py'))
registry_set = set(registry_modules)
missing_files = registry_set - actual_files
extra_files = actual_files - registry_set
if missing_files:
    print(f"  WARNING: In registry but file missing: {missing_files}")
if extra_files:
    print(f"  NOTE: Files not in registry: {extra_files}")
if not missing_files:
    print("  ✓ All registry modules exist as files")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"Total strategies in orchestrator: {len(orchestrator_keys)}")
print(f"Total strategy files: {len(file_strategies)}")
print(f"Total allowed strategies: {len(allowed)}")
print(f"Total risk configs: {len(risk_keys)}")
print(f"Total registry modules: {len(registry_modules)}")
