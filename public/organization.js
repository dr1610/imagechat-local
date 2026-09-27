export function createOrganizer({api,state,esc,safe,toast,switchSession,refreshSessions,newSession,leaveChat}) {
 const $=id=>document.getElementById(id);
 let model={collections:[],placements:[]}, signature='', selected=null, lastMarkup='', saving=false;
 let current=null,moreProjects=false,moreRecent=false,viewSequence=0,lastProjectMarkup='';
 const page=document.createElement('section');page.id='projectView';page.className='project-view';page.hidden=true;
 document.querySelector('main').append(page);
 async function showProject(id){const seq=++viewSequence;await leaveChat();if(seq!==viewSequence)return;current=id;localStorage.setItem('qic.projectView',id);applyView();render();}
 function applyView(){
  page.hidden=current===null;$('chatView').hidden=current!==null;
  $('renameChat').disabled=current!==null;
  if(current!==null){const c=model.collections.find(c=>c.id===current);$('chatTitle').textContent=c?.name||'未分類';}
 }
 function showChat(){++viewSequence;current=null;localStorage.removeItem('qic.projectView');page.hidden=true;$('chatView').hidden=false;$('renameChat').disabled=false;render();}
 const dialog=document.createElement('dialog');dialog.id='organizeDialog';
 dialog.innerHTML=`<form id="organizeForm"><h2 id="organizeTitle">履歴を整理</h2><div id="organizeFields"></div><div class="dialog-buttons"><button type="button" id="organizeCancel">閉じる</button><button id="organizeSave" class="primary">保存</button></div></form>`;
 document.body.append(dialog);$('organizeCancel').onclick=()=>dialog.close();
 function label(c){return c.parent_id?`${model.collections.find(p=>p.id===c.parent_id)?.name} / ${c.name}`:c.name;}
 function destinations(current){return `<option value="">未分類</option>`+model.collections.map(c=>`<option value="${c.id}" ${c.id===current?'selected':''}>${esc(label(c))}</option>`).join('');}
 async function mutate(body){await api('/api/organization',body);await refresh();}
 function open(mode,item=null,parent=null){
  selected={mode,item,parent};$('organizeSave').hidden=false;
  const session=mode==='session';
  $('organizeTitle').textContent=mode==='create'?(parent?'新しいフォルダ':'新しいプロジェクト'):session?'チャットを整理':'プロジェクト・フォルダを整理';
  const current=session?model.placements.find(p=>p.session_id===item.id)?.collection_id:null;
  $('organizeFields').innerHTML=`<label>名前<input id="organizeName" maxlength="100" required value="${esc(item?.name||item?.title||'')}"></label>`+
   (session?`<label>移動先<select id="organizeDestination">${destinations(current)}</select></label>`:'')+
   (mode!=='create'?`<div class="organize-actions"><button type="button" data-order="-1">↑ 上へ</button><button type="button" data-order="1">↓ 下へ</button>${!session&&!item.parent_id?'<button type="button" id="addFolder">＋ フォルダ</button>':''}${!session?'<button type="button" id="deleteCollection">削除</button>':''}</div><p class="micro">${session?'同じ所属先の中で並べ替えます。':'削除してもチャットと画像は残り、未分類へ移ります。'}</p>`:'');
  $('organizeFields').querySelectorAll('[data-order]').forEach(b=>b.onclick=safe(async()=>{await mutate({action:'reorder',id:item.id,kind:session?'session':'collection',direction:Number(b.dataset.order)});toast('並び順を保存しました。');}));
  if($('addFolder'))$('addFolder').onclick=()=>open('create',null,item.id);
  if($('deleteCollection'))$('deleteCollection').onclick=()=>{
   $('organizeTitle').textContent='この入れ物を削除しますか？';$('organizeFields').replaceChildren();
   const p=document.createElement('p');p.textContent=`「${item.name}」を削除します。中のフォルダも削除されますが、チャット・画像・履歴はすべて未分類に残ります。`;$('organizeFields').append(p);
   selected={mode:'delete',item};$('organizeSave').textContent='削除して未分類へ移す';
  };
  $('organizeSave').textContent='保存';if(!dialog.open)dialog.showModal();$('organizeName').focus();
 }
 $('organizeForm').onsubmit=safe(async e=>{
  e.preventDefault();if(saving)return;saving=true;$('organizeSave').disabled=true;try{const {mode,item,parent}=selected;
  if(mode==='delete')await mutate({action:'delete',id:item.id});
  else {const name=$('organizeName').value.trim();if(!name){toast('名前を入力してください。');return;}
   if(mode==='session'){
    await api('/api/sessions/'+item.id,{title:name});await mutate({action:'move',session_id:item.id,collection_id:$('organizeDestination').value||null});
    if(state.session?.id===item.id){state.session.title=name;$('chatTitle').textContent=name;}
    await refreshSessions();
   }else await mutate({action:mode==='create'?'create':'rename',id:item?.id,parent_id:parent,name});
  }dialog.close();toast('履歴の整理を保存しました。');}finally{saving=false;$('organizeSave').disabled=false;}
 });
 function render(){
  if(current && !model.collections.some(c=>c.id===current)){current='';applyView();}
  const query=$('historySearch').value.trim().toLocaleLowerCase();
  const placements=new Map(model.placements.map(p=>[p.session_id,p]));
  const ordered=[...state.sessions].sort((a,b)=>(placements.get(a.id)?.position??2147483647)-(placements.get(b.id)?.position??2147483647)||a.created-b.created||a.id.localeCompare(b.id));
  const matches=s=>!query||s.title.toLocaleLowerCase().includes(query);
  const chats=cid=>ordered.filter(s=>(placements.get(s.id)?.collection_id||'')===cid&&matches(s));
  const row=(s,detail=false)=>`<div class="history-row ${detail?'project-chat-row':''}" draggable="true" data-drag-session="${s.id}"><button class="session-button ${current===null&&s.id===state.session?.id?'selected':''}" data-session="${s.id}" title="${esc(s.title)}"><span>▧</span><span>${esc(s.title)}${detail?`<small>${new Date(s.updated*1000).toLocaleDateString('ja-JP')} · ${esc(label(model.collections.find(c=>c.id===placements.get(s.id)?.collection_id)||{name:'未分類'}))}</small>`:''}</span></button><button class="history-menu" data-chat-menu="${s.id}" aria-label="${esc(s.title)}を整理">⋯</button></div>`;
  const roots=model.collections.filter(c=>!c.parent_id);
  const filtered=roots.filter(c=>!query||c.name.toLocaleLowerCase().includes(query)||chats(c.id).length||model.collections.some(f=>f.parent_id===c.id&&(f.name.toLocaleLowerCase().includes(query)||chats(f.id).length)));
  const recent=[...state.sessions].filter(matches).sort((a,b)=>b.updated-a.updated||b.created-a.created);
  const markup=`<div class="side-section-title">プロジェクト</div>`+
   filtered.slice(0,moreProjects||query?filtered.length:5).map(c=>`<div class="history-row" data-drop="${c.id}"><button class="session-button ${current===c.id||model.collections.find(f=>f.id===current)?.parent_id===c.id?'selected':''}" data-project="${c.id}" title="${esc(c.name)}"><span>▱</span><span>${esc(c.name)}</span></button><button class="history-menu" data-group-menu="${c.id}" aria-label="${esc(c.name)}を整理">⋯</button></div>`).join('')+
   (filtered.length>5&&!query?`<button class="show-more" data-more-projects>${moreProjects?'表示を減らす':'もっと表示する'}</button>`:'')+
   `<button class="unfiled-link" data-project="" data-drop="">未分類のチャット</button><div class="side-section-title">${query?'検索結果':'最近のチャット'} <small>${recent.length}</small></div>`+
   recent.slice(0,moreRecent||query?recent.length:15).map(s=>row(s)).join('')+
   (recent.length>15&&!query?`<button class="show-more" data-more-recent>${moreRecent?'表示を減らす':'もっと表示する'}</button>`:'')+
   (query&&!recent.length?'<p class="micro">一致するチャットはありません。</p>':'');
  if(markup!==lastMarkup){lastMarkup=markup;$('sessionList').innerHTML=markup;bind($('sessionList'));}
  if(current===null)return;
  const c=model.collections.find(c=>c.id===current),parent=c?.parent_id&&model.collections.find(p=>p.id===c.parent_id);
  const folders=model.collections.filter(f=>f.parent_id===current);
  const visibleFolders=folders.filter(f=>!query||f.name.toLocaleLowerCase().includes(query)||chats(f.id).length);
  const list=chats(current);
  const html=`<div class="project-content"><div class="project-breadcrumb">${parent?`<button data-project="${parent.id}">${esc(parent.name)}</button><span>／</span>`:''}<span>${c?.parent_id?'フォルダ':'プロジェクト'}</span></div><div class="project-hero"><div><span class="project-symbol">▱</span><h1>${esc(c?.name||'未分類のチャット')}</h1><p>会話と画像を、この場所にまとめて。</p></div><div class="project-actions"><button class="primary" data-new-in="${current}">＋ 新しいチャット</button>${c&&!parent?`<button data-add-folder="${c.id}">＋ フォルダ</button>`:''}${c?`<button data-group-menu="${c.id}" aria-label="${esc(c.name)}の設定">⋯</button>`:''}</div></div>`+
   (visibleFolders.length?`<h2>フォルダ</h2><div class="folder-grid">${visibleFolders.map(f=>`<div class="folder-card" data-drop="${f.id}"><button data-project="${f.id}"><span>▱</span><strong>${esc(f.name)}</strong><small>${chats(f.id).length} チャット</small></button><button class="history-menu" data-group-menu="${f.id}" aria-label="${esc(f.name)}を整理">⋯</button></div>`).join('')}</div>`:'')+
   `<div class="project-chat-list" data-drop="${current}"><h2>チャット <small>${list.length}</small></h2>${list.map(s=>row(s,true)).join('')}${!list.length?`<div class="project-empty">${query?'一致するチャットはありません。':'ここにはまだチャットがありません。新しく始めるか、左の履歴をドラッグして追加できます。'}</div>`:''}</div></div>`;
  if(html!==lastProjectMarkup){lastProjectMarkup=html;page.innerHTML=html;bind(page);}
  applyView();
 }
 function bind(container){
  container.querySelectorAll('[data-session]').forEach(b=>b.onclick=safe(()=>switchSession(b.dataset.session)));
  container.querySelectorAll('[data-project]').forEach(b=>b.onclick=safe(()=>showProject(b.dataset.project)));
  container.querySelectorAll('[data-chat-menu]').forEach(b=>b.onclick=()=>open('session',state.sessions.find(s=>s.id===b.dataset.chatMenu)));
  container.querySelectorAll('[data-group-menu]').forEach(b=>b.onclick=()=>open('collection',model.collections.find(c=>c.id===b.dataset.groupMenu)));
  container.querySelectorAll('[data-add-folder]').forEach(b=>b.onclick=()=>open('create',null,b.dataset.addFolder));
  container.querySelectorAll('[data-new-in]').forEach(b=>b.onclick=safe(()=>newSession(b.dataset.newIn||null)));
  container.querySelectorAll('[data-more-projects]').forEach(b=>b.onclick=()=>{moreProjects=!moreProjects;render();});
  container.querySelectorAll('[data-more-recent]').forEach(b=>b.onclick=()=>{moreRecent=!moreRecent;render();});
  container.querySelectorAll('[data-drag-session]').forEach(row=>row.ondragstart=e=>{e.dataTransfer.setData('application/x-qic-session',row.dataset.dragSession);e.dataTransfer.effectAllowed='move';});
  container.querySelectorAll('[data-drop]').forEach(group=>{
   group.ondragover=e=>{if(e.dataTransfer.types.includes('application/x-qic-session')){e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='move';group.classList.add('drop-target');}};
   group.ondragleave=()=>group.classList.remove('drop-target');
   group.ondrop=safe(async e=>{const sid=e.dataTransfer.getData('application/x-qic-session');if(!sid)return;e.preventDefault();e.stopPropagation();document.querySelectorAll('.drop-target').forEach(x=>x.classList.remove('drop-target'));await mutate({action:'move',session_id:sid,collection_id:group.dataset.drop||null});toast('チャットを移動しました。');});
  });
 }
 async function refresh(){const result=await api('/api/organization');const sig=JSON.stringify(result);model=result;if(sig!==signature){signature=sig;render();}}
 $('newProject').onclick=()=>open('create');$('historySearch').oninput=render;
 return {render,refresh,showChat,restore:async id=>{if(id!==null&&(id===''||model.collections.some(c=>c.id===id)))await showProject(id);},move:(sid,cid)=>mutate({action:'move',session_id:sid,collection_id:cid})};
}
