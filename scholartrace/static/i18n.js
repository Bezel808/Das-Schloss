/* Presentation-only localization for the imperative UI. Source records and form
   values are never translated; switching locales does not refetch or rerender graphs. */
(()=>{
 const dictionary=window.SCHLOSS_EN;
 const attributes=['placeholder','aria-label','title'];
 const skip='script,style,pre,code,[translate="no"],[data-no-i18n],[data-language-switch],#name,#results h3,.subgroupNames button,#groupIsolateMembers button,#graph g[role="button"] text,#groupGraph .subgroupNode text';
 const originals=new WeakMap(),attributeSources=new WeakMap();
 let locale='zh',observer;
 try{locale=sessionStorage.getItem('schloss-language')==='en'?'en':'zh'}catch{}
 const missing=new Set();
 const chinese=/[\u3400-\u9fff]/;
 const chunks=/[\u3400-\u9fff][\u3400-\u9fff，。；：、？！“”「」（）《》／＋—–·]*/g;
 const multiPart=Object.keys(dictionary).filter(key=>chinese.test(key)&&(key.match(chunks)||[]).join('')!==key).sort((a,b)=>b.length-a.length);
 const phrasePattern=new RegExp(multiPart.map(key=>key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'),'g');
 const fragments=Object.keys(dictionary).filter(key=>key.length>1&&/^[\u3400-\u9fff，。；：、？！“”「」（）《》／＋—–·]+$/.test(key)).sort((a,b)=>b.length-a.length);
 const fragmentPattern=new RegExp(fragments.map(key=>key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'),'g');
 const patterns=[
  [/^搜索未完成：(.+?)。可重试。$/,(_,message)=>'Search incomplete: '+translate(message).replace(/[。.\s]+$/,'')+'. Please try again.'],
  [/^(\d{4}–\d{4}) 年$/,(_,range)=>range],
  [/^第 (\d+) 页 · (.*?) \/ ([\d,]+) 位$/,(_,p,range,total)=>`Page ${p} · ${range} of ${total}`],
  [/^找到 ([\d,]+) 位学者，请核对机构。$/,(_,n)=>`${n} researchers found. Check the affiliation before opening a profile.`],
  [/^查看 (.+) 的成员间合作论文$/,(_,name)=>`View ${name}'s collaborations with members`],
  [/^第 (\d+) 年同圈合作$/,(_,n)=>`Collaboration in year ${n}`],
  [/^第 (\d+) 年仍有发表$/,(_,n)=>`Publishing in year ${n}`],
  [/^共 (\d+) 篇依据，筛选后 (\d+) 篇；包括目标作者未署名的论文。$/,(_,all,n)=>`${n} of ${all} source papers; includes papers without the focal author.`],
  [/^正在补全 (\d+) 位成员的论文…$/,(_,n)=>`Fetching publication histories for ${n} members…`],
  [/^仍有 (\d+) 位成员待获取，请继续分析。$/,(_,n)=>`${n} members still need publication histories. Resume the analysis.`],
  [/^(\d+)–(\d+) 年 · 成员独立合作，不代表师生身份。$/,(_,a,b)=>`${a}–${b} · Independent collaborations between members; not evidence of supervision.`],
 ];
 function translate(source){
  if(locale==='zh'||!chinese.test(source))return source;
  const trimmed=source.trim();
  if(Object.hasOwn(dictionary,trimmed))return source.replace(trimmed,dictionary[trimmed]);
  for(const [pattern,replace]of patterns)if(pattern.test(trimmed))return source.replace(trimmed,trimmed.replace(pattern,replace));
  return source.replace(phrasePattern,key=>dictionary[key]).replace(chunks,chunk=>{
   if(Object.hasOwn(dictionary,chunk))return dictionary[chunk];
   const result=chunk.replace(fragmentPattern,key=>dictionary[key]);
   if(chinese.test(result))missing.add(chunk);return result;
  });
 }
 function sourceTerms(node){
  const scope=(node.nodeType===Node.ELEMENT_NODE?node:node.parentElement)?.closest('[data-i18n-names]');
  if(!scope)return [];
  try{return JSON.parse(scope.dataset.i18nNames).filter(value=>typeof value==='string'&&value.length)}catch{return []}
 }
 function localized(source,node){
  const terms=[...new Set(sourceTerms(node))].sort((a,b)=>b.length-a.length);
  let masked=source;
  terms.forEach((term,i)=>{masked=masked.split(term).join('\uE000'+i+'\uE001')});
  let result=translate(masked);
  terms.forEach((term,i)=>{result=result.split('\uE000'+i+'\uE001').join(term)});
  return result;
 }
 function textNode(node){
  if(!node.parentElement||node.parentElement.closest(skip))return;
  let saved=originals.get(node);
  if(!saved||node.data!==saved.rendered)saved={source:node.data};
  const rendered=localized(saved.source,node);
  if(node.data!==rendered)node.data=rendered;
  saved.rendered=rendered;originals.set(node,saved);
 }
 function element(node){
  if(node.matches(skip)||node.closest('[translate="no"],[data-no-i18n]'))return;
  let saved=attributeSources.get(node)||{};
  for(const key of attributes){
   if(!node.hasAttribute(key))continue;
   const value=node.getAttribute(key);
   if(!saved[key]||value!==saved[key].rendered)saved[key]={source:value};
   const rendered=localized(saved[key].source,node);
   if(value!==rendered)node.setAttribute(key,rendered);
   saved[key].rendered=rendered;
  }
  attributeSources.set(node,saved);
 }
 function localize(root){
  if(root.nodeType===Node.TEXT_NODE){textNode(root);return}
  if(root.nodeType!==Node.ELEMENT_NODE&&root.nodeType!==Node.DOCUMENT_NODE)return;
  if(root.nodeType===Node.ELEMENT_NODE){element(root);if(root.matches(skip))return}
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{
   acceptNode:n=>n.nodeType===Node.ELEMENT_NODE&&n.matches(skip)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT
  });
  let node;while(node=walker.nextNode())node.nodeType===Node.TEXT_NODE?textNode(node):element(node);
 }
 function controls(){
  document.documentElement.lang=locale==='en'?'en':'zh-CN';
  document.querySelectorAll('[data-language-switch]').forEach(button=>{
   button.textContent=locale==='en'?'中文':'English';
   button.lang=locale==='en'?'zh-CN':'en';
   button.setAttribute('aria-label',locale==='en'?'Switch to Chinese':'Switch to English');
  });
 }
 function observe(){observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:[...attributes,'data-i18n-names']})}
 function setLanguage(value){
  if(!['zh','en'].includes(value))return;
  observer.disconnect();locale=value;missing.clear();
  try{sessionStorage.setItem('schloss-language',locale)}catch{}
  localize(document.documentElement);controls();observe();
  document.dispatchEvent(new CustomEvent('languagechange',{detail:{language:locale}}));
 }
 observer=new MutationObserver(records=>{
  observer.disconnect();
  const roots=new Set();
  for(const record of records){
   if(record.type==='childList')record.addedNodes.forEach(node=>roots.add(node));
   else roots.add(record.target);
  }
  for(const root of roots)if(root.isConnected)localize(root);
  observe();
 });
 window.i18n={get language(){return locale},setLanguage,translate,missing,
  sourceTerms(element){return [...element.querySelectorAll('[translate="no"]')].map(node=>node.textContent)},
  sourceText(element){
   const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT);let node,result='';
   while(node=walker.nextNode())result+=originals.get(node)?.source??node.data;
   return result;
  }};
 document.querySelectorAll('[data-language-switch]').forEach(button=>button.addEventListener('click',()=>setLanguage(locale==='en'?'zh':'en')));
 setLanguage(locale);
})();
