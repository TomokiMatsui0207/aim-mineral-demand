"""Road vehicle scope expansion. Missing classes/scales/intensities are never zeros."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json, re, hashlib
import pandas as pd
import numpy as np
from model import MINERALS
ROOT = Path(__file__).resolve().parent
PREFIX = {'TPPCOG': 'LDV', 'TPPCOD': 'LDV', 'TPBSOI': 'BUS', 'TFTSOI': 'TRUCK_SMALL', 'TFTLOI': 'TRUCK_LARGE'}
SERVICES = {'LDV': {'TPPG', 'TPPD'}, 'BUS': {'TPBS'}, 'TRUCK_SMALL': {'TFTS'}, 'TRUCK_LARGE': {'TFTL'}}
EXPECTED = {'LDV': {'ICE', 'HEV', 'PHV', 'BEV', 'FCV'}, 'BUS': {'ICE', 'HEV', 'BEV', 'FCV'}, 'TRUCK_SMALL': {'ICE', 'HEV', 'BEV', 'FCV'}, 'TRUCK_LARGE': {'ICE', 'HEV', 'BEV', 'FCV'}}
KEY = ['Sc', 'region', 'sector', 'technology', 'year']

def classify(technology):
    m = re.fullmatch('(TPPCOG|TPPCOD|TPBSOI|TFTSOI|TFTLOI)_(EXT|NEW|HEF\\d+|NGV|HEV|PHV|BEV|FCV)', technology)
    if not m:
        raise ValueError('Unmapped road technology: ' + str(technology))
    category = PREFIX[m[1]]
    power = 'ICE' if m[2] in ['EXT', 'NEW', 'NGV'] or m[2].startswith('HEF') else m[2]
    if power not in EXPECTED[category]:
        raise ValueError('Unreviewed class/powertrain combination')
    return (category, power)

def annualize(drivers, outputs, scale_table, start=2020, end=2100):
    if drivers.empty or outputs.empty:
        raise ValueError('Missing vehicle exports')
    if drivers.duplicated(KEY).any() or outputs.duplicated(KEY + ['service']).any():
        raise ValueError('Duplicate native key')
    if scale_table.duplicated(['vehicle_class']).any():
        raise ValueError('Duplicate scale')
    scales = scale_table.set_index('vehicle_class')
    if not set(PREFIX.values()).issubset(scales.index):
        raise ValueError('Missing class scale specification')
    numeric = ['stock_native', 'new_rate_native', 'replacement_rate_native', 'model_time_interval', 'stock_inflow_over_interval_native']
    if not np.isfinite(drivers[numeric]).all().all() or (drivers[numeric] < 0).any().any():
        raise ValueError('Invalid native values')
    np.testing.assert_allclose(drivers.stock_inflow_over_interval_native, (drivers.new_rate_native + drivers.replacement_rate_native) * drivers.model_time_interval, atol=1e-08, rtol=1e-09)
    np.testing.assert_allclose(outputs.effective_output_per_activity, outputs.raw_output_coefficient * (1 + outputs.output_change_phi), atol=1e-08, rtol=1e-09)
    classes = drivers.technology.map(classify)
    d = drivers.copy()
    d['vehicle_class'] = [x[0] for x in classes]
    d['powertrain'] = [x[1] for x in classes]
    merged = d[KEY + ['vehicle_class']].merge(outputs, on=KEY, how='outer', indicator=True, validate='one_to_many')
    if not merged['_merge'].eq('both').all():
        raise ValueError('Unmatched output or driver')
    for r in merged.itertuples():
        if r.service not in SERVICES[r.vehicle_class]:
            raise ValueError('Unexpected service for class')
    records = []
    for r in d.itertuples():
        dt = r.model_time_interval
        if dt < 1 or not float(dt).is_integer():
            raise ValueError('Invalid model interval')
        unit = scales.loc[r.vehicle_class]
        factor = unit['vehicles_per_native_unit']
        if pd.notna(factor) and (not np.isfinite(factor) or factor <= 0):
            raise ValueError('Invalid scale')
        for y in range(max(start, int(r.year - dt + 1)), min(end, int(r.year)) + 1):
            records.append({'Sc': r.Sc, 'region': r.region, 'sector': r.sector, 'technology': r.technology, 'vehicle_class': r.vehicle_class, 'powertrain': r.powertrain, 'year': y, 'model_period_end': r.year, 'annual_additions_native': r.new_rate_native + r.replacement_rate_native, 'new_vehicles_year': (r.new_rate_native + r.replacement_rate_native) * factor if pd.notna(factor) else np.nan, 'unit_status': unit['status']})
    a = pd.DataFrame(records)
    if a.duplicated(['Sc', 'region', 'sector', 'technology', 'year']).any():
        raise ValueError('Overlapping model intervals')
    for _, g in a.groupby(['Sc', 'region', 'sector', 'technology']):
        if set(g.year) != set(range(start, end + 1)):
            raise ValueError('Incomplete time coverage; do not extrapolate partial run')
    return a

def bus_inventory(materials):
    if materials.duplicated(['scope', 'material']).any():
        raise ValueError('Duplicate material row')
    if not np.isfinite(materials.kg_per_vehicle).all() or (materials.kg_per_vehicle < 0).any():
        raise ValueError('Invalid material mass')
    records = []
    for r in materials.itertuples():
        values = {}
        if r.material in MINERALS:
            values[r.material] = r.kg_per_vehicle
        if r.material in ['Cast_Al', 'Wrought_Al']:
            values = {'Al': r.kg_per_vehicle}
        if r.material == 'Graphite':
            values = {'C': r.kg_per_vehicle}
        if r.material == 'Alumina':
            values = {'Al': r.kg_per_vehicle * (2 * 26.9815385) / (2 * 26.9815385 + 3 * 15.999)}
        if r.material == 'Silica':
            values = {'Si': r.kg_per_vehicle * 28.085 / (28.085 + 2 * 15.999)}
        if r.material == 'ZnO':
            values = {'Zn': r.kg_per_vehicle * 65.38 / (65.38 + 15.999)}
        for m, v in values.items():
            records.append({'scope': r.scope, 'mineral': m, 'known_kg_per_vehicle': v, 'material': r.material})
    p = pd.DataFrame(records)
    q = p.groupby('mineral').known_kg_per_vehicle.sum()
    inv = pd.DataFrame({'vehicle_class': 'BUS', 'powertrain': 'BEV', 'mineral': MINERALS, 'known_kg_per_vehicle': [q.get(m, np.nan) for m in MINERALS]})
    inv['whole_vehicle_complete'] = False
    inv['traction_battery_included'] = False
    inv['case'] = 'Italian_12m_bus_preprint2025_selected_parts_NOT_global_mean'
    inv['source'] = 'https://www.preprints.org/manuscript/202509.2057 TableA2; published version data not fully compared'
    return (p, inv)

def run(root=ROOT):
    out = root / 'output/road_vehicle_extension'
    out.mkdir(parents=True, exist_ok=True)
    inp = root / 'input/road_vehicle_extension'
    materials = pd.read_csv(inp / 'bus_BEV_selected_materials.csv')
    parts, bus = bus_inventory(materials)
    scope = []
    for cls, powers in EXPECTED.items():
        for power in sorted(powers):
            for m in MINERALS:
                rows = bus.loc[bus.mineral == m] if (cls, power) == ('BUS', 'BEV') else bus.iloc[:0]
                scope.append({'vehicle_class': cls, 'powertrain': power, 'mineral': m, 'known_component_kg_per_vehicle': rows.known_kg_per_vehicle.iloc[0] if len(rows) else np.nan, 'status': 'selected_nonbattery_bus_parts_only' if len(rows) and rows.known_kg_per_vehicle.notna().iloc[0] else 'not_imported_or_not_quantified_not_zero', 'whole_vehicle_complete': False})
    mapping = []
    source = root / 'originals/runtime_gms2iamc/gms2iamc/individual/tech_share/define/tech_map.gms'
    technologies = set(re.findall('(?m)^\\s*((?:TPPCOG|TPPCOD|TPBSOI|TFTSOI|TFTLOI)_\\w+)\\s*\\.', source.read_text()))
    for tech in sorted(technologies):
        cls, power = classify(tech)
        mapping.append({'technology': tech, 'vehicle_class': cls, 'powertrain': power, 'source': 'old runtime tech_map; verify updated model definition'})
    scales = pd.DataFrame([{'vehicle_class': cls, 'vehicles_per_native_unit': 1000000.0 if cls == 'LDV' else np.nan, 'status': 'old LDV numeric check only; updated model confirmation pending' if cls == 'LDV' else 'PENDING_bus_truck_unit_calibration_no_default_multiplier'} for cls in EXPECTED])
    sources = pd.DataFrame([{'source': 'Italian urban bus', 'url': 'https://www.preprints.org/manuscript/202509.2057', 'status': 'preprint v2 TableA2 selected values transcribed; peer-reviewed DOI10.3390/su17219786 exists, numeric final comparison pending'}, {'source': 'MHDV three truck classes 2026', 'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12947617/', 'status': 'methods read; Class6/Class8 regional/longhaul; SI numerical material tables not retrieved'}, {'source': 'ANL2022 component update', 'url': 'https://publications.anl.gov/anlpubs/2022/10/179148.pdf', 'status': 'reference candidate; not numerically imported'}])
    notes = pd.DataFrame({'項目': ['対象', '乗用車既存結果', 'バス参照', 'トラック', '台数', 'その他部門', '電池更新'], '説明': ['乗用車・バス・小型貨物・大型貨物。各車種のICE/HEV/BEV/FCV等を区別。', '既存乗用車係数はこの新表へ未結合。NAは既存研究がないという意味ではない。', '12mバス参照の既知部品だけ。駆動電池未加算、Cu/Brass未分割。世界平均ではない。', 'AIMの大小区分と米国Class6/8の対応・構成比は未確定。乗用車係数の重量比例転用をしない。', 'nativeバス・貨物出力が未取得。native百万台倍率を無条件に転用せず基準年STKで照合。', '追加する2020年明示需要を差し引いて残余を再校正。将来もGDP残余を無変更で上乗せしない。', '車両更新と車載電池単独更新は別。部品交換を文献から自動上乗せしない。']})
    sheets = {'最初に読む': notes, 'AIM車種分類': pd.DataFrame(mapping), '台数倍率_要確認': scales, 'バス既知部品小計': bus, 'バス元素換算': parts, 'バス材料転記': materials, '40鉱物_全車種枠': pd.DataFrame(scope), '文献と取得状況': sources}
    for n, f in [('vehicle_technology_map', pd.DataFrame(mapping)), ('unit_scale_template', scales), ('bus_BEV_partial_inventory', bus), ('bus_component_elements', parts), ('scope_40_slots_NOT_complete', pd.DataFrame(scope)), ('source_register', sources)]:
        f.to_csv(out / (n + '.csv'), index=False)
    with pd.ExcelWriter(out / 'road_vehicle_extension.xlsx', engine='openpyxl') as w:
        for name, f in sheets.items():
            f.to_excel(w, sheet_name=name, index=False)
            ws = w.book[name]
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(65, max(16, max((len(str(c.value or '')) for c in col[:60])) + 1))
    m = {'AIM_new_results_used': False, 'bus_truck_native_activity_available': False, 'all_sector_totals_updated': False, 'vehicle_classes': list(EXPECTED), 'files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, inp / 'bus_BEV_selected_materials.csv', root / 'extend_road_vehicles.py']}}
    (out / 'manifest.json').write_text(json.dumps(m, indent=2))
    print(bus.loc[bus.known_kg_per_vehicle.notna(), ['mineral', 'known_kg_per_vehicle']].to_string(index=False))
    print('Road technologies mapped:', len(mapping), 'No bus/truck total fabricated.')
if __name__ == '__main__':
    run()
