"""Common-32 conditional all-sector demand, with no shortage verdict.
Exclusion changes the reporting scope only; it does not reassign excluded elements.
"""
from pathlib import Path
import sys,json,hashlib
import numpy as np,pandas as pd
O=Path(__file__).resolve().parent
W=Path(__file__).resolve().parents[1];R=W/'mineral2100';V=W/'vehicle_allsector_extension_20261111'
# Use the actual source scope, not a manually shortened metal list.
hits=list((R/'originals').glob('Pelotte*/Data/Scope of the study.xlsx'))
if len(hits)!=1:raise ValueError('Exactly one Pene scope workbook required')
P=hits[0].parent
scope=pd.read_excel(hits[0],sheet_name='metals',index_col=0).iloc[:,0].tolist()
NAME_MAP={'Al':'Aluminum','B':'Boron','Cd':'Cadmium','Cr':'Chromium','Co':'Cobalt','Cu':'Copper','Dy':'Dysprosium','Ga':'Gallium','Ge':'Germanium','Hf':'Hafnium','In':'Indium','Fe':'Iron','Pb':'Lead','Li':'Lithium','Mn':'Manganese','Mo':'Molybdenum','Nd':'Neodymium','Ni':'Nickel','Nb':'Niobium','Pr':'Praesodymium','Se':'Selenium','Si':'Silicon','Ag':'Silver','Ta':'Tantalum','Te':'Tellurium','Tb':'Terbium','Sn':'Tin','W':'Tungsten','V':'Vanadium','Y':'Yttrium','Zn':'Zinc','Zr':'Zirconium'}
assert set(NAME_MAP.values())==set(scope) and len(scope)==32
MINERALS=list(NAME_MAP);HELD=['C','La','Ce','Mg','Ti','Sc','Pt','Ir'];MAIN='F_E_plus_steel_Fe_proxy'
source=V/'all_sectors_extended_CONDITIONAL.csv.gz';raw=pd.read_csv(source)
d=raw[raw.mineral.isin(MINERALS)].copy();assert set(raw.mineral)-set(MINERALS)==set(HELD)
main=d[d['case'].eq(MAIN)].copy();main=main.sort_values(['Sc','mineral','year'])
assert len(main)==2*32*81 and not main.duplicated(['Sc','mineral','year']).any()
assert not main.negative_base.any() and main.year.min()==2020 and main.year.max()==2100
SECTORS={'power':'発電','stationary_battery':'定置蓄電池','hydrogen':'水素製造','grid_CuAl_t_year':'送配電網_CuAl既知小計','vehicles_explicit_t_year':'車両既知小計','other_low_t_year':'その他経済部門'}
np.testing.assert_allclose(main[list(SECTORS)].sum(axis=1),main.conditional_total_low_t_year,rtol=1e-12,atol=1e-6)
np.testing.assert_allclose(main.conditional_total_low_t_year,main.conditional_total_high_t_year,rtol=1e-12,atol=1e-6)
for (sc,m),g in main.groupby(['Sc','mineral']):assert set(g.year)==set(range(2020,2101))
annual=main[['Sc','mineral','year']+list(SECTORS)+['conditional_total_low_t_year','LDV','BUS','TRUCK_SMALL','TRUCK_LARGE','unknown_active_class_powertrain_count']].rename(columns={**SECTORS,'conditional_total_low_t_year':'全部門条件付き合計','LDV':'乗用車_車両内数','BUS':'バス_車両内数','TRUCK_SMALL':'小型貨物_車両内数','TRUCK_LARGE':'大型貨物_車両内数','unknown_active_class_powertrain_count':'原単位未収録の稼働車種数'})
np.testing.assert_allclose(main[['LDV','BUS','TRUCK_SMALL','TRUCK_LARGE']].sum(axis=1),main.vehicles_explicit_t_year,rtol=1e-12,atol=1e-6)
annual['unit']='t/year; conditional known content + residual'
annual.to_csv(O/'annual32.csv.gz',index=False)
periods=[]
for end in [2050,2100]:
 q=d[d.year.between(2020,end)]
 s=q.groupby(['Sc','case','mineral'],as_index=False)[list(SECTORS)+['conditional_total_low_t_year']].sum()
 s['start']=2020;s['end']=end;s['unit']='t cumulative; inclusive annual discrete sum'
 s=s.rename(columns={**SECTORS,'conditional_total_low_t_year':'全部門条件付き合計'});periods.append(s)
