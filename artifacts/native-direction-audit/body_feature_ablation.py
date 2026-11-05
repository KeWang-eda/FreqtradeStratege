"""Compatibility entry for the canonical native prediction-control runner."""
from tools.run_native_direction_control import cli

if __name__ == '__main__':
    cli(default_candidate='body_ablation')
