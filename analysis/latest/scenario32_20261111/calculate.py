"""Explicit assumption cases for 32 minerals, product / recycling / primary accounts.
All references and unobserved shares are assumptions, not fitted or optimized forecasts.
"""
from pathlib import Path
import sys,json,hashlib,copy
import pandas as pd,numpy as np
W=Path(__file__).resolve().parents[1];R=W/'mineral2100';O=Path(__file__).resolve().parent
V=W/'vehicle_allsector_extension_20261111';sys.path.insert(0,str(V));import build as veh
M=['Al','B','Cd','Cr','Co','Cu','Dy','Ga','Ge','Hf','In','Fe','Pb','Li','Mn','Mo','Nd','Ni','Nb','Pr','Se','Si','Ag','Ta','Te','Tb','Sn','W','V','Y','Zn','Zr'];K=len(M);J={m:i for i,m in enumerate(M)}
Y=np.arange(2020,2101);N=len(Y);ALPHA=.5
BASE=dict(name='S1_working',chem='NMC622',large='DAY',li_factor=1.,battery_life=8,storage_hours=12.,vrfb_share=.0,pv_factor=1.,pv_mix='reference',ccs_factor=1.,grid_transformer_Cu=.2,grid_HV_Al=.05,grid_lead_cable_Cu=.01,bus_fcv_pack_kWh=20.,bus_fcv_pack_Whkg=100.,brass_Cu=.7,magnet_Nd=.30,magnet_Dy=.01,legacy=.5,collection_interpretation=False,reuse_fraction=1.,other_future='legacy_intensity',yield_case='source',unreported_recycling_zero=False)
CASES=[BASE,dict(BASE,name='S2_Li_LCE',li_factor=2*6.94/(2*6.94+12.011+3*15.999)),dict(BASE,name='S3_equipment_A',chem='NMC811',battery_life=12,storage_hours=6.,pv_factor=1/1.2,pv_mix='cSi_Cu',ccs_factor=0.,grid_transformer_Cu=.1,grid_HV_Al=.02,grid_lead_cable_Cu=.005,bus_fcv_pack_kWh=10.),dict(BASE,name='S4_equipment_B',large='SLEEP',battery_life=6,vrfb_share=.2,pv_factor=1.2,grid_transformer_Cu=.3,grid_HV_Al=.15,grid_lead_cable_Cu=.05,bus_fcv_pack_kWh=30.,magnet_Nd=.28,magnet_Dy=.03),dict(BASE,name='S5_recovery_alternative',legacy=.25,collection_interpretation=True,reuse_fraction=.8,unreported_recycling_zero=True),dict(BASE,name='S6_other_GDP',other_future='GDP_only'),dict(BASE,name='S7_other_flat',other_future='flat2050'),dict(BASE,name='S8_ideal_yield',yield_case='perfect')]
DATA=R/'update_comparison_20261110/results_updated_native_all_sectors'
old=pd.read_csv(V/'all_sectors_extended_CONDITIONAL.csv.gz');old=old[old['case'].eq('F_E_plus_steel_Fe_proxy')&old.mineral.isin(M)]
inv=pd.read_csv(V/'vehicle_inventory_40_PARTIAL.csv.gz');inv=inv[inv['case'].eq('F_E_plus_steel_Fe_proxy')&inv.mineral.isin(M)]
acts=pd.read_csv(V/'road_activity_annual.csv')
co=pd.read_csv(DATA/'coefficients.csv');co=co[co.statistic.eq('average')&co.mineral.isin(M)]
pa=pd.read_csv(DATA/'power_activity.csv');ba=pd.read_csv(DATA/'battery_native_activity.csv');ha=pd.read_csv(DATA/'hydrogen_native_activity.csv')
pv=pd.read_csv(W/'pv_storage_revision_20261111/PV_technology_coefficients_t_per_GW.csv',index_col=0).reindex(columns=M)
pen=next((R/'originals').glob('Pelotte*/Data'));book=pen/'EV_MI_MS_Recycling.xlsx'
bmi=pd.read_excel(book,sheet_name='MI_Battery',index_col=0);cs=pd.read_csv(R/'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv')
names={'Al': 'Aluminum', 'B': 'Boron', 'Cd': 'Cadmium', 'Cr': 'Chromium', 'Co': 'Cobalt', 'Cu': 'Copper', 'Dy': 'Dysprosium', 'Ga': 'Gallium', 'Ge': 'Germanium', 'Hf': 'Hafnium', 'In': 'Indium', 'Fe': 'Iron', 'Pb': 'Lead', 'Li': 'Lithium', 'Mn': 'Manganese', 'Mo': 'Molybdenum', 'Nd': 'Neodymium', 'Ni': 'Nickel', 'Nb': 'Niobium', 'Pr': 'Praesodymium', 'Se': 'Selenium', 'Si': 'Silicon', 'Ag': 'Silver', 'Ta': 'Tantalum', 'Te': 'Tellurium', 'Tb': 'Terbium', 'Sn': 'Tin', 'W': 'Tungsten', 'V': 'Vanadium', 'Y': 'Yttrium', 'Zn': 'Zinc', 'Zr': 'Zirconium'}
mi_names={m:names[m] for m in M}
parts=pd.read_csv(R/'input/road_vehicle_extension/bus_BEV_selected_materials.csv')
components=pd.read_csv(R/'output/vehicle_completion_v4/component_inventory.csv')
fcvmat=pd.read_csv(R/'output/vehicle_completion_v4/FCV_materials_NOT_elements.csv')
rr=pd.read_excel(pen/'Prod&Demand_Other_Sectors.xlsx',sheet_name='Recovery_Rates',index_col=0).loc[[names[m] for m in M],'RR_Reserve'].to_numpy(float)
P0=pd.read_csv(W/'penelope_constraints2050_20261111/production_original_formula.csv',index_col=0).loc[M,'2020'].to_numpy(float)
rr0=pd.read_excel(book,sheet_name='Recycling_2020_Rates',index_col=0).Initial_Recycling_Rate
rre=pd.read_excel(book,sheet_name='Recycling_Evolution',index_col=0)
# Missing recycling rates are explicit working assumptions, not claims of measured world values.
def recycle_rates():
 out=np.empty((N,K));records=[]
 bulk={'Al':.5,'Fe':.7,'Pb':.6,'Zn':.4,'Sn':.4,'Cr':.4,'Mn':.3,'Mo':.4,'W':.4,'Ni':.4}
 for k,m in enumerate(M):
  name=names[m];initial=float(rr0.get(name,bulk.get(m,.2)));e=rre[(rre.index==name)&rre.SSPs.eq('SSP2')]
  pts={2020:initial,2050:initial};kind='Pene initial' if name in rr0.index else 'analyst assumption'
  if len(e)==1:
   for year in [2028,2032,2050]:pts[year]=float(e.iloc[0][year if year in e.columns else str(year)])
  out[:,k]=np.interp(Y,sorted(pts),[pts[t] for t in sorted(pts)])
  records.append(dict(mineral=m,rate2020=initial,rate2050=float(out[30,k]),source=kind,future='Pene SSP2 where reported; otherwise constant; hold2050 to2100'))
 return out,pd.DataFrame(records)