cumulative=pd.concat(periods,ignore_index=True)
cumulative.to_csv(O/'cumulative32_all_cases.csv',index=False)
cm=cumulative[cumulative['case'].eq(MAIN)].copy()
# Literature reference inventory, with missing data kept as missing. No demand/reference ratios here.
r=pd.read_excel(P/'Prod&Demand_Other_Sectors.xlsx',sheet_name='Reserves_Resources',index_col=0)
latest=pd.read_csv(R/'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv').set_index('mineral')
refs=[]
for m in MINERALS:
 x=r.loc[NAME_MAP[m]];v=latest.loc[m]
 refs.append(dict(mineral=m,name=NAME_MAP[m],鉱物名=v['鉱物名'] if '鉱物名' in v else v.get('日本名',m),Penelope_埋蔵量_t=x.Reserves,Penelope_資源量_t=x.Resources,最新参照量_t=v.comparison_reference_t_element,最新参照量の区分=v.reference_class,最新参照量_追加仮定=bool(v.extended_assumption),対象範囲=v.scope,出典=v.source_url,注意='埋蔵量・資源量は別。需要との物質範囲と回収境界は未統一。'))
refs=pd.DataFrame(refs);assert refs.Penelope_埋蔵量_t.notna().sum()==27 and refs.Penelope_資源量_t.notna().sum()==23
assert refs.最新参照量_追加仮定.sum()==4
refs.to_csv(O/'references32_no_shortage_comparison.csv',index=False)
coverage=pd.read_csv(V/'active_inventory_coverage.csv');coverage=coverage[coverage['case'].eq(MAIN)&coverage.mineral.isin(MINERALS)].copy()
coverage=coverage.rename(columns={'any_coefficient_missing':'原単位未収録あり'})
coverage.to_csv(O/'vehicle32_missing_inventory.csv',index=False)
summary=[]
for m in MINERALS:
 z=dict(mineral=m,鉱物名=refs.set_index('mineral').loc[m,'鉱物名'])
 for end in [2050,2100]:
  for sc in ['Baseline','300C']:
   x=cm[cm.mineral.eq(m)&cm.Sc.eq(sc)&cm.end.eq(end)].iloc[0]
   z[f'{sc}_2020_{end}_Mt']=x['全部門条件付き合計']/1e6
 g=coverage[coverage.mineral.eq(m)&coverage['原単位未収録あり']]
 z['未収録の稼働車種']= '; '.join(g.vehicle_class+'_'+g.powertrain)
 z['需要が完全確定']=False;summary.append(z)
