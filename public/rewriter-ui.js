import {progressMarkup} from './progress-ui.js';
export function createRewriter({state,api,persist,toast,params,editorState}){
 const panels=[], $=id=>document.getElementById(id);let busy=null;
 const payload=()=>({session_id:state.session.id,prompt:$('editorView').hidden?$('prompt').value:$('editorPrompt').value,references:[...(state.draft.references||[])],editor:editorState(),art_style:params().art_style});
 const key=p=>JSON.stringify(p);
 for(const id of ['prompt','editorPrompt']){
  const panel=document.createElement('section');panel.className='rewrite-panel';
  panel.innerHTML='<div class="rewrite-actions"><button type="button" class="rewrite-start">指示を整理 · Qwen公式</button><button type="button" class="rewrite-cancel" hidden>指示整理を停止</button><span class="rewrite-status" role="status"></span></div><div class="rewrite-progress" hidden></div><details hidden><summary>変換した英文を確認・編集</summary><textarea rows="4" aria-label="変換後の英文"></textarea><small class="rewrite-size"></small><p>日本語の原文は保持します。英文を手直ししてから生成できます。</p></details>';
  $(id).after(panel);const p={panel,start:panel.querySelector('.rewrite-start'),cancel:panel.querySelector('.rewrite-cancel'),status:panel.querySelector('.rewrite-status'),progress:panel.querySelector('.rewrite-progress'),details:panel.querySelector('details'),text:panel.querySelector('textarea'),size:panel.querySelector('.rewrite-size')};panels.push(p);
  p.start.onclick=()=>run({manual:true}).catch(e=>toast(e.message));
  p.cancel.onclick=async()=>{if(busy?.id){try{await api('/api/rewrites/'+busy.id+'/cancel',{});}catch(e){toast(e.message);}}};
  p.text.oninput=()=>{if(state.draft.rewrite){state.draft.rewrite.text=p.text.value;for(const q of panels)if(q!==p)q.text.value=p.text.value;persist();}};
 }
 function refresh(){
  const rw=state.draft.rewrite,valid=rw&&rw.key===key(payload());
  for(const p of panels){p.start.disabled=!!busy;p.cancel.hidden=!busy?.id;p.status.textContent=busy?`${busy.job?.stage||'準備中'} · ${Math.floor((Date.now()-busy.started)/1000)}秒` :rw?(valid?'英文を使用できます。':'入力が変わりました。生成前に再変換します。'):'';p.progress.hidden=!busy&&!valid;p.progress.innerHTML=progressMarkup(busy?.job?.progress,{done:!busy&&valid,tokens:true,label:'指示整理の処理量'});p.details.hidden=!rw;if(rw){p.text.value=rw.text;p.size.textContent=`モデル提案の比率：${rw.result.wh_ratio||rw.result.ratio_follow||'元画像'}。出力サイズは通常設定／Canvas設定を使用します。`;}}
 }
 async function run({manual=false}={}){
  if(busy)throw Error('変換中です。完了を待つか停止してください。');
  const body=payload(),sourceKey=key(body);if(!body.prompt.trim())throw Error('変換する指示を入力してください。');
  busy={started:Date.now()};refresh();
  try{
   let j=await api('/api/rewrites',body);busy.id=j.id;busy.job=j;refresh();
   while(['Waiting','Generating'].includes(j.status)){await new Promise(r=>setTimeout(r,1000));j=await api('/api/rewrites/'+j.id);busy.job=j;refresh();}
   if(j.status!=='Completed')throw Error(j.error||(j.status==='Cancelled'?'指示整理を停止しました。':'変換できませんでした。'));
   if(state.session.id!==body.session_id||key(payload())!==sourceKey){toast('変換中に入力が変わったため、結果を適用しませんでした。');return false;}
   state.draft.rewrite={id:j.id,key:sourceKey,text:j.result.rewritten_prompt,result:j.result};if(manual)$('enhancer').value='local';persist();for(const p of panels)p.details.open=true;return true;
  }finally{busy=null;refresh();}
 }
 return {refresh,async beforeSend(){const mode=params().enhancer,sourceKey=key(payload());const plan=await api('/api/generation-plan',{...payload(),params:params()});if(sourceKey!==key(payload())||mode!==params().enhancer)return false;if(!plan.use_enhancer)return {};toast(`指示を整理します：${plan.reason}`);let rw=state.draft.rewrite;if(!rw||rw.key!==key(payload())){if(!await run())return false;rw=state.draft.rewrite;}if(mode!==params().enhancer)return false;return {rewrite_id:rw.id,enhanced_prompt:rw.text};}};
}
