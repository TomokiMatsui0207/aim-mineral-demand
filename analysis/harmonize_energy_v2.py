"""Flow-based energy revision. Restore material coverage, track scope hypotheses explicitly.
Historical v1 outputs are immutable. No empirical probability is assigned to alternatives.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import integrate_all_sectors_conditional as legacy
from model import MINERALS
ROOT=Path(__file__).resolve().parent.parent
STEEL_FE=.9786  # inherited transfer assumption, not a material-specific assay
CCS=['Coa','Gas','Bio']


def coefficient_table(statistic,solar_mode='additive_reference',include_ccs=True,sc_mode='ScSZ_electrolyzer_reference'):
    if solar_mode not in ['additive_reference','replacement_comparator']:raise ValueError('Unknown solar boundary')
    raw=pd.read_csv(ROOT/'input/imported/wei_intensity_rows.csv');raw=raw.loc[raw.reported_average.notna()].copy()
    raw['value']=raw.reported_minimum.where(raw.reported_minimum.notna(),raw.reported_average) if statistic=='minimum' else raw.reported_average
    if statistic not in ['average','minimum']:raise ValueError('Unknown statistic')
    def material(cat,tech,mat):
        q=raw.loc[raw.category.eq(cat)&raw.material.eq(mat)]
        if tech is not None:q=q.loc[q.technology.eq(tech)]
        if len(q)>1:raise ValueError(f'Multiple pooled means need explicit resolution: {cat}/{tech}/{mat}')
        return (float(q.value.iloc[0]),True) if len(q) else (0.,False)
    def element(cat,tech,m):
        direct,seen=material(cat,tech,m)
        steel,steel_seen=material(cat,tech,'Steel') if m=='Fe' else (0.,False)
        # Preserve both separately reported components; the disjoint-scope assumption remains explicit.
        return direct+STEEL_FE*steel,seen or steel_seen,direct,steel
    shares=pd.read_csv(ROOT/'input/imported/wei_S11_Market_share.csv');shares.technology=shares.technology.ffill()
    def share(category):
        q=shares.loc[shares.technology.eq(category)].set_index('abbreviation')['market share assumptions'].astype(float)
        if not np.isclose(q.sum(),1):raise ValueError('Incomplete shares')
        return q
    pv=share('Solar');rows=[]
    for suffix,cat,tech in legacy.MAPPINGS:
        for m in MINERALS:
            common=specific=0.;boundary='direct_source_mean'
            if cat=='Solar':
                common,pc,dc,st=element('Solar','PV',m)
                parts=[(float(s),*element('Solar',t,m)) for t,s in pv.items()]
                specific=sum(s*v for s,v,p,d,steel in parts)
                if solar_mode=='additive_reference':
                    val=common+specific;direct=dc+sum(s*d for s,v,p,d,steel in parts);steel=st+sum(s*steel for s,v,p,d,steel in parts)
                else:
                    val=sum(s*(v if p else common) for s,v,p,d,steel in parts)
                    direct=sum(s*(d if p else dc) for s,v,p,d,steel in parts)
                    steel=sum(s*(steel if p else st) for s,v,p,d,steel in parts)
                seen=pc or any(p for s,v,p,d,steel in parts)
                boundary='common_PV_plus_specific_ASSUMPTION' if solar_mode=='additive_reference' else 'specific_replaces_common_ASSUMPTION'
            else:
                val,seen,direct,steel=element(cat,None if cat=='wind' else tech,m)
                if cat=='wind':boundary='source_pooled_wind_mean_transferred_to_both_siting_types; NOT_a_siting_specific_estimate'
            rows.append(dict(sector='power',technology=suffix,mineral=m,statistic=statistic,intensity=val,coefficient_reported=seen,unit='t/GW',elemental_component_t_GW=direct,steel_material_part_t_GW=steel,steel_Fe_fraction_ASSUMED=STEEL_FE if m=='Fe' else np.nan,scope_assumption=boundary,solar_common_t_GW=common,solar_specific_weighted_t_GW=specific))
    if include_ccs:
        for suffix in CCS:
            for m in MINERALS:
                val,seen,direct,steel=element('Carbon capture and storage','CCS',m)
                rows.append(dict(sector='power',technology='CCS_'+suffix,mineral=m,statistic=statistic,intensity=val,coefficient_reported=seen,unit='t/GW',elemental_component_t_GW=direct,steel_material_part_t_GW=steel,steel_Fe_fraction_ASSUMED=STEEL_FE if m=='Fe' else np.nan,scope_assumption='CCS_inventory_as_incremental_to_base_plant_ASSUMPTION; overlap_unverified',solar_common_t_GW=0.,solar_specific_weighted_t_GW=0.))
    for sec,category,cat,unit in [('hydrogen','Hydrogen by Electricity','Electric hydrogen','t/GW'),('stationary_battery','Electricity Storage','Energy storage','Wei_table_as_t/GW_REPRODUCTION')]:
        ss=share(category)
        for m in MINERALS:
            parts=[(float(s),*element(cat,t,m)) for t,s in ss.items()]
            val=sum(s*v for s,v,p,d,steel in parts);seen=any(p for s,v,p,d,steel in parts)
            if sec=='hydrogen' and m=='Sc' and sc_mode!='Wei_reproduction':
                if sc_mode=='ScSZ_electrolyzer_reference':val=float(ss.get('SOEC',0.))*10*(2*44.955908)/(2*44.955908+3*15.999)
                elif sc_mode=='YSZ_electrolyte_reference':val=0.
                else:raise ValueError('Unknown Sc reference')
            rows.append(dict(sector=sec,technology='weighted_source_shares',mineral=m,statistic=statistic,intensity=val,coefficient_reported=seen,unit=unit,elemental_component_t_GW=(val if sec=='hydrogen' and m=='Sc' else sum(s*d for s,v,p,d,steel in parts)),steel_material_part_t_GW=sum(s*steel for s,v,p,d,steel in parts),steel_Fe_fraction_ASSUMED=STEEL_FE if m=='Fe' else np.nan,scope_assumption=('SOEC_'+sc_mode+'; adoption_unknown; other_device_elements_not_rebuilt' if sec=='hydrogen' and m=='Sc' else 'Wei_fixed_technology_shares; component_and_capacity_basis_pending'),solar_common_t_GW=0.,solar_specific_weighted_t_GW=0.))
    return pd.DataFrame(rows)


def power_activity(aim):
    base,audit=legacy.power_activity(aim);rows=[];checks=[]
    units=pd.read_csv(ROOT/'input/units_and_time_basis.csv').set_index('variable')
    for sc,g in aim.groupby('Sc'):
        values=g.set_index(['Sv','Y5']).value
        for suffix in CCS:
            var='Cap_Add_Ele_'+suffix+'_w_CCS'
            if units.loc[var,'declared_unit']!='GW/yr' or units.loc[var,'time_basis']!='five_year_average_ending_at_label':raise ValueError('CCS time unit mismatch')
            for end in range(2020,2101,5):
                total=float(values.get(('Cap_Add_Ele_'+suffix,end),0.));wc=float(values.get((var,end),0.));wo=float(values.get(('Cap_Add_Ele_'+suffix+'_wo_CCS',end),0.))
                if not np.isclose(total,wc+wo,atol=1e-6,rtol=1e-8):raise ValueError('Power parent/CCS children not additive')
                checks.append(dict(Sc=sc,variable=var,model_year=end,rate_GW_year=wc,sparse_zero_assumed=(var,end) not in values.index,parent_child_balance_GW_year=total-wc-wo))
                for year in ([2020] if end==2020 else range(end-4,end+1)):
                    rows.append(dict(Sc=sc,year=year,technology='CCS_'+suffix,addition_GW_year=wc,basis='incremental_CCS_inventory_on_with_CCS_additions_ASSUMPTION; base_parent_already_counted_once'))
    return pd.concat([base,pd.DataFrame(rows)],ignore_index=True),pd.concat([audit,pd.DataFrame(checks)],ignore_index=True)


def recompute_energy(co,pa,ha,ba):
    frames=[]
    for sec,act in [('power',pa),('hydrogen',ha),('stationary_battery',ba)]:
        c=co.loc[co.sector.eq(sec)]
        d=act.merge(c,on='technology') if sec=='power' else act.merge(c.drop(columns='technology'),how='cross')
        d['explicit_t_year']=d.addition_GW_year*d.intensity
        frames.append(d.groupby(['Sc','year','statistic','sector','mineral'],as_index=False).explicit_t_year.sum())
    return pd.concat(frames,ignore_index=True)


def run():
    tables=legacy.build(coefficient_table,power_activity)
    totals,secsum,detail,grid,osd,base,co,pa,paudit,ha,ba=tables
    out=ROOT/'output/harmonized_energy_v2';out.mkdir(parents=True,exist_ok=True)
    # Reference and alternatives are separate hypotheses. Store exact deltas rather than a huge Cartesian expansion.
    sensitivities=[]
    for name,solar,ccs,sc in [('solar_replacement','replacement_comparator',True,'ScSZ_electrolyzer_reference'),('without_CCS_increment','additive_reference',False,'ScSZ_electrolyzer_reference'),('Wei_Sc_reproduction','additive_reference',True,'Wei_reproduction'),('YSZ_electrolyte','additive_reference',True,'YSZ_electrolyte_reference')]:
        alts=[]
        for stat in ['average','minimum']:alts.append(recompute_energy(coefficient_table(stat,solar,ccs,sc),pa,ha,ba))
        alt=pd.concat(alts,ignore_index=True).groupby(['Sc','year','statistic','mineral'],as_index=False).explicit_t_year.sum()
        ref=secsum.groupby(['Sc','year','statistic','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'reference_explicit_t_year'})
        d=ref.merge(alt,on=['Sc','year','statistic','mineral'],validate='one_to_one')
        d['alternative']=name;d['explicit_delta_t_year']=d.explicit_t_year-d.reference_explicit_t_year
        delta0=d.loc[d.year.eq(2020),['Sc','statistic','mineral','explicit_delta_t_year']].rename(columns={'explicit_delta_t_year':'base_delta_t_year'})
        d=d.merge(delta0,on=['Sc','statistic','mineral'],validate='many_to_one')
        factor=osd.drop_duplicates(['Sc','year','statistic','mineral'])[['Sc','year','statistic','mineral','growth_factor']]
        d=d.merge(factor,on=['Sc','year','statistic','mineral'],validate='one_to_one')
        d['other_delta_t_year']=-d.base_delta_t_year*d.growth_factor
        d['conditional_total_delta_t_year']=d.explicit_delta_t_year+d.other_delta_t_year
        # The linear delta is valid only where alternative residual also remains nonnegative.
        b=base[['Sc','statistic','grid_case','mineral','raw_residual_low_t_year']].merge(delta0,on=['Sc','statistic','mineral'],validate='many_to_one')
        b['alternative_negative_base']=(b.raw_residual_low_t_year-b.base_delta_t_year)<0
        b['reference_negative_base']=b.raw_residual_low_t_year<0
        validity=b.groupby(['Sc','statistic','mineral'],as_index=False)[['alternative_negative_base','reference_negative_base']].any()
        d=d.merge(validity,on=['Sc','statistic','mineral'],validate='many_to_one')
        d['delta_is_valid_full_total']=~(d.alternative_negative_base|d.reference_negative_base)
        d['reviewed_total_delta_t_year']=d.conditional_total_delta_t_year.where(d.delta_is_valid_full_total)
        d=d.sort_values(['Sc','statistic','mineral','year'])
        d['cumulative_reviewed_delta_t']=d.groupby(['Sc','statistic','mineral']).reviewed_total_delta_t_year.transform(lambda x:x.cumsum(skipna=False))
        d['not_additive_across_boundary_hypotheses']=True
        sensitivities.append(d)
    sensitivity=pd.concat(sensitivities,ignore_index=True)
    cumulative=secsum.groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'revised_cumulative_t'})
    v1=pd.read_csv(ROOT/'output/all_sectors_two_scenarios/explicit_sector_annual.csv').groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'previous_v1_cumulative_t'})
    comparison=cumulative.merge(v1,on=['Sc','statistic','sector','mineral'],validate='one_to_one')
    old=pd.read_csv(ROOT/'output/original_R_vs_current_energy/cumulative_comparison.csv')[['Sc','sector','mineral','old_R_2020_2100_point_sum_t']]
    comparison=comparison.merge(old,on=['Sc','sector','mineral'],validate='many_to_one')
    comparison['revised_minus_v1_t']=comparison.revised_cumulative_t-comparison.previous_v1_cumulative_t
    comparison['old_R_is_stock_point_sum_NOT_same_physical_metric']=True
    names=['all_sectors_reference_CONDITIONAL','explicit_sector_annual','explicit_sector_detail','grid_CuAl_annual','other_complement_annual_CONDITIONAL','baseline2020_recalibration','coefficients_with_material_ledger','power_activity','power_activity_audit','hydrogen_activity','battery_activity']
    for name,f in zip(names,tables):
        if name=='all_sectors_reference_CONDITIONAL':f.to_csv(out/(name+'.csv.gz'),index=False,compression='gzip')
        else:f.to_csv(out/(name+'.csv'),index=False)
    sensitivity.to_csv(out/'boundary_and_Sc_alternative_deltas.csv.gz',index=False,compression='gzip')
    comparison.to_csv(out/'old_v1_revised_energy_comparison.csv',index=False)
    totals.loc[totals.year.eq(2100)].to_csv(out/'2100_reference_and_cumulative.csv',index=False)
    notes=pd.DataFrame({'説明':['製造需要には新設フロー、累積には年幅を採用。ストックの出力点和を新設需要と混同しない。','Fe=報告Fe+0.9786×Steel。両項の別部品性と鋼材Fe率は仮定として記録。Steelを落とすバグを修正。','風力表の鉱物ごと単一の平均値を共通使用。陸上/洋上の空欄から物理的ゼロを作らない。','Solar共通PV+種類別を元方式継承の参照に採用。部品重複未確認なので置換方式の差を別出力。','CCSは基本発電設備を親容量で1回計上し、CCS原単位を追加設備と仮定してCCS新設分へ適用。非加算比較も保持。','蓄電池は追加量×Wei原単位。時間を重ね掛けしない。単位と更新の確認事項は残る。','ScはScSZ電解参照6.5197t/GWを設計条件として採用し、Wei原値とYSZの差分を別出力。実際の採用割合は未確定。','その他部門は改訂した2020年明示量から必ず再校正。代替ケースも基準年の差引変更を反映した差分を保存。','代替差分は参照・代替双方の残余が非負の場合に限って合計へ適用。複数の部品範囲仮説を無条件に足さない。','全40鉱物の確定需要ではない。旧出力は履歴として保持。']})
    with pd.ExcelWriter(out/'harmonized_energy_v2.xlsx') as w:
        for name,f in [('統合ルールと仮定',notes),('旧R_前回_改訂の比較',comparison),('発電水素蓄電池_年次',secsum),('Fe鋼材と原単位の台帳',co),('全部門_主要年_参照条件',totals.loc[totals.year.isin([2020,2050,2100])]),('基準年残余_再校正',base),('境界とSc比較_2100年',sensitivity.loc[sensitivity.year.eq(2100)]),('活動量とCCS親子確認',paudit)]:f.to_excel(w,sheet_name=name,index=False)
    meta={'date_Japan':'2026-11-06','Sc_reference':'SOEC_ScSZ_design_6.519656872tSc/GW; adoption_unknown','reference':'flow_based; pooled_wind; additive_PV_reference; Fe_plus_Steel_x0.9786; base_plant_plus_incremental_CCS_ASSUMPTION','full40_observed_total_ready':False,'boundary_alternatives':['PV_replacement','without_CCS_increment'],'Sc_alternatives':['Wei_reproduction','YSZ_electrolyte_reference'],'negative_base_minerals':sorted(base.loc[base.negative_base,'mineral'].unique()),'historical_v1_outputs_overwritten':False}
    (out/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print(comparison.loc[comparison.statistic.eq('average')&comparison.sector.isin(['power','stationary_battery'])&comparison.mineral.isin(['Cu','Al','Fe','Li']),['Sc','sector','mineral','old_R_2020_2100_point_sum_t','previous_v1_cumulative_t','revised_cumulative_t']].to_string(index=False))
    print('Negative baseline minerals:',meta['negative_base_minerals'])
    return tables,sensitivity,comparison
if __name__=='__main__':run()
