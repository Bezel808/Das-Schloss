let insightData=null,insightRequest=0;
const numberOrDash=(v,d=3)=>v===null||v===undefined?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
function table(headers,rows){return '<div class="dataScroll"><table class="dataTable"><thead><tr>'+headers.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}
async function loadInsights(){
 const id=active,request=++insightRequest;if(!id)return;
 $('insightRun').disabled=true;$('insightStatus').textContent='正在计算个人年度统计…';
 try{
  const params=new URLSearchParams({start:$('insightStart').value,end:$('insightEnd').value,window:$('insightWindow').value});
  const data=await computeResult('insights',id,Object.fromEntries([...params].map(([k,v])=>[k,Number(v)])),message=>{if(active===id&&request===insightRequest)$('insightStatus').textContent=message},()=>active===id&&request===insightRequest);
  if(active!==id||request!==insightRequest)return;
  insightData={panel:data.panel,corpus:data.corpus};
  $('insightStatus').textContent=data.corpus.scope+' 已完成 '+data.panel.rows.length+' 个年度截面；'+data.corpus.author_corpora.length+' 位作者的完整采集历史进入观察集合。';
  $('insightPanel').innerHTML='<h3>学者—年份面板</h3><p class="muted">发表与引用按截止年累计；图指标使用所选滚动窗口。引用、h 与 i10 仅统计集合内有年份的引用边，不能与 Google Scholar 总量混用。— 表示缺少观察或指标未定义。</p>'+table(['年份','当年论文','累计论文','集合内引用','集合内 h','集合内 i10','合作者','圈内 z','参与系数','约束度','有效规模','k-core','PageRank','伙伴保留率'],data.panel.rows.map(x=>[x.year,...['papers','cumulative_papers','citations_within_corpus','h_index_within_corpus','i10_index_within_corpus','degree','within_module_z','participation','constraint','effective_size','core','pagerank','neighbor_retention'].map(k=>numberOrDash(x[k],k==='pagerank'?5:3))]))+'<p class="muted">圈内 z：相对本社区的加权连接；参与系数：连接跨社区的分散程度；约束度：邻居连接的冗余程度。社区逐年重新划分，不能把编号变化解释成换组。</p>';
 }catch(error){
  if(active===id&&request===insightRequest){
   insightData=null;$('insightPanel').innerHTML='';
   $('insightStatus').textContent='计算未完成：'+error.message+'。可以修改范围后重试。';
  }
  throw error;
 }finally{if(request===insightRequest)$('insightRun').disabled=false}
}
$('insightRun').onclick=guard(()=>loadInsights());
$('insightExport').onclick=()=>{if(!insightData){notice('请先计算统计');return}const url=URL.createObjectURL(new Blob([JSON.stringify(insightData,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=insightData.panel.focal.split('/').pop()+'-annual-insights.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};

window.resetInsights=()=>{insightRequest++;insightData=null;$('insightRun').disabled=false;$('insightStatus').textContent='';$('insightPanel').innerHTML=''};
