/* Original implementation of community-seeded force layout, using D3 (ISC). */
let networkSimulation, networkZoom, networkSvg, lastNetwork, filteredNetwork;
const networkPositions=new Map();
const communityColors=['#46775e','#b78043','#667cb8','#aa6685','#529a9e','#8b78a9','#8a913f','#c28063'];
window.resetNetwork=function(){
 if(networkSimulation)networkSimulation.stop();
 networkSimulation=null;networkSvg=null;networkZoom=null;lastNetwork=null;filteredNetwork=null;networkPositions.clear();
 for(const id of ['graph','communityLegend','collaborators'])document.getElementById(id).replaceChildren();
 document.getElementById('graphSummary').textContent='正在读取当前学者的网络…';
 document.getElementById('nodeDetail').textContent='加载后点击节点查看论文依据。';
 document.getElementById('communityFilter').replaceChildren(new Option('全部社区',''));
 document.getElementById('nodeSearch').value='';
 for(const id of ['edgeKind','edgeInstitution','edgeRepeat'])document.getElementById(id).value='all';
};
window.drawNetwork=function(report,onEvidence){
  const sameAuthor=lastNetwork?.report.focal_author_id===report.focal_author_id;
  if(sameAuthor&&networkSimulation)for(const n of networkSimulation.nodes())networkPositions.set(n.id,[n.x,n.y]);
  if(!sameAuthor)networkPositions.clear();
  const previousZoom=sameAuthor&&networkSvg?d3.zoomTransform(networkSvg.node()):d3.zoomIdentity;
  lastNetwork={report,onEvidence};
  if(networkSimulation)networkSimulation.stop();
  const control=id=>document.getElementById(id), graph=report.graph, focal=report.focal_author_id;
  const previous=control('communityFilter').value;
  control('communityFilter').replaceChildren(new Option('全部社区',''),...graph.communities.map(c=>new Option(`C${c.id+1} · ${c.label} (${c.size})`,c.id)));
  control('communityFilter').value=previous;
  const min=Number(control('minShared').value)||1, limit=Number(control('maxNodes').value)||100;
  const community=control('communityFilter').value, query=control('nodeSearch').value.toLowerCase();
  const edgeKind=control('edgeKind').value, edgeInstitution=control('edgeInstitution').value, edgeRepeat=control('edgeRepeat').value;
  const matchingEdges=graph.edges.filter(e=>(edgeKind==='all'||e.semantics?.kind===edgeKind)
    &&(edgeInstitution==='all'||e.semantics?.institution_work_ids[edgeInstitution]?.length)
    &&(edgeRepeat==='all'||edgeRepeat==='single'&&e.weight_raw===1||edgeRepeat==='multiple'&&e.weight_raw>=2||edgeRepeat==='cross_year'&&e.active_years.length>=2));
  const endpoints=new Set(matchingEdges.flatMap(e=>[e.source,e.target]));
  const people=graph.nodes.filter(n=>n.id!==focal&&endpoints.has(n.id)&&n.shared_count>=min&&(community===''||n.community===Number(community))).sort((a,b)=>b.shared_count-a.shared_count||a.id.localeCompare(b.id));
  const visible=people.slice(0,limit), center=graph.nodes.find(n=>n.id===focal);
  const nodes=[center,...visible].filter(Boolean).map(n=>({...n})), ids=new Set(nodes.map(n=>n.id));
  const allEdges=matchingEdges.filter(e=>ids.has(e.source)&&ids.has(e.target));
  const direct=allEdges.filter(e=>e.source===focal||e.target===focal);
  const colinks=allEdges.filter(e=>e.source!==focal&&e.target!==focal).sort((a,b)=>b.weight_fractional-a.weight_fractional).slice(0,Number(control('maxLinks').value)||500);
  const links=[...direct,...colinks].map(e=>({...e}));
  const linkedIds=new Set(links.flatMap(e=>[e.source,e.target]));
  for(let i=nodes.length-1;i>=0;i--)if(nodes[i].id!==focal&&!linkedIds.has(nodes[i].id))nodes.splice(i,1);
  for(let i=visible.length-1;i>=0;i--)if(!linkedIds.has(visible[i].id))visible.splice(i,1);
  filteredNetwork={focal,window:graph.window,snapshot:graph.snapshot,filters:{edgeKind,edgeInstitution,edgeRepeat,minShared:min,maxNodes:limit,maxColinks:Number(control('maxLinks').value)},
    matching_edge_count:matchingEdges.length,nodes:JSON.parse(JSON.stringify(nodes)),edges:JSON.parse(JSON.stringify(links)),
    note:'Filters select whole edges within the publication window. Institution evidence subsets may overlap. Communities are computed before display filtering.'};
  control('nodeDetail').textContent=links.length?'点击一条线，查看关系含义、机构证据与逐年共同论文。':'没有满足当前组合条件的边，请放宽筛选。';
  const communities=[...new Set(visible.map(n=>n.community))].sort((a,b)=>a-b);
  const anchors=new Map(communities.map((c,i)=>[c,[500+260*Math.cos(i*2*Math.PI/communities.length),330+220*Math.sin(i*2*Math.PI/communities.length)]]));
  const grouped=d3.group(visible,d=>d.community);
  for(const n of nodes){const group=grouped.get(n.community)||[],i=group.findIndex(x=>x.id===n.id),a=anchors.get(n.community)||[500,330];n.x=a[0]+45*Math.cos(i*2.399);n.y=a[1]+45*Math.sin(i*2.399);const size=control('nodeSize').value==='citations'?(n.cited_by_count||0):n.shared_count;n.r=n.id===focal?19:Math.min(24,5+Math.sqrt(size)*1.7);if(n.id===focal){n.x=500;n.y=330;n.fx=500;n.fy=330}}
  for(const n of nodes){const saved=networkPositions.get(n.id);if(saved&&n.id!==focal){n.x=saved[0];n.y=saved[1]}}
  networkSvg=d3.select('#graph');networkSvg.selectAll('*').remove();
  networkSvg.attr('viewBox','0 0 1000 660');
  const viewport=networkSvg.append('g');
  networkZoom=d3.zoom().scaleExtent([.2,6]).on('zoom',e=>viewport.attr('transform',e.transform));networkSvg.call(networkZoom).on('dblclick.zoom',null);networkSvg.call(networkZoom.transform,previousZoom);
  const link=viewport.append('g').selectAll('line').data(links).join('line').attr('class','network-edge').attr('role','button').attr('tabindex',0).attr('aria-label',d=>'查看合作边 '+d.source+' — '+d.target).attr('stroke',d=>d.source===focal||d.target===focal?'#829b8a':'#8c9692').attr('stroke-opacity',.35).attr('stroke-width',d=>Math.min(6,.7+Math.sqrt(d.weight_fractional))).attr('stroke-dasharray',d=>d.source===focal||d.target===focal?null:'4 3');
  link.append('title').text(e=>`${e.semantics?.kind==='focal_coauthor'?'目标作者与合作者共同署名':'合作者在目标作者论文内共同署名'}\n${e.first_observed_year}–${e.last_observed_year} · ${e.weight_raw} 篇共同论文\n${(e.yearly_weights||[]).map(y=>y.year+': '+y.weight_raw+' 篇').join(' / ')}\n仅这些年份有发表记录，不代表持续合作。`);
  function inspectEdge(event,e){
   event.stopPropagation();const panel=control('nodeDetail');panel.replaceChildren();
   const heading=document.createElement('h3');heading.innerHTML='合作边 · '+sourceHTML(e.source.name)+' — '+sourceHTML(e.target.name);panel.append(heading);
   const meaning=document.createElement('p');meaning.className='modelNote';meaning.textContent=e.semantics?.kind==='focal_coauthor'
    ?'绿色实线：这两位作者在当前时间范围内共同署名。它是无方向的发表关系，不能据此认定谁指导谁。'
    :'灰色虚线：这两位合作者出现在目标作者参与的同一篇论文中。这不证明他们在目标作者未参与时也有独立合作；独立合作证据请看「团队与新人」。';panel.append(meaning);
   const note=document.createElement('p');note.textContent=`观察年份 ${e.active_years.join('、')} · 当前窗口 ${e.weight_raw} 篇 · 分数权重 ${e.weight_fractional.toFixed(3)}（每篇贡献 1 / [全部作者数 − 1]）。线越粗表示分数共著权重越大，不表示指导强度。仅这些年份有发表记录，不假设间隔年持续合作。`;panel.append(note);
   const evidenceButton=(text,ids)=>{const b=document.createElement('button');b.className='chip';b.textContent=text;b.disabled=!ids.length;b.onclick=()=>onEvidence(ids,text);panel.append(b)};
   evidenceButton('全部共同论文 · '+e.work_ids.length+' 篇',e.work_ids);
   for(const [kind,label] of Object.entries({shared:'同篇共同机构',disjoint:'同篇机构无交集',unknown:'同篇机构缺失'})){
    const ids=e.semantics?.institution_work_ids[kind]||[];evidenceButton(label+' · '+ids.length+' 篇',ids);
   }
   const scope=document.createElement('p');scope.textContent='机构依据来自当篇署名，不是当前单位或任职证明；一条边可在不同论文中具有不同机构状态。社区颜色来自筛选前的共著图，不是关系身份标签。';panel.append(scope);
   for(const year of e.yearly_weights)evidenceButton(year.year+' 年 · '+year.weight_raw+' 篇',year.work_ids);
  }
  link.style('cursor','pointer').on('click',inspectEdge).on('keydown',(event,e)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspectEdge(event,e)}});
  const linkHit=viewport.append('g').selectAll('line').data(links).join('line').attr('stroke','transparent').attr('stroke-width',16).attr('aria-hidden','true').style('cursor','pointer').on('click',inspectEdge);
  const node=viewport.append('g').selectAll('g').data(nodes).join('g').attr('role','button').attr('tabindex',0).attr('aria-label',d=>d.name).attr('data-i18n-names',d=>JSON.stringify([d.name])).attr('opacity',d=>!query||d.name.toLowerCase().includes(query)?1:.2);
  node.append('circle').attr('r',d=>d.r).attr('fill',d=>d.id===focal?'#244d3b':communityColors[d.community%communityColors.length]).attr('stroke','#ffffff').attr('stroke-width',2);
  node.append('text').attr('dx',d=>d.r+4).attr('dy',4).text(d=>d.name).style('font-size','11px').style('pointer-events','none').style('display',d=>control('showLabels').checked&&(d.id===focal||visible.slice(0,25).some(n=>n.id===d.id)||query&&d.name.toLowerCase().includes(query))?null:'none');
  node.append('title').text(d=>`${d.name}\n共同论文 ${d.shared_count}\n首次/末次合作 ${d.first_shared_year}–${d.last_shared_year}\n当前生涯引用（非历史） ${d.cited_by_count??'未补全'}`);
  function inspect(event,d){if(event)event.stopPropagation();const adjacent=new Set([d.id]);for(const e of links){const a=e.source.id,b=e.target.id;if(a===d.id)adjacent.add(b);if(b===d.id)adjacent.add(a)}node.attr('opacity',n=>adjacent.has(n.id)?1:.13);node.select('text').style('display',n=>adjacent.has(n.id)&&control('showLabels').checked?null:'none');link.attr('stroke-opacity',e=>e.source.id===d.id||e.target.id===d.id?.9:.08);const panel=control('nodeDetail');panel.replaceChildren();const title=document.createElement('h3');title.textContent=d.name;title.setAttribute('translate','no');panel.append(title);const info=document.createElement('p');info.setAttribute('data-i18n-names',JSON.stringify(Object.values(d.institutions)));info.textContent=`共同论文 ${d.shared_count} · ${d.first_shared_year}–${d.last_shared_year} · 当前生涯引用（非历史） ${d.cited_by_count??'尚未补全'} · ${Object.values(d.institutions).join(' / ')||'机构未提供'}`;panel.append(info);const button=document.createElement('button');button.textContent='查看共同论文证据 →';button.onclick=()=>onEvidence(d.work_ids,d.name,[d.name]);panel.append(button);const years=document.createElement('p');years.textContent='有合作发表的年份：'+(d.active_years||[]).join('、');panel.append(years);const a=document.createElement('a');a.href=d.id;a.target='_blank';a.rel='noreferrer';a.textContent=' OpenAlex 主页 ↗';panel.append(a)}
  node.on('click',inspect).on('keydown',(e,d)=>{if(e.key==='Enter')inspect(e,d)}).on('contextmenu',(e,d)=>{e.preventDefault();window.open(d.id,'_blank','noopener')});
  networkSvg.on('click',()=>{node.attr('opacity',1);link.attr('stroke-opacity',.35);control('nodeDetail').textContent='点击节点查看邻居与论文依据。'});
  networkSimulation=d3.forceSimulation(nodes).randomSource(d3.randomLcg(.42)).force('link',d3.forceLink(links).id(d=>d.id).distance(d=>70+110/(1+Math.sqrt(d.weight_fractional))).strength(.13)).force('charge',d3.forceManyBody().strength(-110)).force('collision',d3.forceCollide().radius(d=>d.r+9)).force('clusterX',d3.forceX(d=>(anchors.get(d.community)||[500,330])[0]).strength(.12)).force('clusterY',d3.forceY(d=>(anchors.get(d.community)||[500,330])[1]).strength(.12)).force('cohesion',alpha=>{const centroids=d3.rollup(nodes.filter(n=>n.id!==focal),ns=>[d3.mean(ns,n=>n.x),d3.mean(ns,n=>n.y)],n=>n.community);for(const n of nodes){const c=centroids.get(n.community);if(c){n.vx+=(c[0]-n.x)*alpha*.025;n.vy+=(c[1]-n.y)*alpha*.025}}}).on('tick',()=>{linkHit.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);node.attr('transform',d=>`translate(${d.x},${d.y})`)});
  node.call(d3.drag().on('start',(e,d)=>{if(!e.active)networkSimulation.alphaTarget(.2).restart();d.fx=d.x;d.fy=d.y}).on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y}).on('end',(e,d)=>{if(!e.active)networkSimulation.alphaTarget(0);if(d.id!==focal){d.fx=null;d.fy=null}}));
  control('graphSummary').textContent=`展示 ${nodes.filter(n=>n.id!==focal).length} / ${graph.nodes.length-1} 位合作者，${links.length} 条边（条件匹配 ${matchingEdges.length} 条，节点和边数上限可能进一步截断） · ${graph.communities.length} 个社区 · Louvain 分辨率 ${graph.resolution} · 同色表示共著社区，不代表师生或实验室。`;
  control('communityLegend').replaceChildren(...communities.map(c=>{const span=document.createElement('span');span.className='legendItem';span.style.color=communityColors[c%communityColors.length];span.dataset.i18nNames=JSON.stringify([graph.communities.find(x=>x.id===c)?.label||'']);span.textContent=`● C${c+1} ${graph.communities.find(x=>x.id===c)?.label||''}`;return span}));
  control('collaborators').replaceChildren();
};
window.addEventListener('DOMContentLoaded',()=>{
  for(const id of ['minShared','maxNodes','maxLinks','communityFilter','nodeSize','edgeKind','edgeInstitution','edgeRepeat','showLabels'])document.getElementById(id).onchange=()=>{if(lastNetwork)window.drawNetwork(lastNetwork.report,lastNetwork.onEvidence)};
  let debounce;document.getElementById('nodeSearch').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>{if(lastNetwork)window.drawNetwork(lastNetwork.report,lastNetwork.onEvidence)},250)};
  document.getElementById('resetGraph').onclick=()=>{if(networkSvg)networkSvg.transition().call(networkZoom.transform,d3.zoomIdentity)};
  document.getElementById('exportFilteredGraph').onclick=()=>{if(!filteredNetwork)return;const url=URL.createObjectURL(new Blob([JSON.stringify(filteredNetwork,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='filtered-collaboration-edges.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
  document.getElementById('exportGraph').onclick=()=>{
   const original=document.getElementById('graph'),svg=original.cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
   // Standalone SVGs cannot rely on the page stylesheet or CSS variables.
   const sources=original.querySelectorAll('*'),copies=svg.querySelectorAll('*');
   sources.forEach((source,i)=>{const style=getComputedStyle(source);for(const property of ['fill','stroke','stroke-width','stroke-opacity','fill-opacity','opacity','font-family','font-size','font-weight','paint-order','stroke-linejoin','display'])copies[i].style.setProperty(property,style.getPropertyValue(property))});
   const backdrop=document.createElementNS('http://www.w3.org/2000/svg','rect');
   for(const [name,value]of Object.entries({x:0,y:0,width:1000,height:660,fill:'#f5f8f2','data-export-background':'true'}))backdrop.setAttribute(name,value);
   svg.insertBefore(backdrop,svg.firstChild);
   const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download='collaboration-network.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
});
