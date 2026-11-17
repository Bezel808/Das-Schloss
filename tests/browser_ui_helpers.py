"""Controlled profile responses for browser tests; no real collection or keys."""
def mock_profile(page, author_id='A5091518548', name='Chao Huang'):
    author={'id':'https://openalex.org/'+author_id,'display_name':name,
            'last_known_institutions':[{'display_name':'Example University'}], 'works_count':2}
    job={'id':author_id,'status':'complete','received':2,'total':2,'author':author,'updated':'test'}
    report={'author':author,'timeline':[],'graph':{'nodes':[{'id':author['id']}],'edges':[]},
            'papers':[],'omitted':[],'missing_year_count':0,'status':'complete','retrieved_at':'test'}
    page.route('**/api/settings',lambda r:r.fulfill(json={'key_configured':True,'storage':'temporary_memory'}))
    page.route('**/api/authors?*',lambda r:r.fulfill(json={'results':[author]}))
    page.route('**/api/jobs',lambda r:r.fulfill(json=job if r.request.method=='POST' else [job]))
    page.route('**/api/jobs/'+author_id,lambda r:r.fulfill(json=job))
    page.route('**/api/report/'+author_id+'?*',lambda r:r.fulfill(json=report))
