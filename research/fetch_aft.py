"""Download only the non-demographic AFT tables needed for validation.

Ke et al. (2022), doi:10.1038/s41597-022-01578-x; data CC BY 4.0.
Files stay outside git. Downloads are verified against the published checksum.
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1] / 'data/research/aft'
RECORD = 'https://zenodo.org/api/records/4917086'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    record = httpx.get(RECORD, follow_redirects=True, timeout=60).raise_for_status().json()
    files = [f for f in record['files'] if f['key'] in {'mentorship.csv.gz', 'researcher.csv.gz', 'authorship.csv.gz'}]
    (ROOT / 'manifest.json').write_text(json.dumps({'record': RECORD, 'license': record['metadata']['license'],
                                                  'files': files}, indent=2))
    def download(f):
        path = ROOT / f['key']
        expected = f['checksum'].split(':', 1)[1]
        if path.exists() and hashlib.md5(path.read_bytes()).hexdigest() == expected:
            print(f['key'], 'verified cache', flush=True); return
        temp = path.with_suffix('.part')
        prefix = temp.stat().st_size if temp.exists() else 0
        chunks = [(start, min(start + 4 * 1024 * 1024, f['size']) - 1)
                  for start in range(prefix, f['size'], 4 * 1024 * 1024)]
        def segment(bounds):
            start, end = bounds
            part = ROOT / (f['key'] + '.' + str(start) + '.segment')
            if part.exists() and part.stat().st_size == end - start + 1:
                return part
            for attempt in range(3):
                try:
                    response = httpx.get(f['links']['self'], headers={'Range': f'bytes={start}-{end}'},
                                         follow_redirects=True, timeout=120)
                    response.raise_for_status()
                    if response.status_code != 206 or len(response.content) != end - start + 1:
                        raise ValueError('Server did not honor byte range')
                    part.write_bytes(response.content)
                    return part
                except (httpx.HTTPError, ValueError):
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
        with ThreadPoolExecutor(max_workers=8) as pool:
            segments = list(pool.map(segment, chunks))
        with temp.open('ab') as out:
            for part in segments:
                out.write(part.read_bytes()); part.unlink()
        if hashlib.md5(temp.read_bytes()).hexdigest() != expected:
            raise ValueError('Checksum mismatch: ' + f['key'])
        temp.replace(path)
        print(f['key'], path.stat().st_size, 'verified', flush=True)
    for f in sorted(files, key=lambda f: f['size']):
        download(f)


if __name__ == '__main__':
    main()
