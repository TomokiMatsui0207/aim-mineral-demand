"""HEV/FCV reference inventories with physical ownership and missing-data ledgers.
Not complete vehicle assays or a silent replacement of the published all-sector result.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
from model import MINERALS
from refine_HEV_intensity_v3 import build as hev_v3
from integrate_HEV_vehicle import check_disjoint_scopes
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/vehicle_completion_v4'

def drop_competing_ownership(parts, mode):
    """Conservative exclusion pending source-level physical boundary confirmation."""
    if mode == 'teardown':
        banned = ('vehicle.transmission.', 'vehicle.powertrain.powertrain_electrical')
    elif mode == 'GREET_blocks':
        banned = ('vehicle.traction_motor', 'vehicle.generator', 'vehicle.power_electronics')
    else:
        raise ValueError('Unknown ownership mode')
    mask = parts.scope.map(lambda s: any((s == p or s.startswith(p) for p in banned)))
    removed = parts.loc[mask].copy()
    kept = parts.loc[~mask].copy()
    return (kept, removed)

def build_hev(root=ROOT):
    old, total, cases, audit, cfg = hev_v3(root)
    frames = []
    excluded = []
    meta = []
    for body in ['sedan', 'smallSUV']:
        base = old.loc[old.case.eq('HEV3_' + body + '_Nordelof_reference')].copy()
        for mode in ['teardown', 'GREET_blocks']:
            case = 'HEV4_' + body + '_' + mode
            p, r = drop_competing_ownership(base, mode)
            p['case'] = case
            r['case'] = case
            r['reason'] = 'potential physical boundary overlap; not proof that source inventories definitely duplicate'
            for scope in r.scope.unique():
                unknown = r.loc[r.scope.eq(scope)].copy()
                unknown['quantified_kg_per_vehicle'] = np.nan
                unknown['evidence'] = 'EXCLUDED_competing_inventory; boundary or component completion pending'
                p = pd.concat([p, unknown], ignore_index=True)
            frames.append(p)
            excluded.append(r)
            meta.append({'case': case, 'vehicle_type': 'TP_HEV', 'ownership_mode': mode, 'all40_complete': False, 'whole_vehicle_complete': False, 'same_vehicle_assay': False, 'future_fleet_share_known': False, 'note': 'GREET transmission vs physical motor/PCU boundary not confirmed; families must not be added'})
    return (pd.concat(frames, ignore_index=True), pd.concat(excluded, ignore_index=True), pd.DataFrame(meta))

def add_scope(records, case, scope, values, source, evidence):
    for m in MINERALS:
        records.append(dict(case=case, scope=scope, mineral=m, quantified_kg_per_vehicle=values.get(m, np.nan), source=source, evidence=evidence))

def build_fcv(root=ROOT):
    cfg = json.loads((root / 'input/vehicle_completion_v4/references.json').read_text())
    bodies = json.loads((root / 'input/hev_body_nimh_v3.json').read_text())['body_cases']
    records = []
    materials = []
    parents = []
    meta = []
    for vehicle in cfg['fcv_reference_vehicles']:
        body = next((b for b in bodies if ('smallSUV' in b['case']) == (vehicle['body'] == 'smallSUV')))
        mass = vehicle['mass_lb'] * 0.45359237
        for pt in cfg['Pt_cases']:
            case = vehicle['case'] + '_' + pt['case']
            meta.append({'case': case, 'vehicle_type': 'TP_FCV', 'ownership_mode': 'ANL_component_blocks', 'all40_complete': False, 'whole_vehicle_complete': False, 'same_vehicle_assay': False, 'future_fleet_share_known': False, 'Pt_g_per_stack': pt['g_per_stack'], 'note': pt['meaning'] if 'meaning' in pt else pt['source']})
            major = {k: mass * vehicle[k] for k in ['glider', 'powertrain', 'transmission', 'battery', 'electric_machines_control', 'wheels']}
            parents.append(dict(case=case, quantity='vehicle_rounding_balance', mass_kg=mass - sum(major.values()), meaning='printed major shares not normalized; not additional element'))

            def part(scope, kg, fractions):
                if not np.isfinite(kg) or kg < 0 or sum(fractions.values()) > 1.00000001:
                    raise ValueError('Invalid component partition')
                vals = {}
                for mat, f in fractions.items():
                    v = kg * f
                    materials.append(dict(case=case, scope=scope, material=mat, material_kg=v, component_kg=kg, source='ANL22_27_Tables26_32', add_to_element_total=False))
                    if mat == 'Cu' and v > 0:
                        vals['Cu'] = vals.get('Cu', 0) + v
                    if mat in ['Wrought_Al', 'Cast_Al'] and v > 0:
                        vals['Al'] = vals.get('Al', 0) + v
                if scope == 'vehicle.powertrain.fuel_cell_stack_BOP' and pt['g_per_stack'] is not None:
                    p = pt['g_per_stack'] / 1000
                    other = kg * fractions['Other']
                    if p > other:
                        raise ValueError('Pt exceeds stack other-material pool')
                    vals['Pt'] = p
                    parents.append(dict(case=case, quantity='stack_other_remaining_after_Pt', mass_kg=other - p, meaning='nonadditive parent-child accounting; source Other includes unidentified minor materials'))
                add_scope(records, case, scope, vals, 'ANL22_27_Rev1_plus_Pt_reference', 'major Cu/Al material proxies; other elements unknown; Pt case transferred separately')
                parents.append(dict(case=case, quantity=scope + '_unextracted_material_balance', mass_kg=kg * (1 - sum(fractions.values())), meaning='unextracted materials; not pure Fe or graphite'))
            for p in body['parts']:
                part('vehicle.glider.' + p['part'].lower(), major['glider'] * p['share'], {m: p[m] for m in ['Steel', 'Wrought_Al', 'Cast_Al', 'Cu']})
            for name, share in [('fuel_cell_stack_BOP', vehicle['stack_share_of_powertrain']), ('hydrogen_storage_BOP', vehicle['tank_share_of_powertrain'])]:
                part('vehicle.powertrain.' + name, major['powertrain'] * share, cfg['selected_material_fractions'][name])
            part('vehicle.transmission', major['transmission'], cfg['selected_material_fractions']['transmission'])
            for name in ['rims', 'tires']:
                part('vehicle.wheels.' + name, major['wheels'] * 0.5, cfg['selected_material_fractions'][name])
            for name in ['battery', 'electric_machines_control']:
                add_scope(records, case, 'vehicle.' + name, {}, 'ANL22_27_Table26_27', 'parent block known; traction/auxiliary or motor/control suballocation unresolved; no extra battery or magnets appended')
                parents.append(dict(case=case, quantity=name + '_unallocated_block', mass_kg=major[name], meaning='physical parent block; elemental quantity unknown'))
    p = pd.DataFrame(records)
    check_disjoint_scopes(p)
    return (p, pd.DataFrame(materials), pd.DataFrame(parents), pd.DataFrame(meta))

def battery_recipe_coefficients(cfg):
    aw = {'Li': 6.94, 'Ni': 58.6934, 'Mn': 54.938044, 'Co': 58.933194, 'O': 15.999, 'P': 30.973761998, 'F': 18.998403163}
    mol = {'Li': 1, 'Ni': 1 / 3, 'Mn': 1 / 3, 'Co': 1 / 3, 'O': 2}
    den = sum((aw[m] * n for m, n in mol.items()))
    c = cfg['battery_recipe_reference']
    out = {m: c['active_NMC111'] * aw[m] * mol[m] / den for m in ['Li', 'Ni', 'Mn', 'Co']}
    out['Li'] += c['LiPF6'] * aw['Li'] / (aw['Li'] + aw['P'] + 6 * aw['F'])
    out.update(Al=c['Al_material'], Cu=c['Cu_material'])
    return out

def fcv_stainless_chromium_bounds(materials, cfg):
    stainless = materials.loc[materials.material.eq('Stainless')].groupby('case', as_index=False).material_kg.sum().rename(columns={'material_kg': 'selected_stainless_material_kg'})
    stainless['Cr_minimum_in_selected_material_kg'] = stainless.selected_stainless_material_kg * cfg['stainless_chromium_definition']['minimum_mass_fraction']
    stainless['point_estimate_kg'] = np.nan
    stainless['meaning'] = 'conditional lower bound from stainless definition; not point estimate; component percentages rounded; no global uncertainty interval'
    stainless['source'] = cfg['stainless_chromium_definition']['source']
    return stainless

def split_high_power_battery(block_mass_kg, auxiliary_mass_kg, cfg):
    """Explicit scenario allocation, no default auxiliary mass or chemistry adoption."""
    if auxiliary_mass_kg is None or not np.isfinite(block_mass_kg) or (not np.isfinite(auxiliary_mass_kg)) or (not 0 <= auxiliary_mass_kg <= block_mass_kg):
        raise ValueError('Explicit valid auxiliary allocation required')
    traction = block_mass_kg - auxiliary_mass_kg
    out = {m: traction * v for m, v in battery_recipe_coefficients(cfg).items()}
    out['Pb'] = auxiliary_mass_kg * 0.69
    return out

def plated_partition(fe_ni_masses, cu_ni_mass, fe_ni_Ni_fractions, cu_ni_Ni_fraction):
    if not np.isfinite(cu_ni_mass) or cu_ni_mass < 0:
        raise ValueError('Invalid Cu-Ni mass')
    f = np.array(fe_ni_Ni_fractions, dtype=float)
    m = np.array(fe_ni_masses, dtype=float)
    if f.shape != m.shape or not np.isfinite(f).all() or (not np.isfinite(m).all()) or (m < 0).any() or ((f < 0) | (f > 1)).any() or (not np.isfinite(cu_ni_Ni_fraction)) or (not 0 <= cu_ni_Ni_fraction <= 1):
        raise ValueError('Invalid plating allocation')
    ni = float(np.dot(m, f) + cu_ni_mass * cu_ni_Ni_fraction)
    return {'Ni': ni, 'Fe': float(np.dot(m, 1 - f)), 'Cu': cu_ni_mass * (1 - cu_ni_Ni_fraction)}

def totals(parts):
    d = parts.groupby(['case', 'mineral'], as_index=False).agg(known_subtotal_kg_per_vehicle=('quantified_kg_per_vehicle', lambda x: x.sum(min_count=1)), unknown_scope_count=('quantified_kg_per_vehicle', lambda x: x.isna().sum()))
    d['whole_vehicle_kg_per_vehicle'] = np.nan
    d['whole_vehicle_complete'] = False
    d['interpretation'] = 'known partial subtotal; missing scopes do not equal zero; gross contained material proxy, not primary supply'
    return d

def map_native(activity, inventory, meta):
    if activity.duplicated(['Sc', 'year', 'vehicle_type']).any():
        raise ValueError('Duplicate activity')
    if not np.isfinite(activity.native_vehicle_additions_year).all() or (activity.native_vehicle_additions_year < 0).any():
        raise ValueError('Invalid activity')
    inv = inventory.merge(meta[['case', 'vehicle_type']], on='case', validate='many_to_one')
    a = activity.merge(inv, on='vehicle_type', validate='many_to_many')
    a['known_subtotal_t_year'] = a.native_vehicle_additions_year * a.known_subtotal_kg_per_vehicle / 1000
    a.loc[a.native_vehicle_additions_year.eq(0), 'known_subtotal_t_year'] = 0
    a['unknown_coefficient'] = a.known_subtotal_kg_per_vehicle.isna()
    a['active_unknown_coefficient'] = a.native_vehicle_additions_year.gt(0) & a.unknown_coefficient
    a['whole_vehicle_t_year'] = np.where(a.native_vehicle_additions_year.eq(0), 0, np.nan)
    return a

def run(root=ROOT):
    out = root / 'output/vehicle_completion_v4'
    out.mkdir(exist_ok=True, parents=True)
    cfg = json.loads((root / 'input/vehicle_completion_v4/references.json').read_text())
    h, excluded, hm = build_hev(root)
    f, materials, parents, fm = build_fcv(root)
    p = pd.concat([h, f], ignore_index=True)
    check_disjoint_scopes(p)
    meta = pd.concat([hm, fm], ignore_index=True)
    inv = totals(p)
    activity = pd.read_csv(root / 'output/native_vehicle_demand_two_scenarios/annual_vehicle_additions.csv')
    annual = map_native(activity.loc[activity.vehicle_type.isin(['TP_HEV', 'TP_FCV'])], inv, meta)
    cumulative = annual.groupby(['Sc', 'case', 'vehicle_type', 'mineral'], as_index=False).agg(known_partial_cumulative_t=('known_subtotal_t_year', lambda x: x.sum(min_count=1)), active_unquantified_years=('active_unknown_coefficient', 'sum'))
    cumulative.loc[cumulative.active_unquantified_years.gt(0), 'known_partial_cumulative_t'] = np.nan
    cumulative['whole_vehicle_complete'] = False
    battery = pd.DataFrame([{'mineral': m, 'kg_per_kg_NMC111_battery': v, 'use': 'standalone recipe; NOT multiplied by ANL battery mass block without auxiliary split; not actual Mirai cathode'} for m, v in battery_recipe_coefficients(cfg).items()])
    crbounds = fcv_stainless_chromium_bounds(materials, cfg)
    envelopes = pd.DataFrame([{'mineral': m, 'minimum_additional_kg': 0, 'maximum_additional_kg': upper, 'scope': 'Fe-Ni 1.55+0.92+0.23kg and Cu-Ni0.23kg ONLY', 'interpretation': 'marginal physical envelope, not confidence interval; maxima cannot coexist; Ni+Fe+Cu=2.93 in binary-material approximation; plating chemistry unverified'} for m, upper in [('Ni', 2.93), ('Fe', 2.7), ('Cu', 0.23)]])
    changes = []
    old = hev_v3(root)[1]
    for case in hm.case:
        body = hm.loc[hm.case.eq(case)].case.iloc[0].split('_')[1]
        o = old.loc[old.case.eq('HEV3_' + body + '_Nordelof_reference')].set_index('mineral').quantified_subtotal_kg_per_vehicle
        n = inv.loc[inv.case.eq(case)].set_index('mineral').known_subtotal_kg_per_vehicle
        for m in MINERALS:
            changes.append({'case': case, 'mineral': m, 'previous_partial_kg': o[m], 'revised_partial_kg': n[m], 'reason': 'coverage changed by conservative competing-ownership exclusions; not an actual demand reduction'})
    overview = pd.DataFrame({'項目': ['位置付け', 'HEVの2系列', 'FCVのPt', 'FCV駆動電池', 'Cr', 'C', 'NiMHめっき', 'AIM活動量', '統合状態'], '説明': ['kg/新車1台の既知部品小計。全40鉱物の全車両量ではない。空欄は未確定。', 'GREET装置区分と分解部品を併用しない代替ケース。小計の差は範囲の差で、実需要の減少や上下限ではない。', '未確定/30g文献推計転用/40g文献推計転用。メーカー実測値や世界平均ではなく、ケース間合算禁止。', '親ブロックは分かるが補機電池との質量配分未確定。NMC係数は別表で、自動適用しない。', 'ステンレス10.5%という定義を使う条件付き下限。点推計へ足していない。', 'CFRP・樹脂・カーボン紙を黒鉛として加算しない。', 'Ni・Fe・Cuの物理的な限界を別表化。各元素の最大値は同時採用不可。', '旧AIM出力2608261554のnative台数。新版未反映。独自寿命更新を追加しない。', '旧全部門v6は上書きせず。本版は車両原単位・車両部分需要の別出力。基準年残余の再校正前。']})
    wide = inv.pivot(index='case', columns='mineral', values='known_subtotal_kg_per_vehicle').reset_index()
    occurrence = []
    for tech in ['TP_HEV', 'TP_FCV']:
        selected = inv.merge(meta[['case', 'vehicle_type']], on='case').loc[lambda x: x.vehicle_type.eq(tech)]
        for m in MINERALS:
            q = selected.loc[selected.mineral.eq(m), 'known_subtotal_kg_per_vehicle']
            state = 'quantity_in_some_reference_cases_PARTIAL' if q.notna().any() else 'not_quantified_not_zero'
            note = 'No proof of physical absence; uncertain alloy/electronic and trace components remain.'
            source = 'component_inventory and references.json'
            if tech == 'TP_FCV' and m == 'Cr':
                state = 'material_definition_lower_bound_only'
                note = 'Stainless material proxy contains Cr >=10.5%; actual grade and full Cr amount unknown.'
                source = cfg['stainless_chromium_definition']['source']
            if tech == 'TP_HEV' and m == 'Y':
                state = 'presence_reported_no_bulk_quantity'
                note = 'ORNL Fig2.31 local insulator phase contains Y; phase concentration is not whole module composition.'
                source = cfg['ornl_url']
            if m == 'C':
                note = 'Graphite scope: polymers/CFRP and generic graphite-carbon mixture not automatically converted to graphite.'
            occurrence.append({'vehicle_type': tech, 'mineral': m, 'status': state, 'note': note, 'source': source, 'whole_vehicle_complete': False})
    occurrence = pd.DataFrame(occurrence)
    tables = {'最初に読む': overview, 'ケース別部分小計kg': wide, '40鉱物の補完状況': occurrence, '1台部分原単位': inv, 'ケース定義': meta, '部品別寄与': p, 'HEV併用除外': excluded, 'FCV材料_元素ではない': materials, 'FCV親子質量_非加算': parents, 'NMC参照係数_未統合': battery, 'NiMHめっき物理範囲': envelopes, 'FCV_Cr下限_点推計でない': crbounds, 'HEV旧版との比較': pd.DataFrame(changes), 'native累積_条件付き': cumulative}
    for name, frame in [('inventory_40_PARTIAL', inv), ('occurrence_status_40', occurrence), ('cases', meta), ('component_inventory', p), ('HEV_excluded_competing_inventory', excluded), ('FCV_materials_NOT_elements', materials), ('FCV_parent_child_mass_ledger', parents), ('NMC111_coefficients_NOT_integrated', battery), ('NiMH_plating_marginal_envelopes', envelopes), ('FCV_Cr_lower_bound_NOT_point_estimate', crbounds), ('HEV_previous_comparison', pd.DataFrame(changes)), ('native_cumulative_PARTIAL', cumulative)]:
        frame.to_csv(out / (name + '.csv'), index=False)
    annual.to_csv(out / 'native_annual_PARTIAL.csv.gz', index=False, compression='gzip')
    with pd.ExcelWriter(out / 'HEV_FCV_component_completion_v4.xlsx', engine='openpyxl') as w:
        for name, frame in tables.items():
            frame.to_excel(w, sheet_name=name, index=False)
            ws = w.book[name]
            ws.freeze_panes = 'C2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(65, max(16, max((len(str(c.value or '')) for c in col[:50])) + 1))
    inputs = [root / 'input/vehicle_completion_v4/references.json', root / 'input/hev_body_nimh_v3.json', root / 'input/hev_refinement_v2/references.json', root / 'input/hev_refinement_v2/additional_component_materials.csv', root / 'input/hev_refinement_v3/reference.json', root / 'input/hev_evidence_v2.json', root / 'input/nimh_AB5_v5.json', root / 'input/wang2021_S1_transcribed.csv', root / 'input/wang2021_S2_transcribed.csv', root / 'output/native_vehicle_demand_two_scenarios/annual_vehicle_additions.csv']
    files = inputs + [root / 'complete_vehicle_components_v4.py', root / 'refine_HEV_intensity_v3.py', root / 'refine_HEV_intensity_v2.py', root / 'integrate_HEV_vehicle.py', root / 'integrate_wang_nimh_v4.py', root / 'supplement_nimh_AB5_v5.py', root / 'verify_body_nimh_v3.py', root / 'model.py', root / 'test_complete_vehicle_components_v4.py']
    manifest = {'version': cfg['version'], 'inputs_and_implementation': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, 'all_sectors_v6_overwritten': False, 'AIM_output_id': '2608261554', 'new_AIM_output_used': False, 'annual_rows': len(annual), 'case_count': len(meta)}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(inv.loc[inv.mineral.isin(['Cu', 'Al', 'Pt', 'Ni', 'Fe'])].pivot(index='case', columns='mineral', values='known_subtotal_kg_per_vehicle').to_string())
    print('Cases:', len(meta), 'annual rows:', len(annual), 'all-sector v6 retained unchanged')
if __name__ == '__main__':
    run()
