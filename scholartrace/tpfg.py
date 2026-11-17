"""Time-constrained advisor ranking (Wang et al., KDD 2010, equations 1–10).

The joint objective is solved by binary integer programming, rather than the
paper's approximate message schedule. Scores are normalized MAX-marginals,
not posterior probabilities. Explicit adaptations: YEAR2 uses differences of
segment means; the unobserved-advisor potential is a configurable constant.
"""
from collections import Counter, defaultdict
import math
import time

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from scipy.special import softmax

VERSION = 'tpfg-milp-3'
REFERENCE = 'https://hanj.cs.illinois.edu/pdf/kdd10_cwang.pdf'


def local_evidence(student, advisor):
    """Paper's strict career ordering and R3; retain exclusion reasons."""
    from .inference import entry
    joint = [w for w in student['works'] if entry(w, advisor['id'])]
    if not joint:
        return None
    start = min(w['publication_year'] for w in joint)
    last = max(w['publication_year'] for w in joint)
    reasons = []
    if advisor['first'] >= student['first']:
        reasons.append('advisor_not_observed_earlier')
    if start == last:
        reasons.append('single_joint_publication_year')
    own = Counter(w['publication_year'] for w in student['works'])
    other = Counter(w['publication_year'] for w in advisor['works'])
    together = Counter(w['publication_year'] for w in joint)
    stop = max(max(own), max(other))
    a = sum(n for y, n in own.items() if y < start)
    b = sum(n for y, n in other.items() if y < start)
    c = 0
    series = []
    for year in range(start, stop + 1):
        a += own[year]; b += other[year]; c += together[year]
        kulc = c * (1 / a + 1 / b) / 2
        imbalance = (b - a) / max(1, a + b - c)
        series.append({'year': year, 'student_papers': a, 'advisor_papers': b,
                       'joint_papers': c, 'kulczynski': kulc, 'imbalance': imbalance})
    if any(r['joint_papers'] > min(r['student_papers'], r['advisor_papers']) for r in series):
        reasons.append('inconsistent_author_histories')
    # YEAR2: a boundary must leave two observed joint years in its first segment.
    # If no decline is observable, the end remains right-censored at last joint year.
    boundaries = []
    second_joint_year = sorted(together)[1] if len(together) >= 2 else last + 1
    for end in range(second_joint_year, last + 1):
        before = [r['kulczynski'] for r in series if r['year'] <= end]
        after = [r['kulczynski'] for r in series if r['year'] > end]
        if after:
            boundaries.append((float(np.mean(before) - np.mean(after)), -end))
    decline, neg_end = max(boundaries, default=(0., -last))
    end = -neg_end if decline > 0 else last
    segment = [r for r in series if r['year'] <= end]
    potential = sum((r['kulczynski'] + r['imbalance']) / 2 for r in segment) / len(segment)
    return {'eligible': not reasons, 'exclusion_reasons': reasons,
            'start': start, 'end': end, 'end_censored': decline <= 0,
            'local_potential': max(1e-9, min(1., potential)), 'annual_evidence': series}