summary=pd.DataFrame(summary);summary.to_csv(O/'summary32.csv',index=False)
issues=pd.DataFrame([
 ('発電','更新版AIMの導入量×原単位で集計。PV重複と風力REEを整理。','PVのDC/AC容量基準、プール原単位の部品境界、CCS増分の重複。','原典の定格・設備境界を技術別に固定。PV方式転換は2050別ケースとして扱う。'),
 ('定置蓄電池','AIM導入量・12hモデル設定・Wei Li-ion3方式で集計。','12hは実測パック容量ではない。VRFBシェア・V原単位は未確定。','AIM整合の方式シェアとt/kWhを整備。IEA全置換は比較ケースに留める。'),
 ('水素製造','設備導入量×方式別原単位を集計。32枠に限定。','PEM等の方式シェア、原単位境界、設備交換。Pt/Ir/Scを保留すると主要触媒/電解質を対象外とする。','水素設備全材料の完全量ではなく対象32鉱物の既知小計と明示。'),
 ('車両','乗用・バス・貨物のVR+VP換算、HEV/FCV部品、残余再校正。','バスFCV駆動系、各車種の未収録元素、合金/混合部材、車種対応、電池単独交換。','未収録一覧の主要需要元素を優先補完。Fケースの鋼材Fe97.86%等を感度ケースと照合。'),
 ('送配電網','IEA Cu・Alを延長。','Cu/Al以外の鋼材Fe・Zn・Pb等、世界設備構成と更新フローが未統合。','Cu/Alのみの既知小計。非CuAlを0使用と扱わず、幾何原単位・採用率を整備。'),
 ('その他経済部門','基準年供給−明示需要の残余をGDP等で延長。','供給の一次/二次・在庫・元素/化合物範囲、2050以降の変化率固定。','明示部門を変えるたび残余を再校正。特にLiのLCE/元素基準を原典で確認。'),
 ('原単位共通','t/yearへ換算して集計。','Pénélopeの電池Li等の元素量/LCE境界、製品含有と採掘必要量の違い。','需要の主要元素から物質範囲・歩留まりを統一。回収控除を全期間へ適用。'),
 ('埋蔵量','32枠について原典値・独自参照を整理。','Pénélope埋蔵量5欠損、資源量9欠損。独自参照でもGe/Hf/Si/Taは条件付き。','欠損を0や無限大にしない。原データの年・定義・地理・換算を統一。'),
 ('再現性','GitHubで最新コードを公開、入力仕様と検証を記録。','生GDXから最終集計までの全入力生成は未一体化。非公開中間表が必要。','固定入力一覧・ハッシュ・コマンド・AIM版を揃え、32鉱物で全工程を通し再実行。')
],columns=['部門・項目','できていること','できていないこと','完成に向けた作業'])
notes=pd.DataFrame([
 ('位置付け','32鉱物に限定した現時点の条件付き需要。全32元素・全部材の実測完全需要を確定した意味ではない。'),
 ('保留8鉱物',', '.join(HELD)+'。結果表から除外するだけで、残る32鉱物へ質量を再配分しない。'),
 ('本表','更新版AIM2611091342、世界、Baseline/300C、2020–2100。非最適化・AIM蓄電維持。'),
 ('参照ケース',MAIN+'。Fの鋼材Fe97.86%・FCV補完等の仮定を含む。A–F別ケースの累積量を併記。'),
 ('会計','年間新設・交換需要の既知部品含有量と基準年残余の和。一次採掘必要量や回収後純需要ではない。'),
 ('単位','年次t/year。累積は2020–2050の31年、2020–2100の81年を単純合計。Mt=100万t。'),
 ('車両内数','乗用・バス・小型貨物・大型貨物は車両合計の内訳。合計へ重ねて足さない。'),
 ('欠損','部門の0は今回の明示計上なし。未収録の原単位を物理的なゼロ使用と解釈しない。'),
 ('技術転換ケース','直近のPV方式変更・IEA蓄電置換は2050専用の別ケース。本表の2100までの需要には混在させていない。'),
 ('送配電','本表はCu/Alのみ。電線・変圧器等の32元素全量ではない。'),
 ('埋蔵量','Pénélope同梱の埋蔵量27/32、資源量23/32。最新独自参照は世界系参照28、条件付き4。年・定義は一致しない。'),
 ('結果の公開','本ExcelやCSVは非公開の研究結果。GitHubへはコードと入力仕様のみを公開する。')
],columns=['項目','説明'])
with pd.ExcelWriter(O/'mineral32_results.xlsx',engine='xlsxwriter') as w:
 for name,z in [('最初に読む',notes),('32鉱物概要_Mt',summary),('部門別累積_参照ケース',cm),('年次_参照ケース_t',annual.drop(columns='unit')),('A–F累積感度_t',cumulative),('参照量_超過判定なし',refs),('車両未収録',coverage),('残る課題',issues)]:
  z.to_excel(w,sheet_name=name,index=False);ws=w.sheets[name];ws.freeze_panes(1,0);ws.autofilter(0,0,len(z),len(z.columns)-1);ws.set_column(0,len(z.columns)-1,19)
 w.sheets['最初に読む'].set_column(1,1,110);w.sheets['残る課題'].set_column(1,3,65)
issues.to_csv(O/'remaining_issues32.csv',index=False)
(O/'README.md').write_text('''# 共通32鉱物に限定した全部門需要

保留：C、La、Ce、Mg、Ti、Sc、Pt、Ir。

本表は更新版AIMの世界・Baseline/300C・2020–2100年。参照はFケース、A–Fを感度表に保持。
PV転換・IEA蓄電置換の2050最適化とは別の非最適化需要表。主要な仮定・未収録を表内に記載。
32に限定しても全材料の原単位が揃うわけではなく、条件付きの既知小計＋残余である。

'''+ '\n'.join(f'- **{r[0]}**：未完了＝{r[2]}。次の作業＝{r[3]}' for r in issues.itertuples(index=False,name=None)))
inputs=[source,hits[0],P/'Prod&Demand_Other_Sectors.xlsx',R/'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv',V/'active_inventory_coverage.csv']
(O/'verification.json').write_text(json.dumps({'target_minerals':MINERALS,'held':HELD,'annual_rows':len(annual),'case_cumulative_rows':len(cumulative),'six_sector_sum_matches_total':True,'vehicle_inner_parts_match_vehicle_total':True,'no_negative_base':True,'not_complete_physical_inventory':True,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},ensure_ascii=False,indent=2))
print('Excel bytes',(O/'mineral32_results.xlsx').stat().st_size)
print(summary[summary.mineral.isin(['Fe','Al','Cu','Li','Co','Ni','Dy','Se','Te','V'])].drop(columns=['未収録の稼働車種','需要が完全確定']).to_string(index=False))
