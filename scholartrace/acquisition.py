"""Complete-author-query observation and certifiable common-neighbor rankings.

Certificates concern the completed historical CN score, NOT future link truth.
Only an explicitly completed author query certifies absence of incident edges.
"""
from collections import Counter, defaultdict
from itertools import combinations
import math
import random

VERSION = 'author-query-cn-4'


class Observation:
    def __init__(self, focal, cutoff):
        self.focal = focal
        self.cutoff = cutoff
        self.adj = defaultdict(set)
        self.complete = set()
        self.papers = set()
        self.event_content = {}
        self.author_events = defaultdict(set)
        self.counts = Counter()
        self.last = {}
        self.query_log = []

    def reveal(self, author, events):
        if author in self.complete:
            raise ValueError('Author was already queried')
        # Validate the whole response before mutating state.
        rows = list(events)
        if any(year > self.cutoff or author not in people or len(people) != len(set(people))
               for _, year, people in rows):
            raise ValueError('Query must contain complete, past-only author events')
        incoming = {}
        for event_id, year, people in rows:
            signature = (year, tuple(sorted(people)))
            if event_id in incoming and incoming[event_id] != signature:
                raise ValueError('Conflicting duplicate event within query response')
            if event_id in self.event_content and self.event_content[event_id] != signature:
                raise ValueError('Event content changed across completed queries')
            incoming[event_id] = signature
        rows = [(e, year, people) for e, (year, people) in incoming.items()]
        if not self.author_events.get(author,set()) <= incoming.keys():
            raise ValueError('Completed query omits an already observed incident event')
        returned_neighbors = {a for _, _, people in rows for a in people} - {author}
        if not self.adj.get(author,set()) <= returned_neighbors:
            raise ValueError('Completed query omits an already observed neighbor')
        if any(event_id not in self.papers and self.complete.intersection(people)
               for event_id, _, people in rows):
            raise ValueError('New event contradicts a previously completed author history')
        self.adj[author]
        for event_id, year, people in rows:
            if event_id in self.papers:
                continue
            self.papers.add(event_id)
            self.event_content[event_id] = (year, tuple(people))
            for a in people:
                self.adj[a]
                self.author_events[a].add(event_id)
            for a, b in combinations(sorted(people), 2):
                self.adj[a].add(b); self.adj[b].add(a)
                self.counts[a,b] += 1
                self.last[a,b] = max(year, self.last.get((a,b), year))
        self.complete.add(author)
        self.query_log.append({'author':author, 'returned_events':len(rows), 'observed_events':len(self.papers)})

    @property
    def neighbors(self):
        if self.focal not in self.complete:
            raise ValueError('Query the focal author before constructing the risk set')
        return self.adj[self.focal]

    def candidates(self):
        return set(self.adj) - self.neighbors - {self.focal}

    def bounds(self):
        neighbors = self.neighbors
        unqueried = neighbors - self.complete
        result = {}
        for v in self.candidates():
            common = neighbors & self.adj[v]
            lower = len(common)
            width = 0 if v in self.complete else len(unqueried - common)
            result[v] = (lower, lower + width)
        return result, len(unqueried)

    def scores(self):
        n = self.neighbors
        result = {}
        for v in self.candidates():
            common = n & self.adj[v]
            result[v] = {
                'common_neighbors':float(len(common)),
                'adamic_adar':sum(1/math.log(len(self.adj[q])) for q in common if len(self.adj[q]) > 1),
                'resource_allocation':sum(1/len(self.adj[q]) for q in common),
                'preferential_attachment':float(len(n)*len(self.adj[v])),
                # Deliberately retain uninformative baselines in the new-edge task.
                'edge_bank':0., 'past_joint_count':0.,
            }
        return result

    def certificate(self, k=10):
        bounds, unseen_upper = self.bounds()
        ordered = sorted(bounds, key=lambda v:(-bounds[v][0],v))
        chosen = ordered[:k]
        outside = [bounds[v][1] for v in ordered[k:]]
        threshold = min((bounds[v][0] for v in chosen), default=0)
        rival = max(outside+[unseen_upper])
        # Strict separation avoids certifying an arbitrary ID-based tie order.
        certified = len(chosen)==k and threshold > rival
        return {'k':k,'members':chosen,'certified':certified,'min_selected_lower':threshold,
                'max_outside_upper':rival,'unseen_candidate_upper':unseen_upper,
                'scope':'historical CN top-k under complete author queries; not forecast correctness',
                'bounds':bounds}

    def next_query(self, policy, rng, k=10):
        available = set(self.adj)-self.complete
        if not available: return None
        if policy in {'neighbor_random','neighbor_degree'}:
            eligible = self.neighbors-self.complete
            if not eligible:return None
            if policy=='neighbor_random':return rng.choice(sorted(eligible))
            return min(eligible,key=lambda a:(-len(self.adj[a]),a))
        if policy=='random':return rng.choice(sorted(available))
        if policy=='observed_degree':return min(available,key=lambda a:(-len(self.adj[a]),a))
        bounds, unseen_upper = self.bounds()
        unqueried = self.neighbors-self.complete
        if policy=='uncertainty':
            uncertain = [v for v,(lo,hi) in bounds.items() if hi>lo and v in available]
            if uncertain:return min(uncertain,key=lambda v:(-(bounds[v][1]-bounds[v][0]),-bounds[v][1],v))
            return min(available,key=lambda a:(-len(self.adj[a]),a))
        if policy not in {'ambiguity_cover','uniform_cover'}:raise ValueError('Unknown policy')
        if not unqueried:return None  # CN is exact; extra queries cannot resolve its remaining ties.
        # Coverage is over unknown entries of the N(focal) x candidates matrix.
        # Querying a neighbor reveals a row; querying a candidate reveals a column.
        # Boundary weights are computed only from current intervals. This adaptive
        # heuristic has no claimed global approximation ratio or novelty guarantee.
        lowers = sorted((lo for lo,_ in bounds.values()),reverse=True)
        threshold = lowers[min(k,len(lowers))-1] if lowers else 0
        weights = {v:(1. if policy=='uniform_cover' else 1/(1+abs((lo+hi)/2-threshold)))
                   for v,(lo,hi) in bounds.items() if hi>lo and hi>=threshold}
        gains = defaultdict(float)
        for v, weight in weights.items():
            unknown = unqueried - self.adj[v]
            gains[v] += weight*len(unknown)
            for q in unknown:gains[q] += weight
        # One explicit unseen-candidate sentinel, not a fabricated node count.
        if unseen_upper >= threshold:
            for q in unqueried:gains[q] += 1
        return min(available,key=lambda a:(-gains[a],-len(self.adj[a]),a))
