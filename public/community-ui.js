export function setupCommunity({state,persist,toast}){
 const $=id=>document.getElementById(id);
 $('qualityProfile').addEventListener('change',()=>{
  const turbo=$('qualityProfile').value==='turbo4';
  if(turbo){state.draft.standardSampling=Object.fromEntries(['steps','cfg','sampler','scheduler','denoise'].map(k=>[k,$(k).value]));for(const [k,v]of Object.entries({steps:4,cfg:1,sampler:'euler',scheduler:'simple',denoise:1}))$(k).value=v;toast('試用の高速4step：細部や指示の追従が標準より低下する場合があります。');}
  else if(state.draft.standardSampling){for(const [k,v]of Object.entries(state.draft.standardSampling))$(k).value=v;delete state.draft.standardSampling;}
  persist();
 });
 $('outpaintMode').addEventListener('change',()=>persist());
}
