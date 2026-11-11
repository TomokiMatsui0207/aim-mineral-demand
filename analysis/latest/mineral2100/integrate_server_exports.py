"""Validate new server exports; exclude uncomputed years before interpolation."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import numpy as np
import pandas as pd
from model import MINERALS, annual
from calculate_ldv_from_export import calculate
ROOT = Path(__file__).parent

def validated_exports(ldv, battery):
    if ldv.duplicated(['Sc', 'Sr', 'year', 'technology']).any():
        raise ValueError('Duplicate LDV keys')
    if battery.duplicated(['Sc', 'region', 'year']).any():
        raise ValueError('Duplicate battery keys')
    if set(ldv.Sc) != set(battery.Sc):
        raise ValueError('Scenario mismatch')
    numeric_ldv = ['service_bn_pkm_year', 'service_share_fraction', 'total_service_bn_pkm_year', 'demand_bn_pkm_year', 'output_minus_demand']
    numeric_bat = ['raw_battery_capacity', 'raw_battery_addition', 'lifetime_tn_years', 'model_time_interval']
    if not np.isfinite(ldv[numeric_ldv].to_numpy()).all() or not np.isfinite(battery[numeric_bat].to_numpy()).all():
        raise ValueError('Nonfinite input values')
    if (battery.model_time_interval < 0).any():
        raise ValueError('Negative time interval')
    dt = battery.groupby(['Sc', 'year']).model_time_interval.agg(['first', 'nunique']).reset_index()
    if not dt['nunique'].eq(1).all():
        raise ValueError('Regional time intervals differ')
    dt = dt.rename(columns={'first': 'model_time_interval'}).drop(columns='nunique')
    ldv = ldv.merge(dt, on=['Sc', 'year'], how='left', validate='many_to_one')
    if ldv.model_time_interval.isna().any():
        raise ValueError('Missing year metadata')
    discarded = ldv.loc[ldv.model_time_interval.eq(0)]
    if discarded[numeric_ldv].abs().to_numpy().max(initial=0) > 1e-08:
        raise ValueError('Nonzero service in unsolved year')
    if (battery.loc[battery.model_time_interval.eq(0), ['raw_battery_capacity', 'raw_battery_addition']].abs() > 1e-08).any().any():
        raise ValueError('Nonzero battery state in unsolved year')
    l = ldv.loc[ldv.model_time_interval.gt(0)].copy()
    b = battery.loc[battery.model_time_interval.gt(0)].copy()
    if (l.service_bn_pkm_year < 0).any() or (b.raw_battery_capacity < 0).any() or (b.raw_battery_addition < 0).any():
        raise ValueError('Negative activity')
    if not l.groupby(['Sc', 'year']).technology.nunique().eq(5).all():
        raise ValueError('Incomplete technologies')
    totals = l.groupby(['Sc', 'year']).agg(service=('service_bn_pkm_year', 'sum'), reported=('total_service_bn_pkm_year', 'first'), shares=('service_share_fraction', 'sum'), demand=('demand_bn_pkm_year', 'first'), residual=('output_minus_demand', 'first'))
    np.testing.assert_allclose(totals.service, totals.reported, rtol=1e-10, atol=1e-07)
    np.testing.assert_allclose(totals.shares, 1.0, atol=1e-10)
    np.testing.assert_allclose(totals.service - totals.demand, totals.residual, atol=1e-07)
    return (l, b, totals.reset_index())

def run():
    inp = ROOT / 'input/server_exports'
    out = ROOT / 'output/verified_exports'
    out.mkdir(exist_ok=True, parents=True)
    ldv = pd.concat([pd.read_csv(f) for f in sorted(inp.glob('mineral_LDV_*.csv')) if f.name in {'mineral_LDV_Baseline.csv', 'mineral_LDV_300C.csv'}], ignore_index=True)
    bat = pd.concat([pd.read_csv(f) for f in sorted(inp.glob('mineral_battery_*.csv'))], ignore_index=True)
    l, b, checks = validated_exports(ldv, bat)
    l.to_csv(out / 'LDV_verified_model_years.csv', index=False)
    b.to_csv(out / 'battery_verified_model_years_REGIONAL.csv', index=False)
    checks.to_csv(out / 'LDV_balance_checks.csv', index=False)
    sales = []
    for occupancy in [1.2, 1.5, 2.0]:
        for lifetime in [12, 15, 18]:
            sales.append(calculate(l, 19300.0, occupancy, lifetime, initial_year=2005, first_output_year=2020))
    flows = pd.concat(sales, ignore_index=True)
    flows.to_csv(out / 'LDV_stock_sales_by_technology_SENSITIVITY.csv', index=False)
    central = flows.loc[flows.occupancy_assumed.eq(1.5) & flows.lifetime_years_assumed.eq(12)].copy()
    central.to_csv(out / 'LDV_stock_sales_central_ASSUMPTIONS.csv', index=False)
    annual_service = []
    for (sc, tech), g in l.groupby(['Sc', 'technology']):
        s = annual(g.set_index('year').service_bn_pkm_year, 2020, 2100)
        annual_service.extend([[sc, y, tech, v] for y, v in s.items()])
    annual_service = pd.DataFrame(annual_service, columns=['Sc', 'year', 'technology', 'service_bn_pkm_year'])
    annual_service['LDV_service_share'] = annual_service.service_bn_pkm_year / annual_service.groupby(['Sc', 'year']).service_bn_pkm_year.transform('sum')
    annual_service.to_csv(out / 'LDV_annual_service_and_shares.csv', index=False)
    world = b.groupby(['Sc', 'year'], as_index=False).agg(raw_battery_capacity=('raw_battery_capacity', 'sum'), raw_battery_addition=('raw_battery_addition', 'sum'), model_time_interval=('model_time_interval', 'first'), min_lifetime=('lifetime_tn_years', 'min'), max_lifetime=('lifetime_tn_years', 'max'))
    world['native_addition_times_model_interval'] = world.raw_battery_addition * world.model_time_interval
    world['period_start'] = world.year - world.model_time_interval + 1
    world['units_status'] = 'native units; GW and GWh labels reuse same raw capacity; duration unknown'
    world.to_csv(out / 'battery_WORLD_NATIVE_units.csv', index=False)
    energy = []
    for sc, g in world.groupby('Sc'):
        s = annual(g.set_index('year').raw_battery_capacity, 2020, 2100)
        for h in [2.0, 4.0, 6.0, 6.2113]:
            energy.extend([[sc, y, h, v * h, 'assumes raw capacity is GW; duration is external assumption'] for y, v in s.items()])
    pd.DataFrame(energy, columns=['Sc', 'year', 'hours_assumed', 'GWh_if_raw_is_GW', 'status']).to_csv(out / 'battery_energy_duration_SENSITIVITY.csv', index=False)
    data = next((ROOT / 'originals').rglob('EV_MI_MS_Recycling.xlsx'))
    body = pd.read_excel(data, 'MI_Vehicle', index_col=0)
    battery = pd.read_excel(data, 'MI_Battery', index_col=0)
    motor = pd.read_excel(data, 'MI_Motor', index_col=0)
    motor_share = pd.read_excel(data, 'MS_Motor', index_col=0).loc['MS']
    size = pd.read_excel(data, 'Vehicle_Stat', index_col=0).loc['Battery']
    shares = pd.read_csv(ROOT / 'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv')
    from import_workbooks import NAMES
    coverage = set((NAMES[str(x)] for tab in [body, battery, motor] for x in tab.index))
    demand = []
    for r in central.loc[central.technology.isin(['TP_BEV', 'TP_PHV'])].itertuples():
        vehicle = 'BEV' if r.technology == 'TP_BEV' else 'PHEV'
        chemistry = shares.loc[shares.year.eq(r.year)].set_index('Battery_type').share
        for m in sorted(coverage):
            parts = []
            for name, row in body.iterrows():
                if NAMES[name] == m:
                    parts.append(float(row[vehicle]))
            for name, row in battery.iterrows():
                if NAMES[name] == m:
                    parts.append(float(size[vehicle]) * sum((float(row[t]) * float(chemistry[t]) for t in chemistry.index)))
            for name, row in motor.iterrows():
                if NAMES[name] == m:
                    parts.append(sum((float(row[t]) * float(motor_share[t]) for t in ['PM', 'Ind'])))
            intensity = sum(parts) / 1000000.0
            demand.append([r.Sc, r.year, vehicle, m, r.new, intensity, r.new * intensity, 'Penelope_reported_scope; other components unreported assumed zero; not 40-mineral total'])
    d = pd.DataFrame(demand, columns=['Sc', 'year', 'vehicle_type', 'mineral', 'vehicles_sold_assumed', 't_per_vehicle', 'demand_t_year', 'scope'])
    d = d.sort_values(['Sc', 'vehicle_type', 'mineral', 'year'])
    d['cumulative_2020_through_year_t'] = d.groupby(['Sc', 'vehicle_type', 'mineral']).demand_t_year.cumsum()
    d.to_csv(out / 'BEV_PHEV_13_minerals_REPORTED_SCOPE.csv', index=False)
    pd.DataFrame({'mineral': MINERALS, 'in_penelope_vehicle_scope': [m in coverage for m in MINERALS], 'whole_vehicle_total_complete': False}).to_csv(out / 'vehicle_mineral_coverage.csv', index=False)
    summary = annual_service.loc[annual_service.year.isin([2020, 2050, 2100])].pivot(index=['Sc', 'year'], columns='technology', values='LDV_service_share').reset_index()
    summary.to_csv(out / 'LDV_share_summary.csv', index=False)
    print(summary.to_string(index=False))
    print('Valid model years per scenario:', l.groupby('Sc').year.nunique().to_dict())
    print('Unsolved LDV rows excluded:', len(ldv) - len(l))
    print('Maximum absolute LDV output/demand residual:', checks.residual.abs().max())
if __name__ == '__main__':
    run()
