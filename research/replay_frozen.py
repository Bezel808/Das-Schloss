"""Recompute immutable experiments in an empty workspace, isolated from live code."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PROJECT=Path(__file__).resolve().parents[1]


def replay(suite='holdout'):
    snapshot=PROJECT/'research/frozen/forecast-v1'
    manifest=json.loads((snapshot/'manifest.json').read_text())
    for path,expected in manifest['files_sha256'].items():
        if hashlib.sha256((snapshot/path).read_bytes()).hexdigest()!=expected:raise ValueError('Snapshot changed: '+path)
    environment=json.loads((snapshot/'research/environment.json').read_text())
    if '.'.join(map(str,sys.version_info[:3]))!=environment['python']:raise ValueError('Use the pinned Python '+environment['python'])
    for package,version in environment['packages'].items():
        if importlib.metadata.version(package)!=version:raise ValueError('Install requirements.lock before exact replay: '+package)
    protocol=json.loads((snapshot/'research/protocols/frozen-forecast-v1.json').read_text())
    protocol_hash=hashlib.sha256((snapshot/'research/protocols/frozen-forecast-v1.json').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='das-schloss-replay-') as tmp:
        root=Path(tmp);shutil.copytree(snapshot,root,dirs_exist_ok=True)
        data=root/'data/research/temporal';data.mkdir(parents=True)
        (root/'research/results').mkdir(exist_ok=True)
        (root/'scholartrace/static').mkdir(exist_ok=True)
        for dataset in protocol['datasets']:
            original=PROJECT/'data/research/temporal'/(dataset+'.npz')
            if not original.exists():raise ValueError('Download and prepare the source data first: '+dataset)
            if hashlib.sha256(original.read_bytes()).hexdigest()!=protocol['source_sha256'][dataset]:raise ValueError('Source changed')
            # Only immutable input arrays are linked. Indexes, feature caches and
            # every author result must be rebuilt inside this empty workspace.
            (data/original.name).symlink_to(original)
        entry='research/run_development.py' if suite=='all' else 'research/frozen_forecast.py'
        launcher="""import sys,runpy
from pathlib import Path
root=Path.cwd();sys.path[:0]=[str(root/'research'),str(root)]
import scholartrace.acquisition as acquisition
assert Path(acquisition.__file__).resolve().is_relative_to(root)
sys.argv=[sys.argv[1]]
runpy.run_path(str(root/sys.argv[0]),run_name='__main__')
"""
        subprocess.run([sys.executable,'-I','-c',launcher,entry],cwd=root,check=True)
        stage_checks={}
        if suite=='all':
            development_states=candidate_rows=0
            for path in sorted((root/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json')):
                regenerated=json.loads(path.read_text());original=json.loads((PROJECT/'research/results'/path.name).read_text())
                for key in ['protocol','summary']:
                    if original[key]!=regenerated[key]:raise AssertionError('Development summary mismatch: '+path.name+' '+key)
                for fresh in (root/regenerated['rows_path']).glob('author-*.json'):
                    old=json.loads((PROJECT/original['rows_path']/fresh.name).read_text());new=json.loads(fresh.read_text())
                    # Wall time is intentionally measured again, not deterministic.
                    for row in old+new:row.pop('elapsed_seconds')
                    if old!=new:raise AssertionError('Development state mismatch: '+fresh.name)
                    development_states+=len(new)
            for path in sorted((root/'research/results').glob('candidate-coauth-*-observed-ppr-1.json')):
                regenerated=json.loads(path.read_text());original=json.loads((PROJECT/'research/results'/path.name).read_text())
                if original['summary']!=regenerated['summary']:raise AssertionError('Candidate summary mismatch: '+path.name)
                for fresh in (root/regenerated['rows_path']).glob('author-*.json'):
                    old=json.loads((PROJECT/original['rows_path']/fresh.name).read_text());new=json.loads(fresh.read_text())
                    if old!=new:raise AssertionError('Candidate state mismatch: '+fresh.name)
                    candidate_rows+=len(new)
            ml_name='forecast-ml-coauth-DBLP-2008-tie-expectation-1.json'
            original=json.loads((PROJECT/'research/results'/ml_name).read_text())
            regenerated=json.loads((root/'research/results'/ml_name).read_text())
            if original!=regenerated:raise AssertionError('Retrained ML model or evaluation differs')
            if development_states!=143360 or candidate_rows!=98304:raise AssertionError('Incomplete stage comparison')
            stage_checks={'development_states_compared':development_states,'candidate_rows_compared':candidate_rows,
                          'exact_development_metrics_and_queries':True,'exact_candidate_metrics':True,
                          'exact_retrained_ml_models_sampling_and_evaluation':True,
                          'ignored_nondeterministic_fields':['development elapsed_seconds','process peak RSS','derived report hashes containing measurements']}
        original_folder=PROJECT/'data/research/temporal/holdout'/protocol_hash[:16]
        fresh_folder=data/'holdout'/protocol_hash[:16]
        count=0
        for path in fresh_folder.glob('*/author-*.json'):
            old=json.loads((original_folder/path.relative_to(fresh_folder)).read_text());new=json.loads(path.read_text())
            for key in ['query_log','metrics','walk_diagnostics','gold_new_seen','gold_new_cold']:
                if old[key]!=new[key]:raise AssertionError(f'Replay mismatch: {path.parent.name}/{path.name} {key}')
            count+=1
        expected=protocol['targets']*len(protocol['datasets'])*sum(len(v) for v in protocol['stages'].values())
        if count!=expected:raise AssertionError('Replay omitted a declared target')
        original=json.loads((PROJECT/'research/results/frozen-forecast-v1.json').read_text())
        regenerated=json.loads((root/'research/results/frozen-forecast-v1.json').read_text())
        if original!=regenerated:raise AssertionError('Holdout summary differs')
        result={'suite':suite,'protocol_sha256':protocol_hash,'recomputed_target_years':count,
                'reused_author_checkpoints':0,'exact_query_logs':True,'exact_all_method_metrics':True,
                'exact_numerical_diagnostics':True,'exact_holdout_summary':True,
                'live_code_imported':False,'environment':environment,
                'snapshot_manifest_sha256':hashlib.sha256((snapshot/'manifest.json').read_bytes()).hexdigest()}
        result['additional_stage_checks']=stage_checks
        dest=PROJECT/'research/results'/f'frozen-replay-{suite}.json'
        dest.write_text(json.dumps(result,indent=2)+'\n')
        print('Independent empty-workspace replay passed:',count,'target-years; no old checkpoints reused',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--suite',choices=['holdout','all'],default='holdout')
    replay(parser.parse_args().suite)
