"""Local BM25 retrieval over a frozen scholar corpus; no generation or invented answers."""
import math
import re
from collections import Counter


def tokens(text):
    text = text.lower()
    return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]', text)


def abstract(work):
    positions = {}
    for word, indices in (work.get('abstract_inverted_index') or {}).items():
        for index in indices:
            if isinstance(index, int) and 0 <= index < 50000:
                positions[index] = word
    return ' '.join(positions[k] for k in sorted(positions))


def retrieve(works, query, limit=10):
    terms = set(tokens(query))
    docs = [(w, abstract(w)) for w in works]
    counts = [Counter(tokens((w.get('title') or '') + ' ' + text + ' ' + ' '.join(t.get('display_name','') for t in w.get('topics',[])))) for w,text in docs]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths)/max(1,len(lengths)) or 1
    frequency = Counter(t for c in counts for t in terms if t in c)
    results = []
    for (work,text), count, length in zip(docs, counts, lengths):
        score = 0
        for term in terms:
            tf = count[term]
            idf = math.log(1 + (len(docs)-frequency[term]+.5)/(frequency[term]+.5))
            score += idf * tf * 2.5 / (tf + 1.5*(.25+.75*length/average))
        if score:
            results.append({'id':work['id'],'title':work.get('title'),'year':work.get('publication_year'),
                            'score':round(score,5),'excerpt':text[:1600] or '源数据未提供摘要',
                            'matched_terms':sorted(terms & count.keys())})
    return sorted(results,key=lambda x:(-x['score'],x['id']))[:limit]