def solve_states(states, *, seconds=30):
    """Exact MAP and conditional MAP for every state, component by component.

states[student] = [{advisor: id|None, start, end, potential}, ...].
One state is selected per person. Incompatible A→B→C intervals cannot both
be selected. Every component has a feasible all-null assignment. A time limit
never silently turns a feasible incumbent into a certified ranking.
"""
    deadline = time.monotonic() + seconds
    dependency = nx.Graph()
    dependency.add_nodes_from(states)
    for person, choices in states.items():
        if not choices or not any(s['advisor'] is None for s in choices):
            raise ValueError('Every person requires an unobserved-advisor state')
        for s in choices:
            if not 0 < s['potential'] <= 1 or not math.isfinite(s['potential']):
                raise ValueError('Potentials must be finite in (0,1]')
            if s['advisor'] is not None:
                if s['advisor'] not in states or s['advisor'] == person:
                    raise ValueError('Invalid advisor reference')
                dependency.add_edge(person, s['advisor'])
    results = {}; diagnostics = []
    for component in sorted(nx.connected_components(dependency), key=lambda c: sorted(c)):
        people = sorted(component)
        variables = [(p, j, s) for p in people for j, s in enumerate(states[p])]
        index = {(p, j): k for k, (p, j, _) in enumerate(variables)}
        conflicts = []
        for p, j, s in variables:
            if s['advisor'] is None:
                continue
            for k, parent in enumerate(states[s['advisor']]):
                if parent['advisor'] is not None and parent['end'] >= s['start']:
                    conflicts.append((index[p, j], index[s['advisor'], k]))
        matrix = lil_matrix((len(people) + len(conflicts), len(variables)), dtype=float)
        for r, p in enumerate(people):
            for j in range(len(states[p])):
                matrix[r, index[p, j]] = 1
        for r, (a, b) in enumerate(conflicts, len(people)):
            matrix[r, a] = matrix[r, b] = 1
        lower = np.r_[np.ones(len(people)), np.full(len(conflicts), -np.inf)]
        constraints = LinearConstraint(matrix.tocsc(), lower, np.ones(len(lower)))
        cost = -np.log([s['potential'] for _, _, s in variables])
        def optimize(fixed=None):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            lo = np.zeros(len(variables)); hi = np.ones(len(variables))
            if fixed is not None:
                lo[fixed] = 1
            fit = milp(cost, integrality=np.ones(len(cost)), bounds=Bounds(lo, hi),
                       constraints=constraints,
                       options={'time_limit': remaining, 'mip_rel_gap': 0.0})
            return fit if fit.status == 0 and fit.fun is not None else None
        fit = optimize()
        conditionals = {}
        if fit is not None:
            chosen = {k for k, v in enumerate(fit.x) if v > .5}
            for k, (p, j, _) in enumerate(variables):
                fixed = fit if k in chosen else optimize(k)
                if fixed is None:
                    break
                conditionals[p, j] = -float(fixed.fun)
        complete = len(conditionals) == len(variables)
        diagnostics.append({'people': len(people), 'states': len(variables),
                            'temporal_conflicts': len(conflicts),
                            'status': 'optimal' if complete else 'solver_incomplete',
                            'objective_log_potential': -float(fit.fun) if fit is not None else None,
                            'mip_gap': float(fit.mip_gap) if fit is not None else None})
        for p in people:
            if not complete:
                results[p] = {'status': 'solver_incomplete', 'scores': None}
                continue
            logs = [conditionals[p, j] for j in range(len(states[p]))]
            scores = softmax(np.array(logs) - max(logs)).tolist()
            results[p] = {'status': 'optimal', 'scores': scores, 'log_max_marginals': logs,
                          'map_state': next(j for j in range(len(states[p])) if index[p, j] in chosen)}
    return results, diagnostics


def rank(profiles, *, null_potential=.5, seconds=30, candidate_ids=None):
    if not 0 < null_potential < 1:
        raise ValueError('null_potential must be in (0,1)')
    states = {p: [{'advisor': None, 'start': -math.inf, 'end': -math.inf,
                   'potential': null_potential}] for p in profiles}
    evidence = {}
    for student in sorted(profiles):
        for advisor in sorted(profiles[student]['neighbors'] & profiles.keys()):
            if candidate_ids is not None and student in candidate_ids and advisor not in candidate_ids[student]:
                continue
            if profiles[advisor]['first'] >= profiles[student]['first']:
                continue
            local = local_evidence(profiles[student], profiles[advisor])
            if not local:
                continue
            evidence[advisor, student] = local
            if local['eligible']:
                states[student].append({'advisor': advisor, 'start': local['start'],
                                        'end': local['end'], 'potential': local['local_potential']})
    solved, diagnostics = solve_states(states, seconds=seconds)
    for student, choices in states.items():
        result = solved[student]
        ranked = sorted(range(len(choices)), key=lambda j: (-(result['scores'][j] if result['scores'] else 0), j))
        for j, state in enumerate(choices[1:], 1):
            item = evidence[state['advisor'], student]
            item.update(solver_status=result['status'], ranking_score=result['scores'][j] if result['scores'] else None,
                        null_score=result['scores'][0] if result['scores'] else None,
                        rank=ranked.index(j) + 1, map_selected=result.get('map_state') == j)
    return evidence, {'method': 'TPFG temporal objective · exact MILP max-marginal ranking',
                     'version': VERSION, 'reference': REFERENCE, 'null_potential': null_potential,
                     'status': 'optimal' if all(d['status'] == 'optimal' for d in diagnostics) else 'solver_incomplete',
                     'components': diagnostics, 'probability_calibrated': False,
                     'training_labels': 'unsupervised objective; external validation is reported separately',
                     'warning': '分数是时序约束模型的相对排序分数，不是师生概率。模型假定指导开始前已结束受指导阶段；同时读博与指导他人的情况不符合此假定。',
                     'adaptations': ['exact MILP instead of approximate message passing',
                                     'YEAR2 segment-mean difference; no observed decline is right-censored',
                                     'explicit constant unobserved-advisor potential']}
