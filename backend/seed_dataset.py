"""Regenerate the synthetic demo history: python seed_dataset.py [--reset]"""
import asyncio, sys
from modules.dataset import seed_dataset

if __name__ == '__main__':
    print(asyncio.run(seed_dataset(reset='--reset' in sys.argv)))
