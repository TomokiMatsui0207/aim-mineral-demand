"""Two AIM native scenarios -> period-preserving annual vehicle activity and partial mineral demand.
Vehicle scale is numerically checked (raw STK/native=1e6), not explicitly documented in metadata.
No missing mineral intensity is silently replaced by zero. No new survival model is imposed.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import re, hashlib
import numpy as np
import pandas as pd
from model import MINERALS
ROOT = Path(__file__).resolve().parent
KEY = ['Sc', 'region', 'sector', 'technology', 'year']
SCENARIOS = ['Baseline', '300C']

def annualize_rates(periods, start=2020, end=2100):
    records = []
    for r in periods.itertuples():
        dt = float(r.model_time_interval)
        if dt < 1 or not dt.is_integer():
            raise ValueError('Require positive integer model interval')
        if r.new_rate_native < 0 or r.replacement_rate_native < 0:
            raise ValueError('Negative rate')
        for year in range(max(start, r.year - int(dt) + 1), min(end, r.year) + 1):
            records.append(dict(Sc=r.Sc, year=year, vehicle_type=r.vehicle_type, model_period_end=r.year, period_years=int(dt), new_vehicles_year=r.new_rate_native * 1000000.0, replacement_vehicles_year=r.replacement_rate_native * 1000000.0, native_vehicle_additions_year=(r.new_rate_native + r.replacement_rate_native) * 1000000.0))
    f = pd.DataFrame(records)
    if f.duplicated(['Sc', 'year', 'vehicle_type']).any():
        raise ValueError('Overlapping model intervals')
    for _, g in f.groupby(['Sc', 'vehicle_type']):
        if set(g.year) != set(range(start, end + 1)):
            raise ValueError('Missing annual coverage')
    f['vehicle_unit_basis'] = 'native_x1e6; numeric_ratio_verified_for_31regions_2005; explicit_unit_note_pending'
    f['year_allocation'] = 'constant annual rate inside model period; not linear interpolation'
    return f

def native_activity():
    mapping_source = ROOT / 'originals/runtime_gms2iamc/gms2iamc/individual/tech_share/define/tech_map.gms'
    mapping = {}
    for line in mapping_source.read_text().splitlines():
        match = re.match('\\s*(TPPC\\w+)\\s*\\.\\s*\\(?(TP_(?:ICE|HEV|PHV|BEV|FCV))(?:,TP_ZEV\\))?\\s*\\.\\s*TPP\\s*$', line)
        if match:
            mapping[match[1]] = match[2]
    native = []
    checks = []
    service_reference = pd.read_csv(ROOT / 'output/verified_exports/LDV_verified_model_years.csv')
    for sc in SCENARIOS:
        d = pd.read_csv(ROOT / f'input/server_exports/mineral_LDV_native_drivers_{sc}.csv')
        o = pd.read_csv(ROOT / f'input/server_exports/mineral_LDV_native_outputs_{sc}.csv')
        if d.duplicated(KEY).any() or o.duplicated(KEY + ['service']).any():
            raise ValueError('Duplicate native keys')
        if set(d.Sc) != {sc} or set(o.Sc) != {sc}:
            raise ValueError('Wrong scenario label')
        if not d.sector.eq('PSR').all() or not o.service.isin(['TPPG', 'TPPD']).all():
            raise ValueError('Non-LDV scope')
        if not np.isfinite(d.select_dtypes('number')).all().all() or not np.isfinite(o.select_dtypes('number')).all().all():
            raise ValueError('Nonfinite native values')
        np.testing.assert_allclose(d.stock_inflow_over_interval_native, (d.new_rate_native + d.replacement_rate_native) * d.model_time_interval, atol=1e-08, rtol=1e-09)
        np.testing.assert_allclose(o.effective_output_per_activity, o.raw_output_coefficient * (1 + o.output_change_phi), atol=1e-08, rtol=1e-09)
        if o.duplicated(KEY).any():
            raise ValueError('Multiple services per technology require coefficient aggregation')
        m = d.merge(o, on=KEY, validate='one_to_one')
        if len(m) != len(d) or len(m) != len(o):
            raise ValueError('Unmatched native keys')
        m['vehicle_type'] = m.technology.map(mapping)
        if m.vehicle_type.isna().any():
            raise ValueError('Unmapped native technology')
        m['service_bn_pkm_year'] = m.activity_native * m.effective_output_per_activity
        totals = m.groupby(['Sc', 'year', 'vehicle_type'], as_index=False).service_bn_pkm_year.sum()
        ref = service_reference.loc[service_reference.Sc.eq(sc), ['Sc', 'year', 'technology', 'service_bn_pkm_year']].rename(columns={'technology': 'vehicle_type', 'service_bn_pkm_year': 'reference_service'})
        c = totals.merge(ref, on=['Sc', 'year', 'vehicle_type'], how='outer', indicator=True, validate='one_to_one')
        if not c['_merge'].eq('both').all():
            raise ValueError('Model service key mismatch')
        np.testing.assert_allclose(c.service_bn_pkm_year, c.reference_service, atol=1e-06, rtol=1e-09)
        if not m.groupby('year').model_time_interval.nunique().eq(1).all():
            raise ValueError('Inconsistent time interval')
        checks.append(dict(Sc=sc, native_rows=len(m), regions=m.region.nunique(), detailed_technologies=m.technology.nunique(), max_service_difference=float((c.service_bn_pkm_year - c.reference_service).abs().max()), lifetime_min=m.lifetime_tn_years.min(), lifetime_max=m.lifetime_tn_years.max(), replacement_rate_sum=m.replacement_rate_native.sum()))
        native.append(m)
    native = pd.concat(native, ignore_index=True)
    p = native.groupby(['Sc', 'year', 'vehicle_type'], as_index=False).agg(stock_native=('stock_native', 'sum'), new_rate_native=('new_rate_native', 'sum'), replacement_rate_native=('replacement_rate_native', 'sum'), model_time_interval=('model_time_interval', 'first'), service_bn_pkm_year=('service_bn_pkm_year', 'sum'))
    p['stock_vehicles_native_scale'] = p.stock_native * 1000000.0
    return (native, p, annualize_rates(p), pd.DataFrame(checks))

def penelope_inventory():
    ints = pd.read_csv(ROOT / 'input/imported/penelope_intensities_long.csv')
    shares = pd.read_csv(ROOT / 'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv')
    np.testing.assert_allclose(shares.groupby('year').share.sum(), 1.0, atol=1e-08)
    motor_share = pd.read_csv(ROOT / 'input/imported/penelope_MS_Motor.csv').set_index('Motor_type').loc['MS', ['PM', 'Ind']].astype(float)
    np.testing.assert_allclose(motor_share.sum(), 1.0)
    sizes = {'TP_PHV': 21.8, 'TP_BEV': 62.5}
    vehicle_names = {'TP_ICE': 'ICEV', 'TP_PHV': 'PHEV', 'TP_BEV': 'BEV'}
    rows = []

    def entry(component, tech, mineral):
        a = ints.loc[ints.component.eq(component) & ints.technology.eq(tech) & ints.mineral.eq(mineral)]
        if len(a) > 1:
            raise ValueError('Duplicate intensity')
        return float(a.iloc[0].t_per_unit) if len(a) == 1 else np.nan
    for year in range(2020, 2101):
        bs = shares.loc[shares.year.eq(year)].set_index('Battery_type').share
        for tech in ['TP_ICE', 'TP_PHV', 'TP_BEV', 'TP_FCV']:
            for mineral in MINERALS:
                parts = []
                expected = 1 if tech == 'TP_ICE' else 3
                if tech == 'TP_FCV':
                    expected = 3
                else:
                    parts.append(entry('vehicle_body', vehicle_names[tech], mineral))
                    if tech != 'TP_ICE':
                        values = [(entry('vehicle_battery', t, mineral), s) for t, s in bs.items() if s > 0]
                        parts.append(sizes[tech] * sum((v * s for v, s in values)) if all((np.isfinite(v) for v, s in values)) else np.nan)
                        values = [(entry('vehicle_motor', t, mineral), s) for t, s in motor_share.items() if s > 0]
                        parts.append(sum((v * s for v, s in values)) if all((np.isfinite(v) for v, s in values)) else np.nan)
                finite = [x for x in parts if np.isfinite(x)]
                rows.append(dict(year=year, vehicle_type=tech, mineral=mineral, known_t_per_vehicle=sum(finite) if finite else np.nan, reported_component_count=len(finite), selected_component_count=expected, whole_vehicle_complete=False, inventory_basis='Penelope reported component subtotal; chemical material basis not independently verified' if tech != 'TP_FCV' else 'FCV inventory unavailable', battery_profile='Penelope Current Trend; 2050 shares held after 2050', motor_profile='PM/Ind constant Penelope share', battery_kWh=sizes.get(tech, np.nan)))
    return pd.DataFrame(rows)

def apply_inventory(activity, inventory, coefficient='known_t_per_vehicle'):
    keys = ['year', 'vehicle_type', 'mineral']
    if inventory.duplicated(keys).any():
        raise ValueError('Duplicate vehicle/year/mineral coefficient')
    if activity.duplicated(['Sc', 'year', 'vehicle_type']).any():
        raise ValueError('Duplicate annual activity')
    a = activity.merge(inventory, on=['year', 'vehicle_type'], how='inner', validate='many_to_many')
    a['coefficient_missing'] = a[coefficient].isna()
    a['known_subtotal_t_year'] = a.native_vehicle_additions_year * a[coefficient]
    a.loc[a.native_vehicle_additions_year.eq(0), 'known_subtotal_t_year'] = 0.0
    a['whole_vehicle_complete'] = False
    return a

def run():
    native, periods, activity, checks = native_activity()
    inventory = penelope_inventory()
    common = apply_inventory(activity, inventory)
    hev_inventory = pd.read_csv(ROOT / 'output/HEV_integrated_vehicle/HEV_inventory_40_slots_PARTIAL.csv')
    hev_inventory['known_t_per_vehicle'] = hev_inventory.quantified_subtotal_kg_per_vehicle / 1000.0
    hev = []
    combined = []
    common_total = common.groupby(['Sc', 'year', 'mineral'], as_index=False).agg(common_known_subtotal_t_year=('known_subtotal_t_year', lambda s: s.sum(min_count=1)), common_active_missing_vehicle_types=('native_vehicle_additions_year', lambda x: 0))
    missing = common.assign(active_missing=common.native_vehicle_additions_year.gt(0) & common.coefficient_missing).groupby(['Sc', 'year', 'mineral']).active_missing.sum()
    common_total['common_active_missing_vehicle_types'] = [missing.loc[r.Sc, r.year, r.mineral] for r in common_total.itertuples()]
    for case, inv in hev_inventory.groupby('case'):
        h = activity.loc[activity.vehicle_type.eq('TP_HEV')].merge(inv, how='cross')
        h['known_subtotal_t_year'] = h.native_vehicle_additions_year * h.known_t_per_vehicle
        h.loc[h.native_vehicle_additions_year.eq(0), 'known_subtotal_t_year'] = 0.0
        h['active_missing_HEV'] = h.native_vehicle_additions_year.gt(0) & h.known_t_per_vehicle.isna()
        hev.append(h)
        t = common_total.merge(h[['Sc', 'year', 'mineral', 'known_subtotal_t_year', 'active_missing_HEV']], on=['Sc', 'year', 'mineral'], validate='one_to_one')
        t['case'] = case
        reported_common = common.groupby(['Sc', 'year', 'mineral']).coefficient_missing.agg(lambda x: (~x).any())
        t['any_reported_coefficient_in_selected_inventory'] = [bool(reported_common.loc[r.Sc, r.year, r.mineral]) or pd.notna(inv.set_index('mineral').loc[r.mineral, 'known_t_per_vehicle']) for r in t.itertuples()]
        t['known_partial_vehicle_demand_t_year'] = t[['common_known_subtotal_t_year', 'known_subtotal_t_year']].sum(axis=1, min_count=1)
        t.loc[~t.any_reported_coefficient_in_selected_inventory, 'known_partial_vehicle_demand_t_year'] = np.nan
        t['full40_vehicle_total_t_year'] = np.nan
        t['whole_vehicle_complete'] = False
        t['OSD_overlap_resolved'] = False
        t['case_assignment'] = 'same alternative reference HEV for every new HEV; not measured fleet mix'
        combined.append(t)
    hev = pd.concat(hev, ignore_index=True)
    combined = pd.concat(combined, ignore_index=True).sort_values(['Sc', 'case', 'mineral', 'year'])
    combined['cumulative_known_partial_2020_through_year_t'] = combined.groupby(['Sc', 'case', 'mineral']).known_partial_vehicle_demand_t_year.transform(lambda s: s.cumsum(skipna=False))
    cumulative = combined.loc[combined.year.eq(2100)].copy()
    sales_summary = activity.groupby(['Sc', 'vehicle_type'], as_index=False).native_vehicle_additions_year.sum().rename(columns={'native_vehicle_additions_year': 'cumulative_2020_2100_vehicle_additions'})
    oldbase = pd.read_csv(ROOT / 'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv')
    b = common.loc[common.year.eq(2020)].groupby(['Sc', 'mineral']).known_subtotal_t_year.sum(min_count=1)
    assert activity.loc[activity.year.eq(2020) & activity.vehicle_type.isin(['TP_HEV', 'TP_FCV'])].native_vehicle_additions_year.eq(0).all()
    patch = oldbase.copy()
    patch['new_reported_scope_vehicle_deduction_t_year'] = [float(b.loc[r.Sc, r.mineral]) if pd.notna(b.loc[r.Sc, r.mineral]) else 0.0 for r in patch.itertuples()]
    patch['residual_scope_policy'] = 'unreported vehicle elements retained in complementary residual; zero deduction is not physical absence'
    patch['vehicle_deduction_change_t_year'] = patch.new_reported_scope_vehicle_deduction_t_year - patch.vehicles_t_year
    for side in ['low', 'high']:
        patch[f'patched_raw_residual_{side}_t_year'] = patch[f'raw_residual_{side}_t_year'] - patch.vehicle_deduction_change_t_year
    patch['patched_negative_residual_flag'] = patch.patched_raw_residual_low_t_year.lt(0)
    patch['bridge_assumption'] = 'legacy primary proxy s=0,y=1; manufacturing/recycling/stock allocation unresolved'
    out = ROOT / 'output/native_vehicle_demand_two_scenarios'
    out.mkdir(parents=True, exist_ok=True)
    tables = [('model_period_activity', periods), ('annual_vehicle_additions', activity), ('native_service_checks', checks), ('penelope_40_slot_intensities', inventory), ('ICE_PHEV_BEV_FCV_partial_demand', common), ('HEV_reference_partial_demand', hev), ('alternative_HEV_combined_partial_demand', combined), ('cumulative_partial_demand', cumulative), ('cumulative_vehicle_additions', sales_summary), ('baseline_residual_patch_CONDITIONAL', patch)]
    for name, f in tables:
        f.to_csv(out / (name + '.csv'), index=False)
    files = [ROOT / f'input/server_exports/mineral_LDV_native_{k}_{sc}.csv' for sc in SCENARIOS for k in ['drivers', 'outputs']] + [ROOT / 'input/imported/penelope_intensities_long.csv', ROOT / 'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv', ROOT / 'input/imported/penelope_MS_Motor.csv', ROOT / 'output/HEV_integrated_vehicle/HEV_inventory_40_slots_PARTIAL.csv', ROOT / 'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv', ROOT / 'originals/runtime_gms2iamc/gms2iamc/individual/tech_share/define/tech_map.gms', ROOT / 'output/verified_exports/LDV_verified_model_years.csv']
    pd.DataFrame([dict(file=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]).to_csv(out / 'input_hashes.csv', index=False)
    notes = pd.DataFrame({'説明': ['Baseline/300Cを同じnative VR×百万台換算で計算。全31地域の2005年倍率は数値照合済み、台数の明示単位説明は未取得。', 'モデル期間内は年率を一定配分。期間量をさらに年幅で割らず、合計保存。独自の12年寿命モデルを重ねていない。', 'VPは両シナリオ全行0。VRに交換分が含まれ得るため、VPゼロを買替需要ゼロと解釈しない。', 'ICE/PHEV/BEVはPenelope収録部品の小計、HEVは8代替参照の部品小計、FCVは未収録。いずれも40鉱物完全総量ではない。', 'HEV8参照は代替で合算禁止。測定された世界車種シェアではない。', '原単位未収録はNA。活動0なら当年需要0だが係数欠測フラグは保持。', '電池構成はCurrent Trendを両シナリオ共通で使用、2050以降据置。車両電池交換は別計上していない。', '残余更新は2020年の車両差引だけの条件付き修正。全体の将来総需要は未更新。']})
    with pd.ExcelWriter(out / 'native_vehicle_demand_two_scenarios.xlsx') as w:
        for name, f in [('最初に読む', notes), ('年次車種別新設台数', activity), ('モデル年ストックと新設率', periods), ('サービス照合', checks), ('累積新設台数', sales_summary), ('ICE_EV等の鉱物小計年次', common), ('HEV参照1台原単位', hev_inventory), ('HEV代替別累積鉱物小計', cumulative), ('主要年_代替別鉱物小計', combined.loc[combined.year.isin([2020, 2030, 2050, 2100])]), ('2020残余の条件付き修正', patch)]:
            f.to_excel(w, sheet_name=name, index=False)
    print(checks.to_string(index=False))
    print(activity.loc[activity.year.isin([2020, 2050, 2100])].pivot(index=['Sc', 'year'], columns='vehicle_type', values='native_vehicle_additions_year').round().to_string())
    return (activity, common, combined, patch)
if __name__ == '__main__':
    run()
