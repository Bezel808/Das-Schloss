const $=id=>document.getElementById(id);let active=null,report=null,evidence=null,poll=null,refreshVersion=0,retrieveRequest=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sourceHTML=(value,fallback='')=>value?`<span translate="no">${esc(value)}</span>`:esc(fallback);
async function api(path,body){const r=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'请求参数无效');return data}
function notice(s){$('notice').textContent=s}function guard(fn){return async(...a)=>{try{await fn(...a)}catch(e){if(e.message.includes('API Key')&&!$('settingsDialog').open)$('settingsDialog').showModal();notice(e.message)}}}
function tab(name){if(name==='network'&&report)renderGraph();if(name==='papers'&&report)renderPapers();if(name!=='network')window.stopTimePlayback?.();document.querySelectorAll('.tab').forEach(x=>x.hidden=x.id!==name);document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x.dataset.tab===name))}
document.querySelectorAll('[data-tab]').forEach(x=>x.onclick=()=>tab(x.dataset.tab));
$('save').onclick=guard(async()=>{await api('settings',{api_key:$('key').value});$('key').value='';await keyStatus();notice('设置已更新，Key 仅保存在当前服务内存中。')});
async function keyStatus(){const s=await api('settings');$('storageStatus').textContent=s.storage==='temporary_memory'?'论文与分析仅暂存在内存；空闲 30 分钟或重启后清空。':'当前使用显式指定的研究数据文件。';$('clearSession').hidden=s.storage!=='temporary_memory';$('keyStatus').textContent=s.key_configured?'● Key 已配置':'○ 未配置：搜索可尝试匿名访问，完整采集需要 Key'}
$('clearSession').onclick=guard(async()=>{await api('session/reset',{});$('history').innerHTML='';window.resetAuthorSearch?.();$('home').click();notice('临时查询已清空，Key 仍可使用。')});
$('home').onclick=()=>{
 document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
 document.body.classList.add('landing');window.resetInsights?.();window.resetGroups?.();window.stopTimePlayback?.();window.resetNetwork?.();
 $('searchView').hidden=false;$('profile').hidden=true;active=null;refreshVersion++;retrieveRequest++;
 clearTimeout(poll);notice('');window.history.replaceState(null,'',location.pathname);
 window.scrollTo(0,0);$('query').focus();
};

