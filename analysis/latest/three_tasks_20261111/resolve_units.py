from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, json, hashlib
import pandas as pd
import numpy as np
O = Path(__file__).resolve().parent
R = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'mineral2100'))
sys.path.insert(0, str(R))
from extend_road_vehicles import annualize
service = (O / 'service_v3.txt').read_text()
stock = (O / 'stock_pinned.txt').read_text()
power = (O / 'power_pinned.txt').read_text()
battery = (O / 'source_2.txt').read_text()
for family in ['TPPCOG', 'TPPCOD', 'TPBSOI', 'TFTSOI', 'TFTLOI']:
    assert f"trp_ind_load('STK','{family}',R,Sy)/1000" in service
    assert f"trp_ind_t(R,'STK','{family}','2005')/1000" in stock
assert "t_disc(R,'BAT')         =12;" in battery
assert "'Storage capacity by USDOE in GW'" in power
assert "'Storage capacity of CAES in TWh'" in power
cfg = dict(source_commit='e90c5d3407a68fed47021469338e655971fd12c1', data_commit='793cb4129994951e30a780e51985f76109e3d801', source_definition_verified=True, runtime_snapshot_verified=False, vehicle_native_unit='million vehicles, source-chain interpretation of original STK as vehicles', vehicles_per_native_unit=1000000, vehicle_annual_additions='(VR+VP)*1000000', interval_total='annual additions * model_time_interval', battery_native_capacity_unit='GW', battery_native_additions_unit='GW/year', battery_model_discharge_budget_hours=12, battery_energy_capacity_formula='native_GW*12 = GWh model energy budget', physical_pack_duration_measured=False, extra_vehicle_replacement=False, main_mineral_totals_recomputed=False)
(O / 'units_source_verified.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
scales = pd.DataFrame([dict(vehicle_class=k, vehicles_per_native_unit=1000000.0, status='SOURCE_CHAIN_x1e6; runtime snapshot not yet compared') for k in ['LDV', 'BUS', 'TRUCK_SMALL', 'TRUCK_LARGE']])
rows = []
for sc in ['Baseline', '300C']:
    d = pd.read_csv(R / f'input/updated_2611091342/native/updated_native_drivers_{sc}.csv')
    o = pd.read_csv(R / f'input/updated_2611091342/native/updated_native_road_outputs_{sc}.csv')
    road = d[d.technology.str.match('TPPCOG_|TPPCOD_|TPBSOI_|TFTSOI_|TFTLOI_')]
    oo = o[o.technology.isin(road.technology.unique())]
    a = annualize(road, oo, scales)
    a.to_csv(O / f'road_annual_source_units_{sc}.csv.gz', index=False)
    rows.append(a.groupby(['Sc', 'vehicle_class', 'powertrain', 'year'], as_index=False).new_vehicles_year.sum())
s = pd.concat(rows)
s.to_csv(O / '道路全車種_年間新設台数_定義換算.csv', index=False)
with pd.ExcelWriter(O / '単位確定_定義根拠と道路台数.xlsx') as w:
    pd.DataFrame([{'setting': k, 'value': str(v)} for k, v in cfg.items()]).to_excel(w, sheet_name='設定と確認範囲', index=False)
    s.to_excel(w, sheet_name='全車種年間新設', index=False)
    pd.read_csv(O / 'バス貨物車_モデル寿命.csv').to_excel(w, sheet_name='寿命出力照合', index=False)
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in O.glob('*.txt')}
(O / 'source_hashes.json').write_text(json.dumps(manifest, indent=2))
print(s.groupby(['Sc', 'vehicle_class']).new_vehicles_year.sum().to_string())
print('Flow identity, interval coverage, unique keys and output coefficients checked by annualize().')