RATES,RATE_AUDIT=recycle_rates()
def vec(d):return np.array([float(d.get(m,0.)) for m in M])
def matrix(frame,col):return frame.pivot(index='year',columns='mineral',values=col).reindex(index=Y,columns=M).to_numpy(float)
def delayed_retirement(flow,life,legacy):
 """Uniform-age initial stock: historical annual manufacturing=legacy*2020 flow."""
 out=np.zeros_like(flow)
 for i in range(N):out[i]=flow[i-life] if i>=life else legacy*flow[0]
 return out

def _compute_pack(cls,pt,year,c):
 y=min(2100,max(2020,int(year)))
 if cls=='LDV' and pt in ['BEV','PHV']:
  w=cs[cs.year.eq(y)].set_index('Battery_type').share
  kwh=62.5 if pt=='BEV' else 21.8
  v=vec({m:kwh*sum(float(weight)*float(bmi.loc[names[m],chem]) for chem,weight in w.items())/1000 if names[m] in bmi.index else 0. for m in M})
  v[J['Li']]*=c['li_factor'];return v
 if cls=='LDV' and pt=='HEV':
  g=components[components.case.eq('HEV4_sedan_teardown')&components.scope.str.startswith('vehicle.traction_battery')&components.mineral.isin(M)]
  return vec(g.groupby('mineral').quantified_kg_per_vehicle.sum(min_count=1).fillna(0).to_dict())
 if cls in ['TRUCK_SMALL','TRUCK_LARGE'] and pt in ['HEV','BEV','FCV']:
  cl='C6' if cls=='TRUCK_SMALL' else c['large'];d=veh.ANL['classes'][cl];r=d[c['chem']]
  kg=(d['battery_energy_kWh'] if pt=='BEV' else d['battery_power_kW'][pt])*1000/r['specific'][pt]
  vals=veh.battery_recipe(kg,r['recipe'][pt],c['chem'],0)
  f=.1 if pt=='BEV' else (.7 if cl=='C6' or (pt=='HEV' and c['chem']=='NMC811') else .6)
  vals['Fe']=kg*f/100*.9786;return vec(vals)
 if cls=='BUS' and pt=='BEV':
  r=veh.ANL['classes']['C6'][c['chem']];kg=395*1000/r['specific']['BEV']
  return vec(veh.battery_recipe(kg,r['recipe']['BEV'],c['chem'],0))
 if cls=='BUS' and pt in ['HEV','FCV']:
  # High-power NMC111 surrogate, separate auxiliary battery belongs to the body side.
  kg=c['bus_fcv_pack_kWh']*1000/c['bus_fcv_pack_Whkg']
  return vec(veh.battery_recipe(kg,[19,18,18,1,10],'NMC111',0))
 return np.zeros(K)

