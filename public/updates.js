export function setupUpdates({api,persist}) {
 const panel=document.createElement('section');
 panel.innerHTML='<hr><h3>アプリの更新</h3><label><input type="checkbox" id="autoUpdateCheck"> 起動時にGitHubの更新を確認</label><p class="micro">リリース情報だけを取得します。画像・プロンプトは送信しません。</p><p id="updateStatus" role="status"></p><details><summary>更新内容</summary><pre id="updateNotes" style="white-space:pre-wrap;max-height:12rem;overflow:auto"></pre></details><button id="checkUpdate" type="button">更新を確認</button> <button id="installUpdate" type="button" hidden>更新して再起動</button><p class="micro">生成・Enhancer完了後に更新します。ローカル変更との競合時は停止します。</p>';
 document.querySelector('#settingsDialog .dialog-body').append(panel);
 const badge=document.createElement('button');badge.type='button';badge.hidden=true;badge.textContent='更新があります';
 document.querySelector('.header-actions').prepend(badge);
 badge.onclick=()=>document.getElementById('settingsDialog').showModal();
 const get=id=>panel.querySelector('#'+id);let restarting=false,version=null;
 function render(s){
  if(version===null)version=s.current;
  else if(s.current!==version){location.reload();return;}
  get('autoUpdateCheck').checked=s.automatic;
  get('updateStatus').textContent=`現在 ${s.current}：${s.message}`+(s.last_result?'\n'+s.last_result.message:'');
  get('updateNotes').textContent=s.notes||'公開リリースの更新内容がここに表示されます。';
  get('installUpdate').hidden=s.status!=='available'||!s.supported;
  get('checkUpdate').disabled=['checking','downloading','waiting','restarting'].includes(s.status);
  badge.hidden=s.status!=='available';
  if(s.status==='restarting')restarting=true;
 }
 async function action(body){try{render(await api('/api/updates',body));}catch(e){get('updateStatus').textContent=e.message;}}
 get('checkUpdate').onclick=()=>action({action:'check'});
 get('installUpdate').onclick=async()=>{await persist(true);await action({action:'install'});};
 get('autoUpdateCheck').onchange=()=>action({action:'settings',automatic:get('autoUpdateCheck').checked});
 async function poll(){try{render(await api('/api/updates'));}catch(e){if(restarting)get('updateStatus').textContent='再起動しています…';}}
 poll();setInterval(poll,2500);
}
