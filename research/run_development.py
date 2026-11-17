"""Reproduce the released development + frozen holdout pipeline in isolation.

The live implementation can evolve without silently altering released results.
Use replay_frozen.py --suite holdout for the shorter independent holdout replay.
"""
from replay_frozen import replay

if __name__=='__main__':
    replay('all')