_PACK_CACHE={}
def pack(cls,pt,year,c):
 key=(cls,pt,min(2100,max(2020,int(year))),c['chem'],c['large'],c['li_factor'],c['bus_fcv_pack_kWh'],c['bus_fcv_pack_Whkg'])
 if key not in _PACK_CACHE:_PACK_CACHE[key]=_compute_pack(cls,pt,year,c)
 return _PACK_CACHE[key]

def bus_additions(pt,c):
 selected=parts if pt in ['BEV','FCV','HEV'] else parts[parts.scope.isin(['body','chassis'])]
 # F already has body/chassis; transfer BEV drive/aux/gearbox exactly once for FCV/HEV.
 b=veh.bus_inventory(pt,dict(veh.PROFILE if hasattr(veh,'PROFILE') else next(p for p in veh.CASE_PROFILES if p['case']=='F_E_plus_steel_Fe_proxy')),parts)
 vals={}
 if pt in ['FCV','HEV']:
  full=veh.bus_inventory('BEV',dict(next(p for p in veh.CASE_PROFILES if p['case']=='F_E_plus_steel_Fe_proxy')),parts)
  # Full BEV minus its traction pack leaves a common electric body/drive surrogate.
  pc=pack('BUS','BEV',2020,dict(BASE))
  vals={m:full.get(m,0)-pc[k]-b.get(m,0) for k,m in enumerate(M)}
  if min(vals.values()) < -1e-7:raise ValueError('Bus surrogate ownership overlap')
 if pt in ['BEV','FCV','HEV']:
  magnet=float(selected.loc[selected.material.eq('Nd_Dy_Fe_B_unsplit'),'kg_per_vehicle'].sum())
  for m,f in {'Nd':c['magnet_Nd'],'Dy':c['magnet_Dy'],'B':.01,'Fe':1-c['magnet_Nd']-c['magnet_Dy']-.01}.items():vals[m]=vals.get(m,0)+magnet*f
  st=float(selected.loc[selected.material.eq('Stainless'),'kg_per_vehicle'].sum())
  for m,f in {'Fe':.74,'Cr':.18,'Ni':.08}.items():vals[m]=vals.get(m,0)+st*f
 if pt in ['FCV','HEV']:
  # Passenger stack+BOP known elements scaled by stack output; only FCV has a stack.
  if pt=='FCV':
   g=components[components.case.eq('FCV_sedan_300_Pt_SFA2019_30g_transfer')&components.scope.eq('vehicle.powertrain.fuel_cell_stack_BOP')&components.mineral.isin(M)]
   for m,v in g.groupby('mineral').quantified_kg_per_vehicle.sum(min_count=1).fillna(0).items():vals[m]=vals.get(m,0)+v*70/114
 # Resolve previously unassigned Cu+brass pools; no second addition of known Cu.
 brass=float(selected.loc[selected.material.isin(['Cu_Brass_unsplit','Brass']),'kg_per_vehicle'].sum())
 vals['Cu']=vals.get('Cu',0)+brass*c['brass_Cu'];vals['Zn']=vals.get('Zn',0)+brass*(1-c['brass_Cu'])
 return vec(vals)

