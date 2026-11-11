"""All-sector 2020--2100 conditional ledger, both AIM scenarios.
Reported-scope exclusions remain in the calibrated complement; they are not physical zeros.
No global full40 completion claim. No new observed supply data or gross/primary reconciliation.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from model import MINERALS, annual
from grid_penelope_2100 import calculate as grid_calculate
ROOT = Path(__file__).resolve().parent

def growth_multiplier(gdp_ratio, decadal_change):
    if not np.isfinite([gdp_ratio, decadal_change]).all() or gdp_ratio <= 0 or decadal_change <= -1:
        raise ValueError('Invalid growth factor')
    return gdp_ratio * (1 + decadal_change) ** 0.1
MAPPINGS = [('Coa', 'coal', 'coal'), ('Gas', 'gas', 'gas'), ('Oil', 'oil', 'oil'), ('Hyp', 'hydropower', 'hydropower'), ('Bio', 'Biomass', 'Biomass'), ('Geo', 'Geothermal', 'Geothermal'), ('Nuc', 'Nuclear', 'Nuclear'), ('Win_Ons', 'wind', 'Onshore'), ('Win_Off', 'wind', 'Offshore'), ('SolarPV', 'Solar', 'PV')]

def wei_coefficients(statistic):
    a = pd.read_csv(ROOT / 'input/imported/wei_intensity_rows.csv')
    a = a.loc[a.reported_average.notna()]
    if a.duplicated(['category', 'technology', 'material']).any():
        raise ValueError('Ambiguous MI')
    lookup = {(r.category, r.technology, r.material): r.reported_minimum if statistic == 'minimum' and pd.notna(r.reported_minimum) else r.reported_average for r in a.itertuples()}

    def one(cat, tech, m):
        if (cat, tech, m) in lookup:
            return (lookup[cat, tech, m], True)
        if m == 'Fe' and (cat, tech, 'Steel') in lookup:
            return (0.9786 * lookup[cat, tech, 'Steel'], True)
        return (0.0, False)

    def solar(tech, m):
        v, p = one('Solar', tech, m)
        return (v, p) if p else one('Solar', 'PV', m)
    rows = []
    for suffix, cat, tech in MAPPINGS:
        for m in MINERALS:
            if cat == 'Solar':
                vals = [(s, *solar(t, m)) for t, s in {'a-Si': 0.003, 'c-Si': 0.954, 'CdTe': 0.024, 'CIGS': 0.019}.items()]
                val = sum((s * v for s, v, p in vals))
                reported = any((p for s, v, p in vals))
            else:
                val, reported = one(cat, tech, m)
                if cat == 'wind':
                    v, p = one(cat, 'Not defined', m)
                    val += v
                    reported = reported or p
            rows.append(dict(sector='power', technology=suffix, mineral=m, statistic=statistic, intensity=val, coefficient_reported=reported, unit='t/GW'))
    shares = pd.read_csv(ROOT / 'input/imported/wei_S11_Market_share.csv')
    shares.technology = shares.technology.ffill()
    for sec, sourcecat, mi_cat, unit in [('hydrogen', 'Hydrogen by Electricity', 'Electric hydrogen', 't/GW'), ('stationary_battery', 'Electricity Storage', 'Energy storage', 'Wei_table_as_t/GW_REPRODUCTION')]:
        ss = shares.loc[shares.technology.eq(sourcecat)].set_index('abbreviation')['market share assumptions'].astype(float)
        if not np.isclose(ss.sum(), 1):
            raise ValueError('Incomplete technology shares')
        for m in MINERALS:
            parts = [(float(s), *one(mi_cat, t, m)) for t, s in ss.items()]
            rows.append(dict(sector=sec, technology='weighted_source_shares', mineral=m, statistic=statistic, intensity=sum((s * v for s, v, p in parts)), coefficient_reported=any((p for s, v, p in parts)), unit=unit))
    return pd.DataFrame(rows)

def power_activity(aim):
    rows = []
    audit = []
    units = pd.read_csv(ROOT / 'input/units_and_time_basis.csv').set_index('variable')
    endpoints = list(range(2020, 2101, 5))
    for sc, g in aim.groupby('Sc'):
        for suffix, _, _ in MAPPINGS:
            var = 'Cap_Add_Ele_' + suffix
            s = g.loc[g.Sv.eq(var)].set_index('Y5').value
            if suffix in ['Oil', 'Hyp']:
                rawcap = g.loc[g.Sv.eq('Cap_Ele_' + suffix)].set_index('Y5').value
                points = {y: float(rawcap.get(y, 0.0)) for y in sorted(g.loc[g.Y5.between(2010, 2100), 'Y5'].unique())}
                for y in points:
                    audit.append(dict(Sc=sc, variable='Cap_Ele_' + suffix, model_year=y, rate_GW_year=np.nan, sparse_zero_assumed=y not in rawcap.index))
                cap = annual(pd.Series(points), 2010, 2100)
                additions = cap.diff().clip(lower=0)
                additions.loc[2020] = max(0.0, cap.loc[2020] - cap.loc[2010]) / 10
                for year in range(2020, 2101):
                    rows.append(dict(Sc=sc, year=year, technology=suffix, addition_GW_year=additions.loc[year], basis='positive_net_stock_change_PROXY; gross_replacement_missing'))
                continue
            if var not in units.index or units.loc[var, 'declared_unit'] != 'GW/yr':
                raise ValueError('Unverified power rate unit: ' + var)
            if units.loc[var, 'time_basis'] != 'five_year_average_ending_at_label':
                raise ValueError('Unexpected averaging basis')
            for y in endpoints:
                reported = y in s.index
                v = float(s.get(y, 0.0))
                if v < 0 or not np.isfinite(v):
                    raise ValueError('Invalid addition')
                audit.append(dict(Sc=sc, variable=var, model_year=y, rate_GW_year=v, sparse_zero_assumed=not reported))
                for year in [2020] if y == 2020 else range(y - 4, y + 1):
                    rows.append(dict(Sc=sc, year=year, technology=suffix, addition_GW_year=v, basis='IAMC_five_year_average; omitted_solved_endpoint_assumed_zero' if not reported else 'IAMC_five_year_average_ending_at_label'))
        for y in endpoints:
            total = g.loc[g.Sv.eq('Cap_Add_Ele_Solar') & g.Y5.eq(y), 'value'].sum()
            pv = g.loc[g.Sv.eq('Cap_Add_Ele_SolarPV') & g.Y5.eq(y), 'value'].sum()
            if not np.isclose(total, pv, atol=1e-06):
                raise ValueError('Non-PV solar requires separate MI')
    f = pd.DataFrame(rows)
    if f.duplicated(['Sc', 'year', 'technology']).any():
        raise ValueError('Power activity duplicates')
    return (f, pd.DataFrame(audit))

def other_activities(aim):
    hrows = []
    brows = []
    haudit = []
    b = pd.read_csv(ROOT / 'output/verified_exports/battery_WORLD_NATIVE_units.csv')
    for sc, g in aim.groupby('Sc'):
        years = sorted(g.loc[g.Y5.between(2020, 2100), 'Y5'].unique())
        s = g.loc[g.Sv.eq('Cap_Hyd_Ele')].set_index('Y5').value
        points = pd.Series({y: float(s.get(y, 0.0)) for y in years})
        h = annual(points, 2015 if 2015 in points.index else 2020, 2100)
        inc = h.diff().clip(lower=0)
        inc.loc[2020] = 0.0
        for y in range(2020, 2101):
            hrows.append(dict(Sc=sc, year=y, addition_GW_year=inc.loc[y], basis='positive_net_H2_capacity_change; 2020_proxy_zero; capacity_input_output_unverified'))
        q = b.loc[b.Sc.eq(sc)]
        for r in q.itertuples():
            dt = int(r.model_time_interval)
            if dt <= 0:
                raise ValueError('Unsolved battery interval')
            for y in range(max(2020, int(r.year) - dt + 1), min(2100, int(r.year)) + 1):
                brows.append(dict(Sc=sc, year=y, addition_GW_year=r.raw_battery_addition, basis='battery_native_addition_assumed_GW/year; Wei_MI_t/GW_reproduction; duration_unresolved'))
    b = pd.DataFrame(brows)
    h = pd.DataFrame(hrows)
    if b.duplicated(['Sc', 'year']).any() or h.duplicated(['Sc', 'year']).any():
        raise ValueError('Overlapping intervals')
    for f in [b, h]:
        for sc, g in f.groupby('Sc'):
            if set(g.year) != set(range(2020, 2101)):
                raise ValueError('Activity coverage missing')
    return (h, b)

def sum_explicit(demand, keys):
    return demand.groupby(keys, as_index=False).agg(explicit_t_year=('explicit_t_year', 'sum'), reported_inventory=('coefficient_reported', 'any'))

def build(coefficient_factory=None, power_activity_factory=None, other_activity_factory=None):
    coefficient_factory = coefficient_factory or wei_coefficients
    power_activity_factory = power_activity_factory or power_activity
    other_activity_factory = other_activity_factory or other_activities
    aim = pd.read_csv(ROOT / 'input/AIM_World.csv.gz')
    aim = aim.loc[aim.Sr.eq('World')]
    pa, p_audit = power_activity_factory(aim)
    ha, ba = other_activity_factory(aim)
    allco = []
    sector = []
    for stat in ['average', 'minimum']:
        co = coefficient_factory(stat)
        allco.append(co)
        for sec, activity in [('power', pa), ('hydrogen', ha), ('stationary_battery', ba)]:
            c = co.loc[co.sector.eq(sec)].drop(columns='technology') if sec != 'power' else co.loc[co.sector.eq(sec)]
            if sec == 'power':
                d = activity.merge(c, on='technology', validate='many_to_many')
            else:
                d = activity.merge(c, how='cross')
            d['explicit_t_year'] = d.addition_GW_year * d.intensity
            d['quantified_t_year'] = d.explicit_t_year.where(d.coefficient_reported)
            d['inventory_complete'] = False
            sector.append(d)
    sectors = pd.concat(sector, ignore_index=True)
    secsum = sum_explicit(sectors, ['Sc', 'year', 'statistic', 'sector', 'mineral'])
    grid = grid_calculate(pd.read_csv(ROOT / 'input/imported/penelope_Demand_Network.csv'), aim)
    grid = grid.loc[grid.extension_case.eq('AIM_electricity_ratio')].copy().rename(columns={'source_scenario': 'grid_case', 'demand_t_year': 'explicit_t_year'})
    vehicle = pd.read_csv(ROOT / 'output/native_vehicle_demand_two_scenarios/alternative_HEV_combined_partial_demand.csv')
    old = pd.read_csv(ROOT / 'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv')
    v0 = vehicle.loc[vehicle.year.eq(2020)].copy()
    v0['v'] = v0.known_partial_vehicle_demand_t_year.fillna(0.0)
    if v0.groupby(['Sc', 'mineral']).v.nunique().max() > 1:
        raise ValueError('Base-year HEV cases need separate calibration')
    v0 = v0.groupby(['Sc', 'mineral']).v.first()
    bases = []
    osd = []
    rate = pd.read_csv(ROOT / 'input/imported/penelope_Metal_Intensity_Reduction.csv').iloc[0]
    for (sc, stat, gcase), g in old.groupby(['Sc', 'statistic', 'grid_case']):
        explicit = secsum.loc[secsum.Sc.eq(sc) & secsum.statistic.eq(stat) & secsum.year.eq(2020)].groupby('mineral').explicit_t_year.sum()
        gr = grid.loc[grid.Sc.eq(sc) & grid.grid_case.eq(gcase) & grid.year.eq(2020)].set_index('mineral').explicit_t_year
        gdp = annual(aim.loc[aim.Sc.eq(sc) & aim.Sv.eq('GDP_PPP')].set_index('Y5').value, 2020, 2100)
        factors = {2020: 1.0}
        for y in range(2021, 2101):
            end = 2030 if y <= 2030 else 2040 if y <= 2040 else 2050
            factors[y] = factors[y - 1] * growth_multiplier(gdp[y] / gdp[y - 1], float(rate[str(end)]))
        for r in g.itertuples():
            deduction = float(explicit[r.mineral]) + float(gr.get(r.mineral, 0.0)) + float(v0.loc[sc, r.mineral])
            lo = r.supply_low_t_year - deduction
            hi = r.supply_high_t_year - deduction
            bases.append(dict(Sc=sc, statistic=stat, grid_case=gcase, mineral=r.mineral, year=2020, supply_low_t_year=r.supply_low_t_year, supply_high_t_year=r.supply_high_t_year, explicit_deduction_t_year=deduction, raw_residual_low_t_year=lo, raw_residual_high_t_year=hi, negative_base=lo < 0, closure_error_low=r.supply_low_t_year - (deduction + lo)))
            for y, factor in factors.items():
                osd.append(dict(Sc=sc, statistic=stat, grid_case=gcase, mineral=r.mineral, year=y, other_low_t_year=lo * factor if lo >= 0 else np.nan, other_high_t_year=hi * factor if lo >= 0 else np.nan, raw_other_low_t_year=lo * factor, raw_other_high_t_year=hi * factor, growth_factor=factor, negative_base=lo < 0))
    bases = pd.DataFrame(bases)
    osd = pd.DataFrame(osd)
    totals = []
    for (sc, stat, gcase), o in osd.groupby(['Sc', 'statistic', 'grid_case']):
        sel = secsum.loc[secsum.Sc.eq(sc) & secsum.statistic.eq(stat)].pivot(index=['Sc', 'year', 'mineral'], columns='sector', values='explicit_t_year').reset_index()
        d = o.merge(sel, on=['Sc', 'year', 'mineral'], validate='one_to_one')
        gr = grid.loc[grid.Sc.eq(sc) & grid.grid_case.eq(gcase), ['Sc', 'year', 'mineral', 'explicit_t_year']].rename(columns={'explicit_t_year': 'grid_CuAl_t_year'})
        d = d.merge(gr, on=['Sc', 'year', 'mineral'], how='left', validate='one_to_one')
        d.grid_CuAl_t_year = d.grid_CuAl_t_year.fillna(0.0)
        v = vehicle.loc[vehicle.Sc.eq(sc), ['Sc', 'year', 'mineral', 'case', 'known_partial_vehicle_demand_t_year', 'any_reported_coefficient_in_selected_inventory']]
        d = d.merge(v, on=['Sc', 'year', 'mineral'], validate='one_to_many')
        d['vehicles_explicit_t_year'] = d.known_partial_vehicle_demand_t_year.fillna(0.0)
        d['selected_explicit_sum_t_year'] = d[['power', 'hydrogen', 'stationary_battery', 'grid_CuAl_t_year', 'vehicles_explicit_t_year']].sum(axis=1)
        d['conditional_total_low_t_year'] = d.selected_explicit_sum_t_year + d.other_low_t_year
        d['conditional_total_high_t_year'] = d.selected_explicit_sum_t_year + d.other_high_t_year
        d['full40_observed_total_ready'] = False
        d['basis'] = 'legacy_primary_proxy_y1_secondary0; as_reported_MI; unresolved material_forms_and_inventory'
        d['unreported_scope_policy'] = 'retained_in_other_complement; zero_explicit_deduction_is_not_zero_physical_use'
        totals.append(d)
    totals = pd.concat(totals, ignore_index=True).sort_values(['Sc', 'statistic', 'grid_case', 'case', 'mineral', 'year'])
    group = ['Sc', 'statistic', 'grid_case', 'case', 'mineral']
    for bound in ['low', 'high']:
        totals[f'cumulative_conditional_{bound}_t'] = totals.groupby(group)[f'conditional_total_{bound}_t_year'].transform(lambda x: x.cumsum(skipna=False))
    return (totals, secsum, sectors, grid, osd, bases, pd.concat(allco), pa, p_audit, ha, ba)

def run():
    tables = build()
    names = ['all_sector_totals_CONDITIONAL', 'explicit_sector_annual', 'explicit_sector_detail', 'grid_CuAl_annual', 'other_complement_annual_CONDITIONAL', 'baseline2020_recalibration', 'Wei_coefficients_and_coverage', 'power_annual_activity', 'power_sparse_zero_audit', 'hydrogen_net_addition_PROXY', 'battery_native_activity_UNIT_ASSUMPTION']
    out = ROOT / 'output/all_sectors_two_scenarios'
    out.mkdir(parents=True, exist_ok=True)
    for name, f in zip(names, tables):
        f.to_csv(out / (name + '.csv'), index=False)
    total, sec, detail, grid, osd, base, co, pa, audit, ha, ba = tables
    np.testing.assert_allclose(base.closure_error_low, 0.0, atol=1e-06)
    if total.duplicated(['Sc', 'statistic', 'grid_case', 'case', 'mineral', 'year']).any():
        raise ValueError('Duplicate totals')
    if len(total) != 2 * 2 * 3 * 8 * 40 * 81:
        raise ValueError('Unexpected scenario coverage')
    notes = pd.DataFrame({'説明': ['6部門を共通年次台帳へ接続した条件付き合計。物理的に確定した全40鉱物需要ではない。', '発電はIAMC新設年率、石油・水力は正の容量純増代理。2020新設は5年平均を基準年代理に使用。', '水素は正の容量純増。更新なし、電力入力/水素出力基準未確認。ScはWei原値の再現。', '蓄電池はnative追加量をGW/年と仮定、Wei表をt/GWとして使用。6.2113変換の解釈と蓄電時間は未確認。', '網はCu/AlをIEA3ケース、2050以降AIM電力比で延長。その他元素は残余に保持。', '車両はnative新設×既存原単位の定量化部分。HEV8参照は代替で足し合わせない。', 'その他は今回の明示2020需要を差引して再校正、GDP×旧原単位改善で延長。負の残余は0にせずNA合計。', '未収録明示用途は残余へ保持。将来も正しく補えると実証したわけではない。', '平均/最小、IEA3ケース、HEV8参照は条件の組合せ。確率・信頼区間ではない。', 'Li等の化合物/元素、一次/二次・歩留まり・在庫の一致は未解決。full40_ready=False。']})
    checkpoints = total.loc[total.year.isin([2020, 2030, 2050, 2100])]
    summary = total.loc[total.year.eq(2100)]
    with pd.ExcelWriter(out / 'all_sectors_two_scenarios_CONDITIONAL.xlsx') as w:
        for name, f in [('最初に読む', notes), ('6部門合計_主要年_条件付き', checkpoints), ('2100年と累積_条件付き', summary), ('発電水素蓄電池_年次', sec), ('網CuAl_年次', grid), ('その他残余_年次_条件付き', osd), ('2020基準年の再校正', base), ('Wei原単位と収録範囲', co), ('発電活動量_年次', pa), ('水素活動量_純増代理', ha), ('蓄電池活動量_単位仮定', ba)]:
            f.to_excel(w, sheet_name=name, index=False)
    print('Total rows', len(total), 'negative bases', base.negative_base.sum(), 'max closure', base.closure_error_low.abs().max())
    print('Negative base minerals:', sorted(base.loc[base.negative_base, 'mineral'].unique()))
    ref = summary.loc[summary.statistic.eq('average') & summary.grid_case.eq('SPS') & summary.case.eq('HEV_sedan_MG2010_WangNiMH_DOE2011_AB5_transfer') & summary.mineral.isin(['Cu', 'Al', 'Li', 'Fe', 'C'])]
    print(ref[['Sc', 'mineral', 'conditional_total_low_t_year', 'cumulative_conditional_low_t']].to_string(index=False))
if __name__ == '__main__':
    run()
