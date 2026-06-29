#!/usr/bin/env python3
"""Show current strategy enable/disable status."""

from orchestrator import STRATEGY_CONFIG, load_strategy_state, is_strategy_enabled


def main():
    # Load current state
    state = load_strategy_state()
    
    # If no state file exists, show all as enabled
    if not state:
        print('='*60)
        print('STRATEGY STATUS')
        print('='*60)
        print()
        print('Note: .strategy_state.json does not exist yet.')
        print('All strategies default to ENABLED.')
        print()
        print('To disable strategies, use the dashboard toggle at:')
        print('  http://localhost:3001/strategies')
        print()
        print('-'*60)
        print('ALL STRATEGIES (10 total) - ALL ENABLED')
        print('-'*60)
        for name, config in STRATEGY_CONFIG.items():
            tf = config["timeframe"]
            style = config["style"]
            print(f'  [ENABLED]  {name:25} ({tf}, {style})')
        print()
        return
    
    # State file exists - show actual status
    enabled = []
    disabled = []
    
    for name in STRATEGY_CONFIG.keys():
        if is_strategy_enabled(name, state):
            enabled.append(name)
        else:
            disabled.append(name)
    
    print('='*60)
    print('STRATEGY STATUS')
    print('='*60)
    print()
    print(f'Total: {len(STRATEGY_CONFIG)} strategies')
    print(f'Enabled: {len(enabled)}')
    print(f'Disabled: {len(disabled)}')
    print()
    
    if enabled:
        print('-'*60)
        print(f'ENABLED STRATEGIES ({len(enabled)})')
        print('-'*60)
        for name in enabled:
            config = STRATEGY_CONFIG[name]
            tf = config["timeframe"]
            style = config["style"]
            print(f'  [ON]  {name:25} ({tf}, {style})')
        print()
    
    if disabled:
        print('-'*60)
        print(f'DISABLED STRATEGIES ({len(disabled)})')
        print('-'*60)
        for name in disabled:
            config = STRATEGY_CONFIG[name]
            tf = config["timeframe"]
            style = config["style"]
            print(f'  [OFF] {name:25} ({tf}, {style})')
        print()


if __name__ == "__main__":
    main()
