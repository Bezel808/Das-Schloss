"""Parse original event arrays; keep author IDs and timestamps exactly as supplied."""
import hashlib
import json
from pathlib import Path
import tarfile
import numpy as np
from fetch_temporal import file_sha256
ROOT=Path(__file__).resolve().parents[1]/'data/research/temporal'

def prepare(name):
 archive=ROOT/(name+'.tar.gz'); arrays={}
 with tarfile.open(archive,'r:gz') as source:
  for member in source:
   for kind in ['times','nverts','simplices']:
    if member.name.endswith('-'+kind+'.txt'):
     arrays[kind]=np.fromstring(source.extractfile(member).read().decode('ascii'),sep=' ',dtype=np.int64)
 if set(arrays)!={'times','nverts','simplices'}:raise ValueError('Missing arrays')
 times,nverts,vertices=(arrays[k] for k in ['times','nverts','simplices'])
 if len(times)!=len(nverts) or nverts.sum()!=len(vertices) or nverts.min()<1 or nverts.max()>25:raise ValueError('Invalid event sizes')
 offsets=np.r_[0,np.cumsum(nverts)]
 # Data order is not chronological. Preserve event identity and provide a stable
 # year sort; annual experiments batch tied events, never use within-year order.
 order=np.argsort(times,kind='stable')
 np.savez_compressed(ROOT/(name+'.npz'),times=times.astype(np.int32),nverts=nverts.astype(np.int16),
                     vertices=vertices.astype(np.int32),offsets=offsets,year_order=order.astype(np.int32))
 years,counts=np.unique(times,return_counts=True)
 report={'dataset':name,'events':len(times),'nodes':len(np.unique(vertices)),
         'incidences':len(vertices),'min_team':int(nverts.min()),'max_team':int(nverts.max()),
         'year_counts':{str(y):int(c) for y,c in zip(years,counts)},
         'source_sha256':json.loads(archive.with_suffix('.json').read_text())['sha256'],
         'processed_sha256':file_sha256(ROOT/(name+'.npz'))}
 dest=Path(__file__).resolve().parent/'temporal-data-manifest.json'
 manifest=json.loads(dest.read_text()) if dest.exists() else {}
 manifest[name]=report;dest.write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='year_counts'}),flush=True)

if __name__=='__main__':
 for name in ['coauth-DBLP','coauth-MAG-History']:
  if (ROOT/(name+'.tar.gz')).exists():prepare(name)
