/* One query owns its cursor history. No papers are fetched by pagination. */
(()=>{
 let state={query:'',page:0,cursors:['*'],next:null,total:0},generation=0,controller=null,busy=false;
 const updateControls=()=>{
  const changed=$('query').value.trim()!==state.query;
  $('searchPrev').disabled=busy||changed||state.page===0;
  $('searchNext').disabled=busy||changed||!state.next;
  $('search').setAttribute('aria-busy',String(busy));
 };
 function cancel(){generation++;controller?.abort();controller=null;busy=false;updateControls()}
 window.pauseAuthorSearch=cancel;
 window.resetAuthorSearch=()=>{cancel();state={query:'',page:0,cursors:['*'],next:null,total:0};$('results').replaceChildren();$('searchPagination').hidden=true};
 $('query').addEventListener('input',()=>{cancel();if(state.query&&$('query').value.trim()!==state.query)notice('输入完成后点击搜索。')});
 async function load(query,page,cursor,fresh=false){
  cancel();const version=generation;controller=new AbortController();busy=true;
  if(fresh){state={query,page:0,cursors:['*'],next:null,total:0};$('results').replaceChildren();$('searchPagination').hidden=true}
  updateControls();notice('搜索中…');
  try{
   const response=await fetch('/api/authors?'+new URLSearchParams({q:query,cursor}),{signal:controller.signal});
   const data=await response.json();
   if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'搜索失败，请重试');
   if(version!==generation)return;
   const rows=data.results||[],total=data.meta?.count??rows.length;
   const hasMore=data.meta?.count==null||(page*12+rows.length)<total;
   const next=rows.length&&hasMore&&data.meta?.next_cursor!==cursor?data.meta?.next_cursor:null;
   state={query,page,cursors:[...state.cursors.slice(0,page),cursor],next:next||null,total};
   $('results').innerHTML=rows.map((a,i)=>`<article class="card"><button data-pick="${i}">查看档案</button><h3>${esc(a.display_name)}</h3><p>${sourceHTML((a.last_known_institutions||[]).map(x=>x.display_name).join(' · '),'机构信息缺失')}<br>${a.works_count||0} 篇论文 · ORCID ${esc(a.orcid||'未提供')}<br>${esc(a.id)}</p></article>`).join('')||'<p class="empty">没有匹配的学者，试试其他姓名写法或 ORCID。</p>';
   $('results').querySelectorAll('[data-pick]').forEach(button=>button.onclick=guard(async()=>{
    button.disabled=true;cancel();
    try{const job=await api('jobs',{author_id:rows[button.dataset.pick].id});await openProfile(job.id)}
    finally{button.disabled=false}
   }));
   $('searchPagination').hidden=!rows.length&&page===0;
   $('searchPageStatus').textContent=`第 ${page+1} 页 · ${rows.length?page*12+1:0}–${page*12+rows.length} / ${total.toLocaleString()} 位`;
   notice(rows.length?`找到 ${total.toLocaleString()} 位学者，请核对机构。`:'');
   if(!fresh)$('results').scrollIntoView({block:'start'});
  }catch(error){if(version===generation&&error.name!=='AbortError'){notice('搜索未完成：'+error.message+'。可重试。');if(error.message.includes('API Key')&&!$('settingsDialog').open)$('settingsDialog').showModal()}}
  finally{if(version===generation){busy=false;updateControls()}}
 }
 $('search').onsubmit=event=>{event.preventDefault();const query=$('query').value.trim();if(query.length>=2)load(query,0,'*',true)};
 $('searchNext').onclick=()=>{if(!busy&&state.next)load(state.query,state.page+1,state.next)};
 $('searchPrev').onclick=()=>{if(!busy&&state.page>0)load(state.query,state.page-1,state.cursors[state.page-1])};
})();
