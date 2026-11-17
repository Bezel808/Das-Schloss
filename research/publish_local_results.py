"""Publish measured development summaries into the local app; never promote a model."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
reports=[]
for file in sorted((ROOT/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json')):
    result=json.loads(file.read_text())
    reports.append({'file':str(file.relative_to(ROOT)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                    'dataset':result['protocol']['dataset'],'cutoff':result['protocol']['cutoff'],
                    'targets':result['protocol']['targets'],'summary':result['summary'],
                    'metric_version':result['protocol']['metric_version'],
                    'limitations':result['limitations']})
ml=json.loads((ROOT/'research/results/forecast-ml-coauth-DBLP-2008-tie-expectation-1.json').read_text())
artifact={'status':'development_only','message':'开发实验尚未证明稳定优于简单基线，最终时间留出尚未执行。',
          'reviews':json.loads((ROOT/'research/reviews/scoreboard.json').read_text()),
          'acquisition':reports,
          'ml':{'training_cutoffs':[p['cutoff'] for p in ml['protocols'][:-1]],'evaluation_cutoff':ml['protocols'][-1]['cutoff'],
                'evaluation_targets':ml['protocols'][-1]['targets'],'metric_version':ml.get('metric_version'),
                'summaries':{name:r['summary'] for name,r in ml['results'].items()},'limitations':ml['limitations']},
          'paired_intervals':json.loads((ROOT/'research/results/acquisition-paired-tie-development.json').read_text())}
if len(reports)!=8:raise ValueError('The declared eight development cohorts must all finish before publication')
artifact['normalization_audit']=json.loads((ROOT/'research/results/temporal-normalization-audit.json').read_text())
artifact['verification']=json.loads((ROOT/'research/results/development-verification.json').read_text())
artifact['error_decomposition']=json.loads((ROOT/'research/results/collaboration-error-decomposition.json').read_text())
artifact['candidate_ablation']=[json.loads(p.read_text()) for p in sorted((ROOT/'research/results').glob('candidate-coauth-*-observed-ppr-1.json'))]
if len(artifact['candidate_ablation'])!=8:raise ValueError('Candidate ablation must finish all eight cohorts')
artifact['holdout']=json.loads((ROOT/'research/results/frozen-forecast-v1.json').read_text())
if len(artifact['holdout']['reports'])!=10:raise ValueError('All declared validation and test cohorts must finish')
artifact['status']='development_and_frozen_temporal_holdout'
artifact['message']='已完成开发实验与固定参数后的独立时间留出。预测合作表现不等于师生身份、学位或晋升判断。'
artifact['holdout_aggregate']=json.loads((ROOT/'research/results/frozen-forecast-aggregate.json').read_text())
artifact['frozen_snapshot_manifest']=json.loads((ROOT/'research/frozen/forecast-v1/manifest.json').read_text())
artifact['holdout_costs']=json.loads((ROOT/'research/results/frozen-forecast-costs.json').read_text())
replay=ROOT/'research/results/frozen-replay-holdout.json'
if replay.exists():artifact['independent_replay']=json.loads(replay.read_text())
full_replay=ROOT/'research/results/frozen-replay-all.json'
if full_replay.exists():artifact['independent_full_pipeline_replay']=json.loads(full_replay.read_text())
destination=ROOT/'scholartrace/static/experiments.json'
destination.with_suffix('.tmp').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
destination.with_suffix('.tmp').replace(destination)
print('Published measured development summaries; production models unchanged.')
