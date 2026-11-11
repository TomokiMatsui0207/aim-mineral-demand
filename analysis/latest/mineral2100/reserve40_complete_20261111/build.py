"""Build a complete 40-slot reference case without relabelling proxies as world reserves."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from docx import Document
from docx.shared import Pt, Inches
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
P = Path(__file__).resolve().parent
R = P.parent
B = R / 'wei_style_reserves_20261110/40鉱物_Wei方式の埋蔵量参照値.csv'
D = R / 'update_comparison_20261110/results_updated_native_all_sectors/all_sectors_CONDITIONAL.csv.gz'
m = pd.read_csv(B).set_index('mineral')
m['comparison_reference_t_element'] = m.reserves_t_element
m['reference_class'] = '世界埋蔵量の統計・換算・既往推計'
m['geography'] = 'World'
m['scope'] = m.basis_note
m['formula'] = '既存出典値をt元素量で採録（元台帳参照）'
m['source_url'] = m.reserve_source
m['source_section'] = m.reserve_source_section
m['reference_time'] = m.reserve_reference_time
m['extended_assumption'] = False
m['global_reserve_confirmed'] = False
m['world_reference_case'] = m.usable_as_global_reserve_reference
m['scope_match_to_all_sector_demand'] = '元素量対応。製品/地中量、回収、工程歩留まりは未整合'
OECD = 'https://www.oecd.org/en/publications/due-diligence-for-responsible-sand-and-silicate-supply-chains_7be0093e-en/full-report/component-5.html'
BROCHURE = 'https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/due-diligence-guidance-for-responsible-business-conduct/brochure-key-findings-sand-and-silicates.pdf'
GA = 'https://www.ga.gov.au/scientific-topics/minerals/aimr/2026-preliminary-tables'
US = 'https://pubs.usgs.gov/periodicals/mcs2026/mcs2026.pdf'
GE = 'https://scrreen.eu/wp-content/uploads/2023/09/SCRREEN2_factsheets_GERMANIUM-1.pdf'
EC = 'https://rmis.jrc.ec.europa.eu/uploads/rmprofiles/info-production.pdf'
sc_lit = m.loc['Sc', 'conditional_source']

def put(sym, v, cl, geo, scope, formula, url, section, year, match):
    m.loc[sym, ['comparison_reference_t_element', 'reference_class', 'geography', 'scope', 'formula', 'source_url', 'source_section', 'reference_time', 'extended_assumption', 'world_reference_case', 'scope_match_to_all_sector_demand']] = [v, cl, geo, scope, formula, url, section, year, True, False, match]
put('C', 310000000.0, '対象限定の世界埋蔵量', 'World; natural graphite only', '天然黒鉛のみ。合成黒鉛・炭素一般を含まない。', '310,000,000 t natural graphite', US, 'Graphite (Natural), World total Reserves', 'USGS2026', '全Cへ適用不可。天然由来黒鉛需要を分離して比較。全C天然ケースは極端な仮定としてのみ。')
put('Ge', 8600, '過去年の世界埋蔵量推計', 'World historical estimate', '2012年推計。2020年・2025年末へ更新した値ではない。', '8,600 t Ge (historical literature estimate)', GE, 'Supply from primary materials; cites Bio Intelligence Service 2015 / EC2014', '2012 estimate cited in EC2020 and SCRREEN2', '資源量36,000tと別ケース。元の2015一次推計は独立未照合。')
hf = float(m.loc['Zr', 'reserves_t_element']) / 50
put('Hf', hf, 'Zr埋蔵量に伴う含有量の推計', 'World host-reserve proxy', 'Zr:Hf=50:1を全Zr埋蔵量へ転用。可採Hf量そのものではない。', '70e6 t ZrO2 * 91.224/(91.224+2*15.999) / 50', EC, '27 Hafnium, 27.2; USGS2026 zirconium reserves', 'USGS2026 host + RMIS2023 method', 'ホストが>70Mtなので、固定組成仮定下の下限参照。Hf回収率・採算・分離能力は含まない。')
mg_factor = 0.478 * 24.305 / (24.305 + 15.999)
put('Mg', 7800000000.0 * mg_factor, 'マグネサイト埋蔵量のMg換算推計', 'World magnesite only', 'USGSの一般換算47.8%MgOを埋蔵量へ転用する仮定。ドロマイト・塩水等は含まない。', '7.8e9 t magnesite * 0.478 MgO * 24.305/(24.305+15.999)', US, 'Magnesium Compounds, reserve table and footnote2/6', 'USGS2026', '全Mg世界埋蔵量ではない。Mg金属の原料範囲が異なるので全金属需要への機械適用はしない。')
put('Sc', 6180, '公表済み国別埋蔵量', 'Australia only', '豪州Ore ReservesのSc含有量。EDR51,580tと加算しない。', '6.18 kt Sc * 1000', GA, 'Table2 Total Ore Reserves, Scandium', '2025-12-31, AIMR2026 preliminary', '世界需要/豪州値は対象限定指標。超過しても世界不足とは判定しない。')
put('Ta', 400150, '公表国の埋蔵量合計', 'Australia + Brazil + China + Russia', '他国NAを0とせず、公表4か国のみ。', '120000 + 40000 + 240000 + 150 t Ta', US, 'Tantalum, World Mine Production and Reserves', 'USGS2026', '世界総量NA。既知公表国集計。全世界の不足判定には使わない。')
si_factor = 28.085 / (28.085 + 2 * 15.999)
put('Si', 250000000.0 * si_factor, '金属Si用石英の埋蔵量からの換算推計', 'World estimate; quartz suitable for silicon-metal production', 'OECD図の約250Mt石英を純SiO2相当とする。全Si鉱物やガラス原料を含む総量ではない。', '250e6 t quartz * 28.085/(28.085+2*15.999)', OECD, 'Figure2.5; brochure p4', 'OECD2026; underlying reserve reference year unspecified', '採算・回収・グレードを統一した世界Si埋蔵量ではない。Si金属/PV用途限定の含有量参照。')
m['case'] = 'DOCUMENTED_SCOPE_REFERENCE_40_NOT_40_GLOBAL_RESERVES'
m['shortage_verdict_ready'] = False
out = m.reset_index()
cols = ['mineral', '鉱物名', 'comparison_reference_t_element', 'reference_class', 'geography', 'reference_time', 'scope', 'formula', 'source_url', 'source_section', 'extended_assumption', 'world_reference_case', 'scope_match_to_all_sector_demand', 'shortage_verdict_ready', 'case']
master = out[cols].copy()
master.to_csv(P / '40鉱物_埋蔵量と推計参照値.csv', index=False)
alt = []

def a(sym, case, v, kind, url, note):
    alt.append(dict(mineral=sym, case=case, value_t_element=v, reference_class=kind, source=url, note=note))
a('Sc', 'world_literature_0.5Mt', 500000, '分類未整合の文献世界推計', sc_lit, 'Mykhailov2023記載の0.5–1.8Mt。原典は2019–2020市場資料等。世界確認埋蔵量と扱わない。')
a('Sc', 'world_literature_1.8Mt', 1800000, '分類未整合の文献世界推計', sc_lit, '低/高は文献の推計幅。信頼区間ではない。')
a('Sc', 'Australia_EDR', 51580, '経済的確認資源量', GA, 'Table3 EDR。Ore Reservesと重複し得る。')
a('Hf', 'host_ratio40', float(m.loc['Zr', 'reserves_t_element']) / 40, '固定組成の随伴量代理', 'https://scrreen3.flexx.camp/factsheet-689', '暫定SCRREEN3の40:1。50:1と独立感度。暫定版の生産量は不整合があり採用しない。')
a('Mg', 'pure_MgCO3', 7800000000.0 * 24.305 / (24.305 + 12.011 + 3 * 15.999), '純化合物相当の含有量', US, '以前の純MgCO3仮定との比較。実鉱石品位の証拠ではない。')
a('Si', 'regional_fig_sum246Mt', 246000000.0 * si_factor, '図の地域別丸め値の合計', OECD, '90+90+40+20+6=246Mt。図の世界丸め250Mtと不一致4Mtを記録。異なる地質シナリオとは扱わない。')
a('Ge', 'resource_Lundaev2023', 36000, '資源量', 'https://doi.org/10.1016/j.mineng.2023.108282', '2012埋蔵量推計と加算しない。')
a('Si', 'quartz_grade99.4percent', 250000000.0 * 0.994 * si_factor, '図の石英量に最低適合純度を適用した含有量推計', OECD, '本文の金属Si原料適合純度99.4〜99.8%を適用。鉱床別の実測平均品位ではない。')
a('Si', 'quartz_grade99.8percent', 250000000.0 * 0.998 * si_factor, '図の石英量に適合純度を適用した含有量推計', OECD, '純SiO2相当の主表より不純物を考慮。実測分布ではない。')
alt = pd.DataFrame(alt)
alt.to_csv(P / '追加ケース_資源量と推計幅.csv', index=False)
d = pd.read_csv(D)
d = d[(d.statistic == 'average') & (d.grid_case == 'SPS') & (d.case == 'HEV_sedan_MG2010_WangNiMH_DOE2011_AB5_transfer') & d.year.between(2026, 2100)].copy()
assert not d.duplicated(['Sc', 'mineral', 'year']).any()
cum = d.groupby(['Sc', 'mineral'])[['conditional_total_low_t_year', 'conditional_total_high_t_year']].sum().reset_index().rename(columns={'conditional_total_low_t_year': 'gross_2026_2100_low_t', 'conditional_total_high_t_year': 'gross_2026_2100_high_t'})
cmp = cum.merge(master, on='mineral', validate='many_to_one')
cmp['gross_low_divided_by_reference'] = cmp.gross_2026_2100_low_t / cmp.comparison_reference_t_element
cmp['gross_high_divided_by_reference'] = cmp.gross_2026_2100_high_t / cmp.comparison_reference_t_element
cmp['interpretation'] = np.where(cmp.extended_assumption, '範囲未整合・仮定付きの数値感度。世界の不足/充足判定ではない。', '総含有需要対埋蔵量参照の圧力指標。一次採掘不足の判定ではない。')
cmp['cumulative_demand_basis'] = '2026–2100 inclusive annual sum; gross conditional inventory; no recycling subtraction here'
cmp.to_csv(P / '両シナリオ40鉱物_累積参照比_不足判定ではない.csv', index=False)
globalcases = []
for label, scval in [('Sc_published_world_low', 500000), ('Sc_published_world_high', 1800000)]:
    g = master.copy()
    mask = g.mineral.eq('Sc')
    g.loc[mask, 'comparison_reference_t_element'] = scval
    g.loc[mask, 'reference_class'] = '世界文献推計（埋蔵量分類未整合）'
    g.loc[mask, 'geography'] = 'World estimate; nonharmonized'
    g.loc[mask, 'source_url'] = sc_lit
    g.loc[mask, 'source_section'] = 'Scandium chapter, 0.5–1.8 Mt estimate'
    g.loc[mask, 'reference_time'] = '2019–2020 original estimates, compiled2023'
    g.loc[mask, 'formula'] = 'published 0.5 or 1.8 Mt Sc converted to t'
    g.loc[mask, 'scope'] = '市場資料等に基づく文献世界推計。USGS/JORCの統一世界埋蔵量ではない。'
    g.loc[mask, 'scope_match_to_all_sector_demand'] = '豪州6,180tを世界値へ拡大せず、独立した文献推計ケース。信頼区間ではない。'
    g['case'] = label
    globalcases.append(g)
globalcases = pd.concat(globalcases, ignore_index=True)
globalcases.to_csv(P / '40鉱物_文献世界推計併用の別ケース.csv', index=False)
pv = d[d.mineral == 'Si'].groupby('Sc').power.sum().reset_index(name='PV_equipment_contained_Si_2026_2100_t')
pv['quartz_reference_t'] = 250000000.0
pv['Si_fraction_pure_SiO2'] = si_factor
pv['quartz_equivalent_at_unit_yield_t'] = pv.PV_equipment_contained_Si_2026_2100_t / si_factor
pv['contained_Si_to_quartz_Si_reference'] = pv.PV_equipment_contained_Si_2026_2100_t / (250000000.0 * si_factor)
pv['note'] = 'PV部門のみ。回収0、製造歩留まり1とする参照比較。全経済Si需要との比較とは区別。'
pv.to_csv(P / 'Si_PV用途限定の比較.csv', index=False)
fig = pd.DataFrame({'region': ['North America', 'Asia', 'Europe', 'Africa', 'Oceania', 'World rounded'], 'quartz_reserve_Mt': [90, 90, 40, 20, 6, 250]})
fig['source'] = BROCHURE
fig['section'] = 'p4; OECD2026 Figure2.5'
fig['retrieval'] = 'official web indexed numerical transcription; screenshot tool returned text placeholder, no local source image'
fig.to_csv(P / 'OECD_石英埋蔵量_図の採録.csv', index=False)
formula = pd.DataFrame([['Si', 'quartz_to_Si', si_factor, '28.085/(28.085+2*15.999)', '純SiO2相当の含有量換算。収率ではない。'], ['Mg', 'magnesite_to_Mg', mg_factor, '0.478*24.305/(24.305+15.999)', '一般MgO換算値を埋蔵量へ転用する仮定'], ['Hf', 'Zr_to_Hf', 0.02, '1/50', '固定Zr:Hf比。可採率ではない。'], ['Ta', 'four_country_sum', 400150, '120000+40000+240000+150', '原表単位t。露を150ktと誤読しない。']], columns=['mineral', 'conversion', 'factor_or_result', 'formula', 'note'])
readme = [('成果', '40種類すべてに有限・正の比較参照値を用意した。33種類は前段の世界埋蔵量参照ケース、7種類は対象範囲や推計条件を付けた補完。40種類の世界確認埋蔵量が確定したという意味ではない。'), ('新規のSi候補', 'OECD2026の図2.5は、Si金属製造に適した石英の世界埋蔵量を約250Mtと表示。純SiO2相当の元素換算で約116.86Mt Siとなる。全地殻Si量や全シリカ鉱物の可採量ではない。原典地質評価の統一分類と基準年は未確認。'), ('Si図の丸め', '地域別表示90+90+40+20+6=246Mtに対して世界250Mt。原図の値を両方保存し、都合よく合計を修正しない。OECDの本文では金属Si原料と、るつぼ用超高純度石英を分けている。本ケースは前者。'), ('Scの選択', '主表は豪州2025年末Ore Reserves 6,180t Scという範囲限定の確認値を採用。世界0.5–1.8Mtという既往推計は分類未整合なので別ケース。これを使った40鉱物表も別シートに収録。豪州値を世界総量へ外挿しない。'), ('C/Mg/Hf', 'Cは天然黒鉛のみ。Mgはマグネサイトだけの含有量参照であり、金属Mgの原料であるドロマイトや塩水等は含めない。HfはZrに伴う固定組成推計で、実際に回収できる埋蔵量とは別。'), ('Ge/Ta', 'Geは2012年世界推計8,600tを年代付きで採用し、資源量36,000tと別にする。Taは公表4か国400,150tで、未報告国をゼロとしない。'), ('需要比較', '更新AIM、平均原単位、網SPS、HEV sedan/MG2010/AB5 transferの同一条件を使用。2026–2100年の年次和を参照量で割った80件を出力。これは総含有量の圧力指標で、回収控除後の一次必要量ではない。特に補完7鉱物の全需要比は、物質範囲を機械的に当てた感度値として扱う。'), ('整合性の注意', '出典はUSGS2026・2022版、2012推計、2023論文など複数年代の統合。2020年末に統一された埋蔵量ではない。供給−需要の残余法へ自動投入しない。埋蔵量と資源量を加算しない。合成黒鉛に天然黒鉛埋蔵量を割り当てない。'), ('次の使い方', '主解析は33世界参照値、補完込み40は出典・対象範囲を示す拡張解析として並記。世界Scの文献ケース、Hf組成、Si対象石英の範囲を変えた結果も別表に残す。埋蔵量未報告を0または無限大で埋めていない。'), ('再現', 'build.pyをPythonで実行。入力2CSVのSHA256と出力のSHA256はmanifest.json。元の需要CSV・従来の埋蔵量マスターは上書きしない。')]
with pd.ExcelWriter(P / '40鉱物_埋蔵量と推計参照値_完成版.xlsx', engine='openpyxl') as w:
    for name, df in [('採用値40_分類を必ず確認', master), ('世界文献併用40_弱い推計含む', globalcases), ('追加ケース', alt), ('両シナリオの参照比80', cmp), ('Si_PV用途限定', pv), ('OECD石英図採録', fig), ('換算式', formula), ('方法と限界', pd.DataFrame(readme, columns=['item', 'explanation']))]:
        df.to_excel(w, sheet_name=name, index=False)
    from openpyxl.styles import PatternFill, Alignment, Font
    for sh in w.book:
        sh.freeze_panes = 'C2'
        sh.auto_filter.ref = sh.dimensions
        for col in sh.columns:
            sh.column_dimensions[col[0].column_letter].width = min(65, max(14, max((len(str(c.value or '')) for c in col)) + 2))
        for row in sh:
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for cell in sh[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24496B')
    for row in w.book.worksheets[0].iter_rows(min_row=2):
        if row[0].value in ['C', 'Ge', 'Hf', 'Mg', 'Sc', 'Si', 'Ta']:
            for cell in row:
                cell.fill = PatternFill('solid', fgColor='FFF1CC')
(P / '方法と限界.md').write_text('# 40鉱物の埋蔵量・推計参照値\n\n2026年11月11日\n\n' + '\n\n'.join(('## ' + h + '\n' + t for h, t in readme)))
doc = Document()
doc.styles['Normal'].font.name = 'Noto Sans CJK JP'
doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), 'Noto Sans CJK JP')
doc.styles['Normal'].font.size = Pt(9)
doc.add_heading('40鉱物の埋蔵量・推計参照値', 0)
doc.add_paragraph('2026年11月11日｜33世界参照値＋7条件付き補完｜Weiの原値の再現ではない')
for h, t in readme[:4]:
    doc.add_heading(h, 2)
    doc.add_paragraph(t)
doc.add_page_break()
doc.add_heading('採用した40種類の比較参照値', 1)
doc.add_paragraph('単位はt元素量。*は追加条件付き。世界総量・対象限定量・含有量代理が混在するため、分類列とExcelの対象範囲を必ず併記する。')
t = doc.add_table(rows=1, cols=3)
t.style = 'Light Shading Accent 1'
for cell, v in zip(t.rows[0].cells, ['鉱物', '参照値（t元素）', '分類']):
    cell.text = v
pr = t.rows[0]._tr.get_or_add_trPr()
rep = OxmlElement('w:tblHeader')
pr.append(rep)
for _, r in master.iterrows():
    rr = t.add_row().cells
    rr[0].text = r.mineral + ('*' if r.extended_assumption else '')
    rr[1].text = f'{r.comparison_reference_t_element:,.0f}'
    rr[2].text = r.reference_class
    for cell in rr:
        for para in cell.paragraphs:
            para.paragraph_format.space_after = Pt(2)
            para.paragraph_format.space_before = Pt(0)
t.autofit = False
for table_row in t.rows:
    for cell, width in zip(table_row.cells, [0.6, 1.65, 4.0]):
        cell.width = Inches(width)
    for cell in table_row.cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.font.size = Pt(8)
doc.add_page_break()
doc.add_heading('計算方法と説明上の注意', 1)
for h, t in readme[4:]:
    doc.add_heading(h, 2)
    doc.add_paragraph(t)
doc.add_heading('Si新規出典', 2)
doc.add_paragraph(OECD)
doc.add_paragraph('OECD (2026), Figure2.5 / official key findings brochure p4. 原図採録値と換算式はExcelへ保存。')
doc.save(P / '40鉱物_採用値と根拠の説明.docx')
assert len(master) == 40 and master.mineral.nunique() == 40
assert np.isfinite(master.comparison_reference_t_element).all() and (master.comparison_reference_t_element > 0).all()
assert master.extended_assumption.sum() == 7 and master.world_reference_case.sum() == 33
assert len(cmp) == 80 and np.isfinite(cmp.gross_low_divided_by_reference).all()
assert master.set_index('mineral').loc['Ta', 'comparison_reference_t_element'] == 400150
assert 116000000.0 < float(m.loc['Si', 'comparison_reference_t_element']) < 118000000.0
assert 0.467 < si_factor < 0.468 and 0.288 < mg_factor < 0.289
assert all(cmp.shortage_verdict_ready == False)
assert 90 + 90 + 40 + 20 + 6 == 246
(P / 'verification.txt').write_text('PASS: 40 unique minerals; 40 finite positive reference denominators; 33 prior world references + 7 scope-qualified complements; 80 comparison rows; Ta units checked; no physical shortage verdict asserted; 246 vs250Mt rounding discrepancy preserved.\n')
manifest = {'date': '2026-11-11 Asia/Tokyo', 'inputs': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [B, D]}, 'outputs': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file() and f.name != 'manifest.json'}, 'new_source': OECD, 'wei_exact_reserves_reproduced': False, 'all40_global_reserves_confirmed': False}
(P / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
print(master[master.extended_assumption][['mineral', 'comparison_reference_t_element', 'reference_class']].to_string(index=False))
print('Validated 40 reference denominators and 80 comparison rows.')
