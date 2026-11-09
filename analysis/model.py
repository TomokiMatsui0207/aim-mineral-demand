"""Auditable preparatory calculations; never interpret missing mineral data as zero."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

MINERALS = 'Ag Al B C Cd Ce Co Cr Cu Dy Fe Ga Ge Hf In Ir La Li Mg Mn Mo Nb Nd Ni Pb Pr Pt Sc Se Si Sn Ta Tb Te Ti V W Y Zn Zr'.split()


def annual(series, start, end):
    """Linear interpolation of point observations, no extrapolation or silent gaps."""
    series = series.sort_index()
    if series.index.duplicated().any() or not np.isfinite(series.to_numpy()).all():
        raise ValueError('Duplicate years or nonfinite observations')
    if series.index.min() > start or series.index.max() < end:
        raise ValueError(f'Missing endpoint for {start}--{end}')
    return series.reindex(range(start, end + 1)).interpolate(method='index', limit_area='inside')


def stock_flows(target, lifetime):
    """Fixed-life cohorts, initially uniform ages; oldest-first premature retirement.

    First year is initial stock, not new demand. New cohorts also retire and are
    replaced after lifetime, including repeated replacement through 2100.
    """
    if not isinstance(lifetime, int) or lifetime < 1:
        raise ValueError('Lifetime must be a positive integer')
    years = list(target.index)
    if years != list(range(years[0], years[-1] + 1)):
        raise ValueError('Target must be consecutive annual years')
    if not np.isfinite(target.to_numpy()).all() or (target < 0).any():
        raise ValueError('Target stock must be finite and nonnegative')
    y0, initial = years[0], float(target.iloc[0])
    cohorts = {y0-age: initial/lifetime for age in range(lifetime)}
    rows = []
    previous = initial
    for year in years[1:]:
        retire = 0.
        for vintage in list(cohorts):
            if year-vintage >= lifetime:
                retire += cohorts.pop(vintage)
        remaining = sum(cohorts.values())
        early = max(0., remaining-float(target.loc[year]))
        take_left = early
        for vintage in sorted(cohorts):
            take = min(cohorts[vintage], take_left)
            cohorts[vintage] -= take
            take_left -= take
        retire += early
        additions = max(0., float(target.loc[year])-sum(cohorts.values()))
        cohorts[year] = additions
        end_stock = sum(cohorts.values())
        residual = end_stock-previous-additions+retire
        if not np.isclose(end_stock, target.loc[year], atol=1e-5, rtol=1e-10):
            raise AssertionError('Cohort mass balance failed')
        rows.append((year, end_stock, additions, retire, early, residual))
        previous = end_stock
    return pd.DataFrame(rows, columns=['year','stock','new','retired','early_retired','balance_residual'])


def strict_material_demand(activity, coefficients):
    """activity: Sc/year/component/unit/quantity; coeff: component/unit/mineral/t_per_unit.

    Each activity component must have an explicit coefficient for ALL 40 minerals.
    Missing coefficients propagate to incomplete totals. Explicit zero requires a
    documented evidence/status in the supplied coefficient table.
    """
    keys = ['component','unit','mineral']
    if coefficients.duplicated(keys).any():
        raise ValueError('Duplicate intensity coefficients')
    if not set(coefficients.mineral).issubset(MINERALS):
        raise ValueError('Unknown mineral')
    activity = activity.copy()
    if (activity.quantity < 0).any() or not np.isfinite(activity.quantity).all():
        raise ValueError('Activity quantities must be finite/nonnegative')
    values = pd.to_numeric(coefficients.t_per_unit, errors='raise')
    if (values.dropna() < 0).any() or np.isinf(values.dropna()).any():
        raise ValueError('Intensities must be nonnegative and finite')
    coefficients = coefficients.assign(t_per_unit=values)
    expanded = activity.merge(pd.DataFrame({'mineral':MINERALS}), how='cross')
    expanded = expanded.merge(coefficients, on=keys, how='left', validate='many_to_one')
    expanded['demand_t'] = expanded.quantity*expanded.t_per_unit
    expanded['missing'] = expanded.t_per_unit.isna()
    totals = expanded.groupby(['Sc','year','mineral'], as_index=False).agg(
        known_subtotal_t=('demand_t',lambda s:s.sum(min_count=1)),
        missing_components=('missing','sum'))
    totals['complete_demand_t'] = totals.known_subtotal_t.where(totals.missing_components.eq(0))
    return expanded, totals


def run(aim_path, out):
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(aim_path)
    df = df.loc[df.Sr.eq('World')]
    if df.duplicated(['Sc','Sv','Y5']).any():
        raise ValueError('Duplicate AIM rows')
    drivers, osd, vehicle, grid, battery, checks = [], [], [], [], [], []
    for sc, group in df.groupby('Sc'):
        def get(var):
            s = group.loc[group.Sv.eq(var)].set_index('Y5').value
            return annual(s, 2020, 2100)
        gdp, pop, ele, ldv = (get(v) for v in ['GDP_PPP','Pop','Fin_Ene_Ele','Ene_Ser_Tra_Pss_Roa_LDV'])
        for year in gdp.index:
            drivers.append([sc,year,gdp[year],pop[year],ele[year],ldv[year]])
            # These are analyst-selected sensitivities, NOT Penelope's OECD rates.
            for rate in [0., .005, .01]:
                osd.append([sc,year,rate,gdp[year]/gdp[2020]*(1-rate)**(year-2020),pop[year]/pop[2020]])
        for occupancy in [1.2,1.5,2.]:
            # bn passenger-km / (km/vehicle/year * passengers/vehicle)
            stock = ldv*1e9/(19300.*occupancy)
            for life in [12,15,18]:
                f = stock_flows(stock,life)
                f.insert(0,'Sc',sc);f['occupancy']=occupancy;f['km_per_vehicle_year']=19300.;f['lifetime']=life
                vehicle.append(f)
        # Grid stock proxy: separate observed 2021 TX/DX anchors; no APS mapping.
        for level, base in [('transmission',5.3e6),('distribution',71.7e6)]:
            for elasticity in [.5,1.]:
                target = base*(ele.loc[2021:]/ele[2021])**elasticity
                f = stock_flows(target,40)
                f.insert(0,'Sc',sc);f['level']=level;f['elasticity']=elasticity;f['lifetime']=40
                grid.append(f)
        power = group.loc[group.Sv.eq('Cap_Ele_Sto_Bat')].set_index('Y5').value.sort_index()
        energy = group.loc[group.Sv.eq('Cap_Ele_Sto_Cap')].set_index('Y5').value
        common = power.index.intersection(energy.index)
        checks.append({'Sc':sc,'check':'reported_storage_GWh_equals_battery_GW',
                       'result':bool(np.allclose(power.loc[common],energy.loc[common])),
                       'interpretation':'Runtime global code reuses ELECAP_BAT vs_l for GW and GWh-labelled outputs without energy conversion; duration not established'})
        # Sparse early battery capacity is NOT filled with zero. Consequently no
        # battery stock-flow simulation is produced before initial stock is known.
        for year, gw in power.items():
            for hours in [2.,4.,6.]:
                battery.append([sc,year,gw,hours,gw*hours,'duration_assumption_not_AIM_setting'])
    pd.DataFrame(drivers,columns=['Sc','year','GDP_PPP_billion_2010USD','population_original_unit','electricity_original_unit','LDV_bn_pkm_year']).to_csv(out/'annual_drivers.csv',index=False)
    pd.DataFrame(osd,columns=['Sc','year','annual_intensity_reduction_assumption','GDP_demand_index_2020_1','population_index_2020_1']).to_csv(out/'other_sector_indices.csv',index=False)
    pd.concat(vehicle,ignore_index=True).to_csv(out/'vehicle_total_stock_sales_SENSITIVITY.csv',index=False)
    pd.concat(grid,ignore_index=True).to_csv(out/'grid_stock_additions_SENSITIVITY.csv',index=False)
    pd.DataFrame(battery,columns=['Sc','year','battery_GW','duration_hours_assumption','battery_GWh_assumed','status']).to_csv(out/'battery_energy_SENSITIVITY.csv',index=False)
    pd.DataFrame(checks).to_csv(out/'checks.csv',index=False)
    shares = df.loc[df.Sv.str.startswith('Tec_sto_Sha_Tra_Pss_Roa_')]
    shares.to_csv(out/'vehicle_technology_shares_ROAD_SERVICE.csv',index=False)
    audit = shares.groupby(['Sc','Y5']).value.agg(['sum','count']).reset_index()
    audit['reported_sum_is_one']=np.isclose(audit['sum'],1.,atol=1e-7)
    audit['basis']='verified transport-service share; all passenger road including bus; fraction 0..1 despite percent label'
    audit.to_csv(out/'vehicle_share_checks.csv',index=False)
    # Convert average annual additions for endpoint periods to interval totals.
    basis_path = Path(__file__).parent/'input'/'units_and_time_basis.csv'
    if basis_path.exists():
        basis=pd.read_csv(basis_path)
        allowed=basis.loc[basis.time_basis.eq('five_year_average_ending_at_label') & basis.declared_unit.eq('GW/yr'),'variable']
        adds=df.loc[df.Sv.isin(allowed) & df.Sv.str.startswith('Cap_Add_Ele_') & df.Y5.between(2025,2100)].copy()
        adds['period_start']=adds.Y5-4;adds['period_end']=adds.Y5
        adds['interval_addition_GW']=adds.value*5
        adds['warning']='Contains aggregate and child technologies: do not sum all rows'
        adds.to_csv(out/'power_interval_additions.csv',index=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--aim',required=True)
    parser.add_argument('--out',default=str(Path(__file__).parent/'output'))
    args=parser.parse_args()
    run(args.aim,Path(args.out))
