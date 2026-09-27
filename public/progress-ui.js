export function progressMarkup(progress,{done=false,tokens=false,label='生成進捗'}={}){
 const value=Number(progress?.value),max=Number(progress?.max),known=Number.isFinite(value)&&Number.isFinite(max)&&max>0;
 const percent=done?100:known?Math.max(0,Math.min(100,Math.floor(value/max*100))):null;
 const detail=done?'完了':known?`${value.toLocaleString()} / ${max.toLocaleString()} ${tokens?'トークン（上限に対する割合）':'ステップ'}`:'準備・読込中';
 return `<div class="progress-summary"><span>${detail}</span><strong>${percent===null?'—':percent}%</strong></div><div class="progress-track ${percent===null?'indeterminate':''}" role="progressbar" aria-label="${label}" aria-valuemin="0" aria-valuemax="100" ${percent===null?'':`aria-valuenow="${percent}"`}><span style="width:${percent===null?25:percent}%"></span></div>${tokens&&!done?'<small class="progress-note">思考と英文生成の処理量です。完成までの残り時間や完成率ではありません。</small>':''}`;
}
