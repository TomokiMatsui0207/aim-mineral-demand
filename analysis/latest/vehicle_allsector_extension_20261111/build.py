"""Road classes and revised HEV/FCV inventories integrated into conditional totals.
Missing component masses remain unknown. No measured all40 or primary-demand claim.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json, hashlib, sys
import pandas as pd
import numpy as np
O = Path(__file__).resolve().parent
R = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'mineral2100'))
sys.path.insert(0, str(R))
from model import MINERALS
ANL = json.loads((O / 'truck_reference.json').read_text())
LB = 0.45359237
CASE_PROFILES = [dict(case='A_day_NMC622_known_subtotal', large='DAY', chem='NMC622', cu_fraction=0.0, graphite_fraction=0.0, hev='HEV4_sedan_teardown', fcv='FCV_sedan_300_Pt_SFA2019_30g_transfer'), dict(case='B_day_NMC622_mixed_material_endpoints', large='DAY', chem='NMC622', cu_fraction=1.0, graphite_fraction=1.0, hev='HEV4_sedan_teardown', fcv='FCV_sedan_300_Pt_SFA2019_30g_transfer'), dict(case='C_sleeper_NMC811_known_subtotal', large='SLEEP', chem='NMC811', cu_fraction=0.0, graphite_fraction=0.0, hev='HEV4_sedan_teardown', fcv='FCV_sedan_300_Pt_SFA2019_30g_transfer'), dict(case='E_Pt_power_and_FCV_auxiliary_transfer', large='DAY', chem='NMC622', cu_fraction=0.0, graphite_fraction=0.0, hev='HEV4_sedan_teardown', fcv='FCV_sedan_300_Pt_SFA2019_30g_transfer', additional_fcv_transfer=True), dict(case='F_E_plus_steel_Fe_proxy', large='DAY', chem='NMC622', cu_fraction=0.0, graphite_fraction=0.0, hev='HEV4_sedan_teardown', fcv='FCV_sedan_300_Pt_SFA2019_30g_transfer', additional_fcv_transfer=True, steel_Fe_fraction=0.9786), dict(case='D_day_NMC622_alternative_LDV_blocks', large='DAY', chem='NMC622', cu_fraction=0.0, graphite_fraction=0.0, hev='HEV4_smallSUV_GREET_blocks', fcv='FCV_smallSUV_400_Pt_NASEM2021_40g_transfer')]
AW = {'Li': 6.94, 'Ni': 58.6934, 'Mn': 54.938044, 'Co': 58.933194, 'O': 15.999, 'P': 30.973762, 'F': 18.998403163}

def battery_recipe(kg, recipe, chem, graphite_fraction):
    active, cu, al, salt, carbon = np.array(recipe) / 100
    fractions = {'NMC111': {'Li': 1, 'Ni': 1 / 3, 'Mn': 1 / 3, 'Co': 1 / 3, 'O': 2}, 'NMC622': {'Li': 1, 'Ni': 0.6, 'Mn': 0.2, 'Co': 0.2, 'O': 2}, 'NMC811': {'Li': 1, 'Ni': 0.8, 'Mn': 0.1, 'Co': 0.1, 'O': 2}}[chem]
    mol = sum((AW[m] * n for m, n in fractions.items()))
    v = {m: kg * active * AW[m] * fractions[m] / mol for m in ['Li', 'Ni', 'Mn', 'Co']}
    v['Li'] += kg * salt * AW['Li'] / (AW['Li'] + AW['P'] + 6 * AW['F'])
    v.update(Cu=kg * cu, Al=kg * al)
    if graphite_fraction:
        v['C'] = kg * carbon * graphite_fraction
    assert sum(v.values()) <= kg + 1e-09
    return v

def truck_inventory(cl, pt, profile):
    d = ANL['classes'][cl]
    i = ANL['powertrains'].index(pt)
    nonbattery = (sum(d['fixed_component_lb']) + sum(d['variable_component_lb'][i])) * LB
    values = {'Al': nonbattery * d['Al_material_pct'][i] / 100, 'Pb': d['Pb_battery_count'][i] * 69 * LB * 0.69}
    if profile['cu_fraction']:
        values['Cu'] = nonbattery * d['Cu_brass_pct'][i] / 100 * profile['cu_fraction']
    pack = 0.0
    if pt != 'ICE':
        rec = d[profile['chem']]
        pack = (d['battery_energy_kWh'] if pt == 'BEV' else d['battery_power_kW'][pt]) * 1000 / rec['specific'][pt]
        for m, v in battery_recipe(pack, rec['recipe'][pt], profile['chem'], profile['graphite_fraction']).items():
            values[m] = values.get(m, 0.0) + v
    if profile.get('steel_Fe_fraction'):
        steel_pct = {'C6': [49.4, 49.4, 50.6, 47.8], 'DAY': [50.8, 50.7, 50.7, 44.2], 'SLEEP': [51.5, 51.4, 51.5, 42.0]}[cl][i]
        batt_steel_pct = 0.1 if pt == 'BEV' else 0.7 if cl == 'C6' or (pt == 'HEV' and profile['chem'] == 'NMC811') else 0.6
        values['Fe'] = (nonbattery * steel_pct / 100 + pack * batt_steel_pct / 100) * profile['steel_Fe_fraction']
    if pt == 'FCV' and profile.get('additional_fcv_transfer'):
        values['Pt'] = {'C6': 190, 'DAY': 428, 'SLEEP': 426}[cl] * (30 / 114) / 1000
    return (values, dict(nonbattery_material_mass_kg=nonbattery, traction_battery_mass_kg=pack, source=ANL['source'], scope=ANL['boundary']))

def bus_inventory(pt, profile, parts):
    if pt == 'BEV':
        p = parts.copy()
    else:
        p = parts[parts.scope.isin(['body', 'chassis'])].copy()
    values = {}
    for r in p.itertuples():
        m = r.material
        kg = r.kg_per_vehicle
        if m in ['Cast_Al', 'Wrought_Al']:
            key = 'Al'
            v = kg
        elif m == 'Alumina':
            key = 'Al'
            v = kg * 2 * 26.9815385 / (2 * 26.9815385 + 3 * 15.999)
        elif m == 'Silica':
            key = 'Si'
            v = kg * 28.085 / (28.085 + 2 * 15.999)
        elif m == 'ZnO':
            key = 'Zn'
            v = kg * 65.38 / (65.38 + 15.999)
        elif m == 'Graphite':
            key = 'C'
            v = kg
        elif m in MINERALS:
            key = m
            v = kg
        elif m in ['Cu_Brass_unsplit', 'Brass'] and profile['cu_fraction']:
            key = 'Cu'
            v = kg * profile['cu_fraction']
        else:
            continue
        values[key] = values.get(key, 0.0) + v
    if pt == 'ICE':
        values['Pb'] = 43.5
    if pt == 'BEV':
        t = ANL['classes']['C6'][profile['chem']]
        kg = 395 * 1000 / t['specific']['BEV']
        for m, v in battery_recipe(kg, t['recipe']['BEV'], profile['chem'], profile['graphite_fraction']).items():
            values[m] = values.get(m, 0.0) + v
    if profile.get('steel_Fe_fraction'):
        steel = 1880 + 2930 + (72.3 + 0.366 + 62.1 if pt == 'BEV' else 0)
        values['Fe'] = steel * profile['steel_Fe_fraction']
    if pt == 'FCV' and profile.get('additional_fcv_transfer'):
        values['Pt'] = 70 * (30 / 114) / 1000
    return values

def build_inventory():
    old = pd.read_csv(R / 'output/native_vehicle_demand_two_scenarios/penelope_40_slot_intensities.csv')
    comp = pd.read_csv(R / 'output/vehicle_completion_v4/inventory_40_PARTIAL.csv')
    parts = pd.read_csv(R / 'input/road_vehicle_extension/bus_BEV_selected_materials.csv')
    records = []
    masses = []
    for profile in CASE_PROFILES:
        for year in range(2020, 2101):
            for pt in ['ICE', 'PHV', 'BEV']:
                src = old[(old.year == year) & old.vehicle_type.eq('TP_' + pt)]
                assert len(src) == 40
                for r in src.itertuples():
                    records.append(dict(case=profile['case'], year=year, vehicle_class='LDV', powertrain=pt, mineral=r.mineral, known_kg_per_vehicle=r.known_t_per_vehicle * 1000, scope='existing Penelope subtotal'))
            for pt, ref in [('HEV', profile['hev']), ('FCV', profile['fcv'])]:
                src = comp[comp.case.eq(ref)]
                assert len(src) == 40
                extras = {}
                if pt == 'FCV' and profile.get('additional_fcv_transfer'):
                    cfg = json.loads((R / 'input/vehicle_completion_v4/references.json').read_text())
                    refveh = next((x for x in cfg['fcv_reference_vehicles'] if ref.startswith(x['case'] + '_')))
                    block = refveh['mass_lb'] * LB * refveh['battery']
                    if block < 12.7:
                        raise ValueError('Auxiliary reference exceeds full battery block')
                    recipe = cfg['battery_recipe_reference']
                    extras = battery_recipe(block - 12.7, [recipe['active_NMC111'] * 100, recipe['Cu_material'] * 100, recipe['Al_material'] * 100, recipe['LiPF6'] * 100, recipe['graphite_carbon_combined'] * 100], 'NMC111', 0)
                    extras['Pb'] = 12.7 * 0.69
                    if profile.get('steel_Fe_fraction'):
                        extras['Fe'] = (block - 12.7) * 0.02 * profile['steel_Fe_fraction']
                if profile.get('steel_Fe_fraction'):
                    if pt == 'HEV':
                        bodydata = json.loads((R / 'input/hev_body_nimh_v3.json').read_text())['body_cases']
                        body = next((x for x in bodydata if 'sedan' in x['case']))
                        steel = body['vehicle_weight_lb'] * LB * body['glider_share'] * sum((x['share'] * x['Steel'] for x in body['parts']))
                    else:
                        materials = pd.read_csv(R / 'output/vehicle_completion_v4/FCV_materials_NOT_elements.csv')
                        steel = materials[materials.case.eq(ref) & materials.material.eq('Steel')].material_kg.sum()
                    extras['Fe'] = extras.get('Fe', 0) + steel * profile['steel_Fe_fraction']
                for r in src.itertuples():
                    val = r.known_subtotal_kg_per_vehicle
                    if r.mineral in extras:
                        val = (val if pd.notna(val) else 0.0) + extras[r.mineral]
                    records.append(dict(case=profile['case'], year=year, vehicle_class='LDV', powertrain=pt, mineral=r.mineral, known_kg_per_vehicle=val, scope=ref + ('; explicit 12.7kg auxiliary transfer split' if extras else '')))
            for cls in ['BUS', 'TRUCK_SMALL', 'TRUCK_LARGE']:
                for pt in ['ICE', 'HEV', 'BEV', 'FCV']:
                    if cls == 'BUS':
                        vals = bus_inventory(pt, profile, parts)
                        scope = '12m bus transfer; BEV battery chemistry alternative; HEV/FCV common body-chassis ONLY'
                    else:
                        cl = 'C6' if cls == 'TRUCK_SMALL' else profile['large']
                        vals, meta = truck_inventory(cl, pt, profile)
                        scope = 'ANL2021 ' + cl + ' transfer, rounded material percentages; batteries added once'
                        if year == 2020:
                            masses.append(dict(case=profile['case'], vehicle_class=cls, powertrain=pt, **meta))
                    for m in MINERALS:
                        records.append(dict(case=profile['case'], year=year, vehicle_class=cls, powertrain=pt, mineral=m, known_kg_per_vehicle=vals.get(m, np.nan), scope=scope))
    inv = pd.DataFrame(records)
    inv['whole_vehicle_complete'] = False
    inv['Al_scope'] = 'cast/wrought aluminum material mass proxy, alloy constituents not resolved'
    inv['missing_policy'] = 'NA unknown; no zero-use assertion; omitted content retained in calibrated residual at base year'
    assert not inv.duplicated(['case', 'year', 'vehicle_class', 'powertrain', 'mineral']).any()
    inv.to_csv(O / 'vehicle_inventory_40_PARTIAL.csv.gz', index=False)
    pd.DataFrame(masses).to_csv(O / 'truck_component_mass_audit.csv', index=False)
    pd.DataFrame(CASE_PROFILES).to_csv(O / 'cases.csv', index=False)
    return inv

def build():
    inv = build_inventory()
    acts = pd.concat([pd.read_csv(Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'three_tasks_20261111')) / f'road_annual_source_units_{sc}.csv.gz') for sc in ['Baseline', '300C']])
    a = acts.groupby(['Sc', 'year', 'vehicle_class', 'powertrain'], as_index=False).new_vehicles_year.sum()
    a.to_csv(O / 'road_activity_annual.csv', index=False)
    assert not a.duplicated(['Sc', 'year', 'vehicle_class', 'powertrain']).any()
    detail = pd.concat([g.merge(inv, on=['year', 'vehicle_class', 'powertrain'], validate='one_to_many') for _, g in a.groupby('Sc')], ignore_index=True)
    assert len(detail) == len(inv) * a.Sc.nunique()
    detail['known_demand_t_year'] = detail.new_vehicles_year * detail.known_kg_per_vehicle / 1000
    detail['coefficient_unknown'] = detail.known_kg_per_vehicle.isna()
    detail.loc[detail.new_vehicles_year.eq(0), 'known_demand_t_year'] = 0.0
    detail['unknown_active_inventory'] = detail.coefficient_unknown & detail.new_vehicles_year.gt(0)
    keys = ['Sc', 'case', 'year', 'mineral']
    v = detail.groupby(keys, as_index=False).agg(known_partial_vehicle_demand_t_year=('known_demand_t_year', lambda s: s.sum(min_count=1)), unknown_active_class_powertrain_count=('unknown_active_inventory', 'sum'))
    vc = detail.groupby(keys + ['vehicle_class'], as_index=False).known_demand_t_year.sum(min_count=1).pivot(index=keys, columns='vehicle_class', values='known_demand_t_year').reset_index()
    v = v.merge(vc, on=keys, validate='one_to_one')
    old = pd.read_csv(R / 'update_comparison_20261110/results_updated_native_all_sectors/all_sectors_CONDITIONAL.csv.gz')
    old = old[(old.statistic == 'average') & (old.grid_case == 'SPS') & (old['case'] == 'HEV_sedan_MG2010_WangNiMH_DOE2011_AB5_transfer')].drop(columns=['case'])
    assert len(old) == 6480
    base = old[old.year.eq(2020)][['Sc', 'mineral', 'vehicles_explicit_t_year', 'raw_other_low_t_year', 'raw_other_high_t_year']]
    totals = []
    bases = []
    for case in v['case'].unique():
        vv = v[v['case'].eq(case)]
        b = vv[vv.year.eq(2020)][['Sc', 'mineral', 'known_partial_vehicle_demand_t_year']].merge(base, on=['Sc', 'mineral'], validate='one_to_one')
        b['case'] = case
        b['added_explicit_base_t_year'] = b.known_partial_vehicle_demand_t_year.fillna(0) - b.vehicles_explicit_t_year
        b['new_residual_low'] = b.raw_other_low_t_year - b.added_explicit_base_t_year
        b['new_residual_high'] = b.raw_other_high_t_year - b.added_explicit_base_t_year
        b['negative_residual'] = b.new_residual_low.lt(0)
        bases.append(b)
        t = old.merge(vv, on=['Sc', 'year', 'mineral'], validate='one_to_one', suffixes=('_old', '_new')).merge(b[['Sc', 'mineral', 'new_residual_low', 'new_residual_high']], on=['Sc', 'mineral'], validate='many_to_one')
        t = t.rename(columns={'any_reported_coefficient_in_selected_inventory': 'previous_inventory_any_reported_coefficient'})
        t['previous_vehicle_t_year'] = t.vehicles_explicit_t_year
        t['vehicles_explicit_t_year'] = t.known_partial_vehicle_demand_t_year_new.fillna(0)
        t['raw_other_low_t_year'] = t.new_residual_low * t.growth_factor
        t['raw_other_high_t_year'] = t.new_residual_high * t.growth_factor
        t['negative_base'] = t.new_residual_low.lt(0)
        t['other_low_t_year'] = t.raw_other_low_t_year.where(~t.negative_base)
        t['other_high_t_year'] = t.raw_other_high_t_year.where(~t.negative_base)
        t['selected_explicit_sum_t_year'] = t[['power', 'hydrogen', 'stationary_battery', 'grid_CuAl_t_year', 'vehicles_explicit_t_year']].sum(axis=1)
        for bound in ['low', 'high']:
            t[f'conditional_total_{bound}_t_year'] = t.selected_explicit_sum_t_year + t[f'other_{bound}_t_year']
            t[f'cumulative_conditional_{bound}_t'] = t.groupby(['Sc', 'mineral'])[f'conditional_total_{bound}_t_year'].transform(lambda s: s.cumsum(skipna=False))
        t['total_change_low_t_year'] = t.conditional_total_low_t_year - old.set_index(['Sc', 'year', 'mineral']).conditional_total_low_t_year.reindex(pd.MultiIndex.from_frame(t[['Sc', 'year', 'mineral']])).to_numpy()
        t['full40_observed_total_ready'] = False
        t['basis'] = 'known_partial_gross_product_content; source transfer cases; primary accounting NOT applied'
        totals.append(t)
    t = pd.concat(totals, ignore_index=True)
    b = pd.concat(bases, ignore_index=True)
    t.to_csv(O / 'all_sectors_extended_CONDITIONAL.csv.gz', index=False)
    v.to_csv(O / 'vehicle_annual_by_class.csv.gz', index=False)
    detail.to_csv(O / 'vehicle_detail_audit.csv.gz', index=False)
    b.to_csv(O / 'baseline2020_recalibration.csv', index=False)
    check = t[t.year.eq(2020)].copy()
    np.testing.assert_allclose(check.selected_explicit_sum_t_year + check.raw_other_low_t_year, old[old.year.eq(2020)].set_index(['Sc', 'mineral']).conditional_total_low_t_year.reindex(pd.MultiIndex.from_frame(check[['Sc', 'mineral']])).to_numpy(), atol=1e-06)
    cumulative = t.groupby(['Sc', 'case', 'mineral'], as_index=False).agg(**{c: (c, lambda s: s.sum(min_count=len(s))) for c in ['LDV', 'BUS', 'TRUCK_SMALL', 'TRUCK_LARGE', 'vehicles_explicit_t_year', 'other_low_t_year', 'conditional_total_low_t_year', 'total_change_low_t_year']})
    cumulative = cumulative.rename(columns={col: col.replace('_t_year', '_cumulative_t') if col.endswith('_t_year') else col + '_known_cumulative_t' for col in ['LDV', 'BUS', 'TRUCK_SMALL', 'TRUCK_LARGE', 'vehicles_explicit_t_year', 'other_low_t_year', 'conditional_total_low_t_year', 'total_change_low_t_year']})
    cumulative.to_csv(O / 'cumulative_2020_2100.csv', index=False)
    coverage = detail[detail.new_vehicles_year.gt(0)].groupby(['case', 'vehicle_class', 'powertrain', 'mineral'], as_index=False).agg(any_coefficient_missing=('coefficient_unknown', 'any'))
    coverage.to_csv(O / 'active_inventory_coverage.csv', index=False)
    with pd.ExcelWriter(O / '車両拡張と全部門需要_条件付き.xlsx', engine='openpyxl') as w:
        pd.DataFrame([{'項目': k, '説明': v} for k, v in [('計算範囲', '世界・Baseline/300C・2020–2100年。エネルギーaverage、送配電SPSを固定した比較。'), ('結果の意味', '全40鉱物の既知部品小計と基準年残余を組み合わせた条件付き需要。全車両の40元素含有量を確定した値ではない。'), ('空欄と0', '原単位NAは不明。部門小計0は今回の明示計上がないという意味。使用不存在ではない。'), ('基準年', '車両を追加・置換した分を2020年残余から差し引き、GDP倍率で延長。二重上乗せを防ぐ。'), ('車種対応', '小型=C6配送車、大型=米国Class8地域配送/長距離。AIM区分との同一性・世界シェアは未実証。'), ('合金等', 'Alは材料量代理。Cu/Brassと黒鉛/CarbonはAでは控除せずBで全量換算する端点ケース。'), ('FCV', 'Aではバス・トラックPtを未計上、Eで出力比例転用。乗用車FCV新設は両シナリオ0台。'), ('未完了', 'FCVバス駆動系、HEV混合部材、合金の元素分解、未収録鉱物、部品単独交換、一次需要。'), ('ケース', 'A–Fは技術・物質範囲の別ケース。確率や信頼区間ではなくケース間の加算は禁止。')]]).to_excel(w, sheet_name='最初に読む', index=False)
        pd.DataFrame(CASE_PROFILES).to_excel(w, sheet_name='ケース定義', index=False)
        cumulative.to_excel(w, sheet_name='全40鉱物_累積', index=False)
        t[t.year.isin([2020, 2030, 2050, 2100])].to_excel(w, sheet_name='主要年_全部門', index=False)
        b.to_excel(w, sheet_name='2020残余再校正', index=False)
        inv[inv.year.eq(2020)].to_excel(w, sheet_name='1台原単位_2020', index=False)
        a.to_excel(w, sheet_name='クラス別新設台数', index=False)
        coverage.to_excel(w, sheet_name='未収録鉱物_稼働車種', index=False)
        for ws in w.book.worksheets:
            ws.freeze_panes = 'D2'
            ws.auto_filter.ref = ws.dimensions
    manifest = {'new_run': '2611091342', 'range': '2020–2100 inclusive', 'energy_and_grid': 'same updated average/SPS values held', 'bus_and_truck_added': True, 'HEV_v4_FCV_v4_added': True, 'all40_observed_complete': False, 'uncertainty_cases_are_not_confidence_intervals': True, 'source_mappings_are_assumptions': True, 'base_negative_rows': int(b.negative_residual.sum()), 'vehicle_flows_million_multiplier': 1000000, 'replacement_vehicle_demand_double_added': False, 'spare_battery_replacements_included': False, 'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [O / 'truck_reference.json', Path(__file__), R / 'output/vehicle_completion_v4/inventory_40_PARTIAL.csv', R / 'input/road_vehicle_extension/bus_BEV_selected_materials.csv', R / 'output/native_vehicle_demand_two_scenarios/penelope_40_slot_intensities.csv', R / 'update_comparison_20261110/results_updated_native_all_sectors/all_sectors_CONDITIONAL.csv.gz']}}
    (O / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print('Negative base rows:', manifest['base_negative_rows'])
    print(cumulative[cumulative['case'].eq(CASE_PROFILES[0]['case']) & cumulative.mineral.isin(['Cu', 'Al', 'Li', 'Co', 'Ni', 'Pt', 'Dy', 'Tb'])].to_string(index=False))
    return (inv, t, b)
if __name__ == '__main__':
    build()