async function loadHistory(){const list=await api('jobs');$('history').innerHTML=list.map(x=>`<button data-job="${esc(x.id)}">${sourceHTML(x.author?.display_name||x.id)}<small>${esc(x.status)} · ${x.received} 篇</small></button>`).join('')||'<small>暂无记录</small>';$('history').querySelectorAll('[data-job]').forEach(x=>x.onclick=guard(()=>openProfile(x.dataset.job)));return list}
async function openProfile(id){
 window.pauseAuthorSearch?.();
 document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
 document.body.classList.remove('landing');lastReportSignature=null;
 window.history.replaceState(null,'',location.pathname+'?author='+encodeURIComponent(id));window.scrollTo(0,0);
 window.resetInsights?.();window.resetGroups?.();window.resetTimeControls?.();window.resetNetwork?.();clearTimeout(poll);retrieveRequest++;notice('');
 active=id;report=null;evidence=null;
 $('from').value='';$('to').value='';$('name').textContent=id;$('bio').textContent='';
 for(const field of ['stats','timeline','paperList','retrieved'])$(field).innerHTML='';
 $('coverage').textContent='';$('evidenceLabel').textContent='';$('paperSearch').value='';
 $('pause').hidden=true;$('resume').hidden=true;$('progress').textContent='正在读取论文与合作网络…';
 $('searchView').hidden=true;$('profile').hidden=false;tab('timeline');
 try{await loadHistory();if(active!==id)return;await refresh();}
 catch(error){if(active===id)$('progress').textContent='加载未完成：'+error.message+'。请返回搜索重试。';throw error}
}
let lastReportSignature=null;
async function refresh(){clearTimeout(poll);const version=++refreshVersion;const id=active;if(!id)return;const job=await api('jobs/'+id);if(active!==id||version!==refreshVersion)return;const signature=JSON.stringify([id,job.updated,job.status,job.received,...['from','to','workType','byline','resolution'].map(k=>$(k).value)]);if(signature===lastReportSignature){if(['queued','running','waiting'].includes(job.status))poll=setTimeout(()=>guard(refresh)(),2000);return}const r=await api('report/'+id+`?start=${$('from').value||0}&end=${$('to').value||9999}&work_type=${encodeURIComponent($('workType').value)}&institution=${encodeURIComponent($('byline').value)}&resolution=${$('resolution').value}`);if(active!==id||version!==refreshVersion)return;lastReportSignature=signature;report=r;window.syncTimeControls?.(r);render();$('progress').textContent=`${({waiting:'等待成员历史获取',queued:'已排队，等待数据源采集',running:'正在采集',complete:'采集完成',error:'采集中断',paused:'已暂停',interrupted:'等待恢复'})[job.status]} · ${job.received} / ${job.total||'…'} 篇 · ${job.error||''}`;$('resume').hidden=['queued','running','waiting','complete'].includes(job.status);$('pause').hidden=!['queued','running','waiting'].includes(job.status);if(['queued','running','waiting'].includes(job.status))poll=setTimeout(()=>guard(refresh)(),2000)}
$('resume').onclick=guard(async()=>{await api('jobs',{author_id:active});await refresh()});$('pause').onclick=guard(async()=>{await api('jobs/'+active+'/pause',{});await refresh()});$('filter').onclick=guard(async()=>{window.stopTimePlayback?.();$('timeMode').value='custom';evidence=null;await refresh()});
function showEvidence(ids,label,names=[]){evidence=ids;tab('papers');$('evidenceLabel').dataset.i18nNames=JSON.stringify(names);$('evidenceLabel').textContent=label;renderPapers()}
function chips(items){return Object.values(items).map(x=>`<button class="chip" data-evidence="${esc(JSON.stringify(x.work_ids))}">${sourceHTML(x.name)} · ${x.work_ids.length}</button>`).join('')}
function render(){const r=report;$('name').textContent=r.author?.display_name||active;$('bio').innerHTML=sourceHTML((r.author?.last_known_institutions||[]).map(x=>x.display_name).join(' · '))+' · 最新机构';const rows=r.timeline,total=rows.reduce((s,x)=>s+x.work_count,0),abstracts=rows.reduce((s,x)=>s+x.abstract_available_rate*x.work_count,0);$('stats').innerHTML=[['统计论文',total],['覆盖年份',rows.length],['合作者',Math.max(0,r.graph.nodes.length-1)],['摘要覆盖',total?Math.round(100*abstracts/total)+'%':'—']].map(([k,v])=>`<div class="stat"><span>${k}</span><strong>${v}</strong></div>`).join('');$('coverage').textContent=`数据获取时间：${r.retrieved_at||'等待采集'} · ${r.status==='complete'?'已完成分页':'部分数据，采集尚未完成'} · 当前范围 ${r.papers.length} 篇；排除统计 ${r.omitted.length} 篇；全库缺年份 ${r.missing_year_count} 篇。`;$('timeline').innerHTML=[...rows].reverse().map(y=>`<article class="year"><h2>${y.year} <small>${y.work_count} 篇论文</small></h2><div class="bar" style="width:${Math.max(3,100*y.work_count/Math.max(...rows.map(x=>x.work_count)))}%"></div><div class="chips">${Object.entries(y.roles).map(([k,ids])=>`<button class="chip" data-evidence="${esc(JSON.stringify(ids))}">${esc({first:'第一作者',last:'末位作者',middle:'中间作者',corresponding:'通讯作者',unknown:'位次未知'}[k]||k)} ${ids.length}</button>`).join('')}</div><small>论文署名机构</small><div class="chips">${chips(y.institutions)||'暂无信息'}</div><small>来源主题标签</small><div class="chips">${chips(y.topics)||'暂无标签'}</div><button data-evidence="${esc(JSON.stringify(y.works.map(x=>x.id)))}">查看本年论文 →</button></article>`).join('')||'<p class="empty">当前没有可统计的论文。采集完成后将自动显示。</p>';$('timeline').querySelectorAll('[data-evidence]').forEach(x=>x.onclick=()=>showEvidence(JSON.parse(x.dataset.evidence),i18n.sourceText(x),i18n.sourceTerms(x)));if(!$('papers').hidden)renderPapers();if(!$('network').hidden)renderGraph()}
function renderPapers(){if(!report)return;const q=$('paperSearch').value.toLowerCase(),omitted=new Map(report.omitted.map(x=>[x.id,x.reason]));const papers=report.papers.filter(p=>(!evidence||evidence.includes(p.id))&&(p.title||'').toLowerCase().includes(q)).sort((a,b)=>(b.publication_year||0)-(a.publication_year||0));$('paperList').innerHTML=papers.map(p=>{const words=[];for(const [word,positions]of Object.entries(p.abstract_inverted_index||{}))for(const pos of positions)if(Number.isInteger(pos)&&pos>=0&&pos<50000)words[pos]=word;const href=/^https:\/\/openalex.org\/W\d+$/.test(p.id)?p.id:'#';return `<article class="paper"><a target="_blank" rel="noreferrer" href="${esc(href)}">${sourceHTML(p.title,'无标题')} ↗</a><p>${p.publication_year||'年份缺失'} · ${sourceHTML(p.primary_location?.source?.display_name,'发表场所未提供')} · ${p.authors_count??p.authorships?.length} 位作者</p>${omitted.has(p.id)?`<p class="error">${esc(omitted.get(p.id))}</p>`:''}<details><summary>查看摘要和署名证据</summary><p>${sourceHTML((p.authorships||[]).map(x=>x.author?.display_name).join(' · '))}</p>${sourceHTML(words.join(' '),'源数据未提供摘要')}<p>${esc(p.id)} · ${esc(p.doi||'')}</p></details></article>`}).join('')||'<p class="empty">没有符合筛选条件的论文。</p>'}
$('paperSearch').oninput=renderPapers;$('clearEvidence').onclick=()=>{evidence=null;$('evidenceLabel').textContent='';renderPapers()};
function renderGraph(){window.drawNetwork(report,showEvidence)}
$('export').onclick=()=>{if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=active+'-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
guard(async()=>{await keyStatus();const id=new URLSearchParams(location.search).get('author');if(id&&/^A\d+$/.test(id))await openProfile(id)})();

$('retrieveForm').onsubmit=guard(async e=>{e.preventDefault();const id=active,version=++retrieveRequest;const data=await api('retrieve/'+id+'?q='+encodeURIComponent($('retrieveQuery').value));if(id!==active||version!==retrieveRequest)return;$('retrieved').innerHTML='<p class="muted">BM25 · '+data.corpus_size+' 篇本次已获取论文 · '+data.results.length+' 条匹配</p>'+data.results.map((r,i)=>`<article class="paper"><b>[${i+1}] ${sourceHTML(r.title)}</b><p>${r.year} · 相关度 ${r.score} · 匹配词：${sourceHTML(r.matched_terms.join(', '))}</p><p>${sourceHTML(r.excerpt)}</p><button data-source="${esc(r.id)}">查看原始论文证据 →</button></article>`).join('');$('retrieved').querySelectorAll('[data-source]').forEach(x=>x.onclick=guard(async()=>{evidence=[x.dataset.source];$('from').value='';$('to').value='';await refresh();showEvidence(evidence,'检索来源')}))});

$('enrich').onclick=guard(async()=>{notice('正在批量补全合作者的引用数和当前机构…');await api('enrich/'+active,{});lastReportSignature=null;await refresh();notice('合作者资料已补全。')});

async function computeResult(kind,id,params,onProgress,isCurrent){
 for(let attempt=0;attempt<3;attempt++){
  let task=await api('compute/'+kind+'/'+id,params);
  while(task.status==='queued'||task.status==='running'){
   if(!isCurrent())throw Error('已切换分析对象');
   onProgress(task.status==='queued'?'计算任务已排队，正在等待执行…':'正在后台计算，可切换页签；完成后自动显示。');
   await new Promise(resolve=>setTimeout(resolve,1200));
   if(!isCurrent())throw Error('已切换分析对象');
   task=await api('computations/'+task.id);
  }
  if(!isCurrent())throw Error('已切换分析对象');
  if(task.status==='complete')return task.result;
  if(task.status!=='stale')throw Error(task.error||'计算中断，请重新计算');
  onProgress('采集数据已更新，正在使用新数据重新计算…');
 }
 throw Error('论文数据仍在更新，请待本轮采集完成后重试');
}
