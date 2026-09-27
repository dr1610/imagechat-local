export const EDGES=[[1,2],[1,5],[2,3],[3,4],[5,6],[6,7],[1,8],[8,9],[9,10],[1,11],[11,12],[12,13],[1,0],[0,14],[14,16],[0,15],[15,17]];
export function bounds(points){const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};}
export function handles(points,zoom){const b=bounds(points),x=(b.left+b.right)/2,y=(b.top+b.bottom)/2;return {nw:[b.left,b.top],n:[x,b.top],ne:[b.right,b.top],e:[b.right,y],se:[b.right,b.bottom],s:[x,b.bottom],sw:[b.left,b.bottom],w:[b.left,y],rotate:[x,b.top-30/zoom]};}
export function transform(points,handle,start,end,snap=false){
 const b=bounds(points),cx=(b.left+b.right)/2,cy=(b.top+b.bottom)/2;
 if(handle==='move')return points.map(([x,y])=>[x+end.x-start.x,y+end.y-start.y]);
 if(handle==='rotate'){let a=Math.atan2(end.y-cy,end.x-cx)-Math.atan2(start.y-cy,start.x-cx);if(snap)a=Math.round(a/(Math.PI/12))*Math.PI/12;return points.map(([x,y])=>[cx+(x-cx)*Math.cos(a)-(y-cy)*Math.sin(a),cy+(x-cx)*Math.sin(a)+(y-cy)*Math.cos(a)]);}
 const ax=handle.includes('w')?b.right:handle.includes('e')?b.left:cx,ay=handle.includes('n')?b.bottom:handle.includes('s')?b.top:cy;
 let sx=handle==='n'||handle==='s'?1:Math.max(.05,Math.min(20,Math.abs(start.x-ax)<1e-6?1:(end.x-ax)/(start.x-ax)));
 let sy=handle==='e'||handle==='w'?1:Math.max(.05,Math.min(20,Math.abs(start.y-ay)<1e-6?1:(end.y-ay)/(start.y-ay)));
 if(handle.length===2&&!snap){const v=Math.abs(sx-1)>Math.abs(sy-1)?sx:sy;sx=v;sy=v;}
 return points.map(([x,y])=>[ax+(x-ax)*sx,ay+(y-ay)*sy]);
}
export function segmentDistance(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],n=dx*dx+dy*dy;const t=n?Math.max(0,Math.min(1,((p.x-a[0])*dx+(p.y-a[1])*dy)/n)):0;return Math.hypot(p.x-a[0]-t*dx,p.y-a[1]-t*dy);}
export function hitPose(poses,p,zoom,selected,mode){
 if(mode==='whole'&&selected>=0&&poses[selected])for(const [handle,pt]of Object.entries(handles(poses[selected].points,zoom)))if(Math.hypot(p.x-pt[0],p.y-pt[1])*zoom<=10)return {i:selected,handle};
 let hit=null,best=12/zoom;
 poses.forEach((person,i)=>person.points.forEach(([x,y],j)=>{const d=Math.hypot(p.x-x,p.y-y);if(d<best){best=d;hit={i,j,handle:mode==='whole'?'move':'joint'};}}));
 if(hit)return hit;
 for(let i=poses.length-1;i>=0;i--){if(EDGES.some(([a,b])=>segmentDistance(p,poses[i].points[a],poses[i].points[b])*zoom<=7))return {i,handle:'move'};}
 if(mode==='whole'){
  const order=[selected,...poses.map((_,i)=>i).reverse().filter(i=>i!==selected)];
  for(const i of order){if(!poses[i])continue;const b=bounds(poses[i].points);if(p.x>=b.left&&p.x<=b.right&&p.y>=b.top&&p.y<=b.bottom)return {i,handle:'move'};}
 }
 return null;
}
