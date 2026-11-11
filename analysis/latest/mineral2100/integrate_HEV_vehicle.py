"""Combine disjoint HEV component scopes; unknown inventory remains unknown.

These are cross-source reference HEVs, not measured complete real vehicles.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model import MINERALS
from verify_body_nimh_v3 import body_materials
from integrate_wang_nimh_v4 import calculations
from supplement_nimh_AB5_v5 import alloy_inventory
ROOT = Path(__file__).resolve().parent
PENDING_SCOPES = ['engine_fuel_exhaust_powertrain_excluding_motors', 'transmission_excluding_separately_counted_electric_machines', 'inverter_and_nonbattery_electronic_controller', 'separate_wheels_and_tires', 'auxiliary_12V_battery_and_fluids_outside_glider']

def check_disjoint_scopes(frame):
    """Reject duplicate elements or inclusion of a parent and its descendants."""
    keys = ['case', 'scope', 'mineral']
    if frame.duplicated(keys).any():
        raise ValueError('Duplicate component/mineral rows: possible double count')
    for case, g in frame.groupby('case'):
        scopes = sorted(g.scope.unique())
        for i, parent in enumerate(scopes):
            for child in scopes[i + 1:]:
                if child.startswith(parent + '.'):
                    raise ValueError(f'Overlapping parent/child scopes in {case}: {parent}, {child}')
    finite = frame.quantified_kg_per_vehicle.dropna()
    if not np.isfinite(finite).all() or (finite < 0).any():
        raise ValueError('Invalid component intensity')

def build_vehicle_inventory(root=ROOT):
    inp = root / 'input'
    cfg = json.loads((inp / 'hev_body_nimh_v3.json').read_text())
    machine_cfg = json.loads((inp / 'hev_evidence_v2.json').read_text())
    alloy_cfg = json.loads((inp / 'nimh_AB5_v5.json').read_text())
    body, _ = body_materials(cfg)
    battery, _, _, _ = calculations(pd.read_csv(inp / 'wang2021_S1_transcribed.csv'), pd.read_csv(inp / 'wang2021_S2_transcribed.csv'))
    nonalloy = battery.set_index('mineral').quantified_subtotal_kg_per_source_pack.dropna().to_dict()
    alloy = alloy_inventory(alloy_cfg).set_index('mineral').alloy_contribution_kg.to_dict()
    records = []
    cases = []
    magnet = []
    ledger = []
    machines = {c['case']: c for c in machine_cfg['measured_machines']}

    def add(case, scope, source, values, evidence):
        for m in MINERALS:
            records.append({'case': case, 'scope': scope, 'source': source, 'mineral': m, 'quantified_kg_per_vehicle': values.get(m, np.nan), 'evidence': evidence, 'physical_component_count_per_vehicle': 1, 'full_component_element_coverage_confirmed': False})
        ledger.append({'case': case, 'scope': scope, 'source': source, 'action': 'include_once', 'inventory_extent': evidence})
    for b in cfg['body_cases']:
        for year in [2004, 2010]:
            for mode in ['source_only', 'DOE2011_AB5_transfer']:
                body_type = 'sedan' if 'sedan' in b['case'] else 'smallSUV'
                case = f'HEV_{body_type}_MG{year}_WangNiMH_{mode}'
                cases.append({'case': case, 'body_reference': b['case'], 'motor_reference': f'Prius{year}_MG2', 'battery_reference': 'Wang2021_S1_39.07kg_pack', 'AB5_mode': mode, 'case_type': 'cross_source_component_reference_HEV', 'whole_HEV_complete': False, 'measured_single_real_vehicle': False, 'fleet_technology_share_known': False})
                for part in b['parts']:
                    g = body.loc[body.case.eq(b['case']) & body.part.eq(part['part'])].set_index('material').kg_per_glider
                    add(case, 'vehicle.glider.' + part['part'].lower(), 'ANL22_27_Rev1_glider_tables', {'Cu': g['Cu'], 'Al': g['Wrought_Al'] + g['Cast_Al']}, 'GREET_glider_subcomponent; Cu_and_Al_material_proxy_only; steel_not_pure_Fe')
                mg = machines[f'Prius{year}_MG2']
                add(case, 'vehicle.traction_motor', 'ORNL2011_' + mg['case'], {'Cu': mg['Cu_kg']}, 'one_MG2_stator_Cu; other_motor_elements_unquantified')
                gen = machines.get(f'Prius{year}_MG1')
                add(case, 'vehicle.generator', 'ORNL2011_generator' if gen else 'unquantified_generator', {}, 'generator_elements_unknown; measured_magnet_material_separate_when_available')
                add(case, 'vehicle.traction_battery.non_alloy', 'Wang2021_S1_non_AB5_rows', nonalloy, 'one_complete_pack_reference; quantified_nonalloy_rows_including_some_case_metal; remaining_rows_unknown')
                add(case, 'vehicle.traction_battery.AB5_alloy', 'DOE2011_composition_x_Wang9.23kg' if mode != 'source_only' else 'Wang_AB5_elements_unknown', alloy if mode != 'source_only' else {}, 'literature_composition_transfer_not_same_pack_assay' if mode != 'source_only' else 'unquantified_AB5_composition')
                magnet.append({'case': case, 'component': 'MG2', 'NdFeB_material_kg_per_vehicle': mg['NdFeB_kg'], 'Nd_element_kg': np.nan, 'included_in_elemental_total': False})
                magnet.append({'case': case, 'component': 'MG1', 'NdFeB_material_kg_per_vehicle': gen['NdFeB_kg'] if gen else np.nan, 'Nd_element_kg': np.nan, 'included_in_elemental_total': False})
                for scope in PENDING_SCOPES:
                    ledger.append({'case': case, 'scope': 'vehicle.pending.' + scope, 'source': 'not_integrated', 'action': 'unquantified_not_zero', 'inventory_extent': 'boundary_and_inventory_to_be_completed'})
    parts = pd.DataFrame(records)
    check_disjoint_scopes(parts)
    total = parts.groupby(['case', 'mineral'], as_index=False).agg(quantified_subtotal_kg_per_vehicle=('quantified_kg_per_vehicle', lambda x: x.sum(min_count=1)), component_scopes=('scope', 'nunique'), scopes_with_quantified_entries=('quantified_kg_per_vehicle', lambda x: x.notna().sum()))
    missing = parts.loc[parts.quantified_kg_per_vehicle.isna()].groupby(['case', 'mineral']).scope.agg(lambda x: ';'.join(sorted(x)))
    total['unquantified_selected_scopes'] = [missing.get((r.case, r.mineral), '') for r in total.itertuples()]
    total['additional_pending_scopes'] = ';'.join(PENDING_SCOPES)
    total['whole_HEV_kg_per_vehicle'] = np.nan
    total['whole_HEV_complete'] = False
    total['accounting_basis'] = 'gross_embodied_material_subinventory_not_primary_or_ore_demand'
    return (parts, total, pd.DataFrame(cases), pd.DataFrame(magnet), pd.DataFrame(ledger))

def map_to_sales(sales, inventory):
    hev = sales.loc[sales.technology.eq('TP_HEV')].copy()
    if hev.empty or hev.duplicated(['Sc', 'year']).any() or (hev.new < 0).any() or (not np.isfinite(hev.new).all()):
        raise ValueError('Invalid or mixed activity cases')
    for _, g in hev.groupby('Sc'):
        if set(g.year) != set(range(2020, 2101)):
            raise ValueError('Missing activity years')
    d = hev[['Sc', 'year', 'new']].rename(columns={'new': 'HEV_new_assumed'}).merge(inventory, how='cross')
    d['quantified_subtotal_t_year'] = d.HEV_new_assumed * d.quantified_subtotal_kg_per_vehicle / 1000
    d.loc[d.HEV_new_assumed.eq(0), 'quantified_subtotal_t_year'] = 0.0
    d['whole_HEV_t_year'] = np.where(d.HEV_new_assumed.eq(0), 0.0, np.nan)
    d['activity_status'] = '19300km_year_1.5persons_12year_life_2005uniform_initial_cohorts; not_calibrated_fleet_sales'
    d['case_assignment'] = 'hypothetical_reference_case_for_every_HEV_new_vehicle; no_measured_fleet_share'
    d['OSD_overlap_resolved'] = False
    d = d.sort_values(['Sc', 'case', 'mineral', 'year'])
    d['cumulative_quantified_2020_through_year_t'] = d.groupby(['Sc', 'case', 'mineral']).quantified_subtotal_t_year.transform(lambda x: x.cumsum(skipna=False))
    return d

def central_sales(root):
    from integrate_server_exports import validated_exports
    from calculate_ldv_from_export import calculate
    inp = root / 'input/server_exports'
    ldv = pd.concat([pd.read_csv(f) for f in sorted(inp.glob('mineral_LDV_*.csv')) if f.name in {'mineral_LDV_Baseline.csv', 'mineral_LDV_300C.csv'}], ignore_index=True)
    battery = pd.concat([pd.read_csv(f) for f in sorted(inp.glob('mineral_battery_*.csv'))], ignore_index=True)
    valid, _, _ = validated_exports(ldv, battery)
    return calculate(valid, 19300.0, 1.5, 12, initial_year=2005, first_output_year=2020)

def run():
    parts, total, cases, magnets, ledger = build_vehicle_inventory()
    annual = map_to_sales(central_sales(ROOT), total)
    out = ROOT / 'output/HEV_integrated_vehicle'
    out.mkdir(parents=True, exist_ok=True)
    summary = total.pivot(index='case', columns='mineral', values='quantified_subtotal_kg_per_vehicle').reset_index()
    cumulative = annual.loc[annual.year.eq(2100), ['Sc', 'case', 'mineral', 'cumulative_quantified_2020_through_year_t', 'whole_HEV_complete', 'OSD_overlap_resolved']]
    for name, frame in [('component_contributions_kg_per_vehicle', parts), ('HEV_inventory_40_slots_PARTIAL', total), ('reference_cases', cases), ('magnet_material_NOT_element', magnets), ('physical_scope_ledger', ledger), ('annual_HEV_demand_CONDITIONAL_PARTIAL', annual), ('cumulative_HEV_demand_CONDITIONAL_PARTIAL', cumulative)]:
        frame.to_csv(out / f'{name}.csv', index=False)
    with pd.ExcelWriter(out / 'HEV_integrated_vehicle.xlsx') as writer:
        for name, frame in [('1台当たり小計kg_ケース別', summary), ('部品別の寄与kg', parts), ('40鉱物_不足範囲', total), ('参照HEVの定義', cases), ('重複防止と未統合範囲', ledger), ('磁石材料_元素換算せず', magnets), ('AIM対応_累積小計t', cumulative)]:
            frame.to_excel(writer, sheet_name=name, index=False)
    print(summary[['case', 'Cu', 'Al', 'Ni', 'Co', 'La', 'Ce', 'Nd', 'Pr']].to_string(index=False))
    print('Scope overlap audit passed; no full-inventory or OSD-completion claim.')
if __name__ == '__main__':
    run()
