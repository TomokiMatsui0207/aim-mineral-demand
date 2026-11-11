"""Extend the auditable HEV subinventory with published non-overlapping scopes.

Recipe-transfer variants are conditional references, never complete vehicle assays.
Old output files are not modified. Masses of assemblies are never equated to elements.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model import MINERALS
from integrate_HEV_vehicle import build_vehicle_inventory, check_disjoint_scopes, central_sales, map_to_sales
from verify_body_nimh_v3 import body_materials
ROOT = Path(__file__).resolve().parent
MATERIALS = ['Steel', 'Wrought_Al', 'Cast_Al', 'Cu', 'Mg', 'GFRP', 'Glass', 'Plastic', 'Rubber', 'Stainless', 'CFRP', 'Cast_iron', 'Other']

def validate_config(cfg, materials):
    if materials.duplicated(['body_type', 'assembly', 'part']).any():
        raise ValueError('Duplicate source component')
    if not np.isfinite(materials[MATERIALS]).all().all() or ((materials[MATERIALS] < 0) | (materials[MATERIALS] > 100)).any().any():
        raise ValueError('Invalid material percentages')
    if not materials[MATERIALS].sum(axis=1).between(98, 102).all():
        raise ValueError('Unexpected source row total')
    if not 0 < cfg['auxiliary_battery']['lead_fraction'] < 1:
        raise ValueError('Invalid Pb fraction')
    mg2 = cfg['ORNL2010_MG2']
    mg1 = cfg['ORNL2010_MG1']
    if mg2['stator_Cu_kg'] + mg2['stator_core_laminations_kg'] > mg2['stator_kg']:
        raise ValueError('Motor subsets exceed stator')
    for mg in [mg1, mg2]:
        if not 0 < mg['magnet_kg'] < mg['rotor_including_magnets_and_shaft_kg']:
            raise ValueError('Invalid nested magnet mass')
    for dy in cfg['magnet_transfer']['Dy_mass_fractions']:
        if not 0 < dy + cfg['magnet_transfer']['Nd_mass_fraction'] < 1:
            raise ValueError('Invalid magnet recipe')
    for b in cfg['body_cases']:
        if abs(sum(b['major_shares'].values()) - 1) > 0.002 or abs(sum(b['powertrain_shares'].values()) - 1) > 0.011:
            raise ValueError('Unexpected source mass partition')
        if set(materials.loc[materials.body_type.eq(b['type'])].part) != set(b['powertrain_shares']) | {'transmission'}:
            raise ValueError('Missing source component')

def build(root=ROOT):
    inp = root / 'input/hev_refinement_v2'
    cfg = json.loads((inp / 'references.json').read_text())
    mat = pd.read_csv(inp / 'additional_component_materials.csv')
    validate_config(cfg, mat)
    old, oldtotal, _, _, _ = build_vehicle_inventory(root)
    glider_materials, _ = body_materials(json.loads((root / 'input/hev_body_nimh_v3.json').read_text()))
    frames = []
    audits = []
    material_rows = []
    cases = []
    changes = []
    machine_mass = []
    for b in cfg['body_cases']:
        oldcase = f"HEV_{b['type']}_MG2010_WangNiMH_DOE2011_AB5_transfer"
        existing = old.loc[old.case.eq(oldcase)].copy()
        mass = b['nominal_vehicle_lb'] * 0.45359237
        added = []
        non_element = []
        for row in glider_materials.loc[glider_materials.case.eq(b['body_reference'])].itertuples():
            non_element.append({'body_type': b['type'], 'scope': 'vehicle.glider.' + row.part.lower(), 'material': row.material, 'source_percent': row.material_fraction_in_part * 100, 'material_kg_per_vehicle': row.kg_per_glider, 'not_an_elemental_inventory': True})

        def add(scope, source, values, evidence):
            for m in MINERALS:
                added.append({'case': 'pending', 'scope': scope, 'source': source, 'mineral': m, 'quantified_kg_per_vehicle': values.get(m, np.nan), 'evidence': evidence, 'physical_component_count_per_vehicle': 1, 'full_component_element_coverage_confirmed': False})
        for r in mat.loc[mat.body_type.eq(b['type'])].itertuples():
            parent = mass * b['major_shares'][r.assembly]
            subshare = b['powertrain_shares'][r.part] if r.assembly == 'powertrain' else 1.0
            part_mass = parent * subshare
            values = {'Cu': part_mass * r.Cu / 100, 'Al': part_mass * (r.Wrought_Al + r.Cast_Al) / 100}
            values = {m: v for m, v in values.items() if v > 0}
            add(f'vehicle.{r.assembly}.{r.part}', 'GREET_C2G_' + b['composition_table'], values, 'published_material_proxy; source_system_partition; not_element_assay; minor_elements_unresolved')
            for material in MATERIALS:
                non_element.append({'body_type': b['type'], 'scope': f'vehicle.{r.assembly}.{r.part}', 'material': material, 'source_percent': getattr(r, material), 'material_kg_per_vehicle': part_mass * getattr(r, material) / 100, 'not_an_elemental_inventory': True})
            audits.append({'body_type': b['type'], 'check': r.part + '_material_rounding', 'source_assembly_kg': part_mass, 'sum_allocated_kg': part_mass * sum((getattr(r, m) for m in MATERIALS)) / 100, 'residual_kg': part_mass * (1 - sum((getattr(r, m) for m in MATERIALS)) / 100), 'interpretation': 'printed_percent_rounding_no_hidden_normalization'})
        wheel = mass * b['major_shares']['wheels'] / 2
        add('vehicle.wheels.rims', 'GREET_C2G_wheels_50_50_split', {'Al': wheel}, '50percent_of_wheels_assembly; cast_Al_material_proxy')
        add('vehicle.wheels.tires', 'GREET_C2G_tires', {}, 'major materials do not resolve elemental alloys/fillers; no graphite_C_conversion')
        non_element += [{'body_type': b['type'], 'scope': 'vehicle.wheels.rims', 'material': 'Cast_Al', 'source_percent': 100.0, 'material_kg_per_vehicle': wheel, 'not_an_elemental_inventory': True}]
        aux = cfg['auxiliary_battery']
        add('vehicle.auxiliary_battery', 'Yuasa12.7kg_x_GREET_generic_Pb69percent', {'Pb': aux['mass_kg'] * aux['lead_fraction']}, 'product_mass_x_transferred_generic_lead_acid_recipe; not_product_assay; one_initial_battery_only')
        add('vehicle.power_electronics', 'ORNL2011_Table2.3_whole_PCU', {}, '13kg_assembly_known; element_quantities_unresolved_without_recipe_transfer')
        audits += [{'body_type': b['type'], 'check': 'major_source_partition', 'source_assembly_kg': mass, 'sum_allocated_kg': mass * sum(b['major_shares'].values()), 'residual_kg': mass * (1 - sum(b['major_shares'].values())), 'interpretation': 'rounded_source_reference_not_actual_synthesized_vehicle_mass'}, {'body_type': b['type'], 'check': 'powertrain_subpartition', 'source_assembly_kg': mass * b['major_shares']['powertrain'], 'sum_allocated_kg': mass * b['major_shares']['powertrain'] * sum(b['powertrain_shares'].values()), 'residual_kg': mass * b['major_shares']['powertrain'] * (1 - sum(b['powertrain_shares'].values())), 'interpretation': '99percent_reported; remaining1percent_unallocated'}]
        material_rows.extend(non_element)
        for policy, dy in [('unresolved_electrical', None), ('historical_transfer_Dy045', 0.045), ('historical_transfer_Dy060', 0.06)]:
            case = f"HEV2_{b['type']}_NiMH2010_{policy}"
            parts = pd.concat([existing, pd.DataFrame(added)], ignore_index=True)
            parts['case'] = case

            def assign(scope, values, source, evidence):
                for m, value in values.items():
                    mask = parts.scope.eq(scope) & parts.mineral.eq(m)
                    if mask.sum() != 1 or parts.loc[mask, 'quantified_kg_per_vehicle'].notna().any():
                        raise ValueError('Attempt to overwrite existing contribution')
                    parts.loc[mask, 'quantified_kg_per_vehicle'] = value
                    parts.loc[mask, 'source'] = source
                    parts.loc[mask, 'evidence'] = evidence
            if dy is not None:
                h = cfg['historical_electrical_transfer']
                gm = h['generator_reference_lb'] * 0.45359237
                assign('vehicle.generator', {'Cu': gm * h['generator_composition']['Cu'], 'Al': gm * h['generator_composition']['Cast_Al']}, 'GREET2006_Table10_Table12', 'historical_complete_generator_mass_and_recipe; not_measured2010_MG1_Cu_Al')
                pm = cfg['ORNL2010_PCU']['whole_assembly_kg']
                assign('vehicle.power_electronics', {'Cu': pm * h['controller_composition']['Cu'], 'Al': pm * h['controller_composition']['Cast_Al']}, 'ORNL2010_PCU13kg_x_GREET2006_Table10_controller', 'cross_year_composition_transfer; wholePCU_once_not_allocated_inverters_plus_total')
                for scope, mg in [('vehicle.traction_motor', cfg['ORNL2010_MG2']), ('vehicle.generator', cfg['ORNL2010_MG1'])]:
                    assign(scope, {'Nd': mg['magnet_kg'] * cfg['magnet_transfer']['Nd_mass_fraction'], 'Dy': mg['magnet_kg'] * dy}, 'ORNL_magnet_mass_x_DOE2011_vehicle_recipe', 'DOE_composition_transfer_not_Prius_magnet_assay; no_Fe_B_remainder_assignment')
                ep = mass * b['major_shares']['powertrain'] * b['powertrain_shares']['exhaust']
                assign('vehicle.powertrain.exhaust', {'Pt': ep * h['exhaust_Pt_fraction']}, 'GREET2006_Table10_Pt_fraction_x_C2G_exhaust_mass', 'old_exhaust_recipe_transfer; not_actual_catalyst_loading; other_catalyst_metals_unresolved')
            check_disjoint_scopes(parts)
            frames.append(parts)
            for label, mg in [('MG2', cfg['ORNL2010_MG2']), ('MG1', cfg['ORNL2010_MG1'])]:
                machine_mass.append({'case': case, 'machine': label, 'magnet_kg': mg['magnet_kg'], 'rotor_kg_includes_magnet': mg['rotor_including_magnets_and_shaft_kg'], 'stator_kg': mg['stator_kg'], 'rotor_and_stator_kg': mg['rotor_including_magnets_and_shaft_kg'] + mg['stator_kg'], 'assembly_mass_added_as_element': False})
            cases.append({'case': case, 'body_type': b['type'], 'policy': policy, 'Dy_fraction_transferred': dy, 'battery_type': 'NiMH_only', 'AB5_recipe': 'DOE2011_molar_composition_transfer', 'whole_HEV_complete': False, 'generator_recipe': 'unknown' if dy is None else 'GREET2006_complete_generator61lb_not_ORNL_core', 'new_vehicle_only': True, 'global_fleet_share_known': False, 'future_2100_representativeness_established': False})
    parts = pd.concat(frames, ignore_index=True)
    check_disjoint_scopes(parts)
    total = parts.groupby(['case', 'mineral'], as_index=False).agg(quantified_subtotal_kg_per_vehicle=('quantified_kg_per_vehicle', lambda x: x.sum(min_count=1)), scopes_with_quantified_entries=('quantified_kg_per_vehicle', lambda x: x.notna().sum()), component_scopes=('scope', 'nunique'))
    missing = parts.loc[parts.quantified_kg_per_vehicle.isna()].groupby(['case', 'mineral']).scope.agg(lambda x: ';'.join(sorted(x)))
    total['unquantified_selected_scopes'] = [missing.get((r.case, r.mineral), '') for r in total.itertuples()]
    total['additional_pending_scopes'] = 'fluids;minor_electronics;steel_and_alloy_element_speciation;NiMH_plated_mixed_parts;other_catalyst_elements'
    total['whole_HEV_kg_per_vehicle'] = np.nan
    total['whole_HEV_complete'] = False
    total['accounting_basis'] = 'gross_new_vehicle_material_proxy_subinventory; not_full_or_primary_demand'
    total['interpretation'] = np.where(total.quantified_subtotal_kg_per_vehicle.notna(), 'quantified_subtotal_only; other_contributions_unresolved', 'unquantified_not_zero; actual_use_not_determined')
    total.loc[total.mineral.eq('Fe'), 'interpretation'] = 'BATTERY_REPORTED_Fe_PROXY_ONLY; vehicle_steel_castiron_motor_Fe_not_included'
    caseframe = pd.DataFrame(cases)
    for r in total.itertuples():
        bodytype = caseframe.set_index('case').loc[r.case, 'body_type']
        prev = oldtotal.loc[oldtotal.case.eq(f'HEV_{bodytype}_MG2010_WangNiMH_DOE2011_AB5_transfer') & oldtotal.mineral.eq(r.mineral)].quantified_subtotal_kg_per_vehicle.iloc[0]
        changes.append({'case': r.case, 'mineral': r.mineral, 'previous_subtotal_kg': prev, 'new_subtotal_kg': r.quantified_subtotal_kg_per_vehicle, 'difference_where_previous_known_kg': r.quantified_subtotal_kg_per_vehicle - prev})
    materials = pd.DataFrame(material_rows)
    return (parts, total, caseframe, pd.DataFrame(audits), materials, pd.DataFrame(changes), pd.DataFrame(machine_mass), cfg)

def run():
    parts, total, cases, audit, materials, changes, machines, cfg = build()
    out = ROOT / 'output/HEV_refinement_v2'
    out.mkdir(parents=True, exist_ok=True)
    annual = map_to_sales(central_sales(ROOT), total)
    cumulative = annual.loc[annual.year.eq(2100)]
    sources = pd.DataFrame([{'source_id': k, 'url': v, 'retrieval_date': cfg['retrieval_date'], 'local_original_pdf_available': False} for k, v in cfg['source_urls'].items()])
    summary = total.pivot(index='case', columns='mineral', values='quantified_subtotal_kg_per_vehicle').reset_index()
    summary.insert(1, '注意', '全鉱物が部分小計。Feは電池の報告Fe代理値のみ。鋼材由来Feは含まず。')
    overview = pd.DataFrame({'項目': ['結果の位置付け', 'unresolved_electrical', 'historical_transfer_Dy045/060', '共通の仮定', 'Feの重要な注意', 'NA', 'AIM対応', '再実行'], '説明': ['NiMHを搭載する複数資料の参照HEV。実車１台の完全な元素分析ではない。', '発電機・インバータの元素量と磁石・触媒の未確認組成を埋めないケース。', '古い組成の転用を追加する参考ケース。上下限・確率区間ではない。Dy率のみDOE2011の車両向け範囲。', 'GREET車体・動力系、ORNL2010 MG2、Wang電池、DOE AB5、Yuasa12V重量×GREET鉛組成を組み合わせる。', '表示2.46kgは電池の一部のみ。車体・動力系の鋼材をFeに換算していない。', '空欄は不明。不使用・ゼロとは解釈しない。', '走行距離19300km/年、乗車人数1.5、固定寿命12年の台数推計を使用。未校正。', 'python refine_HEV_intensity_v2.py。方法と出典はHEV_REFINEMENT_V2_JA.md。']})
    sheets = [('最初に読む', overview), ('１台小計kg_全量ではない', summary), ('40鉱物_不足範囲', total), ('部品別kg_重複検査済', parts), ('ケース定義', cases), ('旧版との比較', changes), ('丸め誤差_未配賦質量', audit), ('材料kg_元素と混同しない', materials), ('ORNL入れ子質量_非加算', machines), ('出典', sources), ('AIM2100累積_条件付き', cumulative)]
    gaps = ROOT / 'input/hev_refinement_v2/remaining_requirements.csv'
    if gaps.exists():
        sheets.append(('残る必要データ', pd.read_csv(gaps)))
    for name, frame in [('component_inventory', parts), ('inventory_40_PARTIAL', total), ('cases', cases), ('mass_rounding_audit', audit), ('additional_materials_NOT_elements', materials), ('change_from_v1', changes), ('nested_machine_masses_NOT_elements', machines), ('sources', sources), ('annual_demand_CONDITIONAL', annual), ('cumulative_demand_CONDITIONAL', cumulative)]:
        frame.to_csv(out / (name + '.csv'), index=False)
    with pd.ExcelWriter(out / 'HEV_refined_intensities.xlsx', engine='openpyxl') as writer:
        for name, frame in sheets:
            frame.to_excel(writer, sheet_name=name, index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                maxlen = max((len(str(c.value or '')) for c in col[:min(len(col), 100)]))
                ws.column_dimensions[col[0].column_letter].width = min(55, max(14, maxlen + 2))
    print(summary[['case', 'Cu', 'Al', 'Ni', 'Co', 'Nd', 'Dy', 'Pb', 'Pt', 'Fe']].to_string(index=False))
    print('All totals are PARTIAL. No unchanged/unknown mineral set to zero. Legacy electrical transfers optional.')
if __name__ == '__main__':
    run()