def _compute_vehicle_vectors(c):
 profile=dict(next(p for p in veh.CASE_PROFILES if p['case']=='F_E_plus_steel_Fe_proxy'),chem=c['chem'],large=c['large'])
 vectors={};bodies={};flags=[]
 for cls in ['LDV','BUS','TRUCK_SMALL','TRUCK_LARGE']:
  for pt in ['ICE','HEV','PHV','BEV','FCV']:
   life=12 if cls=='LDV' else 15
   vs=[];bs=[]
   for y in Y:
    whole=_INV_LOOKUP.get((cls,pt,int(y)),np.zeros(K)).copy()
    if cls=='LDV' and pt in ['BEV','PHV']:whole[J['Li']]*=c['li_factor']
    if cls.startswith('TRUCK') and pt in ['ICE','HEV','BEV','FCV']:
     cl='C6' if cls=='TRUCK_SMALL' else c['large'];whole=vec(veh.truck_inventory(cl,pt,profile)[0]);d=veh.ANL['classes'][cl];i=veh.ANL['powertrains'].index(pt)
     kg=(sum(d['fixed_component_lb'])+sum(d['variable_component_lb'][i]))*veh.LB
     pool=kg*d['Cu_brass_pct'][i]/100;whole[J['Cu']]+=pool*c['brass_Cu'];whole[J['Zn']]+=pool*(1-c['brass_Cu'])
    if cls=='BUS' and pt in ['ICE','HEV','BEV','FCV']:
     whole+=bus_additions(pt,c)
     if pt=='BEV':whole+=pack(cls,pt,y,c)-pack(cls,pt,y,BASE)
     elif pt in ['HEV','FCV']:whole+=pack(cls,pt,y,c)
    battery=pack(cls,pt,y,c);body=whole-battery
    if body.min() < -1e-6:raise ValueError(('Battery exceeds whole vehicle',cls,pt,y,M[body.argmin()],body.min()))
    vs.append(whole);bs.append(np.maximum(body,0))
   vectors[cls,pt]=np.array(vs);bodies[cls,pt]=np.array(bs)
 return vectors,bodies

_INV_LOOKUP={(cl,pt,int(y)):vec(g.set_index('mineral').known_kg_per_vehicle.fillna(0).to_dict()) for (cl,pt,y),g in inv.groupby(['vehicle_class','powertrain','year'])}
_VECTOR_CACHE={}
def vehicle_vectors(c):
 key=tuple(c[k] for k in ['chem','large','li_factor','bus_fcv_pack_kWh','bus_fcv_pack_Whkg','brass_Cu','magnet_Nd','magnet_Dy'])
 if key not in _VECTOR_CACHE:_VECTOR_CACHE[key]=_compute_vehicle_vectors(c)
 return _VECTOR_CACHE[key]

_VEHICLE_INITIAL_STOCK={}
def vehicle_flows(sc,c):
 whole,body=vehicle_vectors(c);gross=np.zeros((N,K));retired=np.zeros_like(gross);pack_extra=np.zeros_like(gross)
 initial_stock=np.zeros(K)
 sales=acts[acts.Sc.eq(sc)].set_index(['year','vehicle_class','powertrain']).new_vehicles_year
 for key in whole:
  cls,pt=key;life=12 if cls=='LDV' else 15
  def count(v):return float(sales.get((2020 if v<2020 else v,cls,pt),0))*(c['legacy'] if v<2020 else 1.)
  for vintage in range(2020-life,2101):
   n=count(vintage)
   if not n:continue
   vi=max(0,vintage-2020);b=body[key][vi]
   if vintage>=2020:gross[vintage-2020]+=n*b/1000
   death=vintage+life
   if vintage<2020<=death:initial_stock+=n*b/1000
   if 2020<=death<=2100:retired[death-2020]+=n*b/1000
   initialpack=pack(cls,pt,vintage,c)
   if not initialpack.any():continue
   for installed in range(vintage,death,c['battery_life']):
    # Keep the battery system's capacity fixed; chemistry follows installation-year reference.
    bp=pack(cls,pt,installed,c)
    if 2020<=installed<=2100:
     gross[installed-2020]+=n*bp/1000
     if installed>vintage:pack_extra[installed-2020]+=n*bp/1000
    end=min(installed+c['battery_life'],death)
    if installed<2020<=end:initial_stock+=n*bp/1000
    if 2020<=end<=2100:retired[end-2020]+=n*bp/1000
 _VEHICLE_INITIAL_STOCK[c['name'],sc]=initial_stock
 return gross,retired,pack_extra

def grid(sc,c):
 t=old[old.Sc.eq(sc)];cu=matrix(t,'grid_CuAl_t_year')[:,J['Cu']];al=matrix(t,'grid_CuAl_t_year')[:,J['Al']]
 out=np.zeros((N,K));out[:,J['Cu']]=cu;out[:,J['Al']]=al
 transformer=cu*c['grid_transformer_Cu']/47.5 # t Cu/unit, midpoint of source45–50t
 sea=cu*c['grid_lead_cable_Cu']/27. # cable km with source27tCu/km
 land=cu*(1-c['grid_transformer_Cu']-c['grid_lead_cable_Cu'])/27.
 hv=al*c['grid_HV_Al']/5. # source5tAl/route-km
 remainder=al-hv*5-land*3
 if remainder.min() < -1e-6:raise ValueError('Grid Cu/Al design allocation infeasible')
 galv=hv*97+sea*18
 out[:,J['Zn']]=galv*.005
 out[:,J['Fe']]=galv*.995*.9786+transformer*(130*.97+50*.9786)
 out[:,J['Si']]=transformer*130*.03
 out[:,J['Pb']]=sea*11
 # The remaining Al is an Al land-cable surrogate (16t/km); no added known32 components.
 assert np.allclose(land*27+sea*27+transformer*47.5,cu)
 assert np.allclose(hv*5+land*3+remainder,al)
 return out

