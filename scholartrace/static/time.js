/* Publication-time navigation; never reuses all-time weights for a past window. */
let timeOwner=null,timeBusy=false,timePlaying=false,timeGeneration=0,timeDebounce;
const timeControl=id=>document.getElementById(id);
window.stopTimePlayback=function(){timePlaying=false;timeGeneration++;timeControl('timePlay').textContent='▶ 播放';};
window.resetTimeControls=function(){window.stopTimePlayback();clearTimeout(timeDebounce);timeOwner=null;timeControl('timeMode').value='all';};
window.syncTimeControls=function(r){
  const axis=r.time_axis,slider=timeControl('timeYear');
  if(!axis||axis.minimum_year===null){slider.disabled=true;timeControl('timeLabel').textContent='暂无可用年份';timeControl('timePlay').disabled=true;return}
  slider.disabled=false;timeControl('timePlay').disabled=false;
  slider.min=axis.minimum_year;slider.max=axis.maximum_year;
  if(timeOwner!==r.focal_author_id){timeOwner=r.focal_author_id;slider.value=axis.maximum_year;timeControl('timeMode').value='all'}
  const mode=timeControl('timeMode').value,start=timeControl('from').value||axis.minimum_year,end=timeControl('to').value||axis.maximum_year;
  timeControl('timeLabel').textContent=`${start}–${end} · ${({all:'全部历史',cumulative:'累计至当前年',rolling:'滚动窗口',single:'单年',custom:'自定义范围'})[mode]}`;
  timeControl('timeYearValue').textContent=slider.value;
  timeControl('timeNote').textContent='边权重与社区按当前窗口重新计算；颜色不代表跨年固定团队。发表时间不等同于指导关系起止。当前来源元数据用于回看历史。';
  const historical=mode!=='all';
  timeControl('nodeSize').querySelector('[value="citations"]').disabled=historical;
  if(historical)timeControl('nodeSize').value='shared';
};
async function applyTimeWindow(){
  if(!active||!report?.time_axis||report.time_axis.minimum_year===null)return;
  const mode=timeControl('timeMode').value,year=Number(timeControl('timeYear').value),minimum=report.time_axis.minimum_year;
  if(mode==='custom')return;
  const width=Number(timeControl('timeWidth').value);
  timeControl('from').value=mode==='all'?'':mode==='single'?year:mode==='rolling'?Math.max(minimum,year-width+1):minimum;
  timeControl('to').value=mode==='all'?'':year;
  evidence=null;timeControl('evidenceLabel').textContent='';
  // Community numbers are local to each independently recomputed window.
  timeControl('communityFilter').value='';
  await refresh();
}
for(const id of ['timeMode','timeWidth'])timeControl(id).onchange=guard(async()=>{window.stopTimePlayback();await applyTimeWindow()});
timeControl('timeYear').oninput=()=>{window.stopTimePlayback();timeControl('timeYearValue').textContent=timeControl('timeYear').value;if(['all','custom'].includes(timeControl('timeMode').value))timeControl('timeMode').value='cumulative';clearTimeout(timeDebounce);timeDebounce=setTimeout(()=>guard(applyTimeWindow)(),160)};
async function stepTime(delta){window.stopTimePlayback();const s=timeControl('timeYear');s.value=Math.max(Number(s.min),Math.min(Number(s.max),Number(s.value)+delta));if(['all','custom'].includes(timeControl('timeMode').value))timeControl('timeMode').value='cumulative';await applyTimeWindow()}
timeControl('timePrev').onclick=guard(()=>stepTime(-1));timeControl('timeNext').onclick=guard(()=>stepTime(1));
timeControl('timePlay').onclick=guard(async()=>{
  if(timePlaying){window.stopTimePlayback();return}
  if(['all','custom'].includes(timeControl('timeMode').value))timeControl('timeMode').value='cumulative';
  const slider=timeControl('timeYear');if(Number(slider.value)>=Number(slider.max))slider.value=slider.min;
  timePlaying=true;const generation=++timeGeneration;timeControl('timePlay').textContent='Ⅱ 暂停';
  try{while(timePlaying&&generation===timeGeneration){await applyTimeWindow();if(!timePlaying||generation!==timeGeneration)return;if(Number(slider.value)>=Number(slider.max))break;await new Promise(resolve=>setTimeout(resolve,1400));if(!timePlaying||generation!==timeGeneration)return;slider.value=Number(slider.value)+1}}
  finally{if(generation===timeGeneration)window.stopTimePlayback()}
});
