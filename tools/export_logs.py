#!/usr/bin/env python3
"""Export the production database to CSV files.

    python3 tools/export_logs.py [--db ~/.belt_marking/belt_marking.db] [--out ./exports]
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src',
                                'belt_marking_control'))

from belt_marking_control.core.db import ProductionDb  # noqa: E402

TABLES = ('jobs', 'production_log', 'alarm_history', 'audit', 'cycle_times', 'recipes')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='~/.belt_marking/belt_marking.db')
    ap.add_argument('--out', default='./exports')
    args = ap.parse_args()
    db = ProductionDb(args.db, read_only=True)
    out = os.path.join(args.out, datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(out, exist_ok=True)
    for t in TABLES:
        n = db.export_csv(t, os.path.join(out, f'{t}.csv'))
        print(f'{t:15s} {n:7d} rows')
    print('written to', out)


if __name__ == '__main__':
    main()
