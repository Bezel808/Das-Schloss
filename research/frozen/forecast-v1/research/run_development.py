"""Resume the declared eight-cohort development pipeline without unlocking holdout."""
import argparse
import subprocess
import sys
from pathlib import Path
from temporal_benchmark import run, ROOT, PROJECT
from forecast_ml import run as train

COHORTS=[('coauth-DBLP',[2000,2002,2004,2006,2008]),('coauth-MAG-History',[2004,2006,2008])]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['all','graph','audit','ml','candidate','holdout','publish'],default='all')
    phase=parser.parse_args().phase
    if phase in ['all','graph']:
        for dataset,years in COHORTS:
            for year in years:run(dataset,year,512,42)
    if phase in ['all','audit']:
        for name in ['audit_temporal.py','verify_development.py','analyze_acquisition.py','error_decomposition.py']:
            subprocess.run([sys.executable,str(Path(__file__).with_name(name))],cwd=PROJECT,check=True)
    if phase in ['all','ml']:
        suffix='-n512-s42-author-query-cn-3-unique-incidence-1-tie-expectation-1'
        train([ROOT/'runs'/f'coauth-DBLP-{year}{suffix}' for year in [2004,2006]],ROOT/'runs'/f'coauth-DBLP-2008{suffix}')
    if phase in ['all','candidate']:
        subprocess.run([sys.executable,str(Path(__file__).with_name('candidate_benchmark.py'))],cwd=PROJECT,check=True)
    if phase in ['all','holdout']:
        subprocess.run([sys.executable,str(Path(__file__).with_name('frozen_forecast.py'))],cwd=PROJECT,check=True)
    if phase in ['all','publish']:
        subprocess.run([sys.executable,str(Path(__file__).with_name('publish_local_results.py'))],cwd=PROJECT,check=True)
