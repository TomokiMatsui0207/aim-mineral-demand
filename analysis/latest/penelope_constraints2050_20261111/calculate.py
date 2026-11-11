"""2050-only conditional AIM extension of Penelope constraints; not a literal replication.
Requires installed SciPy, pandas, openpyxl, clarabel. Source files remain private/local.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, ast, json, hashlib, warnings
import numpy as np, pandas as pd
from scipy.optimize import linprog
from scipy import sparse
import clarabel
warnings.filterwarnings('ignore', category=FutureWarning)
O = Path(__file__).resolve().parent
S = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'technology_substitution_20261111'))
sys.path.insert(0, str(S))
import optimise as old
old.BLOCKS = [(2026, 2030), (2031, 2034), (2035, 2035), (2036, 2040), (2041, 2045), (2046, 2050)]
Y = np.arange(2020, 2051)
M = old.MINERALS
K = len(M)
pen = old.PEN
book = pen / 'Prod&Demand_Other_Sectors.xlsx'
from mineral_names import PENELOPE_NAMES as name_map
common = [m for m in M if m in name_map]
ix = np.array([M.index(m) for m in common])
names = [name_map[m] for m in common]
rrtab = pd.read_excel(book, sheet_name='Recovery_Rates', index_col=0)
rr = rrtab.loc[names, 'RR_Reserve'].to_numpy(float)
resources = pd.read_excel(book, sheet_name='Reserves_Resources', index_col=0).loc[names]
source = pen.parent / 'IAM_Techno_Optimisation.py'
tree = ast.parse(source.read_text())
fun = next((n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body if isinstance(n, ast.FunctionDef) and n.name == 'Future_Production'))
module = ast.Module(body=[fun], type_ignores=[])
ns = {'pd': pd, 'np': np}
exec(compile(module, str(source), 'exec'), ns)

class D:
    pass
obj = D()
obj.listMetals = names
obj.listYears = [str(y) for y in Y]
obj.listDecades = ['2020', '2030', '2040', '2050']
obj.folder_path = str(pen) + '/'
obj.Prod_2020 = pd.read_excel(book, sheet_name='Prod_2020_Beta', index_col=0).Prod_2020
obj.Recovery_Rates = rrtab
ns['Future_Production'](obj)
production = obj.Prod.loc[names].astype(float)
assert np.isfinite(production.to_numpy()).all() and (production.to_numpy() > 0).all()
production.index = common
production.to_csv(O / 'production_original_formula.csv')
base_rr = pd.read_excel(pen / 'EV_MI_MS_Recycling.xlsx', sheet_name='Recycling_2020_Rates', index_col=0).Initial_Recycling_Rate
future_rr = pd.read_excel(pen / 'EV_MI_MS_Recycling.xlsx', sheet_name='Recycling_Evolution', index_col=0)
recycling = np.zeros((len(Y), K))
for j, m in enumerate(M):
    name = name_map.get(m, '')
    initial = float(base_rr.get(name, 0))
    e = future_rr[(future_rr.index == name) & future_rr.SSPs.eq('SSP2')]
    pts = {2020: initial, 2050: initial}
    if len(e) == 1:
        for yr in [2028, 2032, 2050]:
            pts[yr] = float(e.iloc[0][yr if yr in e.columns else str(yr)])
    recycling[:, j] = np.interp(Y, sorted(pts), [pts[y] for y in sorted(pts)])
inputs = list(old.load())
inputs[-2] = inputs[-2][inputs[-2].year.le(2050)].copy()
rows = []
counts = []
annual = []
shares = []
solvers = []

def arr(t, c):
    return t.pivot(index='year', columns='mineral', values=c).reindex(index=Y, columns=M).to_numpy(float)

def clipped_recovery(v, delay):
    out = np.zeros_like(v)
    out[delay:] = v[:-delay] * recycling[delay:]
    return out
for sc in ['Baseline', '300C']:
    p = old.build_problem(sc, inputs)
    n = len(p.records)
    t = p.total
    fixed = arr(t, 'power') + arr(t, 'stationary_battery') + arr(t, 'grid_CuAl_t_year') + arr(t, 'vehicles_explicit_t_year') + arr(t, 'hydrogen')
    osd = arr(t, 'other_low_t_year')
    storage = arr(t, 'stationary_battery')
    options = np.zeros((31, K, n))
    fixed_rec = np.zeros_like(fixed)
    variable_rec = np.zeros_like(options)
    fixed_vehicles = {cl: arr(t, cl) for cl in ['LDV', 'BUS', 'TRUCK_SMALL', 'TRUCK_LARGE']}
    assert np.allclose(sum(fixed_vehicles.values()), arr(t, 'vehicles_explicit_t_year'))
    for g in p.groups:
        ys = np.arange(g['start'], g['end'] + 1) - 2020
        offset = g['offset']
        fixed[ys] -= g['current']
        cl = None
        if g['name'].startswith('LDV_'):
            cl = 'LDV'
        elif g['name'].startswith('BUS_'):
            cl = 'BUS'
        elif g['name'].startswith('TRUCK_SMALL'):
            cl = 'TRUCK_SMALL'
        elif g['name'].startswith('TRUCK_LARGE'):
            cl = 'TRUCK_LARGE'
        if cl:
            fixed_vehicles[cl][ys] -= g['current']
        for j in range(g['n']):
            z = np.zeros_like(fixed)
            z[ys] = g['options'][j]
            options[:, :, offset + j] = z
            if cl:
                variable_rec[:, :, offset + j] = clipped_recovery(z, 12 if cl == 'LDV' else 15)
    for cl, v in fixed_vehicles.items():
        assert v.min() > -1e-05
        fixed_rec += clipped_recovery(v, 12 if cl == 'LDV' else 15)
    eq = np.zeros((len(p.groups), n))
    ref = np.array([r['reference_share'] for r in p.records])
    for i, g in enumerate(p.groups):
        eq[i, g['offset']:g['offset'] + g['n']] = 1
    limits = []
    lr = []
    for g in p.groups:
        if g['na_cap']:
            na, j = g['na_cap']
            a = np.zeros(n)
            a[g['offset']] = na
            a[g['offset'] + j] = 1
            limits.append(a)
            lr.append(1.1 * na)
    min_gross = fixed.copy()
    max_recovery = fixed_rec.copy()
    for g in p.groups:
        sl = slice(g['offset'], g['offset'] + g['n'])
        min_gross += options[:, :, sl].min(axis=2)
        max_recovery += variable_rec[:, :, sl].max(axis=2)
    gamma = np.minimum(1.0, np.maximum(min_gross, 0.0) / np.maximum(max_recovery, 1e-30))
    fixed_rec *= gamma
    variable_rec *= gamma[:, :, None]
    for recovery in ['no_vehicle_recycling_credit', 'SSP2_post2020_conservative_credit']:
        f = fixed - (fixed_rec if recovery.startswith('SSP2') else 0)
        A = options - (variable_rec if recovery.startswith('SSP2') else 0)
        osdcum = sum(((osd[a] + osd[b]) * 5 for a, b in [(0, 10), (10, 20), (20, 30)]))
        resource_f = f[:, ix].sum(axis=0) / rr + osdcum[ix]
        resource_A = A[:, ix, :].sum(axis=0) / rr[:, None]
        constraints = []
        rhs = []
        meta = []
        for k, m in enumerate(common):
            for basis in ['Resources']:
                cap = float(resources.loc[name_map[m], basis])
                if np.isfinite(cap) and cap > 0:
                    constraints.append(resource_A[k] / cap)
                    rhs.append(1 - resource_f[k] / cap)
                    meta.append(dict(kind=basis, mineral=m, year=2050, capacity_t=cap, fixed_t=resource_f[k], osd_t=osdcum[ix[k]]))
        for year in [2030, 2040, 2050]:
            idx = np.where((Y > year - 10) & (Y <= year))[0]
            end = year - 2020
            fa = f[idx].mean(axis=0) - storage[idx].mean(axis=0) + storage[end]
            aa = A[idx].mean(axis=0)
            for k, m in enumerate(common):
                prod = float(production.loc[m, str(year)])
                cap = max(prod - osd[end, ix[k]], 0.05 * prod)
                constraints.append(aa[ix[k]] / prod)
                rhs.append((cap - fa[ix[k]]) / prod)
                meta.append(dict(kind='Annual_5pct_protected', mineral=m, year=year, capacity_t=cap, production_t=prod, fixed_t=fa[ix[k]], osd_t=osd[end, ix[k]]))
        C = np.array(constraints)
        h = np.array(rhs)
        k = len(h)
        G = np.c_[C, -np.eye(k)]
        hh = h.copy()
        if limits:
            G = np.vstack([G, np.c_[np.array(limits), np.zeros((len(limits), k))]])
            hh = np.r_[hh, lr]
        E = np.c_[eq, np.zeros((len(eq), k))]
        lp = linprog(np.r_[np.zeros(n), np.ones(k)], A_ub=G, b_ub=hh, A_eq=E, b_eq=np.ones(len(eq)), bounds=[(0, 1)] * n + [(0, None)] * k, method='highs')
        if not lp.success:
            raise RuntimeError(lp.message)
        G = np.vstack([G, np.r_[np.zeros(n), np.ones(k)]])
        hh = np.r_[hh, lp.fun + 1e-07]
        P = sparse.diags(np.r_[np.full(n, 2.0), np.zeros(k)], format='csc')
        q = np.r_[-2 * ref, np.zeros(k)]
        up = sparse.hstack([sparse.eye(n), sparse.csc_matrix((n, k))])
        B = sparse.vstack([sparse.csc_matrix(E), sparse.csc_matrix(G), -sparse.eye(n + k), up], format='csc')
        b = np.r_[np.ones(len(eq)), hh, np.zeros(n + k), np.ones(n)]
        settings = clarabel.DefaultSettings()
        settings.verbose = False
        settings.tol_gap_abs = 1e-09
        settings.tol_gap_rel = 1e-09
        settings.tol_feas = 1e-09
        settings.max_iter = 300
        qp = clarabel.DefaultSolver(P, q, B, b, [clarabel.ZeroConeT(len(eq)), clarabel.NonnegativeConeT(len(hh) + n + k + n)], settings).solve()
        z = np.array(qp.x)
        residual = max(np.max(G @ z - hh), np.max(abs(E @ z - 1)), np.max(-z), np.max(z[:n] - 1))
        if str(qp.status) != 'Solved' or residual > 1e-06:
            raise RuntimeError((qp.status, residual))
        solvers.append(dict(Sc=sc, recovery=recovery, status=str(qp.status), variables=n, slacks=k, minimum_normalized_excess=float(lp.fun), max_residual=float(residual)))
        sh = pd.DataFrame(p.records)
        sh['Sc'] = sc
        sh['recovery'] = recovery
        sh['optimized_share'] = z[:n]
        shares.append(sh)
        for solution, x in [('reference', ref), ('optimized', z[:n])]:
            net = f + np.einsum('ykn,n->yk', A, x)
            if net.min() < -0.001:
                raise RuntimeError(('Negative net demand', net.min()))
            net = np.maximum(net, 0.0)
            primary = net[:, ix] / rr + osd[:, ix]
            for yi, y in enumerate(Y):
                for j, m in enumerate(common):
                    annual.append(dict(Sc=sc, recovery=recovery, solution=solution, year=int(y), mineral=m, net_transition_t_year=net[yi, ix[j]], osd_t_year=osd[yi, ix[j]], primary_style_total_t_year=primary[yi, j]))
            for j, m in enumerate(common):
                demand = float(resource_f[j] + resource_A[j] @ x)
                for basis in ['Resources', 'Reserves']:
                    cap = float(resources.loc[name_map[m], basis])
                    ratio = demand / cap if np.isfinite(cap) and cap > 0 else np.nan
                    rows.append(dict(Sc=sc, recovery=recovery, solution=solution, kind=basis, mineral=m, year=2050, demand_t=demand, capacity_t=cap, ratio=ratio, osd_share=osdcum[ix[j]] / demand if demand > 0 else 0, status='missing' if np.isnan(ratio) else 'within' if ratio <= 1 + 1e-06 else 'OSD_dominant_excess' if osdcum[ix[j]] / demand > 0.9 else 'excess'))
            for j, md in enumerate(meta):
                if md['kind'] == 'Resources':
                    continue
                demand = float(md['fixed_t'] + C[j] @ x * md['production_t'])
                ratio = demand / md['capacity_t']
                share = md['osd_t'] / (demand + md['osd_t']) if demand + md['osd_t'] > 0 else 0
                for kind, dem, cap in [('Annual_5pct_protected', demand, md['capacity_t']), ('Annual_total_physical', demand + md['osd_t'], md['production_t'])]:
                    rat = dem / cap
                    rows.append(dict(Sc=sc, recovery=recovery, solution=solution, kind=kind, mineral=md['mineral'], year=md['year'], demand_t=dem, capacity_t=cap, ratio=rat, osd_share=share, status='within' if rat <= 1 + 1e-06 else 'OSD_dominant_excess' if share > 0.9 else 'excess'))
        print(solvers[-1], flush=True)
d = pd.DataFrame(rows)
a = pd.DataFrame(annual)
d.to_csv(O / 'constraints_by_mineral.csv', index=False)
a.to_csv(O / 'annual_primary_style.csv.gz', index=False)
pd.concat(shares).to_csv(O / 'optimized_shares.csv', index=False)
pd.DataFrame(solvers).to_csv(O / 'solver_checks.csv', index=False)
for key, g in d.groupby(['Sc', 'recovery', 'solution', 'kind', 'year']):
    over = g[g.status.isin(['excess', 'OSD_dominant_excess'])]
    counts.append(dict(zip(['Sc', 'recovery', 'solution', 'kind', 'year'], key), available=int(g.ratio.notna().sum()), missing=int(g.ratio.isna().sum()), exceeded=len(over), OSD_dominant=int(over.status.eq('OSD_dominant_excess').sum()), exceeded_minerals=', '.join(over.mineral)))
c = pd.DataFrame(counts)
c.to_csv(O / 'counts.csv', index=False)
notes = [('目的', '2050年専用に累積資源量＋2030/40/50年の生産能力制約を同時適用。元論文完全再現ではない。'), ('鉱物', '共通32、Resources有23、Reserves有27、年間生産量32。'), ('供給', '提供された元コードFuture_Productionを変更せず実行。添付論文本文の2025USGS版と同版であるとは未確認。'), ('回収率', '移行部門をRR_Reserveで除算し累積資源量に比較。OSDは元コードと同じくそのまま。OSD累積は10年台形、2020単独加算なし。'), ('年間式', '10年平均移行部門（蓄電は終点値）≦max(生産量−終点OSD,5%生産量)。実際の全部門需要対生産量も別記。'), ('リサイクル', '主比較は車両回収控除なし。感度ケースはSSP2率、乗用12年/バス貨物15年で2020年以降導入の既知材料のみ回収。2020年以前の回収は両ケース未計上。'), ('回収上限', '全候補の最小当年使用量÷最大回収可能量で元素・年別の控除率に上限を設定。どのシェアでも負の純需要を作らない保守的ケース。余剰回収の他部門移転・在庫は計上しない。'), ('基準年', '既存の全部門残余/GDP経路を維持。元論文の残余法をこの回収境界で再校正したものではない。'), ('部門差', 'H2・HEV・FCV・バス・貨物も含む。発電は既存の新設＋交換方式であり元コードの再エネ純増だけの式とは異なる。'), ('技術選択', '発電源間の変更なし。風車・PV部品・EV電池/モーター・網Cu/Al等。2020–25固定、2026–50最適化。Na2035年以降制限解除は仮定。'), ('最適化目的', '資源量と年間生産量の正規化超過合計を最小化後、シェア変化二乗を最小化。元コードの重み付き単一目的と完全同一ではない。'), ('黄色', '需要の90%以上がOSDである超過を区分。3種類に合わせて他の超過を削除しない。'), ('確定判定不可', '未収録成分・元素/化合物境界・歴史回収・版差が残るため、実供給不足の確定数、論文の3種類の再現とは呼ばない。')]
nt = pd.DataFrame(notes, columns=['項目', '説明'])
with pd.ExcelWriter(O / '2050_constraints.xlsx', engine='xlsxwriter') as w:
    for name, df in [('条件と限界', nt), ('超過数', c), ('鉱物別判定', d), ('年間会計', a), ('生産能力', production.reset_index()), ('求解検証', pd.DataFrame(solvers)), ('技術シェア', pd.concat(shares))]:
        df.to_excel(w, sheet_name=name, index=False)
        ws = w.sheets[name]
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        ws.set_column(0, len(df.columns) - 1, 20)
    w.sheets['条件と限界'].set_column(1, 1, 110)
(O / 'README.md').write_text('\n'.join((f'- **{k}**：{v}' for k, v in notes)))
(O / 'manifest.json').write_text(json.dumps({'same_as_paper': False, 'horizon': 2050, 'resource_and_annual_constraints': True, 'inputs': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [source, book, Path(__file__), old.V / 'all_sectors_extended_CONDITIONAL.csv.gz', old.V / 'road_activity_annual.csv']}}, ensure_ascii=False, indent=2))
print(c[c.recovery.eq('SSP2_post2020_conservative_credit')].to_string(index=False))
