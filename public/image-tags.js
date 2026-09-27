// Insert literal reference tokens without losing the textarea selection.
export function renderImageTags(textarea, references, assetUrl) {
 let bar=document.getElementById(textarea.id+'ImageTags');
 if(!bar){
  const wrapper=document.createElement('div');wrapper.className='tagged-prompt';
  textarea.before(wrapper);wrapper.append(textarea);
  bar=document.createElement('div');bar.id=textarea.id+'ImageTags';bar.className='image-tag-bar';bar.setAttribute('role','group');bar.setAttribute('aria-label','参照画像タグを挿入');wrapper.prepend(bar);
 }
 bar.replaceChildren();bar.hidden=!references.length;
 if(!references.length)return;
 const label=document.createElement('span');label.className='image-tag-label';label.textContent='画像を指示に挿入';bar.append(label);
 references.forEach((id,i)=>{
  const token=`<image${i+1}>`,button=document.createElement('button');
  button.type='button';button.className='image-tag-button';button.setAttribute('aria-label',`画像${i+1}のタグを挿入`);button.title=`${token} をカーソル位置に挿入`;
  const img=document.createElement('img');img.src=assetUrl(id);img.alt='';
  const text=document.createElement('span');text.textContent=`画像${i+1} ${token}`;button.append(img,text);
  button.onmousedown=e=>e.preventDefault();
  button.onclick=()=>{
   const start=textarea.selectionStart,end=textarea.selectionEnd;
   textarea.focus();textarea.setRangeText(token,start,end,'end');
   textarea.dispatchEvent(new Event('input',{bubbles:true}));
  };
  bar.append(button);
 });
 const hint=document.createElement('span');hint.className='image-tag-hint';hint.textContent='番号は添付順です。並べ替え・削除後は文中の番号も確認してください。';bar.append(hint);
}