def nonvehicle(sc,c):
 flows={};ret=[]
 for tech,g in pa[pa.Sc.eq(sc)].groupby('technology'):
  coeff=co[co.sector.eq('power')&co.technology.eq(tech)].set_index('mineral').intensity.reindex(M).to_numpy()
  rate=g.set_index('year').addition_GW_year.reindex(Y).to_numpy()
  if tech=='SolarPV':
   coeff=(pv.loc['c-Si_Cu'].to_numpy() if c['pv_mix']=='cSi_Cu' else coeff)*c['pv_factor']
  if tech.startswith('CCS_'):coeff=coeff*c['ccs_factor']
  f=rate[:,None]*coeff[None,:];flows['power:'+tech]=f
 storecoef=co[co.sector.eq('stationary_battery')].set_index('mineral').intensity.reindex(M).to_numpy().copy()*c['storage_hours']/12
 for m in ['Li','Co','Mn','Ni']:storecoef[J[m]]*=1-c['vrfb_share']
 # Two V atoms (both half-cells) per transferred electron. Parameters are electrochemical design assumptions.
 vkg_kWh=2*.0509415*3.6e6/(96485.33212*1.26*.8*.85)
 storecoef[J['V']]+=c['storage_hours']*1000*c['vrfb_share']*vkg_kWh
 flows['stationary_battery']=ba[ba.Sc.eq(sc)].set_index('year').addition_GW_year.reindex(Y).to_numpy()[:,None]*storecoef
 hco=co[co.sector.eq('hydrogen')].set_index('mineral').intensity.reindex(M).to_numpy()
 flows['hydrogen']=ha[ha.Sc.eq(sc)].set_index('year').addition_GW_year.reindex(Y).to_numpy()[:,None]*hco
 flows['grid']=grid(sc,c)
 for name,f in flows.items():
  life=30 if name.startswith('power:') else {'stationary_battery':10,'hydrogen':20,'grid':40}[name]
  ret.append(delayed_retirement(f,life,c['legacy']))
 agg={'power':sum(f for k,f in flows.items() if k.startswith('power:')),'stationary_battery':flows['stationary_battery'],'hydrogen':flows['hydrogen'],'grid':flows['grid']}
 stock0=sum((30 if name.startswith('power:') else {'stationary_battery':10,'hydrogen':20,'grid':40}[name])*c['legacy']*f[0] for name,f in flows.items())
 return agg,sum(ret),stock0

