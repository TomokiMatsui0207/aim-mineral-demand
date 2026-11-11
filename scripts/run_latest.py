"""Run a declared latest code stage with private inputs and local provenance."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,runpy,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/'analysis/latest'
CASES=['pv_only','pv_plus_IEA_storage','pv_plus_IEA_storage_retrospective2021']

def check_inputs(spec,root=SNAPSHOT):
    missing=[];ambiguous=[];found={}
    for pattern in spec.get('required',[]):
        hits=sorted(p for p in root.glob(pattern) if p.is_file())
        if len(hits)==1:found[pattern]=hits[0]
        elif not hits:missing.append(pattern)
        else:ambiguous.append(pattern)
    return found,missing,ambiguous

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--stage')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--case',choices=CASES,default='pv_only')
    parser.add_argument('--metadata',type=Path,default=ROOT/'config/run_metadata.local.json')
    args=parser.parse_args(argv)
    stages=json.loads((ROOT/'config/latest_stages.json').read_text())['stages']
    if args.list:
        for name,spec in stages.items():print(f"{name}: {spec['description']}")
        return 0
    if args.stage not in stages:parser.error('Select --stage from '+', '.join(stages))
    spec=stages[args.stage];entry=SNAPSHOT/spec['entry']
    found,missing,ambiguous=check_inputs(spec)
    for title,patterns in [('Missing private inputs',missing),('Ambiguous private inputs',ambiguous)]:
        if patterns:print(title+':\n'+'\n'.join('  '+x for x in patterns))
    if missing or ambiguous:return 2
    if args.check:
        print('Listed input paths are present and unique; numeric/source validation is not implied.')
        print(spec.get('preflight_scope','Settings may reference additional private source files.'))
        return 0
    if not args.metadata.is_file():print('Create config/run_metadata.local.json from its example.');return 2
    meta=json.loads(args.metadata.read_text())
    required=['aim_parent_commit','aim_core_commit','aim_data_commit','source_output_id']
    if any(not meta.get(k) for k in required):print('Record actual input-producing AIM/core/data commits and output ID.');return 2
    if args.stage=='pv-revision':os.environ['REVISION_CASE']=args.case
    # Stage scripts keep their original file layout and local imports.
    for folder in reversed([entry.parent,SNAPSHOT,SNAPSHOT/'mineral2100',SNAPSHOT/'mineral2100/update_comparison_20261110']):sys.path.insert(0,str(folder))
    def git(*cmd):
        r=subprocess.run(['git','-C',str(ROOT),*cmd],capture_output=True,text=True)
        return r.stdout.strip() if r.returncode==0 else None
    meta.update(stage=args.stage,case=args.case if args.stage=='pv-revision' else None,analysis_commit=git('rev-parse','HEAD'),analysis_worktree_dirty=bool(git('status','--porcelain')),entry=str(entry.relative_to(ROOT)),command=sys.argv,python=sys.version,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),input_hashes={})
    # Include declared external code/workbooks even if their extension is .py.
    for path in found.values():
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        meta['input_hashes'][str(path.relative_to(SNAPSHOT))]=h.hexdigest()
    recording=True;hashing=False
    def audit(event,event_args):
        nonlocal hashing
        if not recording or hashing or event!='open':return
        filename,mode,flags=event_args
        if not isinstance(filename,(str,bytes,os.PathLike)):return
        if isinstance(mode,str) and any(x in mode for x in 'wax+'):return
        if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR):return
        try:
            path=Path(os.fsdecode(filename)).absolute()
            relative=path.relative_to(SNAPSHOT)
        except (ValueError,TypeError,OSError):return
        if path.suffix in {'.py','.pyc'} or str(relative) in meta['input_hashes'] or not path.is_file():return
        hashing=True
        try:
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            meta['input_hashes'][str(relative)]=h.hexdigest()
        finally:hashing=False
    sys.addaudithook(audit)
    result=0
    try:runpy.run_path(str(entry),run_name='__main__');meta['status']='completed'
    except SystemExit as exc:
        result=exc.code if isinstance(exc.code,int) else (0 if exc.code is None else 1)
        meta['status']='completed' if result==0 else 'failed'
    except Exception as exc:
        meta['status']='failed';meta['error']=repr(exc);raise
    finally:
        recording=False
        meta['finish_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        dest=ROOT/'local_run/latest';dest.mkdir(parents=True,exist_ok=True)
        path=dest/(args.stage+'_'+uuid.uuid4().hex[:10]+'.json')
        path.write_text(json.dumps(meta,ensure_ascii=False,indent=2));print('Local provenance:',path)
    return result
if __name__=='__main__':sys.exit(main())
