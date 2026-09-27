export function createModelUI({state,persist,api}) {
 const $=id=>document.getElementById(id);let catalog,sequence=0,timer;
 async function refresh(){
  if(!catalog)return;
  const seq=++sequence,sid=state.session?.id;
  const body={prompt:$('prompt').value,references:state.draft.references||[],editor:state.draft.editor||null,params:{model_preset:$('modelPreset').value,art_style:$('artStyle').value,sampling_policy:$('samplingPolicy').value,quality_profile:$('qualityProfile').value,outpaint_mode:$('outpaintMode').value,enhancer:$('enhancer').value}};
  try{
   const result=await api('/api/generation-plan',body);
   if(seq!==sequence||sid!==state.session?.id)return;
   const profile=result.model;
   if($('samplingPolicy').value==='recommended'&&$('qualityProfile').value==='standard'){
    for(const [key,value]of Object.entries(profile.settings||{})){const control=$(key==='control_strength'?'controlStrength':key);if(control)control.value=value;}
    $('controlStrength').value=profile.settings?.control_strength??1;
    $('negativePrompt').value=profile.negative||'';
   }
   $('modelNotice').textContent=`使用モデル：${profile.label} · ${profile.reason} · ${result.use_enhancer?'指示整理：'+result.reason:'原文で生成'}`;
  }catch(e){if(seq===sequence)$('modelNotice').textContent='設定確認：'+e.message;}
 }
 for(const id of ['modelPreset','samplingPolicy','artStyle','editorArtStyle','qualityProfile','outpaintMode','enhancer'])$(id).addEventListener('change',()=>{refresh();persist();});
 for(const id of ['steps','cfg','sampler','scheduler','denoise','negativePrompt','controlStrength'])$(id).addEventListener('input',()=>{sequence++;$('samplingPolicy').value='manual';persist();});
 $('prompt').addEventListener('input',()=>{sequence++;clearTimeout(timer);timer=setTimeout(refresh,250);});
 return {refresh,async load(){const r=await fetch('/model-catalog.json');if(!r.ok)throw Error('モデル一覧を読み込めません。');catalog=await r.json();const previous=$('modelPreset').value;$('modelPreset').replaceChildren(new Option('自動 · 画風に合わせる','auto'),...Object.entries(catalog.models).map(([id,p])=>new Option(p.label,id)),new Option('接続設定のモデル','settings'));$('modelPreset').value=previous||'auto';refresh();}};
}
