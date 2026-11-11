"""Compare old/new ALL-sector conditional ledgers; preserve cases and missing data."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd
KEY = ['Sc', 'statistic', 'grid_case', 'case', 'mineral', 'year']
CASE = KEY[:-1]
VALUES = ['power', 'stationary_battery', 'hydrogen', 'vehicles_explicit_t_year', 'grid_CuAl_t_year', 'other_low_t_year', 'other_high_t_year', 'conditional_total_low_t_year', 'conditional_total_high_t_year']

def delta(old, new):
    if old.duplicated(KEY).any() or new.duplicated(KEY).any():
        raise ValueError('Duplicate case/year keys')
    if not set(KEY + VALUES).issubset(old.columns) or not set(KEY + VALUES).issubset(new.columns):
        raise ValueError('Required ledger columns missing')
    d = old[KEY + VALUES].merge(new[KEY + VALUES], on=KEY, how='outer', suffixes=('_old', '_new'), indicator=True, validate='one_to_one')
    if not d['_merge'].eq('both').all():
        raise ValueError('Old/new case coverage differs; do not compare changed methods as a model-only update')
    rows = []
    for metric in VALUES:
        q = d[KEY + [metric + '_old', metric + '_new']].rename(columns={metric + '_old': 'old_t_year', metric + '_new': 'new_t_year'})
        q['metric'] = metric
        q['change_t_year'] = q.new_t_year - q.old_t_year
        valid = q.old_t_year.notna() & q.new_t_year.notna()
        denom = q.old_t_year.ne(0) & valid
        q['change_percent'] = np.where(denom, 100 * q.change_t_year / q.old_t_year.where(denom), np.nan)
        q['comparison_status'] = np.select([~valid, valid & q.old_t_year.eq(0) & q.new_t_year.eq(0), valid & q.old_t_year.eq(0) & q.new_t_year.ne(0)], ['missing_not_zero', 'both_zero', 'zero_to_nonzero'], default='comparable')
        rows.append(q)
    return pd.concat(rows, ignore_index=True)

def cumulative(frame, endpoints=(2050, 2100)):
    rows = []
    for (sc, stat, grid, case, m, metric), g in frame.groupby(CASE + ['metric']):
        if g.year.min() != 2020 or set(g.year) != set(range(2020, 2101)):
            raise ValueError('Require full annual 2020--2100 coverage')
        for end in endpoints:
            q = g.loc[g.year.le(end)]
            old = q.old_t_year.sum() if q.old_t_year.notna().all() else np.nan
            new = q.new_t_year.sum() if q.new_t_year.notna().all() else np.nan
            rows.append(dict(Sc=sc, statistic=stat, grid_case=grid, case=case, mineral=m, metric=metric, start_year=2020, end_year=end, old_cumulative_t=old, new_cumulative_t=new, change_t=new - old, change_percent=100 * (new - old) / old if np.isfinite(old) and np.isfinite(new) and (old != 0) else np.nan, missing_years_old=int(q.old_t_year.isna().sum()), missing_years_new=int(q.new_t_year.isna().sum())))
    return pd.DataFrame(rows)

def run():
    p = argparse.ArgumentParser()
    p.add_argument('old', type=Path)
    p.add_argument('new', type=Path)
    p.add_argument('destination', type=Path)
    a = p.parse_args()
    if a.destination.exists():
        raise SystemExit('Destination exists; choose a new directory')
    d = delta(pd.read_csv(a.old), pd.read_csv(a.new))
    c = cumulative(d)
    a.destination.mkdir(parents=True)
    d.to_csv(a.destination / 'annual_old_new_differences.csv.gz', index=False, compression='gzip')
    c.to_csv(a.destination / 'cumulative_old_new_differences.csv', index=False)
    with pd.ExcelWriter(a.destination / 'old_new_comparison.xlsx') as w:
        d.loc[d.year.isin([2020, 2030, 2050, 2100])].to_excel(w, sheet_name='主要年_部門鉱物差', index=False)
        c.to_excel(w, sheet_name='累積2020_2050_2100', index=False)
    (a.destination / 'manifest.json').write_text(json.dumps({'input_hashes': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [a.old, a.new]}, 'requires_same_intensities_boundaries_and_cases': True, 'primary_secondary_scope_not_resolved': True}, indent=2))
if __name__ == '__main__':
    run()
