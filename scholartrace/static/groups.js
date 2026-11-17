/* Every displayed result belongs to an author, parameter set and request generation. */
(()=>{
 let data=null,proposal=null,epoch=0,request=0,planRequest=0,timer=null,evidenceIds=[],completionSeen=null,refreshing=false,collectionRunning=false,calculating=false;
 let graphPositions=new Map(),graphLayoutKey='',graphViewportKey='',graphTransform=d3.zoomIdentity,selectedMember=null,graphSimulation=null;
 const groupColors=['#46775e','#4e79a7','#b78043','#aa6685','#529a9e','#8a913f','#8b78a9','#cf7895','#9c755f','#7461a7','#528e80','#ba845f','#89915b','#577e9a','#a67593'];
 const fields={start:'groupStart',end:'groupEnd',scope:'groupScope',window:'groupWindow',early_years:'groupEarlyYears',prior_papers:'groupPriorPapers',early_papers:'groupEarlyPapers',followup:'groupFollowup',incumbent_papers:'groupIncumbentPapers',max_team:'groupMaxTeam'};
 const missingNames={history_not_collected:'尚未采集',history_incomplete:'历史采集未完成',undated_source_record:'论文缺年份',author_mismatch:'作者记录不匹配',no_dated_history_at_entry:'入圈时缺有年份的记录'};
 const category={early_career:'科研早期',experienced:'已有发表经历',unknown:'资料仍不足'};
 const awaiting=r=>r.category==='unknown'&&['history_not_collected','history_incomplete'].includes(r.missing_reason);
 const readiness=rows=>({pending:rows.filter(awaiting).length,unresolved:rows.filter(r=>r.category==='unknown'&&!awaiting(r)).length});
 const sameParameters=s=>Object.entries(parameters()).every(([k,v])=>s.plan?.parameters[k]===v);
 const assessment={assessed:'观察期已满',right_censored:'观察期未满',unknown_career_history:'缺完整 / 可用历史',coverage_date_unknown:'采集时间未知',not_early_career:'非科研早期队列',no_eligible_early_papers:'无符合条件的早期论文'};
 const pct=v=>v==null?'—':(100*v).toFixed(1)+'%';
 const parameters=()=>Object.fromEntries(Object.entries(fields).map(([k,id])=>[k,k==='scope'?$(id).value:Number($(id).value)]));
 const valid=(id,e)=>active===id&&epoch===e;
 const button=(label,ids,source=false)=>`<button class="groupEvidenceButton" data-group-evidence="${esc(JSON.stringify(ids))}">${source?sourceHTML(label):esc(label)}</button>`;
 const metric=(label,value,note)=>`<div class="stat groupMetric"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;
 function clearResult(){calculating=false;$('groupRun').textContent='开始分析';graphSimulation?.stop();graphSimulation=null;selectedMember=null;$('groupFindPerson').value='';$('groupFocus').value='all';data=null;request++;$('groupResults').hidden=true;$('groupExport').disabled=true;$('groupRun').disabled=false;$('groupEvidencePanel').hidden=true;d3.select('#groupGraph').selectAll('*').remove()}
 function invalidate(){clearResult();proposal=null;planRequest++;$('groupPlan').disabled=false;$('groupCollect').disabled=true;$('groupPlanInfo').textContent='';$('groupStatus').textContent='范围已更改，请重新分析。'}
 window.resetGroups=()=>{graphPositions.clear();graphLayoutKey='';graphTransform=d3.zoomIdentity;selectedMember=null;completionSeen=null;collectionRunning=false;calculating=false;$('groupCollection').hidden=true;epoch++;clearTimeout(timer);clearResult();proposal=null;planRequest++;$('groupPlan').disabled=false;$('groupCollect').disabled=true;$('groupPause').hidden=true;$('groupPlanInfo').textContent='';$('groupCollectionStatus').textContent='';$('groupStatus').textContent='';$('groupMemberSearch').value='';$('groupCohortCategory').value='';$('groupCohortYear').innerHTML='<option value="">全部年份</option>'};
 Object.values(fields).forEach(id=>$(id).addEventListener('input',invalidate));
 $('groupLimit').oninput=()=>{proposal=null;planRequest++;$('groupPlan').disabled=false;$('groupCollect').disabled=true;$('groupPlanInfo').textContent='补采人数已改变，请重新预览。'};
 function bindEvidence(root){root.querySelectorAll('[data-group-evidence]').forEach(b=>b.onclick=()=>showEvidence(JSON.parse(b.dataset.groupEvidence),i18n.sourceText(b),i18n.sourceTerms(b)))}
 function showEvidence(ids,label,names=[]){if(!data)return;$('groupEvidenceTitle').dataset.i18nNames=JSON.stringify(names);evidenceIds=[...new Set(ids)];$('groupEvidenceTitle').textContent=label+' · 论文依据';$('groupEvidencePanel').hidden=false;$('groupEvidenceSearch').value='';renderEvidence();$('groupEvidencePanel').focus();$('groupEvidencePanel').scrollIntoView({behavior:'smooth',block:'start'})}
 function renderEvidence(){
  if(!data)return;
  const query=$('groupEvidenceSearch').value.toLowerCase();
  const rows=evidenceIds.map(id=>data.evidence[id]).filter(Boolean).filter(p=>(p.title+' '+p.authors.map(a=>a.name).join(' ')).toLowerCase().includes(query)).sort((a,b)=>a.year-b.year||a.id.localeCompare(b.id));
  $('groupEvidenceCount').textContent=`共 ${evidenceIds.length} 篇依据，筛选后 ${rows.length} 篇；包括目标作者未署名的论文。`;
  $('groupEvidence').innerHTML=rows.map(p=>`<article class="paper"><a href="${esc(/^https:\/\/openalex.org\/W\d+$/.test(p.id)?p.id:'#')}" target="_blank" rel="noreferrer">${sourceHTML(p.title)} ↗</a><p>${p.year}${p.is_retracted?' · 撤稿记录（仅用于发表起点）':''}${p.is_paratext?' · 附属文本（仅用于发表起点）':''} · ${p.authors.some(a=>a.id===data.focal)?'目标作者共同署名':'目标作者未署名'}</p><details><summary>作者与当篇机构署名</summary>${p.authors.map(a=>`<p>${sourceHTML(a.name)} · ${sourceHTML((p.institutions[a.id]||[]).join(' / '),'机构未知')}</p>`).join('')}<p>${esc(p.id)}</p></details></article>`).join('')||'<p class="empty">当前筛选没有论文。</p>';
 }
 $('groupEvidenceSearch').oninput=renderEvidence;
 function renderCohorts(){
  if(!data)return;
  const year=$('groupCohortYear').value,cat=$('groupCohortCategory').value,query=$('groupMemberSearch').value.toLowerCase();
  const rows=data.cohorts.filter(r=>(!year||r.entry_year===Number(year))&&(!cat||(cat==='pending'?awaiting(r):cat==='unresolved'?r.category==='unknown'&&!awaiting(r):r.category===cat))&&(r.name+' '+r.id).toLowerCase().includes(query)).sort((a,b)=>b.entry_year-a.entry_year||a.name.localeCompare(b.name));
  $('groupCohorts').innerHTML=`<p class="muted">显示 ${rows.length} / ${data.cohorts.length} 位首次进入者。点击数字查看论文；“未观察到”仅指当前数据与窗口。</p>`+table(['成员 / 入圈证据','进入年','分类','首次收录年 / 年前论文','跟踪状态','目标作者参与','既有成员协作','持续协作','第 H 年同圈合作','既有成员的此前依据','分类依据 / 待处理项'],rows.map(r=>[
   button(r.name,r.entry_work_ids,true),r.entry_year,(awaiting(r)?'等待获取历史':category[r.category]),r.category==='unknown'?'—':button(`${r.first_observed_publication_year} / ${r.papers_before_entry_year}`,r.career_evidence_work_ids),esc(assessment[r.assessment]||r.assessment),
   r.focal_share==null?'—':button(`${r.focal_work_ids.length}/${r.early_work_ids.length} · ${pct(r.focal_share)}`,r.early_work_ids),
   r.peer_supported==null?'—':r.peer_supported?button(`${r.peer_work_ids.length} 篇`,r.peer_work_ids):'未观察到',
   r.persistent_peer_supported==null?'—':r.persistent_peer_supported?button(`${r.persistent_peer_ids.length} 人`,r.peer_work_ids):'未观察到',
   r.circle_continuation==null?'—':r.circle_continuation?button(`${r.circle_followup_work_ids.length} 篇`,r.circle_followup_work_ids):'未观察到',
   r.incumbents.length?button(r.incumbents.length+' 位既有成员',Object.values(r.incumbent_evidence).flat()):'无满足门槛者',
   esc(r.classification_basis==='observed_lower_bound'?'已有论文足以排除科研早期（年限/篇数下界）':r.missing_reason?(missingNames[r.missing_reason]||r.missing_reason):'个人历史已完整采集')
  ]));bindEvidence($('groupCohorts'));
 }
 ['groupCohortYear','groupCohortCategory'].forEach(id=>$(id).onchange=renderCohorts);$('groupMemberSearch').oninput=renderCohorts;
 function subgroupInfo(){
  const s=data.structure,nodeMap=new Map(s.nodes.map(n=>[n.id,n]));
  return s.observed_subgroups.map((g,i)=>{
   const ids=new Set(g.members),internal=s.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)),external=s.edges.filter(e=>ids.has(e.source)!==ids.has(e.target));
   const strength=new Map(g.members.map(id=>[id,0]));internal.forEach(e=>{strength.set(e.source,strength.get(e.source)+1);strength.set(e.target,strength.get(e.target)+1)});
   return {i,ids,color:groupColors[i]||d3.hcl((i*137.508)%360,50,48).formatHex(),members:g.members.map(id=>nodeMap.get(id)).filter(Boolean).sort((a,b)=>strength.get(b.id)-strength.get(a.id)||a.name.localeCompare(b.name)),internal,external,
    papers:[...new Set(internal.flatMap(e=>e.work_ids))],outsidePapers:[...new Set(external.flatMap(e=>e.work_ids))]};
  });
 }
 function focusGroup(index){selectedMember=null;$('groupFocus').value=String(index);$('groupFindPerson').value='';renderGraph();$('groupGraph').scrollIntoView({behavior:'smooth',block:'center'})}
 function selectMember(id){
  const s=data.structure,n=s.nodes.find(n=>n.id===id);if(!n)return;
  const group=subgroupInfo().find(g=>g.ids.has(id));
  selectedMember=id;$('groupFocus').value='all';$('groupFindPerson').value='';renderGraph();
  $('groupSelection').innerHTML=`<strong translate="no">${esc(n.name)}</strong> · ${group?'子群 '+String(group.i+1).padStart(2,'0'):'未归入多人子群'} · ${n.complete?'个人历史已采全':'个人历史尚未采全'}<p class="muted">${esc(n.id)}</p>`+button('查看 '+n.name+' 的成员间合作论文',[...new Set(s.edges.filter(e=>e.source===id||e.target===id).flatMap(e=>e.work_ids))]);
  bindEvidence($('groupSelection'));$('groupGraph').scrollIntoView({behavior:'smooth',block:'center'});
 }
 function renderGraph(){
  if(!data)return;
  const s=data.structure,groups=subgroupInfo(),focus=$('groupFocus').value,query=$('groupFindPerson').value.trim().toLowerCase();
  const nameCounts=new Map();s.nodes.forEach(n=>nameCounts.set(n.name,(nameCounts.get(n.name)||0)+1));
  const displayName=n=>n.name+(nameCounts.get(n.name)>1?' · '+n.id.slice(-5):'');
  const previousAlpha=graphSimulation?.alpha()??0;graphSimulation?.stop();
  const svg=d3.select('#groupGraph');svg.selectAll('*').remove();
  $('groupStructureStats').innerHTML=metric('合作子群',groups.length,'按成员间共著连接划分')+metric('有独立合作连线的成员',s.active_members-s.isolates,'目标作者未署名的论文')+metric('独立合作论文',s.independent_papers,`${s.window_start}–${s.window_end} 年`)+metric('成员历史覆盖',pct(s.history_coverage),`${s.complete_member_histories}/${s.active_members} 人`);
  $('groupStructureNote').textContent=`${s.window_start}–${s.window_end} 年 · 成员独立合作，不代表师生身份。`;
  const groupOf=new Map(groups.flatMap(g=>g.members.map(n=>[n.id,g.i]))),degree=new Map(s.nodes.map(n=>[n.id,0]));
  s.edges.forEach(e=>{degree.set(e.source,(degree.get(e.source)||0)+1);degree.set(e.target,(degree.get(e.target)||0)+1)});
  // Communities guide spatial anchors in one canvas; only observed papers create edges.
  // Keep velocity and resting coordinates when highlighting or resizing.
  const nodes=s.nodes.map(n=>{
   const previous=graphPositions.get(n.id),motion=previous?Object.fromEntries(['x','y','vx','vy','homeX','homeY'].map(k=>[k,previous[k]])):{};
   return {...n,...motion,color:groupOf.has(n.id)?groups[groupOf.get(n.id)].color:'#9aa8a3',degree:degree.get(n.id)||0};
  });
  const byId=new Map(nodes.map(n=>[n.id,n])),allLinks=s.edges.filter(e=>byId.has(e.source)&&byId.has(e.target));
  const isBridge=e=>(groupOf.get(e.source)??e.source)!==(groupOf.get(e.target)??e.target);
  const visibleLinks=allLinks.filter(e=>$('groupShowBridges').checked||!isBridge(e));
  if(selectedMember&&!byId.has(selectedMember))selectedMember=null;
  const layoutKey=JSON.stringify([data.focal,s.nodes.map(n=>[n.id,groupOf.get(n.id)]),allLinks.map(e=>[e.source,e.target,e.weight])]);
  const mobile=window.innerWidth<=650,width=mobile?600:900,height=mobile?700:650;
  svg.attr('viewBox',`0 0 ${width} ${height}`);
  const fit=()=>{
   if(!nodes.length)return d3.zoomIdentity;
   const minX=d3.min(nodes,n=>n.x)-85,maxX=d3.max(nodes,n=>n.x)+100,minY=d3.min(nodes,n=>n.y)-35,maxY=d3.max(nodes,n=>n.y)+35;
   const scale=Math.min(1.3,(width-40)/Math.max(1,maxX-minX),(height-40)/Math.max(1,maxY-minY));
   return d3.zoomIdentity.translate(width/2-scale*(minX+maxX)/2,height/2-scale*(minY+maxY)/2).scale(scale);
  };
  const newLayout=graphLayoutKey!==layoutKey;
  if(newLayout){
   // Pack soft community anchors, then bring actually connected communities closer.
   // These invisible layout anchors are not graph nodes or scientific measurements.
   const centers=groups.map(g=>({id:g.i,r:28+23*Math.sqrt(g.members.length)}));
   const loose=nodes.filter(n=>!groupOf.has(n.id)&&n.degree);
   loose.forEach(n=>centers.push({id:n.id,r:40}));
   d3.packSiblings(centers);
   const anchorOf=n=>groupOf.get(n.id)??n.id;
   const centerLinks=allLinks.filter(e=>anchorOf(byId.get(e.source))!==anchorOf(byId.get(e.target)))
    .map(e=>({source:anchorOf(byId.get(e.source)),target:anchorOf(byId.get(e.target))}));
   const centerSim=d3.forceSimulation(centers).randomSource(d3.randomLcg(42))
    .force('links',d3.forceLink(centerLinks).id(n=>n.id).distance(e=>e.source.r+e.target.r+16).strength(.15))
    .force('collide',d3.forceCollide(n=>n.r+8).iterations(3))
    .force('x',d3.forceX(0).strength(.08)).force('y',d3.forceY(0).strength(.08)).stop();
   centerSim.tick(100);
   const anchors=new Map(centers.map(n=>[n.id,n])),counts=new Map();
   const extentX=d3.max(centers,n=>Math.abs(n.x)+n.r)||100,extentY=d3.max(centers,n=>Math.abs(n.y)+n.r)||80;
   const isolated=nodes.filter(n=>!n.degree).sort((a,b)=>a.id.localeCompare(b.id));
   const ringX=Math.max(240,extentX+90,isolated.length*9),ringY=Math.max(200,extentY+75,isolated.length*7);
   for(const n of nodes){
    if(n.degree){
     const key=anchorOf(n),c=anchors.get(key),i=counts.get(key)||0;counts.set(key,i+1);
     const angle=i*Math.PI*(3-Math.sqrt(5)),radius=20*Math.sqrt(i);
     n.homeX=450+c.x;n.homeY=325+c.y;n.x=n.homeX+radius*Math.cos(angle);n.y=n.homeY+radius*Math.sin(angle);
    }else{
     const angle=2*Math.PI*isolated.indexOf(n)/Math.max(1,isolated.length)-Math.PI/2;
     n.homeX=n.x=450+ringX*Math.cos(angle);n.homeY=n.y=325+ringY*Math.sin(angle);
    }
    n.vx=n.vy=0;n.fx=n.fy=null;
   }
  }
  const linkForce=links=>d3.forceLink(links.map(e=>({...e}))).id(n=>n.id).distance(e=>44+18/Math.sqrt(e.weight||1)).strength(.45);
  const makeSimulation=(links=allLinks)=>d3.forceSimulation(nodes).randomSource(d3.randomLcg(42))
   .force('links',linkForce(links))
   .force('charge',d3.forceManyBody().strength(n=>n.degree?-95:-24).distanceMax(240))
   .force('collision',d3.forceCollide(n=>n.degree?19:14).iterations(2))
   .force('x',d3.forceX(n=>n.homeX).strength(n=>n.degree?.12:.5))
   .force('y',d3.forceY(n=>n.homeY).strength(n=>n.degree?.12:.5))
   .velocityDecay(.36).alphaDecay(.035).stop();
  graphSimulation=makeSimulation();
  if(newLayout){
   graphSimulation.tick(160);
   // Local resting positions retain the network's shape after a drag, while
   // observed links still transmit motion to neighbors. No permanent pinning.
   nodes.forEach(n=>{n.homeX=n.x;n.homeY=n.y;n.vx=n.vy=0});
   graphSimulation=makeSimulation(allLinks);graphSimulation.tick(100);
   graphTransform=fit();graphLayoutKey=layoutKey;
   if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
    nodes.forEach(n=>{n.x=450+(n.x-450)*.94;n.y=325+(n.y-325)*.94});
    graphSimulation.alpha(.45);
   }else graphSimulation.alpha(0);
  }else graphSimulation.alpha(previousAlpha);
  graphPositions=new Map(nodes.map(n=>[n.id,n]));
  const viewportKey=width+'x'+height;
  if(graphViewportKey!==viewportKey){graphTransform=fit();graphViewportKey=viewportKey}
  const layer=svg.append('g').attr('class','groupNetworkLayer');
  let updateLabels=()=>{};
  const zoom=d3.zoom().scaleExtent([.2,6]).on('zoom',event=>{graphTransform=event.transform;layer.attr('transform',event.transform);updateLabels()});
  svg.call(zoom).on('dblclick.zoom',null);svg.call(zoom.transform,graphTransform);
  const chosen=selectedMember?new Set([selectedMember,...visibleLinks.filter(e=>e.source===selectedMember||e.target===selectedMember).map(e=>e.source===selectedMember?e.target:e.source)]):null;
  const emphasized=n=>chosen?chosen.has(n.id):query?(n.name+' '+n.id).toLowerCase().includes(query):focus==='all'||String(groupOf.get(n.id))===focus;
  const lines=layer.append('g').attr('class','groupNetworkEdges').selectAll('line').data(visibleLinks).join('line')
   .attr('data-source',e=>e.source).attr('data-target',e=>e.target)
   .attr('stroke',e=>isBridge(e)?'#71878c':byId.get(e.source).color)
   .attr('stroke-opacity',e=>emphasized(byId.get(e.source))||emphasized(byId.get(e.target)) ? .38 : .04)
   .attr('stroke-dasharray',e=>isBridge(e)?'5 4':null)
   .attr('stroke-width',e=>Math.min(4,.7+Math.sqrt(e.weight))).attr('role','button').attr('tabindex',0)
   .attr('aria-label',e=>byId.get(e.source).name+' 与 '+byId.get(e.target).name+'，'+(e.work_ids.length+' 篇独立合作论文')+(isBridge(e)?' · 跨子群':''));
  const inspectEdge=(event,e)=>{event.stopPropagation();showEvidence(e.work_ids,byId.get(e.source).name+' ↔ '+byId.get(e.target).name+' · '+(e.work_ids.length+' 篇独立合作论文'),[byId.get(e.source).name,byId.get(e.target).name])};
  lines.on('click',inspectEdge).on('keydown',(event,e)=>{if(event.key==='Enter'){event.preventDefault();inspectEdge(event,e)}}).append('title').text(e=>byId.get(e.source).name+' ↔ '+byId.get(e.target).name+' · '+(e.work_ids.length+' 篇独立合作论文'));
  const node=layer.append('g').attr('class','groupNetworkNodes').selectAll('g').data(nodes).join('g')
   .attr('class','subgroupNode').attr('data-author',n=>n.id).attr('data-community',n=>groupOf.get(n.id)??'unassigned')
   .classed('memberSelected',n=>n.id===selectedMember).attr('role','button').attr('tabindex',0).attr('aria-label',n=>'定位成员 '+n.name).attr('data-i18n-names',n=>JSON.stringify([n.name]))
   .attr('opacity',n=>emphasized(n)?1:.16)
   .on('click',(event,n)=>{event.stopPropagation();selectMember(n.id)})
   .on('keydown',(event,n)=>{if(event.key==='Enter'){event.preventDefault();selectMember(n.id)}});
  node.append('circle').attr('r',n=>n.degree?7+Math.min(5,Math.sqrt(n.degree)):6).attr('fill',n=>n.color).attr('stroke','#ffffff').attr('stroke-width',2).attr('stroke-dasharray',n=>n.complete?null:'2 2');
  node.append('text').attr('x',n=>n.x<width/2?-13:13).attr('y',4).attr('text-anchor',n=>n.x<width/2?'end':'start')
   .attr('display',n=>$('groupShowNames').checked||n.id===selectedMember?null:'none')
   .text(n=>displayName(n));
  node.append('title').text(n=>displayName(n)+' · '+(groupOf.has(n.id)?'子群 '+(groupOf.get(n.id)+1):n.degree?'未归入多人子群':'当前没有独立合作连线')+' · '+n.id);
  const position=()=>{
   lines.attr('x1',e=>byId.get(e.source).x).attr('y1',e=>byId.get(e.source).y).attr('x2',e=>byId.get(e.target).x).attr('y2',e=>byId.get(e.target).y);
   node.attr('transform',n=>`translate(${n.x},${n.y})`);
  };
  const labelElements=new Map();node.each(function(n){labelElements.set(n.id,this.querySelector('text'))});
  updateLabels=()=>{
   const screenScale=(svg.node().getBoundingClientRect().width||width)/width;
   const font=(mobile?11:12)/Math.max(.15,graphTransform.k*screenScale),boxes=[];
   node.select('text').style('font-size',font+'px').attr('x',n=>n.x<450?-13:13).attr('text-anchor',n=>n.x<450?'end':'start');
   const priority=[...nodes].sort((a,b)=>(b.id===selectedMember)-(a.id===selectedMember)||b.degree-a.degree||a.id.localeCompare(b.id));
   for(const n of priority){
    const text=labelElements.get(n.id),w=displayName(n).length*font*.58+6;
    const x=n.x<450?n.x-13-w:n.x+13,box={x,y:n.y-font*.8,w,h:font*1.2};
    const collision=boxes.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y);
    const inFrame=graphTransform.applyX(box.x)>=8&&graphTransform.applyX(box.x+box.w)<=width-8&&graphTransform.applyY(box.y)>=8&&graphTransform.applyY(box.y+box.h)<=height-8;
    const show=n.id===selectedMember||($('groupShowNames').checked&&emphasized(n)&&!collision&&inFrame);
    text.setAttribute('display',show?'inline':'none');if(show)boxes.push(box);
   }
  };
  node.on('mouseenter',function(){d3.select(this).raise().select('text').attr('display',null)}).on('mouseleave',updateLabels);
  position();updateLabels();
  let frame=0;
  const simulation=graphSimulation;
  simulation.on('tick',()=>{position();if(++frame%3===0)updateLabels()})
   .on('end',()=>{position();updateLabels();svg.attr('data-motion','settled')});
  const wake=alpha=>{svg.attr('data-motion','running');simulation.alpha(Math.max(simulation.alpha(),alpha)).restart()};
  svg.attr('data-motion',simulation.alpha()>simulation.alphaMin()?'running':'settled');
  if(simulation.alpha()>simulation.alphaMin()&&!document.hidden&&!$('groups').hidden)simulation.restart();
  node.call(d3.drag().clickDistance(4)
   .on('start',function(event,n){d3.select(this).raise().classed('dragging',true);n.fx=n.x;n.fy=n.y;if(!event.active)simulation.alphaTarget(.22);wake(.55)})
   .on('drag',(event,n)=>{n.fx=n.x=event.x;n.fy=n.y=event.y;position();updateLabels()})
   .on('end',function(event,n){d3.select(this).classed('dragging',false);n.fx=n.fy=null;if(!event.active)simulation.alphaTarget(0);wake(.65)}));
  $('groupFitGraph').onclick=()=>{graphTransform=fit();svg.call(zoom.transform,graphTransform)};
  if(!s.nodes.length)layer.append('text').attr('x',30).attr('y',80).text('当前窗口没有成员，可调整范围或补全历史。');
  const bridgeCount=allLinks.filter(isBridge).length;
  $('groupGraphHint').textContent=`${s.nodes.length} 位圈内成员 · 当前显示 ${visibleLinks.length}/${allLinks.length} 条合作边（跨子群 ${bridgeCount} 条）。颜色区分子群。拖动节点，滚轮缩放；点击连线看论文。`;
  $('groupGraph').setAttribute('aria-label','成员独立合作网络，颜色区分子群');
  $('groupSelection').textContent=focus==='all'?'点击成员高亮本人和直接合作者；点击连线查看论文依据。':`已在完整网络中高亮子群 ${Number(focus)+1}，其他成员和跨群关系仍保留。`;
  $('groupGraphLegend').innerHTML=groups.map(g=>`<button class="chip" data-legend-group="${g.i}" aria-pressed="${String(g.i)===focus}"><i style="background:${g.color}"></i>子群 ${String(g.i+1).padStart(2,'0')} · ${g.members.length}</button>`).join('')+'<span class="muted"><i style="background:#9aa8a3"></i>未归入多人子群</span>';
  $('groupGraphLegend').querySelectorAll('[data-legend-group]').forEach(b=>b.onclick=()=>focusGroup(b.dataset.legendGroup));
  const cards=groups.filter(g=>(focus==='all'||String(g.i)===focus)&&(!query||g.members.some(n=>(n.name+' '+n.id).toLowerCase().includes(query))));
  $('groupSubgroups').innerHTML=cards.map(g=>`<article class="subgroupCard" style="--subgroup-color:${g.color}"><button class="subgroupCardHeading" data-focus-group="${g.i}" aria-pressed="${String(g.i)===focus}"><span>子群 ${String(g.i+1).padStart(2,'0')}</span><strong>${g.members.length} 人</strong></button><p class="muted">${g.papers.length} 篇内部合作论文 · ${g.external.length} 条跨群连接</p><div class="subgroupNames">${g.members.map(n=>`<button data-group-member="${esc(n.id)}" title="${esc(n.id)}" class="${query&&(n.name+' '+n.id).toLowerCase().includes(query)?'personMatch':''}">${esc(displayName(n))}${n.complete?'':' ◌'}</button>`).join('')}</div><div class="subgroupCardActions">${button('内部论文 · '+g.papers.length,g.papers)}${g.outsidePapers.length?button('跨群论文 · '+g.outsidePapers.length,g.outsidePapers):''}</div></article>`).join('')||'<p class="empty">没有匹配的子群成员。请清除搜索或查看下方未连接成员。</p>';
  $('groupSubgroups').querySelectorAll('[data-focus-group]').forEach(b=>b.onclick=()=>focusGroup(b.dataset.focusGroup));
  $('groupSubgroups').querySelectorAll('[data-group-member]').forEach(b=>b.onclick=()=>selectMember(b.dataset.groupMember));bindEvidence($('groupSubgroups'));
  const assigned=new Set(groups.flatMap(g=>g.members.map(n=>n.id))),isolates=s.nodes.filter(n=>!assigned.has(n.id));
  $('groupIsolatesSummary').textContent=`未归入多人子群的成员 · ${isolates.length} 人`;
  $('groupIsolateMembers').innerHTML=isolates.filter(n=>!query||(n.name+' '+n.id).toLowerCase().includes(query)).map(n=>`<button class="chip" data-group-member="${esc(n.id)}">${esc(n.name)}</button>`).join('')||'<p class="muted">没有匹配的成员。</p>';
  $('groupIsolateMembers').querySelectorAll('[data-group-member]').forEach(b=>b.onclick=()=>selectMember(b.dataset.groupMember));
 }
 $('groupFocus').onchange=()=>{selectedMember=null;$('groupFindPerson').value='';renderGraph()};
 $('groupFindPerson').oninput=()=>{selectedMember=null;$('groupFocus').value='all';renderGraph()};
 $('groupShowBridges').onchange=renderGraph;
 $('groupShowNames').onchange=renderGraph;
 $('groupResetFocus').onclick=()=>focusGroup('all');
 const syncMotion=()=>{if(!graphSimulation)return;if(document.hidden||$('groups').hidden){graphSimulation.stop()}else if(graphSimulation.alpha()>graphSimulation.alphaMin())graphSimulation.restart()};
 document.addEventListener('visibilitychange',syncMotion);
 new MutationObserver(syncMotion).observe($('groups'),{attributes:true,attributeFilter:['hidden']});
 let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(data)renderGraph()},150)});
 function render(){
  const s=data.summary,p=data.parameters;
  $('groupResults').hidden=false;$('groupExport').disabled=false;
  $('groupSummary').innerHTML=metric('首次进入者',s.entrants,`${p.start}–${p.end} 年`)+metric('科研早期进入者',s.early_career,'达到发表年限与篇数条件')+metric('已有发表经历',s.experienced,'首次进入此合作圈')+metric('等待获取历史',readiness(data.cohorts).pending,'在线获取后自动更新')+metric('资料仍不足',readiness(data.cohorts).unresolved,'身份或年份等证据有缺口');
  $('groupCoverage').textContent=`发表经历可分类覆盖 ${pct(s.age_classification_coverage)}。已分类者中科研早期占 ${pct(s.early_career_share_of_classified)}；考虑未知记录，科研早期人数可能在 ${s.early_career_count_bounds.join('–')} 人之间（缺失数据边界，不是置信区间）。以下后续协作指标仅使用 ${s.assessed} 位观察期已满且历史可用的科研早期进入者，另有 ${s.right_censored} 位观察期未满。获取次序受论文量与并发调度影响，已分类者不是随机样本，不能把其比例外推至整个合作圈。`;
  $('groupCoverage').textContent+=' 未知原因：'+(Object.entries(s.unknown_reasons||{}).map(([k,n])=>(missingNames[k]||k)+' '+n+' 人').join('；')||'无未知记录')+'。';
  const ready=readiness(data.cohorts);
  data.data_readiness={...ready,complete_member_histories:data.members.filter(m=>m.history_complete).length,total_member_histories:data.members.length,meaning:'pending means history not yet fetched or incomplete; unresolved means remaining evidence issues. Neither implies early career.'};
  const byYear=year=>readiness(data.cohorts.filter(r=>r.entry_year===year));
  const largest=Math.max(1,...data.annual.map(r=>r.entrants));
  $('groupAnnualChart').innerHTML='<div class="groupLegend"><span><i class="groupEarly"></i>科研早期</span><span><i class="groupExperienced"></i>已有发表经历</span><span><i class="groupPending"></i>等待获取历史</span><span><i class="groupUnknown"></i>资料仍不足</span></div>'+data.annual.map(r=>`<div class="groupAnnualRow"><span>${r.year}</span><div class="groupAnnualBar" title="${r.year}：科研早期 ${r.early_career}，已有经历 ${r.experienced}，等待获取 ${byYear(r.year).pending}，资料不足 ${byYear(r.year).unresolved}">${[['groupEarly',r.early_career],['groupExperienced',r.experienced],['groupPending',byYear(r.year).pending],['groupUnknown',byYear(r.year).unresolved]].map(([c,n])=>`<span class="${c}" style="width:${100*n/largest}%"></span>`).join('')}</div><span>${r.entrants} 人</span></div>`).join('');
  $('groupAnnual').innerHTML=table(['进入年','首次进入','科研早期','已有经历','等待获取','资料不足','分类覆盖','窗口活跃人数','可跟踪早期人数','持续成员协作'],data.annual.map(r=>[r.year,r.entrants,r.early_career,r.experienced,byYear(r.year).pending,byYear(r.year).unresolved,pct(r.age_classification_coverage),r.active_circle_members,r.assessed,r.assessed?`${r.persistent_peer_count}/${r.assessed}`:'—']));
  $('groupOutcomes').innerHTML=metric('目标作者参与',pct(s.focal_mean_share),'按人等权的早期论文参与比例')+metric('有既有成员协作',pct(s.peer_supported_rate),`${s.peer_supported_count}/${s.assessed} 位进入者`)+metric('有持续成员协作',pct(s.persistent_peer_rate),`${s.persistent_peer_count}/${s.assessed} 位进入者`)+metric(`第 ${p.followup} 年同圈合作`,pct(s.circle_continuation_rate),`${s.circle_continuation_count}/${s.assessed} 位进入者`)+metric(`第 ${p.followup} 年仍有发表`,pct(s.publication_continuation_rate),`${s.publication_continuation_count}/${s.assessed} 位进入者`);
  $('groupOutcomeNote').textContent=`观察入圈当年至第 ${p.followup} 年的前 ${p.early_papers} 篇（第 K 篇所在年全部保留），包括目标作者未署名的论文；协作统计排除超过 ${p.max_team} 位作者的论文。入圈依据必然有目标作者署名，因此参与比例存在这一选择条件，不等于指导投入。第 H 年指恰好入圈年 + H，未见发表不等于退出。`;
  $('groupCohortYear').innerHTML='<option value="">全部年份</option>'+data.annual.map(r=>`<option value="${r.year}">${r.year}</option>`).join('');renderCohorts();
  $('groupPeers').innerHTML=data.peer_support.length?table(['既有成员','合作科研早期人数','跨年持续人数','论文证据'],data.peer_support.map(r=>[sourceHTML(r.name),r.newcomer_ids.length,r.persistent_newcomer_ids.length,button(r.work_ids.length+' 篇',r.work_ids)])):'<p class="empty">尚无满足当前定义且资料足够的协作记录；可检查成员历史覆盖或调整窗口。</p>';bindEvidence($('groupPeers'));
  $('groupFocus').innerHTML='<option value="all">全部子群</option>'+data.structure.observed_subgroups.map((g,i)=>`<option value="${i}">子群 ${String(i+1).padStart(2,'0')} · ${g.members.length} 人</option>`).join('');
  $('groupFindPerson').value='';renderGraph();
  $('groupAudit').textContent=JSON.stringify({version:data.version,parameters:data.parameters,assessment_counts:s.assessment_counts,boundary_exclusions:data.coverage.boundary_exclusions,excluded_records:data.coverage.excluded_records,input_sha256:data.input_sha256},null,2);
 }
 function describeResult(){
  const ready=readiness(data.cohorts);
  $('groupStatus').textContent=`已完成 · ${data.members.length} 位成员${ready.unresolved?' · '+ready.unresolved+' 位资料不足':''}`;
 }
 async function ensureCollection(id,e,r,params){
  let s=await api('groups/'+id+'/collection');if(!valid(id,e)||r!==request)return;
  if(s.status!=='running'){
   try{await api('groups/'+id+'/auto',params)}
   catch(error){
    // Another tab may have started this same collection after our status read.
    const current=await api('groups/'+id+'/collection');
    if(current.status!=='running')throw error;
   }
   if(!valid(id,e)||r!==request)return;
   completionSeen=null;
  }
  await refreshCollection();
 }
 async function calculate({completeHistory=true}={}){
  const id=active,e=epoch;if(!id)return;clearResult();const r=request;
  calculating=true;$('groupRun').disabled=true;$('groupStatus').textContent='正在计算…';
  try{
   const s=await api('groups/'+id+'/collection');if(!valid(id,e)||r!==request)return;
   if(s.status==='running'){
    await refreshCollection();return;
   }
   const value=await computeResult('groups',id,parameters(),message=>{if(valid(id,e)&&r===request)$('groupStatus').textContent=message},()=>valid(id,e)&&r===request);
   if(!valid(id,e)||r!==request)return;
   const missing=value.members.filter(m=>!m.history_complete).length;
   if(missing){
    $('groupStatus').textContent=`正在补全 ${missing} 位成员的论文…`;
    if(completeHistory)await ensureCollection(id,e,r,value.parameters);
    else $('groupStatus').textContent=`仍有 ${missing} 位成员待获取，请继续分析。`;
    return;
   }
   data=value;render();describeResult();$('groupCollection').hidden=true;
  }
  catch(error){if(valid(id,e)&&r===request){data=null;$('groupResults').hidden=true;$('groupExport').disabled=true;$('groupStatus').textContent='未完成：'+error.message+'。请重试。'}}
  finally{if(valid(id,e)&&r===request){calculating=false;$('groupRun').disabled=collectionRunning;$('groupRun').textContent=collectionRunning?'分析中…':data?'重新分析':'开始分析'}}
 }
 $('groupRun').onclick=()=>calculate();
 $('groupPlan').onclick=async()=>{
  const id=active,e=epoch,r=++planRequest;if(!id)return;proposal=null;$('groupPlan').disabled=true;$('groupCollect').disabled=true;$('groupPlanInfo').textContent='正在检查本次数据和缺失历史…';
  try{const p=await api('groups/'+id+'/plan?'+new URLSearchParams({...parameters(),limit:Number($('groupLimit').value)}));if(!valid(id,e)||r!==planRequest)return;proposal=p;$('groupPlanInfo').innerHTML=`<p>${p.member_count} 位圈内成员中 ${p.complete_histories} 位已有完整历史，仍缺 ${p.missing_histories} 位；本批 ${p.authors.length} 位。已知约 ${p.known_estimated_pages} 页请求，另有 ${p.unknown_cost_authors} 位请求量未知。</p><p class="muted">${esc(p.note)}</p>`+p.authors.map(a=>`<span class="chip">${sourceHTML(a.name)} · ${a.entry_year} 年入圈 · ${a.estimated_pages==null?'页数未知':'约 '+a.estimated_pages+' 页'}</span>`).join('');$('groupCollect').disabled=!p.authors.length}
  catch(error){if(valid(id,e)&&r===planRequest)$('groupPlanInfo').textContent='预览失败：'+error.message}
  finally{if(valid(id,e)&&r===planRequest)$('groupPlan').disabled=false}
 };
 async function refreshCollection(){
  clearTimeout(timer);if(refreshing){timer=setTimeout(refreshCollection,2000);return}
  const id=active,e=epoch;if(!id)return;refreshing=true;let running=false;
  try{
   const s=await api('groups/'+id+'/collection');if(!valid(id,e))return;
   running=s.status==='running';collectionRunning=running;
   const names={not_started:'尚未开始',running:'正在获取论文',paused:'已暂停',error:'获取中断',interrupted:'获取中断',complete:'论文已获取'};
   $('groupCollection').hidden=s.status==='not_started'||s.status==='complete';
   $('groupCollectionStatus').textContent=`${names[s.status]||s.status} · ${s.completed||0}/${s.total||0} 位成员${s.elapsed_seconds!=null?' · '+Math.round(s.elapsed_seconds)+' 秒':''}${['error','interrupted'].includes(s.status)&&s.message?' · '+s.message:''}`;
   $('groupPause').hidden=!running;$('groupRun').disabled=running||calculating;
   $('groupRun').textContent=running?'分析中…':data?'重新分析':['paused','error','interrupted'].includes(s.status)?'继续分析':'开始分析';
   if(!sameParameters(s)){
    if(running)$('groupCollectionStatus').textContent+=' · 另一范围正在获取，可暂停后重新分析。';
    return;
   }
   if(running||['paused','error','interrupted'].includes(s.status)){
    graphSimulation?.stop();$('groupResults').hidden=true;$('groupExport').disabled=true;
    $('groupStatus').textContent=running?'获取完成后自动显示结果。':s.status==='paused'?'已暂停，点击继续分析。':'获取中断，请重试。';
   }
   // Never render a partial portrait. One final calculation follows completion.
   if(s.status==='complete'&&completionSeen!==s.updated_at){
    completionSeen=s.updated_at;await calculate({completeHistory:false});
   }
  }
  catch(error){if(valid(id,e)){$('groupCollection').hidden=false;$('groupCollectionStatus').textContent='进度读取失败：'+error.message+'。请刷新进度。';$('groupPause').hidden=false}}
  finally{refreshing=false;if(valid(id,e)&&running)timer=setTimeout(refreshCollection,2500)}
 }
 $('groupCollectionRefresh').onclick=refreshCollection;

 $('groupCollect').onclick=async()=>{
  if(!proposal)return;const id=active,e=epoch,p=proposal;$('groupCollect').disabled=true;
  try{await api('groups/'+id+'/collect',{...p.parameters,limit:p.limit,plan_sha256:p.plan_sha256});if(!valid(id,e))return;proposal=null;await refreshCollection()}
  catch(error){if(valid(id,e)){$('groupCollectionStatus').textContent='未能开始：'+error.message;proposal=null;$('groupPlanInfo').textContent='请处理上述问题后重新预览。'}}
 };
 $('groupPause').onclick=async()=>{const id=active,e=epoch;try{await api('groups/'+id+'/pause',{});if(valid(id,e))await refreshCollection()}catch(error){if(valid(id,e))$('groupCollectionStatus').textContent='暂停未确认：'+error.message+'。请重试。'}};
 $('groupExport').onclick=()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=data.focal.split('/').pop()+'-group-cohorts.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 document.querySelector('[data-tab="groups"]').addEventListener('click',refreshCollection);
})();
