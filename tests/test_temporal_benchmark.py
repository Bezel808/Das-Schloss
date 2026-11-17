import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import temporal_benchmark as bench

class TemporalCorpusRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'research').mkdir();self.data=self.root/'data';self.data.mkdir()
        source=self.data/'test.npz'
        np.savez_compressed(source,times=np.array([2000,2001,2002]),nverts=np.array([2,2,1]),
                            vertices=np.array([0,1,1,2,3]),offsets=np.array([0,2,4,5]))
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        (self.root/'research/temporal-data-manifest.json').write_text(json.dumps({'test':{'processed_sha256':digest}}))
        self.patches=[patch.object(bench,'ROOT',self.data),patch.object(bench,'PROJECT',self.root)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def test_partial_and_corrupt_index_are_rebuilt(self):
        a=bench.TemporalCorpus('test');expected=a.query(1,2001)
        prefix=a.index_prefix.name
        (self.data/(prefix+'.events.npy')).unlink()
        b=bench.TemporalCorpus('test');self.assertEqual(expected,b.query(1,2001))
        path=self.data/(prefix+'.events.npy');raw=bytearray(path.read_bytes());raw[-1]^=1;path.write_bytes(raw)
        c=bench.TemporalCorpus('test');self.assertEqual(expected,c.query(1,2001))
    def test_source_fingerprint_is_checked(self):
        path=self.data/'test.npz';path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'fingerprint'):bench.TemporalCorpus('test')
    def test_history_and_cold_start_are_separate(self):
        c=bench.TemporalCorpus('test')
        self.assertEqual(c.neighbors(1,2000),{0})
        self.assertEqual(c.future(1,2000),{'new_seen':set(),'new_cold':{2},'repeated':set()})

    def test_duplicate_byline_normalization_preserves_events_and_query_completeness(self):
        source=self.data/'test.npz'
        np.savez_compressed(source,times=np.array([2000,2001,2001]),nverts=np.array([4,2,2]),
                            vertices=np.array([1,0,1,0,1,2,1,2]),offsets=np.array([0,4,6,8]))
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        (self.root/'research/temporal-data-manifest.json').write_text(json.dumps({'test':{'processed_sha256':digest}}))
        c=bench.TemporalCorpus('test')
        self.assertEqual(c.query(1,2001),[(0,2000,[1,0]),(1,2001,[1,2]),(2,2001,[1,2])])
        self.assertEqual(c.normalization['affected_events'],1)
        self.assertEqual(c.normalization['removed_duplicate_incidences'],2)
        self.assertEqual(c.cohort(2001,10,42),[1])
        state=bench.Observation(1,2001);state.reveal(1,c.query(1,2001));state.reveal(0,c.query(0,2001))
        self.assertEqual(len(state.papers),3)
        self.assertEqual(state.counts[(1,2)],2)
