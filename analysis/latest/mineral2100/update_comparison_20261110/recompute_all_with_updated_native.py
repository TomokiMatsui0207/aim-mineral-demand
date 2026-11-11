"""Recompute the SAME v6 conditional inventory with updated AIM activity.
No new bus/truck mineral inventory is silently inserted. Original outputs immutable.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, json, hashlib, shutil
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import calculate_native_vehicle_demand as veh
import integrate_all_sectors_conditional as allsec
import reconcile_wind_ree_v6 as v6
import harmonize_energy_v2 as v2
import integrate_energy_native_v3 as v3
from extend_road_vehicles import classify
from compare_uploaded_iamc import merge_like_old
from compare_fixed_method import delta, cumulative
OUT = ROOT / 'update_comparison_20261110/results_updated_native_all_sectors'
DATA = ROOT / 'input/updated_2611091342/native'
KEY = ['Sc', 'region', 'sector', 'technology', 'year']

def updated_activity():
    drivers = []
    outputs = []
    audits = []
    road = []
    for sc in ['Baseline', '300C']:
        d = pd.read_csv(DATA / f'updated_native_drivers_{sc}.csv')
        o = pd.read_csv(DATA / f'updated_native_road_outputs_{sc}.csv')
        if d.duplicated(KEY).any() or o.duplicated(KEY + ['service']).any():
            raise ValueError('Duplicate native key')
        if set(d.Sc) != {sc} or set(o.Sc) != {sc}:
            raise ValueError('Scenario mismatch')
        vals = ['stock_native', 'new_rate_native', 'replacement_rate_native', 'activity_native', 'model_time_interval', 'lifetime_tn_years']
        if not np.isfinite(d[vals]).all().all():
            raise ValueError('Nonfinite native')
        np.testing.assert_allclose(d.stock_inflow_over_interval_native, (d.new_rate_native + d.replacement_rate_native) * d.model_time_interval, atol=1e-08, rtol=1e-08)
        np.testing.assert_allclose(o.effective_output_per_activity, o.raw_output_coefficient * (1 + o.output_change_phi), atol=1e-08, rtol=1e-08)
        if d.new_rate_native.min() < -1e-07 or d.replacement_rate_native.min() < -1e-07:
            raise ValueError('Negative rate exceeds numeric tolerance')
        d['removed_negative_new_native'] = -d.new_rate_native.clip(upper=0)
        d['removed_negative_replacement_native'] = -d.replacement_rate_native.clip(upper=0)
        d['new_rate_native'] = d.new_rate_native.clip(lower=0)
        d['replacement_rate_native'] = d.replacement_rate_native.clip(lower=0)
        passenger = d.loc[d.technology.str.startswith(('TPPCOG_', 'TPPCOD_'))].copy()
        passenger['vehicle_type'] = passenger.technology.map(lambda t: 'TP_' + classify(t)[1])
        po = o.loc[o.technology.str.startswith(('TPPCOG_', 'TPPCOD_'))].copy()
        if po.duplicated(KEY).any():
            raise ValueError('Multiple LDV services require separate aggregation')
        m = passenger.merge(po, on=KEY, validate='one_to_one')
        if len(m) != len(passenger) or len(m) != len(po):
            raise ValueError('Unmatched LDV driver/output')
        m['service_bn_pkm_year'] = m.activity_native * m.effective_output_per_activity
        for year, g in d.groupby('year'):
            if g.model_time_interval.nunique() != 1:
                raise ValueError('Regional interval mismatch')
        audits.append(dict(Sc=sc, driver_rows=len(d), output_rows=len(o), regions=d.region.nunique(), years=d.year.nunique(), max_abs_VP=d.replacement_rate_native.abs().max(), max_negative_removed_native=d.removed_negative_new_native.max(), LDV_rows=len(passenger)))
        drivers.append(d)
        outputs.append(m)
        rd = d.loc[d.technology.str.startswith(('TPPCOG_', 'TPPCOD_', 'TPBSOI_', 'TFTSOI_', 'TFTLOI_'))].copy()
        rd['vehicle_class'] = rd.technology.map(lambda t: classify(t)[0])
        rd['powertrain'] = rd.technology.map(lambda t: classify(t)[1])
        road.append(rd)
    drivers = pd.concat(drivers, ignore_index=True)
    m = pd.concat(outputs, ignore_index=True)
    periods = m.groupby(['Sc', 'year', 'vehicle_type'], as_index=False).agg(stock_native=('stock_native', 'sum'), new_rate_native=('new_rate_native', 'sum'), replacement_rate_native=('replacement_rate_native', 'sum'), model_time_interval=('model_time_interval', 'first'), service_bn_pkm_year=('service_bn_pkm_year', 'sum'))
    periods['stock_vehicles_native_scale'] = periods.stock_native * 1000000.0
    activity = veh.annualize_rates(periods)
    activity['vehicle_unit_basis'] = 'same x1e6 reference as old numeric calibration; updated explicit unit explanation pending; comparison conditional'
    raw = pd.read_csv(ROOT / 'input/updated_2611091342/AIM_World.csv.gz')
    bridge = []
    equipment = []
    for tech, sector, capvar, addvar in [('ELECAP_BAT', 'ELE', 'Cap_Ele_Sto_Cap', 'Cap_Add_Ele_Sto_Cap'), ('H2CAP_ELE', 'H_H', 'Cap_Hyd_Ele', 'Cap_Add_Hyd_Ele')]:
        q = drivers.loc[drivers.technology.eq(tech) & drivers.sector.eq(sector)]
        if q.empty:
            raise ValueError('Missing physical equipment')
        rows = []
        for (sc, y), g in q.groupby(['Sc', 'year']):
            if g.model_time_interval.nunique() != 1:
                raise ValueError('Equipment time disagreement')
            cap = raw.loc[raw.Sc.eq(sc) & raw.Y5.eq(y) & raw.Sv.eq(capvar)].value.sum()
            vr = raw.loc[raw.Sc.eq(sc) & raw.Y5.eq(y) & raw.Sv.eq(addvar)].value.sum()
            c = g.stock_native.sum()
            v = g.new_rate_native.sum()
            vp = g.replacement_rate_native.sum()
            if not np.isclose(c, cap, atol=1e-05, rtol=1e-09) or not np.isclose(v, vr, atol=1e-05, rtol=1e-09):
                raise ValueError('IAMC/native physical equipment mismatch')
            bridge.append(dict(Sc=sc, year=y, technology=tech, stock_difference=c - cap, VR_difference=v - vr, VP_native=vp))
            dt = int(g.model_time_interval.iloc[0])
            for year in range(max(2020, int(y) - dt + 1), min(2100, int(y)) + 1):
                rows.append(dict(Sc=sc, year=year, addition_GW_year=v + vp, basis='native_VR_plus_VP; same old physical GW interpretation; fixed12h battery reference, metadata declaration mismatch retained'))
        equipment.append(pd.DataFrame(rows))
    return (activity, periods, equipment, pd.DataFrame(audits), pd.DataFrame(bridge), pd.concat(road, ignore_index=True), m)

def same_vehicle_coefficients(activity):
    inv = pd.read_csv(ROOT / 'output/native_vehicle_demand_two_scenarios/penelope_40_slot_intensities.csv')
    common = veh.apply_inventory(activity, inv)
    common_total = common.groupby(['Sc', 'year', 'mineral'], as_index=False).agg(common_known_subtotal_t_year=('known_subtotal_t_year', lambda x: x.sum(min_count=1)))
    reported = common.groupby(['Sc', 'year', 'mineral']).coefficient_missing.agg(lambda x: (~x).any())
    hsource = pd.read_csv(ROOT / 'output/HEV_integrated_vehicle/HEV_inventory_40_slots_PARTIAL.csv')
    combined = []
    for case, h in hsource.groupby('case'):
        h = h.copy()
        h['known_t_per_vehicle'] = h.quantified_subtotal_kg_per_vehicle / 1000
        c = activity.loc[activity.vehicle_type.eq('TP_HEV')].merge(h, how='cross')
        c['hev_t_year'] = c.native_vehicle_additions_year * c.known_t_per_vehicle
        c.loc[c.native_vehicle_additions_year.eq(0), 'hev_t_year'] = 0
        q = common_total.merge(c[['Sc', 'year', 'mineral', 'hev_t_year']], on=['Sc', 'year', 'mineral'], validate='one_to_one')
        lookup = h.set_index('mineral').known_t_per_vehicle
        q['any_reported_coefficient_in_selected_inventory'] = [bool(reported.loc[r.Sc, r.year, r.mineral]) or pd.notna(lookup[r.mineral]) for r in q.itertuples()]
        q['known_partial_vehicle_demand_t_year'] = q[['common_known_subtotal_t_year', 'hev_t_year']].sum(axis=1, min_count=1)
        q.loc[~q.any_reported_coefficient_in_selected_inventory, 'known_partial_vehicle_demand_t_year'] = np.nan
        q['case'] = case
        combined.append(q)
    return (pd.concat(combined, ignore_index=True), common)

def build_updated(aim, vehicle, equipment):
    stage = OUT / 'isolated_inputs'
    (stage / 'input').mkdir(parents=True, exist_ok=True)
    aim.to_csv(stage / 'input/AIM_World.csv.gz', index=False, compression='gzip')
    unitfile = stage / 'input/units_and_time_basis.csv'
    if not unitfile.exists():
        unitfile.symlink_to(ROOT / 'input/units_and_time_basis.csv')
    imports = stage / 'input/imported'
    if not imports.exists():
        imports.symlink_to(ROOT / 'input/imported', target_is_directory=True)
    f = stage / 'output/native_vehicle_demand_two_scenarios'
    f.mkdir(parents=True, exist_ok=True)
    vehicle.to_csv(f / 'alternative_HEV_combined_partial_demand.csv', index=False)
    f = stage / 'output/reconciled40_CONDITIONAL'
    f.mkdir(parents=True, exist_ok=True)
    target = f / 'baseline_40_CONDITIONAL.csv'
    if not target.exists():
        target.symlink_to(ROOT / 'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv')
    previous = allsec.ROOT
    try:
        allsec.ROOT = stage
        return allsec.build(v6.coefficients, v2.power_activity, lambda a: (equipment[1], equipment[0]))
    finally:
        allsec.ROOT = previous

def compare_service_and_scope(road, ldv_outputs, aim):
    native = ldv_outputs.groupby(['Sc', 'year'], as_index=False).service_bn_pkm_year.sum()
    demand = aim.loc[aim.Sv.eq('Ene_Ser_Tra_Pss_Roa_LDV'), ['Sc', 'Y5', 'value']].rename(columns={'Y5': 'year', 'value': 'IAMC_demand'})
    native = native.merge(demand, on=['Sc', 'year'], validate='one_to_one')
    native['service_residual'] = native.service_bn_pkm_year - native.IAMC_demand
    r = road.groupby(['Sc', 'year', 'vehicle_class', 'powertrain'], as_index=False).agg(stock_native=('stock_native', 'sum'), new_rate_native=('new_rate_native', 'sum'), replacement_rate_native=('replacement_rate_native', 'sum'), model_time_interval=('model_time_interval', 'first'))
    r['vehicles_per_native_unit_confirmed'] = np.nan
    r['comparison_scope'] = 'new vehicle class activity only; bus/truck old native and class unit calibration not available; excluded from fixed-scope totals'
    return (native, r)

def run():
    OUT.mkdir(parents=True, exist_ok=True)
    activity, periods, equipment, audit, bridge, road, ldv_outputs = updated_activity()
    vehicle, common = same_vehicle_coefficients(activity)
    aim = merge_like_old(pd.read_csv(ROOT / 'input/updated_2611091342/AIM_World.csv.gz'))
    tables = build_updated(aim, vehicle, equipment)
    names = ['all_sectors_CONDITIONAL', 'explicit_sector_annual', 'explicit_sector_detail', 'grid_CuAl_annual', 'other_complement_annual_CONDITIONAL', 'baseline2020_recalibration', 'coefficients', 'power_activity', 'power_activity_audit', 'hydrogen_native_activity', 'battery_native_activity']
    for name, f in zip(names, tables):
        f.to_csv(OUT / (name + ('.csv.gz' if name in ['all_sectors_CONDITIONAL', 'explicit_sector_detail'] else '.csv')), index=False, compression='gzip' if name in ['all_sectors_CONDITIONAL', 'explicit_sector_detail'] else None)
    activity.to_csv(OUT / 'updated_annual_LDV_additions.csv', index=False)
    periods.to_csv(OUT / 'updated_LDV_periods.csv', index=False)
    vehicle.to_csv(OUT / 'updated_vehicle_same_v6_inventory.csv.gz', index=False, compression='gzip')
    audit.to_csv(OUT / 'native_audit.csv', index=False)
    bridge.to_csv(OUT / 'equipment_native_IAMC_bridge.csv', index=False)
    service, road_table = compare_service_and_scope(road, ldv_outputs, pd.read_csv(ROOT / 'input/updated_2611091342/AIM_World.csv.gz'))
    service.to_csv(OUT / 'LDV_native_service_demand_check.csv', index=False)
    road_table.to_csv(OUT / 'bus_truck_road_activity_NOT_unit_calibrated.csv', index=False)
    old = pd.read_csv(ROOT / 'output/wind_ree_reconciliation_v6/all_sectors_CONDITIONAL.csv.gz')
    difference = delta(old, tables[0])
    cum = cumulative(difference)
    difference.to_csv(OUT / 'annual_all_sector_comparison.csv.gz', index=False, compression='gzip')
    cum.to_csv(OUT / 'cumulative_all_sector_comparison.csv', index=False)
    oldactivity = pd.read_csv(ROOT / 'output/native_vehicle_demand_two_scenarios/annual_vehicle_additions.csv')
    act = activity.merge(oldactivity, on=['Sc', 'year', 'vehicle_type'], suffixes=('_new', '_old'), validate='one_to_one')
    act['change_vehicles_year'] = act.native_vehicle_additions_year_new - act.native_vehicle_additions_year_old
    act.to_csv(OUT / 'LDV_sales_old_new_comparison.csv', index=False)
    sales = act.groupby(['Sc', 'vehicle_type'], as_index=False)[['native_vehicle_additions_year_old', 'native_vehicle_additions_year_new']].sum()
    sales['change_percent'] = np.where(sales.native_vehicle_additions_year_old.ne(0), 100 * (sales.native_vehicle_additions_year_new - sales.native_vehicle_additions_year_old) / sales.native_vehicle_additions_year_old.replace(0, np.nan), np.nan)
    sales.to_csv(OUT / 'LDV_cumulative_additions_old_new.csv', index=False)
    oldbase = pd.read_csv(ROOT / 'output/wind_ree_reconciliation_v6/baseline2020_recalibration.csv')
    base = tables[5].merge(oldbase, on=['Sc', 'statistic', 'grid_case', 'mineral', 'year'], suffixes=('_new', '_old'), validate='one_to_one')
    base.to_csv(OUT / 'baseline_recalibration_old_new.csv', index=False)
    neg = base.loc[base.negative_base_new].copy()
    neg.to_csv(OUT / 'negative_residual_diagnostics.csv', index=False)
    oldco = pd.read_csv(ROOT / 'output/wind_ree_reconciliation_v6/coefficients.csv')
    cols = ['sector', 'technology', 'mineral', 'statistic', 'intensity', 'coefficient_reported']
    k = cols[:4]
    co = tables[6][cols].merge(oldco[cols], on=k, suffixes=('_new', '_old'), validate='one_to_one')
    np.testing.assert_allclose(co.intensity_new, co.intensity_old, atol=1e-12, rtol=1e-12)
    assert len(co) == len(oldco) and (co.coefficient_reported_new == co.coefficient_reported_old).all()
    np.testing.assert_allclose(base.closure_error_low_new, 0, atol=1e-06)
    expected = 2 * 2 * 3 * 8 * 40 * 81
    if len(tables[0]) != expected:
        raise ValueError('All-sector case coverage mismatch')
    manifest = {'old_run': '2608261554', 'new_run': '2611091342', 'same_v6_scope_intensities_cases': True, 'power_equipment_coefficients_compared_rows': len(co), 'new_VP_all_exported_rows_zero': bool(audit.max_abs_VP.eq(0).all()), 'LDV_x1e6_scale': 'same conditional transfer as old31-region numeric calibration; explicit updated unit metadata pending', 'battery_capacity_basis': 'fixed old physicalGW_and12h interpretation; report GWh metadata conflicts with unscaled native equation; not newly resolved', 'bus_truck_added_to_main_totals': False, 'vehicle_HEV_v4_added_to_main_totals': False, 'all40_observed_inventory_complete': False, 'rows': len(tables[0]), 'negative_base_minerals': sorted(neg.mineral.unique().tolist()), 'LDV_max_abs_service_residual': float(service.service_residual.abs().max()), 'total_ready_as_same_scope_conditional_comparison': True, 'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in list(DATA.glob('*.csv')) + [ROOT / 'input/updated_2611091342/AIM_World.csv.gz', ROOT / 'output/HEV_integrated_vehicle/HEV_inventory_40_slots_PARTIAL.csv', ROOT / 'output/native_vehicle_demand_two_scenarios/penelope_40_slot_intensities.csv', Path(__file__)]}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    notes = pd.DataFrame({'項目': ['比較の意味', '原単位', '車両台数', '蓄電池', '基準年残余', 'バス・貨物', '完全性'], '説明': ['旧v6と同じ6部門・ケース条件の条件付き比較。AIM更新以外の原単位変更を混ぜない。', '平均/最小、IEA3枝、HEV8枝を維持。最新のHEV4・FCV補完ケースは今回の主比較には入れない。', 'nativeVR+VP×1e6。同じ旧倍率を使用する参照比較で、新しい明示的単位説明は未確認。', 'nativeVP=0を全出力行で確認。12h等価・物理GWという旧解釈を固定。単位宣言不整合は未解決。', '更新2020需要を再差引し、同じGDP・集約度で延長。基準年変更の影響と部門活動量の変化を区別。', '新活動量は取得済みだが、大小区分・倍率・原単位と旧nativeが未整備のため主比較に追加しない。', '全40鉱物の実需や一次資源必要量が実証的に確定した意味ではない。']})
    ref = cum.loc[cum.statistic.eq('average') & cum.grid_case.eq('SPS') & cum.case.eq('HEV_sedan_MG2010_WangNiMH_DOE2011_AB5_transfer') & cum.end_year.eq(2100)]
    with pd.ExcelWriter(OUT / 'updated_vs_old_ALL_SECTORS_CONDITIONAL.xlsx', engine='openpyxl') as w:
        for name, f in [('最初に読む', notes), ('代表ケース_累積部門差', ref), ('全ケース累積差', cum), ('年次差_主要年', difference.loc[difference.year.isin([2020, 2030, 2050, 2100])]), ('車種別累積新設台数', sales), ('車両_主要年の新設', act.loc[act.year.isin([2020, 2030, 2050, 2100])]), ('基準年残余_新旧', base), ('負残余_診断', neg), ('native整合確認', audit), ('設備_IAMC照合', bridge), ('車両サービス照合', service), ('バス貨物_未校正活動', road_table)]:
            f.to_excel(w, sheet_name=name, index=False)
            ws = w.book[name]
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
    print('ACTIVITY\n', sales.to_string(index=False))
    print('TOTALS\n', ref.loc[ref.mineral.isin(['Cu', 'Al', 'Fe', 'Li', 'Dy', 'Tb', 'Ni', 'Co', 'Pt', 'Ir']) & ref.metric.isin(['conditional_total_low_t_year', 'vehicles_explicit_t_year', 'other_low_t_year'])].to_string(index=False))
    print('negative:', manifest['negative_base_minerals'], 'maxVP', audit.max_abs_VP.max(), 'service residual', manifest['LDV_max_abs_service_residual'])
if __name__ == '__main__':
    run()
