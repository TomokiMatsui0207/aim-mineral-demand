"""Validate private prepared inputs, then run the conditional v6 integration."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
REQUIRED=[
 'input/AIM_World.csv.gz',
 'input/units_and_time_basis.csv',
 'input/imported/wei_intensity_rows.csv',
 'input/imported/wei_S11_Market_share.csv',
 'input/imported/penelope_Demand_Network.csv',
 'input/imported/penelope_Metal_Intensity_Reduction.csv',
 'input/energy_unit_check/energy_drivers_Baseline.csv',
 'input/energy_unit_check/energy_drivers_300C.csv',
 'output/native_vehicle_demand_two_scenarios/alternative_HEV_combined_partial_demand.csv',
 'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv',
 'output/solar_overlap_v5/baseline2020_recalibration.csv',
 'output/solar_overlap_v5/explicit_sector_annual.csv',
 'originals/Pelotte*/Data/PowerCap_MI_MS_CF.xlsx',
 'originals/Pelotte*/Data/Market Share in time - Disag.xlsx',
]
def check_inputs():
    matched={};missing=[]
    for pattern in REQUIRED:
        hits=sorted(p for p in ROOT.glob(pattern) if p.is_file())
        if len(hits)==1:matched[pattern]=hits[0]
        elif not hits:missing.append(pattern)
        else:raise ValueError('Ambiguous input: '+pattern)
    return matched,missing
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    p.add_argument('--metadata',type=Path,default=ROOT/'config/run_metadata.local.json')
    a=p.parse_args();files,missing=check_inputs()
    if missing:
        print('Required private inputs are missing:\n'+'\n'.join('  '+s for s in missing))
        return 2
    if a.check:print('All prepared input files are present.');return 0
    if not a.metadata.is_file():print('Create config/run_metadata.local.json from the example.');return 2
    meta=json.loads(a.metadata.read_text())
    if any(not meta.get(k) for k in ['aim_parent_commit','aim_core_commit','aim_data_commit','source_output_id']):
        print('Record the actual AIM/data/output versions before running.');return 2
    # The legacy reader chooses the first matching workbook; preflight above refuses ambiguity.
    import reconcile_wind_ree_v6 as pipeline
    pipeline.run()
    sha=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    dirty=subprocess.run(['git','-C',str(ROOT),'status','--porcelain'],capture_output=True,text=True)
    meta['analysis_commit']=sha.stdout.strip() if sha.returncode==0 else 'uncommitted-local-copy'
    meta['analysis_worktree_dirty']=bool(dirty.stdout.strip()) if dirty.returncode==0 else True
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()
    meta['input_hashes']={str(v.relative_to(ROOT)):digest(v) for v in files.values()}
    (pipeline.OUT/'run_provenance.json').write_text(json.dumps(meta,indent=2))
    return 0
if __name__=='__main__':sys.exit(main())
