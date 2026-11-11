"""Convert the NEW LDV-only service output to annual cohort flows.

No conversion of the old bus-inclusive road-service shares is attempted.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from model import annual, stock_flows
TECHNOLOGIES = {'TP_ICE', 'TP_HEV', 'TP_PHV', 'TP_BEV', 'TP_FCV'}

def calculate(frame, mileage, occupancy, lifetime, *, initial_year=2020, first_output_year=2021):
    if mileage <= 0 or occupancy <= 0:
        raise ValueError('Mileage and occupancy must be positive')
    if frame.duplicated(['Sc', 'Sr', 'year', 'technology']).any():
        raise ValueError('Duplicate rows')
    if set(frame.technology) != TECHNOLOGIES:
        raise ValueError('All 5 LDV technologies, including zeros, are required')
    if not frame.Sr.eq('World').all():
        raise ValueError('World rows required')
    if 'total_service_bn_pkm_year' in frame and frame.total_service_bn_pkm_year.le(0).any():
        raise ValueError('Zero total-service rows present: exclude unsolved years using model_time_interval before conversion')
    if not np.isfinite(frame.service_bn_pkm_year).all() or (frame.service_bn_pkm_year < 0).any():
        raise ValueError('Service values must be nonnegative and finite')
    if not frame.groupby(['Sc', 'year']).technology.nunique().eq(5).all():
        raise ValueError('Missing technology/year rows')
    rows = []
    for sc, group in frame.groupby('Sc'):
        for technology, g in group.groupby('technology'):
            service = annual(g.set_index('year').service_bn_pkm_year, initial_year, 2100)
            target = service * 1000000000.0 / (mileage * occupancy)
            flows = stock_flows(target, lifetime)
            flows = flows.loc[flows.year.ge(first_output_year)].copy()
            flows['Sc'] = sc
            flows['technology'] = technology
            flows['mileage_km_year_assumed'] = mileage
            flows['occupancy_assumed'] = occupancy
            flows['lifetime_years_assumed'] = lifetime
            flows['initial_age_distribution'] = f'{initial_year}_uniform_ASSUMPTION'
            rows.append(flows)
    return pd.concat(rows, ignore_index=True)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('csv', nargs='+', type=Path)
    p.add_argument('--out', type=Path, default=Path('LDV_sales_from_verified_service.csv'))
    p.add_argument('--mileage', type=float, default=19300)
    p.add_argument('--occupancy', type=float, default=1.5)
    p.add_argument('--lifetime', type=int, default=12)
    a = p.parse_args()
    frame = pd.concat([pd.read_csv(f) for f in a.csv], ignore_index=True)
    calculate(frame, a.mileage, a.occupancy, a.lifetime).to_csv(a.out, index=False)
