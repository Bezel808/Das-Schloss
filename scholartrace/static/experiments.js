let experimentData=null;
const policyNames={random:'随机补采',observed_degree:'观察度数优先',uncertainty:'区间宽度优先',neighbor_random:'仅历史合作者·随机',neighbor_degree:'仅历史合作者·按度',uniform_cover:'均匀覆盖',ambiguity_cover:'歧义加权覆盖'};
const scoreNames={common_neighbors:'共同邻居',adamic_adar:'Adamic–Adar',resource_allocation:'资源分配',preferential_attachment:'度数乘积',edge_bank:'EdgeBank',past_joint_count:'历史合作次数',recent_joint_year:'最近合作年'};
const percent=v=>v===null||v===undefined?'—':numberOrDash(100*v,2)+'%';
function updateExperimentScores(){
 const names=$('experimentTask').value==='new'?['common_neighbors','adamic_adar','resource_allocation','preferential_attachment','edge_bank','past_joint_count']:['past_joint_count','recent_joint_year','edge_bank'];
 $('experimentScore').innerHTML=names.map(k=>`<option value="${k}">${esc(scoreNames[k])}</option>`).join('');
}
async function loadExperiments(){
 const button=$('experimentLoad');button.disabled=true;
 try{
  const response=await fetch('/static/experiments.json');if(!response.ok)throw Error('实验记录尚未生成');
  experimentData=await response.json();
  if(!experimentData.acquisition.length)throw Error('没有完成的实验记录');
  $('experimentDataset').innerHTML=experimentData.acquisition.map((r,i)=>`<option value="${i}">${esc(r.dataset)} · ${r.cutoff} 年 · ${r.targets} 人</option>`).join('');
  const reviews=experimentData.reviews.rounds;
  $('experimentStatus').textContent='以下为公共数据集实验，不是当前学者的个人预测。'+experimentData.message+' 三审记录：'+reviews.map(r=>`第 ${r.round} 轮 ${r.methods}/${r.statistics}/${r.systems} 分`).join('；')+'（内部 1–10 分，不是会议录用概率）。';
  updateExperimentScores();renderExperiments();
 }finally{button.disabled=false}
}
function renderExperiments(){
 if(!experimentData)return;
 const report=experimentData.acquisition[Number($('experimentDataset').value)];
 const budget=Number($('experimentBudget').value),repeat=$('experimentTask').value==='repeat',score=$('experimentScore').value;
 const rows=report.summary.filter(r=>r.budget===budget);
 const metric=r=>repeat?r.repeat_edge.methods[score]:r.new_edge[score].tie_expected;
 const gold=r=>repeat?r.repeat_edge.gold_repeated:r.gold_new_seen;
 $('experimentResults').innerHTML=`<p>使用截至 ${report.cutoff} 年的论文，预测 ${report.cutoff+1} 年${repeat?'重复':'首次'}合作。预算最多查询 ${budget} 位作者；保留同一目标人群。主指标对同分候选的全部排列取精确期望，小数命中不是实际整数命中。</p>`+table(['查询策略','目标数','未来关联数','期望命中@10','召回率','候选覆盖','第10位遇并列','实际查询数','返回论文量'],rows.map(r=>{const m=metric(r);return [esc(policyNames[r.policy]||r.policy),r.n_targets,gold(r),numberOrDash(m.expected_hits_at_10,2),percent(m.micro_recall_at_10),repeat?(gold(r)?'100%':'—'):percent(r.new_edge[score].candidate_recall),percent(m.cutoff_tied_target_fraction),numberOrDash(r.mean_actual_queries,1),numberOrDash(r.mean_returned_papers_with_repeats,1)]}))+'<p class="muted">关联数按“目标—合作者”计，同一条无向边可能对应两个被抽中的目标。返回论文量包含重复返回的论文；相同查询数不等于相同传输成本。重复合作候选已由目标论文完整确定，因此额外查询不会提高这些重复合作基线。</p>';
 const ref=rows[0];
 if(!repeat)$('experimentResults').innerHTML+=`<p>首次进入数据集的人物占未来首次合作的 ${percent(ref.cold_start_fraction)}，另计为冷启动。完整历史 CN 参考召回为 ${percent(ref.oracle_cn_tie_expected_recall_at_10)}，它不是未来预测的性能上限。</p>`+table(['策略','历史严格 top-10 已确定','ID 决胜整数命中','并列排列的命中范围'],rows.map(r=>[esc(policyNames[r.policy]),percent(r.certified_top10_rate),Math.round((r.new_edge[score].micro_recall_at_10||0)*r.gold_new_seen),`${metric(r).minimum_hits_at_10}–${metric(r).maximum_hits_at_10}`]))+'<p class="muted">历史证书仅针对共同邻居评分，不代表预测正确。命中范围是改变并列顺序的极端范围，不是统计置信区间。</p>';
 const svg=d3.select('#experimentChart');svg.selectAll('*').remove();
 const width=900,height=280,margin={left:55,right:20,top:20,bottom:45};
 const x=d3.scaleLinear().domain([0,40]).range([margin.left,width-margin.right]);
 const maximum=d3.max(report.summary,d=>metric(d).micro_recall_at_10)||.01;
 const y=d3.scaleLinear().domain([0,Math.min(1,Math.max(.1,maximum*1.1))]).range([height-margin.bottom,margin.top]);
 const colors=d3.scaleOrdinal(communityColors).domain(Object.keys(policyNames));
 svg.attr('viewBox',`0 0 ${width} ${height}`).attr('aria-label',`${repeat?'重复':'首次'}合作的并列期望召回率`);
 svg.append('g').attr('transform',`translate(0,${height-margin.bottom})`).call(d3.axisBottom(x).tickValues([0,5,10,20,40]));
 svg.append('g').attr('transform',`translate(${margin.left},0)`).call(d3.axisLeft(y).tickFormat(d3.format('.0%')));
 svg.append('text').attr('x',width/2).attr('y',height-5).text('作者查询预算');
 const line=d3.line().defined(d=>metric(d).micro_recall_at_10!==null).x(d=>x(d.budget)).y(d=>y(metric(d).micro_recall_at_10));
 for(const policy of Object.keys(policyNames)){
  const rr=report.summary.filter(r=>r.policy===policy).sort((a,b)=>a.budget-b.budget);
  svg.append('path').datum(rr).attr('d',line).attr('fill','none').attr('stroke',colors(policy)).attr('stroke-width',2);
  for(const r of rr){const value=metric(r).micro_recall_at_10;if(value===null)continue;
   svg.append('circle').attr('cx',x(r.budget)).attr('cy',y(value)).attr('r',3).attr('fill',colors(policy)).append('title').text(`${policyNames[policy]}，预算 ${r.budget}，召回 ${percent(value)}`);
  }
 }
 $('experimentLegend').innerHTML=Object.entries(policyNames).map(([id,name])=>`<span style="color:${colors(id)}">● ${esc(name)}</span>`).join(' · ');
 const across=experimentData.acquisition.filter(r=>r.dataset===report.dataset);
 $('experimentAcrossYears').innerHTML='<h3>同一领域的逐年结果</h3><p>主要比较预先固定为预算 20、共同邻居评分：歧义覆盖 vs 仅历史合作者按度查询。以下区间是固定年份与源图下按目标配对重采样的开发性区间，不是未来年份的保证。</p>'+table(['截止年','未来关联数','歧义覆盖召回','历史邻居按度召回','召回差及95%区间'],across.map(r=>{
  const a=r.summary.find(x=>x.policy==='ambiguity_cover'&&x.budget===20),b=r.summary.find(x=>x.policy==='neighbor_degree'&&x.budget===20);
  const pair=experimentData.paired_intervals.find(x=>x.source===r.file)?.comparisons.find(x=>x.policy==='ambiguity_cover'&&x.budget===20);
  const interval=pair?.paired_target_bootstrap_95;
  return [r.cutoff,a.gold_new_seen,percent(a.new_edge.common_neighbors.tie_expected.micro_recall_at_10),percent(b.new_edge.common_neighbors.tie_expected.micro_recall_at_10),pair?`${numberOrDash(100*pair.micro_recall_difference,2)} 个百分点 ${interval?'['+interval.map(v=>numberOrDash(100*v,2)).join(', ')+']':'（无有效区间）'}`:'—'];
 }));
 const diagnostic=experimentData.error_decomposition?.rows.find(r=>r.dataset===report.dataset&&r.cutoff===report.cutoff);
 if(diagnostic){const c=diagnostic.counts,s=diagnostic.shares_of_all_new_associations;
  $('experimentAcrossYears').innerHTML+='<h3>预测损失发生在哪里</h3><p>固定“仅历史合作者·按度”与预算 20；分母包含冷启动的全部未来首次合作。以下四项互不重叠、合计 100%。这比单独看召回率更能判断该改采集还是改排序。</p>'+table(['类别','关联数／期望数','占全部首次合作'],[['首次进入数据集，无法从历史识别人名',c.gold_cold,percent(s.gold_cold)],['历史中存在，但当前采集未找到',c.not_discovered,percent(s.not_discovered)],['候选已找到，但没有排进前10',numberOrDash(c.discovered_but_below_top10,2),percent(s.discovered_but_below_top10)],['排进前10的期望命中',numberOrDash(c.expected_hits,2),percent(s.expected_hits)]])+`<p class="muted">即使完整查询所有历史合作者，二跳集合也仅覆盖 ${percent(diagnostic.full_twohop_coverage_of_seen)} 的非冷启动新合作；扩大二跳内的查询预算无法单独解决范围外候选。</p>`;
 }
 const ml=experimentData.ml,tie=Boolean(ml.metric_version);
 const holdout=experimentData.holdout;
 if(holdout){
  const rr=holdout.reports.filter(r=>r.dataset===report.dataset);
  const methods=['common_neighbors','adamic_adar','resource_allocation','ppr_recent_fractional','ml_activity','ml_activity_network','ml_activity_network_coverage'];
  const labels=['CN','Adamic–Adar','资源分配','近期分数 PPR','ML 活动量','ML 活动＋网络','ML 活动＋网络＋覆盖'];
  const draw=records=>table(['截止年','目标数','未来关联数',...labels,'PPR−AA 95%区间'],records.map(r=>{
   const m=Object.fromEntries(r.models.map(x=>[x.method,x]));const ci=m.ppr_recent_fractional.paired_target_bootstrap_95;
   return [r.cutoff,r.targets,m.ppr_recent_fractional.gold,...methods.map(k=>percent(m[k].micro_recall_at_10)),ci?'['+ci.map(v=>numberOrDash(100*v,2)).join(', ')+'] 个百分点':'—'];
  }));
  const final=rr.filter(r=>r.stage==='final_test');
  const mean=method=>{const values=final.map(r=>r.models.find(m=>m.method===method).micro_recall_at_10).filter(v=>v!==null);return values.length?values.reduce((a,b)=>a+b,0)/values.length:null};
  $('experimentAcrossYears').innerHTML+='<h3>固定参数后的最终时间留出</h3><p>使用截至 2011、2012、2013 年的历史分别预测下一年。方法、参数、采集策略、训练系数和代码在读取这些结果前冻结，之后没有根据留出结果调参。每年 512 个目标，预算 20，所有评分器共享采集与候选。</p>'+draw(final)+`<p>三个最终年份等权平均：近期分数 PPR ${percent(mean('ppr_recent_fractional'))}，预先指定的 Adamic–Adar 对照 ${percent(mean('adamic_adar'))}。区间按每年目标配对计算；三年均值是描述统计，不是晋升或因果结论。</p>`+'<details><summary>查看固定参数下的验证年份与冻结记录</summary>'+draw(rr.filter(r=>r.stage==='validation'))+`<p>冻结时间：${esc(holdout.protocol.frozen_at)}<br>协议指纹：${esc(holdout.protocol_sha256)}。验证年份同样没有用于改动本次最终方案；完整协议、方法参数、源数据与实现指纹包含在导出。</p></details>`;
  const aggregate=experimentData.holdout_aggregate?.rows.find(r=>r.dataset===report.dataset);
  if(aggregate){const ci=aggregate.year_stratified_paired_95,sensitivity=aggregate.author_cluster_paired_95_sensitivity;
   $('experimentAcrossYears').innerHTML+=`<p>三年等权召回差：${numberOrDash(100*aggregate.equal_year_difference,3)} 个百分点，固定年份条件下的 95% 区间 [${ci.map(v=>numberOrDash(100*v,3)).join(', ')}]；按同一作者跨年聚类的敏感性区间 [${sensitivity.map(v=>numberOrDash(100*v,3)).join(', ')}]。${aggregate.target_years} 个学者—年份记录对应 ${aggregate.unique_authors} 位不同作者。History 已参与开发阶段，不能称为完全未见领域。</p>`;
  }
  const costs=experimentData.holdout_costs?.rows.filter(r=>r.dataset===report.dataset&&r.stage==='final_test');
  if(costs?.length)$('experimentAcrossYears').innerHTML+='<details><summary>查看最终年份的采集成本分布</summary><p>返回论文量包含跨作者重复返回，含目标本人的初始查询；额外作者查询数不含目标本人。分页代理假定每页100篇且不跨目标复用缓存，不是实测API账单或延迟。</p>'+table(['截止年','额外查询中位数/P95','返回论文中位数/P95/最大','去重论文中位数/P95','分页代理中位数/P95'],costs.map(r=>[r.cutoff,...['actual_extra_author_queries','returned_events_including_duplicates','unique_observed_events','cold_cache_pages_proxy_100'].map(k=>(k==='returned_events_including_duplicates'?['50','95','100']:['50','95']).map(q=>numberOrDash(r[k][q],1)).join(' / '))]))+'</details>';
 }
 const candidate=experimentData.candidate_ablation?.find(r=>r.dataset===report.dataset&&r.cutoff===report.cutoff);
 if(candidate){
  const names={...scoreNames,ppr_unweighted:'PageRank · 无权',ppr_count:'PageRank · 合作次数',ppr_recent_fractional:'PageRank · 近期分数权重'};
  $('experimentAcrossYears').innerHTML+='<h3>固定采集记录，分别比较候选与排序</h3><p>以下固定预算 20、仅历史合作者按度查询，所有评分器使用相同论文和候选。PageRank 以目标为重启点；近期权重的半衰期固定为 3 年。数值求解已检查收敛，但这些预测分数没有共同邻居的缺边排序证书。</p>'+table(['评分器','期望命中@10','召回率','候选覆盖','候选内召回'],candidate.summary.filter(r=>r.policy==='neighbor_degree'&&r.pool==='all_observed').map(r=>[esc(names[r.method]),numberOrDash(r.expected_hits_at_10,2),percent(r.micro_recall_at_10),percent(r.candidate_coverage),percent(r.conditional_recall_at_10)]))+'<details><summary>查看两种查询策略 × 两种候选范围 × 六种评分器</summary><p>“已发现全部”包含当前观测图中的更远人物；仍不使用未查询的全图。两种查询策略的实际返回论文量不同，不称为等传输成本实验。</p>'+table(['查询策略','候选范围','评分器','召回率','候选覆盖','平均候选数','实际查询数','返回论文量'],candidate.summary.map(r=>[esc(policyNames[r.policy]),r.pool==='twohop'?'二跳':'已发现全部',esc(names[r.method]),percent(r.micro_recall_at_10),percent(r.candidate_coverage),numberOrDash(r.mean_candidates,1),numberOrDash(r.mean_actual_queries,1),numberOrDash(r.mean_returned_papers,1)]))+'</details>';
 }
 $('experimentML').innerHTML=`<h3>轻量预测模型的时间检验</h3><p>在 ${ml.training_cutoffs.join('、')} 年截止的样本训练，在 ${ml.evaluation_cutoff} 年截止的开发样本评估下一年。队列为 ${ml.evaluation_targets} 人，与上方扩展队列分开报告。指标口径：${tie?'并列期望':'旧版 ID 决胜审计'}；此表报告开发阶段，冻结后的最终结果另列于上方。</p>`+table(['模型','策略/预算','召回率','正例目标平均 AP'],Object.entries(ml.summaries).flatMap(([name,summary])=>['neighbor_degree/20','ambiguity_cover/20','ambiguity_cover/40'].filter(k=>summary[k]).map(k=>[esc({activity:'活动量',activity_network:'活动量＋网络',activity_network_coverage:'活动量＋网络＋覆盖'}[name]),esc(k),percent(summary[k][tie?'tie_expected_micro_recall_at_10':'micro_recall_at_10']),numberOrDash(summary[k][tie?'tie_expected_macro_ap_positive_targets':'macro_ap_positive_targets'],4)])))+'<p class="muted">这些开发模型不会自动用于个人身份或机会判断。完整导出保留所有策略、评分器、预算和指标口径。</p>';
}
$('experimentLoad').onclick=guard(loadExperiments);
$('experimentDataset').onchange=$('experimentBudget').onchange=$('experimentScore').onchange=renderExperiments;
$('experimentTask').onchange=()=>{updateExperimentScores();renderExperiments()};
$('experimentExport').onclick=()=>{if(!experimentData)return;const url=URL.createObjectURL(new Blob([JSON.stringify(experimentData,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='das-schloss-development-evidence.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
