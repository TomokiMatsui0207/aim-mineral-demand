"""Conditional substitution QP with fixed AIM macro activity; not full Penelope replication.
Two-stage objective: minimum normalized reserve-reference excess, then minimum
squared share departure. No missing component is replaced by a false zero saving.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, json, hashlib, time
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy import sparse
import clarabel
O = Path(__file__).resolve().parent
R = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'mineral2100'))
V = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'vehicle_allsector_extension_20261111'))
sys.path.insert(0, str(V))
from build import MINERALS, ANL, CASE_PROFILES, truck_inventory, bus_inventory
BASECASE = 'F_E_plus_steel_Fe_proxy'
PROFILE = next((p for p in CASE_PROFILES if p['case'] == BASECASE))
DATA = R / 'update_comparison_20261110/results_updated_native_all_sectors'
PEN = next((R / 'originals').glob('Pelotte*/Data'))
NAMES = {'Al': 'Aluminum', 'Cu': 'Copper', 'Fe': 'Iron', 'Ag': 'Silver', 'Dy': 'Dysprosium', 'Nd': 'Neodymium', 'Pr': 'Praesodymium', 'Tb': 'Terbium', 'Li': 'Lithium', 'Co': 'Cobalt', 'Mn': 'Manganese', 'Ni': 'Nickel'}
BLOCKS = [(2026, 2030), (2031, 2034), (2035, 2035)] + [(y, y + 4) for y in range(2036, 2097, 5)]
assert sorted((y for a, b in BLOCKS for y in range(a, b + 1))) == list(range(2026, 2101))

def vec(values):
    return np.array([values.get(m, 0.0) for m in MINERALS], float)

def load():
    mi = pd.read_excel(PEN / 'PowerCap_MI_MS_CF.xlsx', sheet_name='MI', index_col=0)
    share = pd.read_excel(PEN / 'Market Share in time - Disag.xlsx', sheet_name='2020', index_col=0)
    battery = pd.read_excel(PEN / 'EV_MI_MS_Recycling.xlsx', sheet_name='MI_Battery', index_col=0)
    motor = pd.read_excel(PEN / 'EV_MI_MS_Recycling.xlsx', sheet_name='MI_Motor', index_col=0)
    motorshare = pd.read_csv(R / 'input/imported/penelope_MS_Motor.csv').set_index('Motor_type').loc['MS']
    chemshare = pd.read_csv(R / 'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv')
    co = pd.read_csv(DATA / 'coefficients.csv')
    co = co[co.statistic.eq('average')]
    activity = pd.read_csv(V / 'road_activity_annual.csv')
    power = pd.read_csv(DATA / 'power_activity.csv')
    parts = pd.read_csv(R / 'input/road_vehicle_extension/bus_BEV_selected_materials.csv')
    total = pd.read_csv(V / 'all_sectors_extended_CONDITIONAL.csv.gz')
    total = total[total['case'].eq(BASECASE)]
    reserve = pd.read_csv(R / 'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv')
    return (mi, share, battery, motor, motorshare, chemshare, co, activity, power, parts, total, reserve)

class Problem:

    def __init__(self, sc, inputs):
        self.sc = sc
        self.groups = []
        self.records = []
        self.total = inputs[-2].query('Sc==@sc').copy()
        self.before = vec(self.total.query('year>=2026').groupby('mineral').conditional_total_low_t_year.sum().to_dict())
        self.fixed = self.before.copy()

    def add(self, name, period, candidates, reference, annual_current, annual_options, na_cap=None):
        p = np.asarray(reference, float)
        assert len(candidates) == len(p) and np.all(p >= 0) and np.isclose(sum(p), 1)
        current = np.asarray(annual_current, float)
        options = np.asarray(annual_options, float)
        assert current.shape == (period[1] - period[0] + 1, 40)
        assert options.shape == (len(p), len(current), 40)
        if not np.isfinite(current).all() or not np.isfinite(options).all() or (current < -1e-07).any() or (options < -1e-07).any():
            raise ValueError('Invalid component coefficients')
        self.fixed -= current.sum(axis=0)
        offset = len(self.records)
        self.groups.append(dict(name=name, start=period[0], end=period[1], offset=offset, n=len(p), p=p, current=current, options=options, na_cap=na_cap))
        for i, c in enumerate(candidates):
            self.records.append(dict(group=name, start=period[0], end=period[1], candidate=c, reference_share=p[i]))

    def matrix(self):
        return np.column_stack([g['options'][j].sum(axis=0) for g in self.groups for j in range(g['n'])])

    def reconstruct(self, x):
        rows = []
        for g in self.groups:
            opt = np.einsum('i,iyk->yk', x[g['offset']:g['offset'] + g['n']], g['options'])
            for j, y in enumerate(range(g['start'], g['end'] + 1)):
                for k, m in enumerate(MINERALS):
                    rows.append(dict(Sc=self.sc, group=g['name'], year=y, mineral=m, current_component_t=g['current'][j, k], replacement_component_t=opt[j, k]))
        return pd.DataFrame(rows)

def build_problem(sc, inputs):
    mi, share, battery, motor, motorshare, cs, co, activity, power, parts, total, reserve = inputs
    p = Problem(sc, inputs)
    pa = power[power.Sc.eq(sc)].set_index(['year', 'technology']).addition_GW_year
    act = activity[activity.Sc.eq(sc)].set_index(['year', 'vehicle_class', 'powertrain']).new_vehicles_year
    coeff = co[co.sector.eq('power')].set_index(['technology', 'mineral']).intensity

    def counts(year, cls, pt):
        return float(act.get((year, cls, pt), 0.0))
    bmet = ['Co', 'Cu', 'Li', 'Mn', 'Ni']
    motmet = ['Al', 'Cu', 'Dy', 'Nd', 'Pr']
    windmet = ['Al', 'Cu', 'Fe', 'Dy', 'Nd', 'Pr', 'Tb']
    for start, end in BLOCKS:
        ys = list(range(start, end + 1))
        period = (start, end)
        for loc, tech in [('Onshore', 'Win_Ons'), ('Offshore', 'Win_Off')]:
            cols = [c for c in mi.columns if c.startswith('Wind_') and c.endswith('_' + loc)]
            ref = share.loc['Capacity..Electricity..Wind..' + loc, cols].astype(float).to_numpy()
            rates = np.array([pa.get((y, tech), 0) for y in ys])
            if rates.sum() > 0:
                current = np.array([vec({m: rates[i] * coeff[tech, m] for m in windmet}) for i, y in enumerate(ys)])
                options = np.array([[vec({m: rates[i] * mi.loc[NAMES[m], c] for m in windmet}) for i, y in enumerate(ys)] for c in cols])
                p.add('wind_' + loc, period, cols, ref, current, options)
        rates = np.array([pa.get((y, 'SolarPV'), 0) for y in ys])
        if rates.sum() > 0:
            minor = {m: sum((s * mi.loc[NAMES[m], t] for t, s in [('Sol_CdTe', 0.024), ('Sol_CIGS', 0.019), ('Sol_a-SiGe', 0.003)])) for m in ['Ag', 'Cu']}
            cur = np.array([vec({m: rate * coeff['SolarPV', m] for m in ['Ag', 'Cu']}) for rate in rates])
            opt = np.array([[vec({m: rate * (0.954 * mi.loc[NAMES[m], c] + minor[m]) for m in ['Ag', 'Cu']}) for rate in rates] for c in ['Sol_C-si_Silver', 'Sol_C-si_Copper']])
            p.add('solar_cSi_metallisation', period, ['Ag_cSi', 'Cu_cSi'], [1, 0], cur, opt)
        energy = np.array([counts(y, 'LDV', 'BEV') * 62.5 + counts(y, 'LDV', 'PHV') * 21.8 for y in ys])
        if energy.sum() > 0:
            ref = []
            na = []
            for y, e in zip(ys, energy):
                w = cs[cs.year.eq(y)].set_index('Battery_type').share
                ref.append(vec({m: e * sum((float(w.get(t, 0)) * battery.loc[NAMES[m], t] for t in w.index)) / 1000000.0 for m in bmet}))
                na.append(float(w.get('Na-ion', 0)))
            ref = np.array(ref)
            candidates = ['reference_mix', 'Gr-LFP', 'Gr-NMC(622)', 'Gr-NMC(811)', 'Na-ion']
            opt = [ref] + [np.array([vec({m: e * battery.loc[NAMES[m], c] / 1000000.0 for m in bmet}) for e in energy]) for c in candidates[1:]]
            nacap = (float(np.average(na, weights=energy)), 4) if end < 2035 else None
            p.add('LDV_battery', period, candidates, [1, 0, 0, 0, 0], ref, np.array(opt), na_cap=nacap)
            numbers = np.array([counts(y, 'LDV', 'BEV') + counts(y, 'LDV', 'PHV') for y in ys])
            mref = np.array([vec({m: n * (float(motorshare['PM']) * motor.loc[NAMES[m], 'PM'] + float(motorshare['Ind']) * motor.loc[NAMES[m], 'Ind']) / 1000000.0 for m in motmet}) for n in numbers])
            names = ['PM_Cu', 'Ind_Cu', 'PM_Al', 'Ind_Al']
            mopt = np.array([[vec({m: n * motor.loc[NAMES[m], c] / 1000000.0 for m in motmet}) for n in numbers] for c in names])
            p.add('LDV_motor', period, names, [float(motorshare['PM']), float(motorshare['Ind']), 0, 0], mref, mopt)
        for cls, cl in [('TRUCK_SMALL', 'C6'), ('TRUCK_LARGE', 'DAY')]:
            for pt in ['HEV', 'BEV', 'FCV']:
                n = np.array([counts(y, cls, pt) for y in ys])
                if n.sum() == 0:
                    continue
                vals = []
                for chem in ['NMC622', 'NMC811']:
                    v, _ = truck_inventory(cl, pt, dict(PROFILE, chem=chem))
                    vals.append(v)
                tracked = sorted(set(vals[0]) & set(vals[1]))
                opt = np.array([[vec({m: number * vals[j][m] / 1000 for m in tracked}) for number in n] for j in range(2)])
                p.add(cls + '_' + pt + '_battery', period, ['NMC622', 'NMC811'], [1, 0], opt[0], opt)
        n = np.array([counts(y, 'BUS', 'BEV') for y in ys])
        if n.sum() > 0:
            v = [bus_inventory('BEV', dict(PROFILE, chem=chem), parts) for chem in ['NMC622', 'NMC811']]
            tracked = sorted(set(v[0]) & set(v[1]))
            opt = np.array([[vec({m: num * v[j][m] / 1000 for m in tracked}) for num in n] for j in range(2)])
            p.add('BUS_BEV_battery', period, ['NMC622', 'NMC811'], [1, 0], opt[0], opt)
        cu = np.array([float(total[(total.Sc == sc) & (total.year == y) & (total.mineral == 'Cu')].grid_CuAl_t_year.iloc[0]) for y in ys])
        al = np.array([float(total[(total.Sc == sc) & (total.year == y) & (total.mineral == 'Al')].grid_CuAl_t_year.iloc[0]) for y in ys])
        equivalent = cu + 2 * al
        cur = np.array([vec({'Cu': u, 'Al': a}) for u, a in zip(cu, al)])
        options = np.array([[vec({'Cu': e}) for e in equivalent], [vec({'Al': e / 2}) for e in equivalent]])
        p.add('grid_CuAl', period, ['Cu_equivalent', 'Al_equivalent'], [cu.sum() / equivalent.sum(), 2 * al.sum() / equivalent.sum()], cur, options)
    if p.fixed.min() < -0.0001:
        raise ValueError('Controlled component exceeds baseline total: ' + str(list(zip(MINERALS, p.fixed))))
    p.fixed = np.maximum(p.fixed, 0.0)
    return p

def constraints(p, reserve):
    refs = reserve[~reserve.extended_assumption].copy()
    assert len(refs) == 33
    idx = [MINERALS.index(m) for m in refs.mineral]
    r = refs.comparison_reference_t_element.to_numpy()
    M = p.matrix()
    n = M.shape[1]
    k = len(idx)
    A = M[idx] / r[:, None]
    fixed = p.fixed[idx] / r
    eq = np.zeros((len(p.groups), n + k))
    for i, g in enumerate(p.groups):
        eq[i, g['offset']:g['offset'] + g['n']] = 1
    ub = np.c_[A, -np.eye(k)]
    rhs = 1 - fixed
    limits = []
    lr = []
    for g in p.groups:
        if g['name'] == 'LDV_battery' and getattr(p, 'policy', 'allow_Na_after2035') == 'no_additional_Na':
            row = np.zeros(n + k)
            row[g['offset'] + 4] = 1
            limits.append(row)
            lr.append(0.0)
        if g['na_cap']:
            na, j = g['na_cap']
            row = np.zeros(n + k)
            row[g['offset']] = na
            row[g['offset'] + j] = 1
            limits.append(row)
            lr.append(1.1 * na)
    if limits:
        ub = np.vstack([ub, limits])
        rhs = np.r_[rhs, lr]
    return (refs, M, n, k, eq, ub, rhs)

def solve(p, reserve, free=True):
    refs, M, n, k, eq, ub, rhs = constraints(p, reserve)
    bounds = [(0, 1)] * n + [(0, None)] * k
    if not free:
        x = np.array([r['reference_share'] for r in p.records])
        total = p.fixed + M @ x
        return dict(x=x, total=total, refs=refs, M=M, status='reference without resource optimisation')
    obj = np.r_[np.zeros(n), np.ones(k)]
    result = linprog(obj, A_ub=ub, b_ub=rhs, A_eq=eq, b_eq=np.ones(len(eq)), bounds=bounds, method='highs')
    if not result.success:
        raise RuntimeError(result.message)
    best = float(result.fun)
    eps = 1e-07
    lex = np.r_[np.zeros(n), np.ones(k)][None, :]
    G = np.vstack([ub, lex])
    h = np.r_[rhs, best + eps]
    ref = np.array([r['reference_share'] for r in p.records])
    initial = result.x
    P = sparse.diags(np.r_[np.full(n, 2.0), np.zeros(k)], format='csc')
    q = np.r_[-2 * ref, np.zeros(k)]
    upper_x = sparse.hstack([sparse.eye(n, format='csc'), sparse.csc_matrix((n, k))], format='csc')
    C = sparse.vstack([sparse.csc_matrix(eq), sparse.csc_matrix(G), -sparse.eye(n + k, format='csc'), upper_x], format='csc')
    bvec = np.r_[np.ones(len(eq)), h, np.zeros(n + k), np.ones(n)]
    cones = [clarabel.ZeroConeT(len(eq)), clarabel.NonnegativeConeT(len(h) + n + k + n)]
    settings = clarabel.DefaultSettings()
    settings.verbose = False
    settings.tol_gap_abs = 1e-09
    settings.tol_gap_rel = 1e-09
    settings.tol_feas = 1e-09
    settings.max_iter = 250
    solver = clarabel.DefaultSolver(P, q, C, bvec, cones, settings)
    qp = solver.solve()
    z = np.asarray(qp.x)
    feasibility = max(float(np.max(G @ z - h)), float(np.max(np.abs(eq @ z - 1))), float(np.max(-z)), float(np.max(z[:n] - 1)))
    if str(qp.status) != 'Solved' or feasibility > 1e-06:
        raise RuntimeError(f'QP not certified: {qp.status}; residual={feasibility}')

    def fun(z):
        return float(np.sum((np.asarray(z)[:n] - ref) ** 2))
    x = np.asarray(qp.x[:n])
    total = p.fixed + M @ x
    excess = np.maximum(total[[MINERALS.index(m) for m in refs.mineral]] / refs.comparison_reference_t_element.to_numpy() - 1, 0)
    assert excess.sum() <= best + 2e-06
    return dict(x=x, total=total, refs=refs, M=M, status=str(qp.status), minimum_normalized_excess=best, realized_normalized_excess=float(excess.sum()), share_squared_departure=fun(qp.x), max_constraint_residual=feasibility, QP_iterations=int(qp.iterations), QP_primal_residual=float(qp.r_prim), QP_dual_residual=float(qp.r_dual), QP_absolute_objective_gap=abs(float(qp.obj_val) - float(qp.obj_val_dual)))

def run():
    inputs = load()
    reserve = inputs[-1]
    allannual = []
    allratios = []
    allshares = []
    summaries = []
    deltas = []
    for sc, policy in [(sc, policy) for sc in ['Baseline', '300C'] for policy in ['allow_Na_after2035', 'no_additional_Na']]:
        p = build_problem(sc, inputs)
        p.policy = policy
        print(sc, 'choice variables', len(p.records), 'groups', len(p.groups), flush=True)
        ref = solve(p, reserve, False)
        opt = solve(p, reserve, True)
        sh = pd.DataFrame(p.records)
        sh['Sc'] = sc
        sh['policy'] = policy
        sh['optimized_share'] = opt['x']
        allshares.append(sh)
        for label, result in [('reference', ref), ('optimized', opt)]:
            comp = p.reconstruct(result['x'])
            comp['solution'] = label
            comp['policy'] = policy
            comp['sector'] = np.where(comp.group.str.startswith(('wind_', 'solar_')), 'power', np.where(comp.group.eq('grid_CuAl'), 'grid', 'vehicles'))
            deltas.append(comp)
            change = comp.groupby(['Sc', 'year', 'mineral'], as_index=False)[['current_component_t', 'replacement_component_t']].sum()
            t = p.total.merge(change, on=['Sc', 'year', 'mineral'], how='left', validate='one_to_one')
            t[['current_component_t', 'replacement_component_t']] = t[['current_component_t', 'replacement_component_t']].fillna(0.0)
            t['technology_substitution_delta_t_year'] = t.replacement_component_t - t.current_component_t
            comp['delta_t_year'] = comp.replacement_component_t - comp.current_component_t
            sector_change = comp.groupby(['Sc', 'year', 'mineral', 'sector']).delta_t_year.sum().unstack('sector').add_prefix('delta_').reset_index()
            t = t.merge(sector_change, on=['Sc', 'year', 'mineral'], how='left', validate='one_to_one')
            for sec in ['power', 'grid', 'vehicles']:
                t['delta_' + sec] = t['delta_' + sec].fillna(0.0)
            t['alternative_power_t_year'] = t.power + t.delta_power
            t['alternative_grid_t_year'] = t.grid_CuAl_t_year + t.delta_grid
            t['alternative_vehicles_t_year'] = t.vehicles_explicit_t_year + t.delta_vehicles
            t['alternative_hydrogen_t_year'] = t.hydrogen
            t['alternative_stationary_battery_t_year'] = t.stationary_battery
            t['alternative_other_t_year'] = t.other_low_t_year
            for bound in ['low', 'high']:
                t['alternative_total_' + bound + '_t_year'] = t['conditional_total_' + bound + '_t_year'] + t.technology_substitution_delta_t_year
                t['alternative_cumulative_' + bound + '_t'] = t.groupby(['Sc', 'mineral'])['alternative_total_' + bound + '_t_year'].transform(lambda x: x.cumsum(skipna=False))
            t = t.rename(columns={c: 'current_' + c for c in t.columns if c.startswith('cumulative_conditional_')})
            t['solution'] = label
            t['policy'] = policy
            t['optimization_scope'] = 'conditional shares; 33 reserve references; gross proxy, no annual mining/recycling constraints'
            allannual.append(t)
            for m, v, current in zip(MINERALS, result['total'], p.before):
                r = reserve[reserve.mineral.eq(m)].iloc[0]
                allratios.append(dict(Sc=sc, policy=policy, solution=label, mineral=m, current_gross_2026_2100_t=current, alternative_gross_2026_2100_t=v, reserve_reference_t=r.comparison_reference_t_element, ratio=v / r.comparison_reference_t_element, current_ratio=current / r.comparison_reference_t_element, used_as_constraint=not r.extended_assumption, reference_class=r.reference_class, scope=r.scope, shortage_verdict_ready=False))
        summaries.append({'Sc': sc, 'policy': policy, 'variables': len(p.records), 'groups': len(p.groups), 'reference_normalized_excess': float(sum((max(0, ref['total'][MINERALS.index(m)] / r - 1) for m, r in zip(ref['refs'].mineral, ref['refs'].comparison_reference_t_element)))), **{k: v for k, v in opt.items() if k not in ['x', 'total', 'refs', 'M']}})
        print('SOLVED', summaries[-1], flush=True)
    annual = pd.concat(allannual, ignore_index=True)
    ratios = pd.DataFrame(allratios)
    shares = pd.concat(allshares, ignore_index=True)
    annual.to_csv(O / 'all_sectors_with_substitution_CONDITIONAL.csv.gz', index=False)
    ratios.to_csv(O / 'reserve_pressure_40_NOT_shortage_verdict.csv', index=False)
    shares.to_csv(O / 'technology_shares_before_after.csv', index=False)
    pd.concat(deltas, ignore_index=True).to_csv(O / 'component_changes_audit.csv.gz', index=False)
    pd.DataFrame(summaries).to_csv(O / 'solver_summary.csv', index=False)
    with pd.ExcelWriter(O / '代替技術シフト_最適化結果_条件付き.xlsx', engine='openpyxl') as w:
        pd.DataFrame([{'項目': k, '説明': v} for k, v in [('位置付け', 'Pénélopeに着想を得た部分再現。原論文全体・原目的関数の完全再現ではない。'), ('固定したもの', 'AIMの発電源別導入量・車両台数・電池サービス量・水素・定置電池・その他部門。'), ('変更可能', '風車方式、c-Si銀/銅、乗用車電池とモーター、貨物/バスBEV電池、網Cu/Al。'), ('目的', '33世界参照への正規化超過を最小化後、シェア二乗変化を最小化。超過を需要から削除しない。'), ('参照値', '2026–2100年の総含有量代理。7条件付き鉱物は診断のみ。一次採掘不足判定ではない。'), ('3列比較', '現在計算→候補データで統一した未最適化reference→optimized。原単位変更効果とシフト効果を区別。'), ('未実装', '発電源間の転換、年間採掘上限、回収・歩留まり・在庫、費用・普及速度。'), ('欠損', '未収録成分は固定側に留める。Na元素は40鉱物対象外。Li等の化合物境界は未解決。'), ('機能同等', '風車は同一立地内で同じ設備利用率、電池は同じkWh又はkW、網はCu+2Alを保存する仮定。')]]).to_excel(w, sheet_name='最初に読む', index=False)
        pd.DataFrame(summaries).to_excel(w, sheet_name='求解と超過指標', index=False)
        ratios.to_excel(w, sheet_name='40鉱物_累積参照比', index=False)
        shares.to_excel(w, sheet_name='代替技術シェア', index=False)
        annual[annual.year.isin([2020, 2030, 2050, 2100])].to_excel(w, sheet_name='主要年の全部門需要', index=False)
    manifest = {'type': 'PENELOPE_INSPIRED_PARTIAL_REPRODUCTION', 'same_objective_as_original': False, 'objective': 'lexicographic normalized reserve excess then squared share departure', 'fixed_AIM_macro_activity': True, 'power_mix_between_energy_sources_optimized': False, 'constraint_minerals': 33, 'conditional7_diagnostic_only': True, 'annual_mining_constraints': False, 'recycling_subtracted': False, 'complete40_inventory': False, 'optimization_start': 2026, 'base_vehicle_case': BASECASE, 'Na_policies': ['allow_Na_after2035', 'no_additional_Na_above_embedded_reference_mix'], 'full40_shortage_verdict': False, 'inputs': {str(q): hashlib.sha256(q.read_bytes()).hexdigest() for q in [Path(__file__), V / 'build.py', V / 'truck_reference.json', V / 'all_sectors_extended_CONDITIONAL.csv.gz', V / 'road_activity_annual.csv', DATA / 'coefficients.csv', DATA / 'power_activity.csv', PEN / 'PowerCap_MI_MS_CF.xlsx', PEN / 'EV_MI_MS_Recycling.xlsx', PEN / 'Market Share in time - Disag.xlsx', R / 'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv']}}
    (O / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    run()
