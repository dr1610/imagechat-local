export function createLibrary({api,safe,toast,esc,assetUrl,openChat,editImage,addReference}){
 const dialog=document.createElement('dialog');dialog.className='library-dialog';dialog.setAttribute('aria-label','画像ライブラリ');
 dialog.innerHTML=`<header><h2>画像ライブラリ</h2><button data-close aria-label="ライブラリを閉じる">閉じる ×</button></header><div class="library-filters"><input type="search" aria-label="画像・プロンプト検索" placeholder="プロンプト・画像名・チャット名で検索"><select aria-label="ライブラリの種類"><option value="all">すべての画像</option><option value="generated">生成画像</option><option value="attached">添付画像</option><option value="favorite">お気に入り</option></select><select aria-label="プロジェクトで絞り込み"></select><select aria-label="チャットで絞り込み"></select><button data-refresh>更新</button></div><p class="library-count" role="status"></p><div class="library-body"><section class="library-results"><div class="library-grid"></div><button data-more hidden>もっと表示する</button></section><section class="library-detail" aria-label="画像とプロンプトの詳細"><p>画像を選ぶとプロンプトを確認できます。</p></section></div>`;
 document.body.append(dialog);
 const $=q=>dialog.querySelector(q),search=$('input'),kind=$('select[aria-label="ライブラリの種類"]'),project=$('select[aria-label="プロジェクトで絞り込み"]'),chat=$('select[aria-label="チャットで絞り込み"]');let data=null,limit=60,selected=null,sequence=0;
 $('[data-close]').onclick=()=>dialog.close();
 function groups(sid){const p=data.organization.placements.find(x=>x.session_id===sid);if(!p?.collection_id)return [];const c=data.organization.collections.find(x=>x.id===p.collection_id);return [p.collection_id,c?.parent_id].filter(Boolean);}
 function render(){
  if(!data)return;const q=search.value.trim().toLocaleLowerCase();
  const items=data.items.filter(e=>(kind.value==='all'||kind.value===e.kind||kind.value==='favorite'&&e.favorite)&&(!chat.value||e.contexts.some(c=>c.session_id===chat.value))&&(!project.value||e.contexts.some(c=>groups(c.session_id).includes(project.value)))&&(!q||[e.name,...e.contexts.flatMap(c=>[c.prompt,c.title])].join('\n').toLocaleLowerCase().includes(q)));
  $('.library-count').textContent=`${items.length}枚 · 画像を選択して指示・設定を確認`;
  $('.library-grid').innerHTML=items.slice(0,limit).map(e=>`<button class="library-card ${e.id===selected?'selected':''}" data-image="${esc(e.id)}" aria-label="${esc(e.name)}の詳細"><img loading="lazy" src="${assetUrl(e.id)}" alt="${esc(e.name)}"><span>${e.favorite?'★ ':''}${e.kind==='generated'?'生成':'添付'}${e.missing?' · ファイル欠損':''}</span><small>${esc(e.contexts[0]?.prompt||e.name)}</small></button>`).join('')||'<p>該当する画像はありません。</p>';
  $('.library-grid').querySelectorAll('[data-image]').forEach(b=>b.onclick=safe(()=>select(b.dataset.image)));
  $('.library-grid').querySelectorAll('img').forEach(img=>img.onerror=()=>{img.alt='画像ファイルを読み込めません';});
  $('[data-more]').hidden=items.length<=limit;
 }
 async function select(aid){
  selected=aid;render();const e=data.items.find(e=>e.id===aid);++sequence;
  $('.library-detail').innerHTML=`<img class="library-preview" src="${assetUrl(aid)}" alt="${esc(e.name)}"><h3>${esc(e.name)} · ${e.width||'?'} × ${e.height||'?'}</h3><div class="library-actions"><button data-star>${e.favorite?'★ お気に入り解除':'☆ お気に入り'}</button><a href="${assetUrl(aid)}?download=1" download>保存</a><button data-ref>今のチャットへ参照追加</button></div><label>生成元・使用履歴<select aria-label="画像の生成元・使用履歴">${e.contexts.map((c,i)=>`<option value="${i}">${esc(c.role==='output'?'生成元':c.role==='input'?'参照として使用':'下書き')} · ${esc(c.title)}</option>`).join('')}</select></label><div class="library-prompt"></div>`;
  $('[data-star]').onclick=safe(async()=>{const value=!e.favorite;const button=$('[data-star]');button.disabled=true;try{await api('/api/library/favorite',{asset_id:aid,favorite:value});e.favorite=value;if(selected===aid)button.textContent=e.favorite?'★ お気に入り解除':'☆ お気に入り';render();}finally{button.disabled=false;}});
  $('[data-ref]').disabled=e.missing;$('[data-ref]').onclick=safe(async()=>{await addReference(aid);dialog.close();});
  const contextSelect=$('select[aria-label="画像の生成元・使用履歴"]');contextSelect.disabled=!e.contexts.length;
  const show=async()=>{
   const n=++sequence,c=e.contexts[Number(contextSelect.value)];const box=$('.library-prompt');box.textContent='読込中…';
   if(!c){box.textContent='添付された画像です。このアプリには作成時のプロンプトが記録されていません。';return;}
   let g=null;if(c.generation_id)g=await api('/api/generations/'+c.generation_id);if(n!==sequence||selected!==aid)return;
   box.innerHTML=`<p class="micro">${c.role==='input'?'この画像を参照に使った指示です。画像自体を作ったプロンプトではありません。':c.role==='draft'?'まだ生成に使われていない下書きです。':''}</p><div class="library-actions"><button data-chat>元チャットへ</button><button data-edit ${e.missing?'disabled':''}>この画像から編集</button></div>${g?`<h3>入力したプロンプト</h3><pre>${esc(g.original_prompt||'（記録なし）')}</pre><h3>Enhancer後の指示</h3><pre>${esc(g.enhanced_prompt||'未使用')}</pre><details><summary>実際に生成へ渡した指示・設定</summary><pre>${esc(g.prompt||'')}</pre><pre>${esc(JSON.stringify({model:g.effective_parameters?.model||g.model_selection?.file,seed:g.params?.seed,width:g.effective_parameters?.width,height:g.effective_parameters?.height,workflow:g.workflow_id,parent:g.parent_generation_id,parameters:g.params},null,2))}</pre></details>`:'<p>生成プロンプトはまだありません。</p>'}`;
   box.querySelector('[data-chat]').onclick=safe(async()=>{await openChat(c.session_id);dialog.close();});
   box.querySelector('[data-edit]').onclick=safe(async()=>{await editImage(aid,c.session_id,c.role==='output'?c.generation_id:null);dialog.close();});
  };
  contextSelect.onchange=safe(show);await show();
 }
 async function load(){const result=await api('/api/library');data=result;const oldChat=chat.value,oldProject=project.value;chat.innerHTML='<option value="">すべてのチャット</option>'+data.sessions.map(s=>`<option value="${esc(s.id)}">${esc(s.title)}</option>`).join('');project.innerHTML='<option value="">すべてのプロジェクト</option>'+data.organization.collections.map(c=>`<option value="${esc(c.id)}">${c.parent_id?'　└ ':''}${esc(c.name)}</option>`).join('');chat.value=oldChat;project.value=oldProject;render();if(selected&&data.items.some(e=>e.id===selected))await select(selected);}
 for(const el of [search,kind,chat,project])el.addEventListener(el===search?'input':'change',()=>{limit=60;render();});
 $('[data-more]').onclick=()=>{limit+=60;render();};$('[data-refresh]').onclick=safe(load);
 return {open:async()=>{dialog.showModal();$('.library-count').textContent='画像一覧を読込中…';await load();}};
}