def calculate():
 O.mkdir(exist_ok=True);RATES_OUT=[];records=[];baseaudit=[];sectorrows=[];exports=[]
 RATE_AUDIT.to_csv(O/'recycling_rate_assumptions.csv',index=False)
 for c in CASES:
  for sc in ['Baseline','300C']:
   sectors,re,stock0=nonvehicle(sc,c);vg,vr,extras=vehicle_flows(sc,c);sectors['vehicles']=vg;re+=vr
   explicit=sum(sectors.values())
   effective=RATES.copy()
   if c['unreported_recycling_zero']:effective[:,RATE_AUDIT.source.eq('analyst assumption').to_numpy()]=0.
   effective=effective*(.9 if c['collection_interpretation'] else 1.)*c['reuse_fraction']
   # P0 is original source annual production converted by its supplied RR_Prod formula.
   # Hypothesis: it is product-equivalent primary supply. Recycled supply is explicit, not hidden.
   other0=(P0+effective[0]*re[0]-explicit[0])/(1-effective[0]*c['legacy'])
   draw=np.maximum(-other0*(1-effective[0]*c['legacy']),0);other0=np.maximum(other0,0)
   factor=matrix(old[old.Sc.eq(sc)],'growth_factor')
   other=other0[None,:]*factor
   if c['other_future']!='legacy_intensity':
    # GDP ratio implied by original factor divided by its annual intensity trend after2050.
    rate=pd.read_csv(R/'input/imported/penelope_Metal_Intensity_Reduction.csv').iloc[0]
    tail=float(rate['2050']);inten=(1+tail)**((Y-2050)/10)
    for i,y in enumerate(Y):
     if y>2050:other[i]=other[30] if c['other_future']=='flat2050' else other[30]*(factor[i]/factor[30])/inten[i]
   ro=delayed_retirement(other,20,c['legacy']);re+=ro;sectors['other']=other
   gross=explicit+other
   stock0=stock0+_VEHICLE_INITIAL_STOCK[c['name'],sc]+20*c['legacy']*other0
   inuse_stock=stock0+np.cumsum(gross-re,axis=0)
   if inuse_stock.min() < -1e-5:raise ValueError('Negative in-use material stock')
   recovered=re*effective
   inventory=np.zeros(K);used=np.zeros_like(gross);bank=np.zeros_like(gross)
   initial=np.zeros_like(gross);initial[0]=draw
   for i in range(N):
    available=inventory+recovered[i]
    used[i]=np.minimum(np.maximum(gross[i]-initial[i],0),available)
    inventory=available-used[i];bank[i]=inventory
   primary=gross-used-initial
   if primary.min() < -1e-5:raise ValueError('Negative primary requirement')
   yld=np.ones(K) if c['yield_case']=='perfect' else rr
   mine=primary/yld
   np.testing.assert_allclose(primary[0],P0,rtol=1e-10,atol=1e-6)
   np.testing.assert_allclose(gross,primary+used+initial,rtol=1e-12,atol=1e-5)
   np.testing.assert_allclose(bank,np.cumsum(recovered-used,axis=0),rtol=1e-10,atol=1e-5)
   assert np.isfinite(gross).all() and np.isfinite(mine).all() and bank.min()>-1e-6
   for j,m in enumerate(M):baseaudit.append(dict(case=c['name'],Sc=sc,mineral=m,initial_inuse_stock_t=stock0[j],minimum_inuse_stock_t=inuse_stock[:,j].min(),source_primary_product_proxy=P0[j],explicit2020=explicit[0,j],other2020=other0[j],secondary2020=used[0,j],initial_inventory_draw2020=draw[j],baseline_closure_error=float(gross[0,j]-P0[j]-used[0,j]-draw[j])))
   for i,y in enumerate(Y):
    for j,m in enumerate(M):
     records.append(dict(case=c['name'],Sc=sc,year=int(y),mineral=m,gross_product_t=gross[i,j],recovered_available_t=recovered[i,j],secondary_used_t=used[i,j],initial_inventory_draw_t=initial[i,j],primary_product_equivalent_t=primary[i,j],mine_contained_element_t=mine[i,j],secondary_inventory_t=bank[i,j],extra_traction_battery_t=extras[i,j]))
     sectorrows.append(dict(case=c['name'],Sc=sc,year=int(y),mineral=m,**{k:float(f[i,j]) for k,f in sectors.items()}))
   print(c['name'],sc,'computed; inventory-draw elements',','.join(np.array(M)[draw>1e-6]),flush=True)
 allannual=pd.DataFrame(records);allsectors=pd.DataFrame(sectorrows);base=pd.DataFrame(baseaudit)
 allannual.to_csv(O/'annual32_all_cases.csv.gz',index=False);allsectors.to_csv(O/'sectors32_all_cases.csv.gz',index=False);base.to_csv(O/'baseline32_accounting_audit.csv',index=False)
 cumulative=[]
 keys=['case','Sc','mineral'];values=[x for x in allannual if x not in keys+['year','secondary_inventory_t']]
 for end in [2050,2100]:
  d=allannual[allannual.year.le(end)].groupby(keys,as_index=False)[values].sum();d['start']=2020;d['end']=end
  s=allsectors[allsectors.year.le(end)].groupby(keys,as_index=False)[list(sectors)].sum();d=d.merge(s,on=keys,validate='one_to_one');cumulative.append(d)
 cu=pd.concat(cumulative,ignore_index=True);cu.to_csv(O/'cumulative32_all_cases.csv',index=False)
 pd.DataFrame(CASES).to_csv(O/'scenario_parameters.csv',index=False)
 assumptions=pd.DataFrame([
 ('Li','S1はPénélope表のLiを元素量として使用。S2だけ乗用BEV/PHEVの電池Liを炭酸Li量とみなして0.18786倍。トラック等の化学式から計算したLiは換算しない。原典の確定ではない。'),
 ('供給会計','Pénélope元コードの2020生産量を製品相当の一次供給と仮定し、明示需要＋残余＝一次＋推計再生＋必要時在庫取り崩し、で基準年を解く。元データが製品相当であるとの実証は未完了。'),
 ('歴史在庫','2020以前の年次製造を2020製造の50%（S5は25%）とし、寿命内で均等な年齢構成。実際の過去在庫を観測したものではない。'),
 ('リサイクル','既存率はS1で回収・再生工程込みの実効率と仮定。S5では回収率と解釈して再生歩留90%を掛け、利用可能率80%を追加。既知SSP2は2050以降固定。不明元素は監査表に示す仮定率。S5では不明元素の回収率を0と仮定する。'),
 ('工程損失','一次製品相当必要量をRR_Reserveで一度だけ割り、採掘原料中の元素相当量を算出。鉱石全体の重さではない。製造歩留をさらに重ね掛けしない。S8のみ理想歩留100%。'),
 ('車両・電池寿命','乗用12年、バス貨物15年。車両の新設・更新VR+VPに寿命更新を再加算せず、退役と電池単独交換の時期だけに寿命を使う。電池8年を標準、6/12年を比較。初期電池と交換電池を退役時に二重計上しない。'),
 ('車両代理','Cu+BrassをCu70%/Zn30%、未分解磁石をNd30%/Dy1%/B1%/Fe68%、StainlessをFe74%/Cr18%/Ni8%とする。測定値ではなく組成代理。C4ではNd28%/Dy3%。他の合金残分は未知のまま。'),
 ('バスFCV','BEVの車体を重ねず、モーター・制御器・補機の既知分を転用。燃料電池スタックBOPの既知32元素を乗用114kW→バス70kW比例で補う。駆動電池20kWh/100Whkgを仮定、10/30kWhも比較。'),
 ('送配電','Cu/Al量を保存し、Cu20%を変圧器、Cu1%を鉛被覆海底ケーブル、Al5%を高圧架空線へ配分してFe/Si/Pbを導出。亜鉛めっきは質量0.5%。資産構成は世界統計ではなく仮定。低高配分をS3/S4で比較。'),
 ('VRFB','S4でAIM電力容量×12hの20%をVRFBエネルギーと仮定。Li/Co/Mn/Niを置換し、Cu/Al/Fe等を共通設備代理として保持。Vは両半電池のFaraday式、1.26V、SOC利用80%、放電効率85%から約4.44kgV/kWh。設備・採用率の実測値ではない。'),
 ('蓄電時間','12hを基準、S3は6hの等価設備量。AIM制約パラメータと実電池パックの容量が同じか未確定。'),
 ('PV・CCS','PVは元係数を基準。S3は容量係数1/1.2かつcSi銅方式、S4は容量係数1.2。CCSは標準で増分全量、S3で完全重複端点として増分0。ゼロはCCS装置が不要という主張ではない。'),
 ('その他部門','各ケースで2020残余を再校正。不明成分は残余に含める仮定。2050以降は標準でGDP＋既存強度変化、S6はGDPだけ、S7は2050需要固定。未収録技術部材も同じ経路とする近似。'),
 ('ケース差の解釈','回収条件を変えるケースでは、同じ一次供給量に対応する2020総利用量とその他部門も再推計する。ケース差をそのまま回収政策の純効果と呼ばない。同一製品需要で回収控除する/しない比較を別シートに収録。'),('最適化なし','AIMの活動量を固定した仮定ケース計算。ケースは信頼区間・確率・上下限ではなく、互いに加算しない。'),
 ('32鉱物','C/La/Ce/Mg/Ti/Sc/Pt/Irは保留。未知成分を測定ゼロと断定せず、採用仮定で数値を閉じた条件付き結果。埋蔵量の欠損や限定範囲は需要仮定で解消しない。')
 ],columns=['項目','採用した仮定と意味'])
 assumptions.to_csv(O/'assumptions32.csv',index=False)
 selected=allannual[allannual.year.isin([2020,2030,2050,2100])].copy()
 main=allannual[allannual['case'].eq('S1_working')][['Sc','year','mineral','gross_product_t','secondary_used_t','primary_product_equivalent_t','mine_contained_element_t']]
 recycling_effect=cu[cu['case'].eq('S1_working')][['Sc','mineral','start','end','gross_product_t','primary_product_equivalent_t','mine_contained_element_t']].copy()
 recycling_effect['primary_product_without_recycling_t']=recycling_effect.gross_product_t
 recycling_effect['mine_element_without_recycling_t']=[row.gross_product_t/rr[J[row.mineral]] for row in recycling_effect.itertuples()]
 overview=cu[(cu['case']=='S1_working')&(cu.end==2100)][['Sc','mineral','gross_product_t','secondary_used_t','primary_product_equivalent_t','mine_contained_element_t']].copy()
 for col in overview.columns[2:]:overview[col]/=1e6
 overview=overview.rename(columns={col:col.replace('_t','_Mt') for col in overview.columns[2:]})
 labels={'case':'ケース','Sc':'AIMシナリオ','mineral':'鉱物','year':'年','start':'開始年','end':'終了年','gross_product_t':'製品に必要な量_t','secondary_used_t':'うち再生材使用量_t','recovered_available_t':'再利用可能量_t','primary_product_equivalent_t':'新規一次材料必要量_t','mine_contained_element_t':'採掘段階の元素換算量_t','initial_inventory_draw_t':'仮定上の期首在庫使用_t','extra_traction_battery_t':'電池単独交換需要_t','power':'発電_t','stationary_battery':'定置蓄電池_t','hydrogen':'水素製造_t','grid':'送配電網_t','vehicles':'車両_t','other':'その他経済部門_t','gross_product_Mt':'製品に必要な量_Mt','secondary_used_Mt':'うち再生材使用量_Mt','primary_product_equivalent_Mt':'新規一次材料必要量_Mt','mine_contained_element_Mt':'採掘段階の元素換算量_Mt','primary_product_without_recycling_t':'回収控除なしの一次必要量_t','mine_element_without_recycling_t':'回収控除なし採掘段階換算量_t'}
 ref=pd.read_csv(R/'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv')
 ref=ref[ref.mineral.isin(M)].copy()
 assert ref.mineral.nunique()==32 and ref.comparison_reference_t_element.notna().all()
 penref=pd.read_excel(pen/'Prod&Demand_Other_Sectors.xlsx',sheet_name='Reserves_Resources',index_col=0)
 ref['Penelope_Reserves_t']=[penref.loc[names[m],'Reserves'] for m in ref.mineral]
 ref['Penelope_Resources_t']=[penref.loc[names[m],'Resources'] for m in ref.mineral]
 ref=ref[['mineral','comparison_reference_t_element','reference_class','geography','scope','source_url','extended_assumption','Penelope_Reserves_t','Penelope_Resources_t']]
 ref['注意']='補完ケースは32枠の参照量。Ge/Hf/Si/Taは条件付き。欠損を無限供給と解釈しない。'
 ytable=pd.DataFrame({'mineral':M,'鉱山から製品までの換算係数_RRReserve':rr,'理想工程ケース':np.ones(K)})
 with pd.ExcelWriter(O/'scenario32_results.xlsx',engine='xlsxwriter') as w:
  for name,d in [('最初に読む',assumptions),('標準2100累積_Mt',overview),('ケース設定',pd.DataFrame(CASES)),('全部門累積_t',cu),('主要年年次_t',selected),('2020収支_t',base),('回収率設定',RATE_AUDIT),('同一製品需要_回収効果_t',recycling_effect),('一次換算係数',ytable),('埋蔵量等の参照候補',ref)]:
   d.rename(columns=labels).to_excel(w,sheet_name=name,index=False);ws=w.sheets[name];ws.freeze_panes(1,0);ws.autofilter(0,0,len(d),len(d.columns)-1);ws.set_column(0,len(d.columns)-1,20)
  w.sheets['最初に読む'].set_column(1,1,120)
 verification={'cases':len(CASES),'scenarios':['Baseline','300C'],'minerals':M,'years':[2020,2100],'annual_rows':len(allannual),'baseline_primary_matches_source_proxy':True,'annual_balance_verified':True,'secondary_inventory_balance_verified':True,'in_use_stock_nonnegative':True,'negative_demand':False,'assumptions_not_empirical_estimates':True,'whole_inventory_complete':False}
 inputs=[Path(__file__),V/'all_sectors_extended_CONDITIONAL.csv.gz',V/'vehicle_inventory_40_PARTIAL.csv.gz',V/'road_activity_annual.csv',V/'truck_reference.json',DATA/'coefficients.csv',DATA/'power_activity.csv',DATA/'battery_native_activity.csv',DATA/'hydrogen_native_activity.csv',R/'input/imported/battery_chemistry_shares_2020_2100_ASSUMPTION.csv',R/'input/imported/penelope_Metal_Intensity_Reduction.csv',W/'pv_storage_revision_20261111/PV_technology_coefficients_t_per_GW.csv',R/'input/road_vehicle_extension/bus_BEV_selected_materials.csv',R/'output/vehicle_completion_v4/component_inventory.csv',R/'output/vehicle_completion_v4/FCV_materials_NOT_elements.csv',W/'penelope_constraints2050_20261111/production_original_formula.csv',book,pen/'Prod&Demand_Other_Sectors.xlsx',R/'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv']
 verification['input_sha256']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
 (O/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2))
 print('Excel bytes',(O/'scenario32_results.xlsx').stat().st_size)
 print(overview[overview.mineral.isin(['Cu','Li','Ni','Co','V'])].to_string(index=False))
if __name__=='__main__':calculate()
