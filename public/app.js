import {setupUpdates} from './updates.js';
import {createLibrary} from './library.js';
import {progressMarkup} from './progress-ui.js';
import {nextEditReferences} from './reference-state.js';
import {createModelUI} from './model-ui.js';
import {CanvasEditor} from './editor.js';
import {setupCommunity} from './community-ui.js';
import {createRewriter} from './rewriter-ui.js';
import {renderImageTags} from './image-tags.js';
import {createOrganizer} from './organization.js';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={token:'',sessions:[],session:null,draft:{},defaults:{},settings:{},assets:new Map(),signature:'',polling:false,sending:false};
const draftChains=new Map();let saveTimer,toastTimer,switchSequence=0;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
function showInfo(title,data){$('infoTitle').textContent=title;$('infoContent').textContent=typeof data==='string'?data:JSON.stringify(data,null,2);$('infoDialog').showModal();}
async function api(path,data,options={}){
 const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-QIC-Token':state.token,...options.headers},body:data===undefined?undefined:options.raw?data:JSON.stringify(data)});
 const out=await r.json();if(r.status===403&&!options.retried){const boot=await fetch('/api/bootstrap').then(r=>r.json());state.token=boot.token;return api(path,data,{...options,retried:true});}if(!r.ok){const error=new Error(out.error?.message||'通信に失敗しました。');error.detail=out.error;throw error;}return out;
}
function safe(fn){return (...args)=>{try{return Promise.resolve(fn(...args)).catch(e=>{toast(e.message);console.error(e.detail||e);});}catch(e){toast(e.message);console.error(e.detail||e);}};}
function theme(value){state.settings.theme=value;document.documentElement.dataset.theme=value==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):value;}
const controls={model_preset:'modelPreset',sampling_policy:'samplingPolicy',negative_prompt:'negativePrompt',art_style:'artStyle',aspect:'aspect',resolution:'resolution',seed_mode:'seedMode',seed:'seed',steps:'steps',cfg:'cfg',sampler:'sampler',scheduler:'scheduler',denoise:'denoise',mask_blur:'maskBlur',mask_grow:'maskGrow',control_strength:'controlStrength',workflow:'workflow'};
function captureParams(){const p={...state.defaults,...state.draft.params};for(const [key,id]of Object.entries(controls)){p[key]=['resolution','seed','steps','cfg','denoise','mask_blur','mask_grow','control_strength'].includes(key)?Number($(id).value):$(id).value;}return p;}
function applyParams(){const p={...state.defaults,...state.draft.params};for(const [key,id]of Object.entries(controls)){if($(id).tagName==='SELECT'&&!Array.from($(id).options).some(o=>o.value===String(p[key])))$(id).add(new Option(p[key],p[key]));$(id).value=p[key];}$('editorArtStyle').value=p.art_style||'none';modelUI.refresh();}
function persist(immediate=false){if(!state.session)return;state.draft.prompt=$('prompt').value;state.draft.params=captureParams();const sid=state.session.id,draft=structuredClone(state.draft);clearTimeout(saveTimer);const send=()=>{const prev=draftChains.get(sid)||Promise.resolve();const next=prev.catch(()=>{}).then(()=>api('/api/sessions/'+sid,{draft})).catch(e=>toast('下書き保存：'+e.message));draftChains.set(sid,next);return next;};if(immediate)return send();saveTimer=setTimeout(send,350);}
function renderSessions(){
 organizer.render();
}
async function switchSession(sid){
 if(!$('editorView').hidden)closeEditor();organizer.showChat();if(state.session?.id===sid){$('chatTitle').textContent=state.session.title;return;}const seq=++switchSequence;if(!$('editorView').hidden)closeEditor();await persist(true);const session=await api('/api/sessions/'+sid);if(seq!==switchSequence)return;state.session=session;localStorage.setItem('qic.lastSession',sid);state.draft=structuredClone(session.draft||{});state.draft.references||=[];state.draft.editors||={};state.signature='';$('chatTitle').textContent=session.title;$('prompt').value=state.draft.prompt||'';applyParams();renderSessions();renderRefs();renderMessages(true);
}
async function refreshSessions(){state.sessions=await api('/api/sessions');await organizer.refresh();renderSessions();}
async function newSession(collection=null){const s=await api('/api/sessions',{});if(typeof collection==='string')await organizer.move(s.id,collection);await refreshSessions();await switchSession(s.id);$('prompt').focus();}
const organizer=createOrganizer({api,state,esc,safe,toast,switchSession,refreshSessions,newSession,leaveChat:async()=>{++switchSequence;if(!$('editorView').hidden)closeEditor();await persist(true);}});
function assetUrl(id){return '/api/assets/'+id;}
function rememberAssets(gens){for(const g of gens)for(const a of g.outputs||[])state.assets.set(a.id,a);}
async function assetInfo(id){if(state.assets.has(id))return state.assets.get(id);const img=new Image();img.src=assetUrl(id);await img.decode();const a={id,name:'添付画像',width:img.naturalWidth,height:img.naturalHeight};state.assets.set(id,a);return a;}
function renderRefs(){
 rewriteUI.refresh();modelUI.refresh();
 for(const id of ['prompt','editorPrompt'])renderImageTags($(id),state.draft.references||[],assetUrl);
 const refs=state.draft.references||[];$('references').innerHTML=refs.map((id,i)=>`<div class="reference-chip"><img src="${assetUrl(id)}" alt="${i+1}枚目の参照画像" data-open="${id}"><span>${i===0?'編集対象':'参照'} ${i+1}</span><button data-canvas="${id}" aria-label="${i+1}枚目をCanvasで編集" title="Canvasで編集">✎</button>${i>0?`<button data-up="${i}" aria-label="画像の順序を前に">‹</button>`:''}<button data-remove="${i}" aria-label="${i+1}枚目を解除">×</button></div>`).join('');
 $('references').querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>enlarge(b.dataset.open));
 $('references').querySelectorAll('[data-canvas]').forEach(b=>b.onclick=safe(()=>openEditor(b.dataset.canvas)));
 $('references').querySelectorAll('[data-up]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.up);[refs[i-1],refs[i]]=[refs[i],refs[i-1]];state.draft.editor=null;state.draft.parent_generation_id=null;renderRefs();persist();});
 $('references').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.remove);refs.splice(i,1);if(i===0){state.draft.parent_generation_id=null;state.draft.editor=null;}renderRefs();persist();});
 const e=state.draft.editor;$('editorChip').hidden=!e;$('editorChip').innerHTML=e?`✎ Canvas編集あり · ${e.width} × ${e.height} · Sketch / Mask / Pose を保持 <button id="reopenEditor">編集を開く</button><button id="detachEditor">適用を解除</button>`:'';
 $('aspect').disabled=!!e;$('resolution').disabled=!!e;$('resolution').title=e?'Canvas Editorのピクセル寸法を使用します。':'生成サイズの目安。実際の寸法は比率に応じて調整します。';
 if(e){$('reopenEditor').onclick=safe(()=>openEditor(refs[0]));$('detachEditor').onclick=()=>{state.draft.editor=null;renderRefs();persist();};}
 $('prompt').placeholder=refs.length?'この画像をどう変えますか？':'どんな画像をつくりますか？ 日本語で自由にどうぞ。';
}
function enlarge(id){$('largeImage').src=assetUrl(id);$('imageDialog').showModal();}
function elapsed(g){return Math.max(0,Math.round((g.completed||Date.now()/1000)-g.created));}
function renderMessages(force=false){
 const gens=state.session.generations||[];rememberAssets(gens);const signature=JSON.stringify(gens.map(g=>[g.id,g.status,g.stage,g.progress,g.outputs?.length,g.error]));if(!force&&signature===state.signature)return;state.signature=signature;
 const nearBottom=$('messages').scrollHeight-$('messages').scrollTop-$('messages').clientHeight<160;
 if(!gens.length){$('messages').innerHTML=`<div class="welcome"><div class="intro-mark">✳</div><span class="eyebrow">IMAGINE. TALK. CREATE.</span><h1>思い描いたその一枚を、<br>会話から。</h1><p>日本語で伝えて、画像をつくる。<br>描き足したり、ポーズを変えたり。何度でも、ここから。</p><div class="suggestions"><button data-suggest="夕方の学校の教室。誰もいない。"><small>風景をつくる</small>夕方の教室を描いて ↗</button><button id="welcomeAttach"><small>画像からはじめる</small>画像を添付して編集 ↗</button></div><p class="welcome-note">Qwen-Image 2.1 · ローカル生成 · 元画像はそのまま</p></div>`;$('welcomeAttach').onclick=()=>$('fileInput').click();document.querySelectorAll('[data-suggest]').forEach(b=>b.onclick=()=>{$('prompt').value=b.dataset.suggest;persist();$('prompt').focus();});}
 else $('messages').innerHTML=gens.map((g,i)=>{
  const parent=gens.findIndex(x=>x.id===g.parent_generation_id),label={t2i:'新しい画像',edit:'画像編集',multi_reference:'複数画像から編集',sketch:'Sketchで編集',inpaint:'部分修正',outpaint:'Canvas拡張',pose:'ポーズ指定'}[g.intent]||'準備中';
  let content='';if(g.status==='Completed'){content=(g.outputs||[]).map(a=>`<img class="result-image" src="${assetUrl(a.id)}" alt="${esc(g.original_prompt)}" data-enlarge="${a.id}" loading="lazy"><div class="image-actions"><button data-enlarge="${a.id}">⌕ 拡大</button><a href="${assetUrl(a.id)}?download=1" download>↓ 保存</a><button data-regenerate="${g.id}">↻ 再生成</button><button data-edit="${g.id}" data-asset="${a.id}">✎ この画像から編集</button><button data-editor="${g.id}" data-asset="${a.id}">▧ Canvasで編集</button><button data-reference="${a.id}">＋ 参照に使用</button><button data-info="${g.id}" aria-label="生成情報">•••</button></div>`).join('');}
  else if(g.status==='Failed'){content=`<div class="state-card error"><strong>生成を完了できませんでした</strong><p class="error-text">${esc(g.error?.message)}</p><p>${esc(g.error?.category)} · 入力と元画像は保持されています。</p><button data-regenerate="${g.id}">同じ入力で再試行</button> ${g.prompt_id?`<button data-recover="${g.id}">結果を再取得</button>`:''} <button data-info="${g.id}">詳細</button></div>`;}
  else if(g.status==='Cancelled'){content=`<div class="state-card"><strong>生成を停止しました</strong><p>元画像と入力は残っています。</p><button data-regenerate="${g.id}">もう一度生成</button></div>`;}
  else {const pc=g.progress?.max?Math.round(g.progress.value/g.progress.max*100):0;content=`<div class="state-card"><strong><span class="pending-dot"></span>${esc(g.stage)}</strong>${progressMarkup(g.progress,{label:'画像生成進捗'})}<button data-cancel="${g.id}" ${g.cancel_requested?'disabled':''}>${g.cancel_requested?'停止要求中':'生成を停止'}</button></div>`;}
  return `<article class="generation" data-generation="${g.id}"><div class="user-message"><span class="user-avatar">U</span><div><div class="message-text">${esc(g.original_prompt)}</div>${g.references?.length?`<div class="input-mini">${g.references.map((a,j)=>`<img src="${assetUrl(a)}" alt="入力画像 ${j+1}">`).join('')}</div>`:''}</div></div><div class="generation-body"><div class="generation-label"><b>QWEN IMAGE</b><span>#${i+1} · ${label}${g.params?.art_style&&g.params.art_style!=='none'?' · '+({illustration:'イラスト',photoreal:'フォトリアル'}[g.params.art_style]||''):''}${g.model_selection?.label?' · '+esc(g.model_selection.label):''}${parent>=0?` · #${parent+1}から派生`:''}${g.regenerated_from_generation_id?' · 再生成':''}${g.status==='Completed'?` · ${elapsed(g)}秒`:''}</span></div>${content}</div></article>`;
 }).join('');
 const active=gens.filter(g=>!['Completed','Failed','Cancelled'].includes(g.status));$('activeJobs').innerHTML=active.length?`<span class="pending-dot"></span>${active.length}件の生成を処理しています。チャットを切り替えても続行します。<button data-cancel="${active[0].id}">停止</button>`:'';
 for(const container of [$('messages'),$('activeJobs')]){
  container.querySelectorAll('[data-enlarge]').forEach(b=>b.onclick=()=>enlarge(b.dataset.enlarge));
  container.querySelectorAll('[data-edit]').forEach(b=>b.onclick=safe(()=>selectImage(b.dataset.asset,b.dataset.edit)));
  container.querySelectorAll('[data-editor]').forEach(b=>b.onclick=safe(async()=>{await selectImage(b.dataset.asset,b.dataset.editor);await openEditor(b.dataset.asset);}));
  container.querySelectorAll('[data-reference]').forEach(b=>b.onclick=()=>{if(state.draft.references.length>=10){toast('参照画像は10枚までです。');return;}state.draft.references.push(b.dataset.reference);renderRefs();persist();});
  container.querySelectorAll('[data-regenerate]').forEach(b=>b.onclick=safe(async()=>{await api(`/api/generations/${b.dataset.regenerate}/regenerate`,{});toast('元の入力と設定から別案を生成します。');await poll(true);}));
  container.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=safe(async()=>{await api(`/api/generations/${b.dataset.cancel}/cancel`,{});await poll(true);}));
  container.querySelectorAll('[data-recover]').forEach(b=>b.onclick=safe(async()=>{await api(`/api/generations/${b.dataset.recover}/recover`,{});await poll(true);}));
  container.querySelectorAll('[data-info]').forEach(b=>b.onclick=()=>showInfo('生成情報・実際の入力',gens.find(g=>g.id===b.dataset.info)));
 }
 $('messages').querySelectorAll('img').forEach(img=>{img.onerror=()=>{img.onerror=null;img.alt='画像ファイルが見つかりません。生成情報から確認してください。';img.style.minHeight='60px';};if(force||nearBottom)img.onload=()=>{$('messages').scrollTop=$('messages').scrollHeight;};});
 if(force||nearBottom)$('messages').scrollTop=$('messages').scrollHeight;
}
async function selectImage(aid,gid){await assetInfo(aid);const source=(state.session.generations||[]).find(g=>g.id===gid);state.draft.references=nextEditReferences(aid,source?.references||state.draft.references);state.draft.parent_generation_id=gid||null;state.draft.editor=null;state.draft.params={...captureParams(),aspect:'original'};applyParams();renderRefs();persist();$('prompt').focus();toast('この画像を次の編集対象にしました。参照画像は保持しています。');}
const editor=new CanvasEditor(s=>{state.draft.editor=s;state.draft.editors[state.draft.references[0]]=s;persist();},toast);
async function openEditor(aid){
 if(state.draft.references[0]!==aid){const refs=state.draft.references.filter(x=>x!==aid);state.draft.references=[aid,...refs];state.draft.parent_generation_id=(state.session.generations||[]).find(g=>g.outputs?.some(a=>a.id===aid))?.id||null;state.draft.editor=null;}
 const a=await assetInfo(aid);renderRefs();$('chatView').hidden=true;$('editorView').hidden=false;$('editorSource').textContent=`${a.width} × ${a.height}`;$('editorPrompt').value=$('prompt').value;await editor.open(a,state.draft.editor||state.draft.editors[aid]);state.draft.editor=editor.snapshot();state.draft.editors[aid]=state.draft.editor;persist();
}
function closeEditor(){if($('editorView').hidden)return;state.draft.editor=editor.snapshot();state.draft.editors[state.draft.references[0]]=state.draft.editor;$('prompt').value=$('editorPrompt').value;$('chatView').hidden=false;$('editorView').hidden=true;renderRefs();persist();}
async function send(){
 if(state.sending)return;const prompt=$('prompt').value;if(!prompt.trim()){toast('作りたい画像や変更内容を入力してください。');$('prompt').focus();return;}
 state.sending=true;$('send').disabled=true;
 try{const sid=state.session.id;const rewritten=await rewriteUI.beforeSend();if(rewritten===false||state.session.id!==sid)return;const body={session_id:sid,request_id:crypto.randomUUID(),prompt,references:[...state.draft.references],parent_generation_id:state.draft.parent_generation_id||null,editor:state.draft.editor||null,params:captureParams(),...rewritten};if(!body.references.length&&body.params.aspect==='original')body.params.aspect='1:1';
  await persist(true);const g=await api('/api/generate',body);
  if(state.session.id===sid){state.draft.lastSubmitted=g.id;$('prompt').value='';state.draft.prompt='';await persist(true);await poll(true);}
  else{const previous=await api('/api/sessions/'+sid);const draft=previous.draft||{};draft.lastSubmitted=g.id;if(draft.prompt===prompt)draft.prompt='';await api('/api/sessions/'+sid,{draft});}
 }finally{state.sending=false;$('send').disabled=false;}
}
async function attachFiles(files){if(!$('projectView').hidden){toast('チャットを開いてから画像を添付してください。');return;}const sid=state.session.id;for(const file of files){if(state.draft.references.length>=10){toast('画像は10枚まで添付できます。');break;}if(file.size>40*1024*1024){toast('画像は40MB以下にしてください。');continue;}const a=await api('/api/assets',file,{raw:true,headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)}});state.assets.set(a.id,a);if(state.session.id!==sid){toast('チャットが切り替わったため、添付を中断しました。');break;}state.draft.references.push(a.id);}renderRefs();persist();$('fileInput').value='';}
async function poll(force=false){
 if(state.polling||!state.session)return;state.polling=true;const sid=state.session.id;
 try{const session=await api('/api/sessions/'+sid);if(state.session.id!==sid)return;state.session=session;rememberAssets(session.generations);
  const last=state.draft.lastSubmitted&&session.generations.find(g=>g.id===state.draft.lastSubmitted);
  if(last?.status==='Completed'&&last.outputs.length&&state.draft.lastAutoSelected!==last.id&&$('editorView').hidden&&!$('chatView').hidden){
   // Only advance the target if the user has not selected a different image meanwhile.
   if(JSON.stringify(state.draft.references)===JSON.stringify(last.references)){state.draft.references=nextEditReferences(last.outputs[0].id,last.references);state.draft.parent_generation_id=last.id;state.draft.editor=null;state.draft.params={...captureParams(),aspect:'original'};applyParams();renderRefs();}
   state.draft.lastAutoSelected=last.id;persist();
  }
  renderMessages(force);
 }catch(e){if(force)toast(e.message);}finally{state.polling=false;}
}
function fillSelect(id,values,current,auto='自動検出'){const el=$(id);el.replaceChildren(new Option(auto,''),...values.map(x=>new Option(x,x)));el.value=current||'';}
async function checkConnection(url){
 const result=await api('/api/connection',{url:url||state.settings.comfy_url});$('connectionBadge').innerHTML='<span class="status-dot"></span><span>ローカル接続中</span>';
 const sys=result.system.system,gpu=result.system.devices?.[0];$('connectionResult').textContent=`ComfyUI ${sys.comfyui_version} · ${gpu?.name||''} · ${result.missing_nodes.length?'不足Node: '+result.missing_nodes.join(', '):'基本Node確認済み'}${result.control_available?' · ポーズ/部分修正のNodeあり':''}`;
 const selected={...state.settings};for(const [key,id]of Object.entries({model:'modelSetting',text_encoder:'encoderSetting',vae:'vaeSetting',control_model:'controlSetting'}))fillSelect(id,result.models[key],selected[key]);
 for(const [key,id]of [['samplers','sampler'],['schedulers','scheduler']]){const current=$(id).value;$(id).replaceChildren(...result[key].map(v=>new Option(v,v)));$(id).value=current;}
 return result;
}
async function refreshConnectionBadge(){try{const r=await api('/api/comfy-status');$('connectionBadge').innerHTML=r.connected?'<span class="status-dot"></span><span>ローカル接続中</span>':'<span class="status-dot offline"></span><span>ComfyUI 未接続</span>';}catch(e){$('connectionBadge').innerHTML='<span class="status-dot offline"></span><span>アプリ 再接続待ち</span>';}}
function openSettings(){$('themeSetting').value=state.settings.theme;$('comfyUrl').value=state.settings.comfy_url;$('settingsDialog').showModal();}
$('settingsButton').onclick=openSettings;$('connectionBadge').onclick=openSettings;
$('testConnection').onclick=safe(async()=>{$('connectionResult').textContent='接続を確認しています…';try{await checkConnection($('comfyUrl').value);}catch(e){$('connectionResult').textContent=e.message;throw e;}});
$('saveSettings').onclick=safe(async()=>{const settings={comfy_url:$('comfyUrl').value,theme:$('themeSetting').value};for(const [key,id]of Object.entries({model:'modelSetting',text_encoder:'encoderSetting',vae:'vaeSetting',control_model:'controlSetting'})){if($(id).options.length)settings[key]=$(id).value;}state.settings=await api('/api/settings',settings);theme(state.settings.theme);$('settingsDialog').close();toast('設定を保存しました。');try{await checkConnection();}catch(e){$('connectionBadge').innerHTML='<span class="status-dot offline"></span><span>未接続</span>';}});
$('themeToggle').onclick=safe(async()=>{const value=document.documentElement.dataset.theme==='dark'?'light':'dark';theme(value);await api('/api/settings',{theme:value});});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if(state.settings.theme==='system')theme('system');});
$('shutdown').onclick=safe(async()=>{if(!$('editorView').hidden)closeEditor();await persist(true);await api('/api/shutdown',{});$('settingsDialog').close();toast('アプリを終了しました。このタブを閉じてください。');});
$('artStyle').onchange=()=>{$('editorArtStyle').value=$('artStyle').value;persist();};$('editorArtStyle').onchange=()=>{$('artStyle').value=$('editorArtStyle').value;persist();};
$('newChat').onclick=safe(newSession);$('send').onclick=safe(send);$('attach').onclick=()=>$('fileInput').click();$('fileInput').onchange=safe(e=>attachFiles(e.target.files));
$('prompt').addEventListener('input',()=>persist());$('prompt').addEventListener('keydown',safe(async e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();await send();}}));
for(const id of Object.values(controls))$(id).addEventListener('change',()=>persist());
$('advancedToggle').onclick=()=>{$('advanced').hidden=!$('advanced').hidden;$('advancedToggle').setAttribute('aria-expanded',String(!$('advanced').hidden));};
$('newImage').onclick=()=>{state.draft.references=[];state.draft.parent_generation_id=null;state.draft.editor=null;state.draft.params={...captureParams(),aspect:'1:1'};applyParams();renderRefs();persist();$('prompt').focus();};
$('backToChat').onclick=closeEditor;$('editorGenerate').onclick=safe(async()=>{closeEditor();await send();});$('editorPrompt').oninput=()=>{$('prompt').value=$('editorPrompt').value;persist();};
$('renameChat').onclick=()=>{$('renameInput').value=state.session.title;$('renameDialog').showModal();$('renameInput').focus();};$('cancelRename').onclick=()=>$('renameDialog').close();
$('renameForm').onsubmit=safe(async e=>{e.preventDefault();const title=$('renameInput').value;await api('/api/sessions/'+state.session.id,{title});state.session.title=title;$('chatTitle').textContent=title;$('renameDialog').close();await refreshSessions();});
let dragDepth=0;document.addEventListener('dragenter',e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();dragDepth++;$('dropOverlay').hidden=false;}});document.addEventListener('dragover',e=>{if(e.dataTransfer.types.includes('Files'))e.preventDefault();});document.addEventListener('dragleave',()=>{dragDepth--;if(dragDepth<=0)$('dropOverlay').hidden=true;});document.addEventListener('drop',safe(async e=>{e.preventDefault();dragDepth=0;$('dropOverlay').hidden=true;if(e.dataTransfer.files.length)await attachFiles(e.dataTransfer.files);}));
document.addEventListener('paste',safe(async e=>{const files=[...(e.clipboardData?.items||[])].filter(i=>i.kind==='file').map(i=>i.getAsFile());if(files.length){e.preventDefault();await attachFiles(files);}}));
document.addEventListener('visibilitychange',()=>{if(document.hidden)persist(true);});
async function init(){
 const boot=await api('/api/bootstrap');state.token=boot.token;state.settings=boot.settings;state.defaults=boot.defaults;state.sessions=boot.sessions;theme(state.settings.theme);for(const w of boot.workflows)$('workflow').add(new Option(w.label+(w.error?' (エラー)':''),w.id));
 await modelUI.load();await organizer.refresh();const project=localStorage.getItem('qic.projectView');const last=localStorage.getItem('qic.lastSession');if(!state.sessions.length)await newSession();else await switchSession(state.sessions.some(s=>s.id===last)?last:state.sessions[0].id);await organizer.restore(project);
 try{await checkConnection();}catch(e){$('connectionBadge').innerHTML='<span class="status-dot offline"></span><span>ComfyUI 未接続</span>';}
 setInterval(()=>poll(),1800);setInterval(()=>refreshSessions().catch(()=>{}),12000);setInterval(refreshConnectionBadge,10000);
}
controls.enhancer='enhancer';
controls.quality_profile='qualityProfile';controls.outpaint_mode='outpaintMode';
for(const id of ['prompt','editorPrompt'])renderImageTags($(id),[],assetUrl);
const rewriteUI=createRewriter({state,api,persist,toast,params:captureParams,editorState:()=>$('editorView').hidden?state.draft.editor||null:editor.snapshot()});
setupCommunity({state,persist,toast,refresh:()=>rewriteUI.refresh()});
const modelUI=createModelUI({state,persist,api});
$('enhancer').addEventListener('change',()=>{persist();rewriteUI.refresh();});
const libraryUI=createLibrary({api,safe,toast,esc,assetUrl,openChat:switchSession,
 editImage:async(aid,sid,gid)=>{await switchSession(sid);await selectImage(aid,gid);},
 addReference:async aid=>{if(!state.session)await newSession();if(state.draft.references.length>=10)throw Error('参照画像は10枚までです。');organizer.showChat();state.draft.references.push(aid);renderRefs();await persist(true);toast('今のチャットに参照画像を追加しました。');}});
$('openLibrary').onclick=safe(async()=>{if(!$('editorView').hidden)closeEditor();await persist(true);await libraryUI.open();});
init().then(()=>setupUpdates({api,persist})).catch(e=>{toast(e.message);showInfo('起動エラー',e.detail||e.message);});
