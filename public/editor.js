import {bounds,handles,transform,segmentDistance} from './pose-geometry.mjs';
const $ = id => document.getElementById(id);
const clone = x => structuredClone(x);
const EDGES=[[1,2],[1,5],[2,3],[3,4],[5,6],[6,7],[1,8],[8,9],[9,10],[1,11],[11,12],[12,13],[1,0],[0,14],[14,16],[0,15],[15,17]];
const COLORS=['#ff0000','#ff5500','#ffaa00','#ffff00','#aaff00','#55ff00','#00ff00','#00ff55','#00ffaa','#00ffff','#00aaff','#0055ff','#0000ff','#5500ff','#aa00ff','#ff00ff','#ff00aa','#ff0055'];
const JOINT_NAMES=['鼻','首','右肩','右肘','右手首','左肩','左肘','左手首','右腰','右膝','右足首','左腰','左膝','左足首','右目','左目','右耳','左耳'];
const STANDING=[[.50,.12],[.50,.23],[.38,.25],[.32,.40],[.27,.55],[.62,.25],[.68,.40],[.73,.55],[.43,.52],[.40,.72],[.38,.92],[.57,.52],[.60,.72],[.62,.92],[.46,.10],[.54,.10],[.42,.12],[.58,.12]];

export class CanvasEditor {
 constructor(onChange,notify){
  this.onChange=onChange;this.notify=notify;this.canvas=$('canvas');this.ctx=this.canvas.getContext('2d');this.tool='pen';this.zoom=1;this.pan={x:0,y:0};this.visible={sketch:true,mask:true,pose:true};this.selectedPose=-1;this.undoStack=[];this.redoStack=[];this.space=false;this.poseMode='joint';this.hover=null;this.selectedJoint=-1;this.selection=[];
  document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>this.setTool(b.dataset.tool));
  document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('selected',x===b));if(b.dataset.mode==='expand')$('canvasAspect').focus();else this.setTool({draw:'pen',mask:'mask',pose:'pose'}[b.dataset.mode]);});
  document.querySelectorAll('[data-layer]').forEach(b=>b.onchange=()=>{this.visible[b.dataset.layer]=b.checked;this.draw();});
  $('brushSize').oninput=()=>$('brushValue').textContent=$('brushSize').value;
  $('undo').onclick=()=>this.undo();$('redo').onclick=()=>this.redo();$('fitCanvas').onclick=()=>this.fit();$('zoomIn').onclick=()=>this.scale(1.2);$('zoomOut').onclick=()=>this.scale(1/1.2);
  $('poseMode').onchange=()=>{this.poseMode=$('poseMode').value;this.selection=this.poseMode==='whole'&&this.selectedPose>=0?this.personRefs(this.selectedPose):[];this.setTool('pose');this.sync();this.draw();};$('baseOpacity').oninput=()=>this.draw();
  $('addPose').onclick=()=>this.addPose();$('poseSelect').onchange=()=>{this.selectedPose=Number($('poseSelect').value);this.selectedJoint=-1;this.selection=this.personRefs(this.selectedPose);this.setTool('pose');this.sync();this.draw();};
  $('duplicatePose').onclick=()=>this.poseAction('duplicate');$('flipPose').onclick=()=>this.poseAction('flip');$('smallerPose').onclick=()=>this.poseAction('small');$('largerPose').onclick=()=>this.poseAction('large');$('rotatePose').onclick=()=>this.poseAction('rotate');$('removePose').onclick=()=>this.poseAction('delete');
  $('restoreJoints').onclick=()=>{this.checkpoint();this.state.poses.forEach(p=>p.hidden=[]);this.changed();};$('deletePerson').onclick=()=>this.poseAction('deletePerson');$('tiltPose').onclick=()=>this.poseAction('tilt');$('flipVerticalPose').onclick=()=>this.poseAction('flipVertical');
  $('canvasAspect').onchange=()=>this.proposeSize();$('applyCanvas').onclick=()=>this.expand();
  $('resetCanvas').onclick=()=>{if(!this.state)return;this.checkpoint();this.state={width:this.image.width,height:this.image.height,x:0,y:0,strokes:[],poses:[]};this.changed();this.fit();};
  this.canvas.addEventListener('pointerdown',e=>this.down(e));this.canvas.addEventListener('pointermove',e=>this.move(e));this.canvas.addEventListener('pointerup',e=>this.up(e));this.canvas.addEventListener('pointercancel',e=>this.cancelDrag(e));this.canvas.addEventListener('pointerleave',()=>{if(!this.drag){this.hover=null;this.draw();}});
  this.canvas.addEventListener('wheel',e=>{e.preventDefault();this.scale(Math.exp(-e.deltaY*.001),e.offsetX,e.offsetY);},{passive:false});
  this.canvas.addEventListener('contextmenu',e=>{e.preventDefault();if(this.tool!=='pose'||!this.visible.pose||this.drag)return;const p=this.point(e),hit=this.jointHit(p,true);if(hit){this.checkpoint();const person=this.state.poses[hit.i];person.hidden||=[];if(person.hidden.includes(hit.j))person.hidden=person.hidden.filter(j=>j!==hit.j);else person.hidden.push(hit.j);this.selection=this.selection.filter(r=>r.i!==hit.i||r.j!==hit.j);this.changed();}});
  document.addEventListener('keydown',e=>{
   if($('editorView').hidden||e.target.closest('dialog')||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;
   if(e.code==='Space'||e.code==='KeyF'){this.space=true;e.preventDefault();return;}
   if(e.key==='Escape'){if(this.drag)this.cancelDrag();else{this.selectedJoint=-1;this.selectedPose=-1;this.selection=[];this.sync();this.draw();}return;}
   if(this.drag)return;
   const ctrl=e.ctrlKey||e.metaKey,key=e.key.toLowerCase();
   if(ctrl&&key==='z'){e.preventDefault();e.shiftKey?this.redo():this.undo();return;}
   if(ctrl&&key==='y'){e.preventDefault();this.redo();return;}
   if(this.tool==='pose'&&this.selectedPose>=0){
    if(ctrl&&key==='d'){e.preventDefault();this.poseAction('duplicate');return;}
    if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();this.poseAction('delete');return;}
    const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
    if(delta){e.preventDefault();const refs=this.activeRefs();if(!refs.length)return;this.checkpoint();const n=e.shiftKey?10:1;refs.forEach(r=>{const p=this.state.poses[r.i].points[r.j];p[0]+=delta[0]*n;p[1]+=delta[1]*n;});this.changed();return;}
   }
   if(!ctrl){const tool={p:'pen',e:'eraser',m:'mask',v:'pose',h:'pan'}[key];if(tool)this.setTool(tool);}
  });
  document.addEventListener('keyup',e=>{if(e.code==='Space'||e.code==='KeyF')this.space=false;});window.addEventListener('blur',()=>{this.space=false;if(this.drag)this.cancelDrag();});
  new ResizeObserver(()=>{if(!$('editorView').hidden&&this.image)this.draw();}).observe($('canvasViewport'));
 }
 async open(asset,state){
  this.asset=asset;this.image=new Image();this.image.src='/api/assets/'+asset.id;await this.image.decode();
  this.state=state?clone(state):{width:this.image.width,height:this.image.height,x:0,y:0,strokes:[],poses:[]};this.state.poses ||= [];this.state.strokes ||= [];this.state.poses.forEach(p=>p.hidden||=[]);
  this.drag=null;this.hover=null;this.selectedJoint=-1;this.selection=[];this.undoStack=[];this.redoStack=[];this.selectedPose=this.state.poses.length?0:-1;this.sync();requestAnimationFrame(()=>this.fit());
 }
 snapshot(){return clone(this.state);}
 checkpoint(){this.undoStack.push(this.snapshot());if(this.undoStack.length>70)this.undoStack.shift();this.redoStack=[];}
 changed(){this.sync();this.draw();this.onChange(this.snapshot());}
 undo(){if(!this.undoStack.length)return;this.redoStack.push(this.snapshot());this.state=this.undoStack.pop();this.selection=[];this.hover=null;this.selectedPose=Math.min(this.selectedPose,this.state.poses.length-1);this.changed();}
 redo(){if(!this.redoStack.length)return;this.undoStack.push(this.snapshot());this.state=this.redoStack.pop();this.selection=[];this.hover=null;this.selectedPose=Math.min(Math.max(this.selectedPose,0),this.state.poses.length-1);this.selectedJoint=-1;this.changed();}
 sync(){
  if(!this.state)return;
  if(this.selectedPose>=this.state.poses.length)this.selectedPose=this.state.poses.length-1;
  this.selection=this.selection.filter(r=>this.state.poses[r.i]&&!this.state.poses[r.i].hidden?.includes(r.j));$('poseSelection').textContent=this.selection.length?`${this.selection.length} 関節を選択中`:this.selectedPose>=0?`人形 ${this.selectedPose+1}`:'空白からドラッグして範囲選択';
  $('canvasWidth').value=this.state.width;$('canvasHeight').value=this.state.height;$('canvasDimensions').textContent=`${this.state.width} × ${this.state.height} px`;
  $('undo').disabled=!this.undoStack.length;$('redo').disabled=!this.redoStack.length;
  $('poseSelect').replaceChildren(...(this.state.poses.length?this.state.poses.map((p,i)=>new Option(`人形 ${i+1}`,i)): [new Option('人形なし',-1)]));$('poseSelect').value=this.selectedPose;
  for(const id of ['duplicatePose','flipPose','smallerPose','largerPose','rotatePose','removePose','tiltPose','flipVerticalPose','deletePerson'])$(id).disabled=this.selectedPose<0;
 }
 setTool(tool){this.tool=tool;document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('selected',b.dataset.tool===tool));this.canvas.style.cursor=tool==='pan'?'grab':tool==='pose'?'pointer':'crosshair';$('toolHelp').textContent={pen:'画像に描き込みます。元画像は変更しません。',eraser:'選択したレイヤーだけを消します。',mask:'色を塗った範囲を変更します。空のマスクは生成に使いません。',pose:'空白ドラッグで範囲選択。Shiftで追加選択。選択枠で拡縮・回転。右クリックで関節を非表示／復帰。Space / Fで画面移動。',pan:'ドラッグで表示位置を移動。ホイールで拡大縮小。'}[tool];document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('selected',b.dataset.mode===({pen:'draw',eraser:'draw',mask:'mask',pose:'pose'}[tool])));this.draw();}
 fit(){if(!this.state)return;const r=$('canvasViewport').getBoundingClientRect();this.zoom=Math.min((r.width-36)/this.state.width,(r.height-36)/this.state.height);this.pan={x:(r.width-this.state.width*this.zoom)/2,y:(r.height-this.state.height*this.zoom)/2};this.draw();}
 scale(f,x,y){const r=this.canvas.getBoundingClientRect();x??=r.width/2;y??=r.height/2;const before={x:(x-this.pan.x)/this.zoom,y:(y-this.pan.y)/this.zoom};this.zoom=Math.max(.05,Math.min(8,this.zoom*f));this.pan={x:x-before.x*this.zoom,y:y-before.y*this.zoom};this.draw();}
 point(e){const r=this.canvas.getBoundingClientRect();return {x:(e.clientX-r.left-this.pan.x)/this.zoom,y:(e.clientY-r.top-this.pan.y)/this.zoom};}
 down(e){
  if(!this.state||this.drag)return;if(e.button===2)return;e.preventDefault();this.canvas.focus();this.canvas.setPointerCapture(e.pointerId);const p=this.point(e);
  if(this.space||this.tool==='pan'||e.button===1){this.drag={type:'pan',x:e.clientX,y:e.clientY,pan:{...this.pan}};return;}
  if(this.tool==='pose'){
   if(!this.visible.pose){this.notify('ポーズレイヤーを表示してから編集してください。');return;}
   const hit=this.pick(p);
   if(!hit){this.drag={type:'marquee',start:p,end:p,prior:e.shiftKey?[...this.selection]:[]};if(!e.shiftKey)this.selection=[];this.draw();return;}
   if(hit.handle==='joint'){
    const exists=this.selection.some(r=>r.i===hit.i&&r.j===hit.j);
    if(e.shiftKey){this.selection=exists?this.selection.filter(r=>r.i!==hit.i||r.j!==hit.j):[...this.selection,{i:hit.i,j:hit.j}];this.selectedPose=hit.i;this.sync();this.draw();return;}
    if(!exists)this.selection=[{i:hit.i,j:hit.j}];
    this.selectedPose=hit.i;this.selectedJoint=hit.j;
   }else if(hit.i!==undefined){this.selectedPose=hit.i;this.selection=this.personRefs(hit.i);}
   const refs=this.activeRefs();if(!refs.length)return;
   this.drag={type:'pose',handle:hit.handle==='joint'?'move':hit.handle,refs,start:p,points:refs.map(r=>[...this.state.poses[r.i].points[r.j]]),before:this.snapshot(),pointerId:e.pointerId};this.sync();this.draw();return;
  }

  if(p.x<0||p.y<0||p.x>this.state.width||p.y>this.state.height)return;
  this.checkpoint();const layer=this.tool==='mask'?'mask':this.tool==='eraser'?$('eraseLayer').value:'sketch';const s={layer,erase:this.tool==='eraser',size:Number($('brushSize').value),color:$('penColor').value,points:[[p.x,p.y]]};this.state.strokes.push(s);this.drag={type:'stroke',stroke:s};this.draw();
 }
 move(e){
  const p=this.point(e);
  if(!this.drag){if(this.tool==='pose'&&this.visible.pose){this.hover=this.pick(p);const h=this.hover?.handle;this.canvas.style.cursor=this.space?'grab':h==='joint'?'crosshair':h==='move'?'move':h==='rotate'?'grab':h?({n:'ns-resize',s:'ns-resize',e:'ew-resize',w:'ew-resize',nw:'nwse-resize',se:'nwse-resize',ne:'nesw-resize',sw:'nesw-resize'}[h]):'default';this.draw();}return;}
  const d=this.drag;
  if(d.type==='pan')this.pan={x:d.pan.x+e.clientX-d.x,y:d.pan.y+e.clientY-d.y};
  else if(d.type==='stroke')d.stroke.points.push([Math.max(0,Math.min(this.state.width,p.x)),Math.max(0,Math.min(this.state.height,p.y))]);
  else if(d.type==='marquee'){d.end=p;}
  else if(d.type==='pose'){
   const points=transform(d.points,d.handle,d.start,p,e.shiftKey);
   d.refs.forEach((r,k)=>this.state.poses[r.i].points[r.j]=points[k]);
  }

  this.draw();
 }
 up(e){if(!this.drag)return;const d=this.drag;this.drag=null;if(this.canvas.hasPointerCapture(e.pointerId))this.canvas.releasePointerCapture(e.pointerId);
  if(d.type==='marquee'){const {start:a,end:b}=d,refs=[...d.prior];this.state.poses.forEach((p,i)=>p.points.forEach(([x,y],j)=>{if(!p.hidden?.includes(j)&&x>=Math.min(a.x,b.x)&&x<=Math.max(a.x,b.x)&&y>=Math.min(a.y,b.y)&&y<=Math.max(a.y,b.y)&&!refs.some(r=>r.i===i&&r.j===j))refs.push({i,j});}));this.selection=refs;this.selectedPose=refs[0]?.i??-1;this.sync();this.draw();return;}
  if(d.type==='pose'){if(JSON.stringify(d.before)!==JSON.stringify(this.state)){this.undoStack.push(d.before);if(this.undoStack.length>70)this.undoStack.shift();this.redoStack=[];this.changed();}}else if(d.type!=='pan')this.changed();}
 personRefs(i){const p=this.state?.poses[i];return p?p.points.map((_,j)=>({i,j})).filter(r=>!p.hidden?.includes(r.j)):[];}
 activeRefs(){return this.selection.length?this.selection:this.poseMode==='whole'?this.personRefs(this.selectedPose):[];}
 jointHit(p,hidden=false){let hit=null,best=10/this.zoom;this.state.poses.forEach((person,i)=>person.points.forEach(([x,y],j)=>{if(!hidden&&person.hidden?.includes(j))return;const d=Math.hypot(x-p.x,y-p.y);if(d<best){best=d;hit={i,j,handle:'joint'};}}));return hit;}
 pick(p){
  const refs=this.activeRefs(),pts=refs.map(r=>this.state.poses[r.i].points[r.j]);
  if(pts.length>1){for(const [handle,pt]of Object.entries(handles(pts,this.zoom)))if(Math.hypot(p.x-pt[0],p.y-pt[1])*this.zoom<=9)return {handle};}
  const joint=this.jointHit(p);if(joint)return this.poseMode==='whole'?{i:joint.i,handle:'move'}:joint;
  if(pts.length>1){const b=bounds(pts);if(p.x>=b.left&&p.x<=b.right&&p.y>=b.top&&p.y<=b.bottom)return {handle:'move'};}
  for(let i=this.state.poses.length-1;i>=0;i--){const person=this.state.poses[i];if(EDGES.some(([a,b])=>!person.hidden?.includes(a)&&!person.hidden?.includes(b)&&segmentDistance(p,person.points[a],person.points[b])*this.zoom<=6))return {i,handle:'move'};}return null;
 }
 cancelDrag(e){const d=this.drag;if(!d)return;this.drag=null;if(d.type==='marquee'){this.selection=d.prior;this.sync();}if(d.before){this.state=d.before;this.changed();}else if(d.type==='stroke')this.undo();const id=e?.pointerId??d.pointerId;if(id!==undefined&&this.canvas.hasPointerCapture(id))this.canvas.releasePointerCapture(id);this.draw();}
 addPose(){if(!this.state)return;this.checkpoint();const w=this.state.width,h=this.state.height,scale=Math.min(w,h)*.8;this.state.poses.push({id:crypto.randomUUID(),points:STANDING.map(([x,y])=>[w/2+(x-.5)*scale,h/2+(y-.5)*scale])});this.selectedPose=this.state.poses.length-1;this.selectedJoint=-1;this.selection=this.personRefs(this.selectedPose);this.setTool('pose');this.changed();}
 poseAction(action){
  if(this.selectedPose<0)return;const refs=this.activeRefs();
  if(!refs.length&&!['deletePerson','duplicate'].includes(action)){this.notify('関節をクリック、または範囲選択してください。');return;}
  this.checkpoint();
  if(action==='deletePerson'){this.state.poses.splice(this.selectedPose,1);this.selectedPose=Math.min(this.selectedPose,this.state.poses.length-1);this.selection=[];}
  else if(action==='delete'){refs.forEach(r=>{const p=this.state.poses[r.i];p.hidden=[...new Set([...(p.hidden||[]),r.j])];});this.selection=[];}
  else if(action==='duplicate'){const p=clone(this.state.poses[this.selectedPose]);p.id=crypto.randomUUID();p.points=p.points.map(([x,y])=>[x+25,y+15]);this.state.poses.push(p);this.selectedPose=this.state.poses.length-1;this.selection=this.personRefs(this.selectedPose);}
  else {const b=bounds(refs.map(r=>this.state.poses[r.i].points[r.j])),cx=(b.left+b.right)/2,cy=(b.top+b.bottom)/2,angle=action==='rotate'?Math.PI/12:0,f=action==='small'?.9:action==='large'?1.1:1;
   refs.forEach(r=>{const [x,y]=this.state.poses[r.i].points[r.j];let dx=(x-cx)*f,dy=(y-cy)*f;if(action==='flip')dx=-dx;if(action==='flipVertical')dy=-dy;if(action==='tilt')dx+=.15*dy;this.state.poses[r.i].points[r.j]=[cx+dx*Math.cos(angle)-dy*Math.sin(angle),cy+dx*Math.sin(angle)+dy*Math.cos(angle)];});}
  this.changed();
 }
 proposeSize(){const a=$('canvasAspect').value;if(a==='custom')return;if(a==='original'){$('canvasWidth').value=this.image.width;$('canvasHeight').value=this.image.height;return;}const [w,h]=a.split(':').map(Number),factor=Math.ceil(Math.max(this.image.width/w,this.image.height/h)/32);$('canvasWidth').value=w*factor*32;$('canvasHeight').value=h*factor*32;}
 expand(){
  const w=Number($('canvasWidth').value),h=Number($('canvasHeight').value);if(!Number.isInteger(w)||!Number.isInteger(h)||w<this.image.width||h<this.image.height||w>4096||h>4096||w*h>8388608){this.notify('元画像以上、各辺4096px以下・約800万画素以内で指定してください。');return;}
  const align=$('canvasAlign').value;let x=Math.floor((w-this.image.width)/2),y=Math.floor((h-this.image.height)/2);if(align==='left')x=0;if(align==='right')x=w-this.image.width;if(align==='top')y=0;if(align==='bottom')y=h-this.image.height;
  const dx=x-this.state.x,dy=y-this.state.y;this.checkpoint();this.state.strokes.forEach(s=>s.points=s.points.map(([x,y])=>[x+dx,y+dy]));this.state.poses.forEach(p=>p.points=p.points.map(([x,y])=>[x+dx,y+dy]));Object.assign(this.state,{width:w,height:h,x,y});this.changed();this.fit();
 }
 layerCanvas(layer){const out=document.createElement('canvas');out.width=this.state.width;out.height=this.state.height;const c=out.getContext('2d');for(const s of this.state.strokes.filter(s=>s.layer===layer)){c.globalCompositeOperation=s.erase?'destination-out':'source-over';c.strokeStyle=layer==='mask'?'#f18087':s.color;c.fillStyle=c.strokeStyle;c.lineWidth=s.size;c.lineCap='round';c.lineJoin='round';c.beginPath();s.points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();if(s.points.length===1){c.beginPath();c.arc(...s.points[0],s.size/2,0,Math.PI*2);c.fill();}}return out;}
 draw(){
  if(!this.state||!this.image)return;const r=$('canvasViewport').getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  if(this.canvas.width!==Math.round(r.width*dpr)||this.canvas.height!==Math.round(r.height*dpr)){this.canvas.width=Math.round(r.width*dpr);this.canvas.height=Math.round(r.height*dpr);}
  const c=this.ctx;c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,r.width,r.height);c.translate(this.pan.x,this.pan.y);c.scale(this.zoom,this.zoom);
  const {width:w,height:h,x,y}=this.state;c.fillStyle='#303943';c.fillRect(0,0,w,h);c.fillStyle='#3a444f';const tile=20;for(let a=0;a<w;a+=tile)for(let b=0;b<h;b+=tile)if((Math.floor(a/tile)+Math.floor(b/tile))%2)c.fillRect(a,b,Math.min(tile,w-a),Math.min(tile,h-b));
  c.save();c.beginPath();c.rect(0,0,w,h);c.clip();c.globalAlpha=Number($('baseOpacity').value)/100;c.drawImage(this.image,x,y);c.globalAlpha=1;
  if(this.visible.sketch)c.drawImage(this.layerCanvas('sketch'),0,0);
  if(this.visible.mask){c.globalAlpha=.42;c.drawImage(this.layerCanvas('mask'),0,0);c.globalAlpha=1;}
  if(this.visible.pose)this.state.poses.forEach((p,index)=>{c.lineWidth=Math.max(2.5/this.zoom,Math.min(w,h)/160);EDGES.forEach(([a,b],i)=>{if(p.hidden?.includes(a)||p.hidden?.includes(b))return;c.strokeStyle=COLORS[i];c.beginPath();c.moveTo(...p.points[a]);c.lineTo(...p.points[b]);c.stroke();});p.points.forEach(([x,y],i)=>{if(p.hidden?.includes(i)){c.beginPath();c.strokeStyle='#97a6b088';c.lineWidth=1/this.zoom;c.arc(x,y,4/this.zoom,0,Math.PI*2);c.stroke();return;}const active=this.selection.some(r=>r.i===index&&r.j===i),hover=this.hover?.i===index&&this.hover?.j===i;c.beginPath();c.fillStyle=COLORS[i];c.arc(x,y,(hover||active?7:5)/this.zoom,0,Math.PI*2);c.fill();c.strokeStyle=index===this.selectedPose?'white':'#171b22';c.lineWidth=(hover||active?2:1)/this.zoom;c.stroke();});});c.restore();
  if(this.tool==='pose'&&this.visible.pose&&this.selectedPose>=0){
   const points=this.activeRefs().map(r=>this.state.poses[r.i].points[r.j]);if(points.length>1){
    const b=bounds(points);c.strokeStyle='#6ff7de';c.lineWidth=1/this.zoom;c.setLineDash([5/this.zoom,4/this.zoom]);c.strokeRect(b.left,b.top,b.right-b.left,b.bottom-b.top);c.setLineDash([]);
    if(points.length>1){
     const hs=handles(points,this.zoom);c.beginPath();c.moveTo(...hs.n);c.lineTo(...hs.rotate);c.stroke();
     for(const [key,[hx,hy]]of Object.entries(hs)){c.fillStyle=this.hover?.handle===key?'#6ff7de':'#162129';c.beginPath();if(key==='rotate')c.arc(hx,hy,6/this.zoom,0,Math.PI*2);else c.rect(hx-4/this.zoom,hy-4/this.zoom,8/this.zoom,8/this.zoom);c.fill();c.stroke();}
    }
   }
  }
  if(this.tool==='pose'&&this.hover?.j!==undefined&&this.visible.pose){const pt=this.state.poses[this.hover.i]?.points[this.hover.j];if(pt){c.font=`${12/this.zoom}px sans-serif`;const text=JOINT_NAMES[this.hover.j],tw=c.measureText(text).width;c.fillStyle='#101820e8';c.fillRect(pt[0]+12/this.zoom,pt[1]-25/this.zoom,tw+12/this.zoom,22/this.zoom);c.fillStyle='white';c.fillText(text,pt[0]+18/this.zoom,pt[1]-9/this.zoom);}}
  if(this.drag?.type==='marquee'){const a=this.drag.start,b=this.drag.end;c.fillStyle='#51d9c622';c.strokeStyle='#51d9c6';c.lineWidth=1/this.zoom;c.fillRect(a.x,a.y,b.x-a.x,b.y-a.y);c.strokeRect(a.x,a.y,b.x-a.x,b.y-a.y);}
  c.strokeStyle='#7c929f';c.lineWidth=1/this.zoom;c.strokeRect(0,0,w,h);$('zoomLabel').textContent=Math.round(this.zoom*100)+'%';
 }
}
