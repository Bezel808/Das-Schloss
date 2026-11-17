import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from . import analyze


def main():
    parser = argparse.ArgumentParser(description='Build an evidence-linked scholar timeline from OpenAlex JSON.')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--author', required=True, help='Exact OpenAlex author ID, including https://openalex.org/')
    parser.add_argument('--output', type=Path, default=Path('report.json'))
    parser.add_argument('--db', type=Path, default=Path('scholartrace.sqlite'))
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        data = json.loads(raw)
        works = data if isinstance(data, list) else data['results']
        report = analyze(args.author, works)
        digest = hashlib.sha256(raw).hexdigest()
        report['provenance'] = {'input_sha256': digest, 'imported_at': datetime.now(timezone.utc).isoformat(),
                                'source_retrieved_at': None, 'coverage': 'input file only; completeness not verified'}
        encoded = json.dumps(report, ensure_ascii=False, indent=2)
        with sqlite3.connect(args.db) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS snapshots (author TEXT, digest TEXT, raw BLOB, report TEXT, PRIMARY KEY(author, digest))')
            conn.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?)', (args.author, digest, raw, encoded))
        args.output.write_text(encoded + '\n', encoding='utf-8')
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        parser.exit(2, 'Unable to build report: ' + str(error) + '\n')
    print('Report written to ' + str(args.output))


if __name__ == '__main__':
    main()
