import assert from 'node:assert/strict';
import {bounds,handles,transform,hitPose} from '../public/pose-geometry.mjs';
const points=Array.from({length:18},(_,i)=>[20+(i%3)*50,30+Math.floor(i/3)*40]);
const original=structuredClone(points),b=bounds(points);
const moved=transform(points,'move',{x:0,y:0},{x:25,y:-10});
assert.deepEqual(moved[4],[points[4][0]+25,points[4][1]-10]);
const scaled=transform(points,'se',{x:b.right,y:b.bottom},{x:b.right+100,y:b.bottom+200});
assert.deepEqual(bounds(scaled),{left:20,right:220,top:30,bottom:430});
const rotated=transform(points,'rotate',{x:120,y:130},{x:70,y:180});
for(let i=0;i<18;i++)assert.ok(Math.abs(Math.hypot(rotated[i][0]-70,rotated[i][1]-130)-Math.hypot(points[i][0]-70,points[i][1]-130))<1e-8);
assert.deepEqual(points,original);
for(const zoom of [.2,1,4]){
 const hit=hitPose([{points}],{x:20+6/zoom,y:30},zoom,0,'joint');assert.equal(hit.i,0);
 const h=handles(points,zoom).rotate;assert.equal(hitPose([{points}],{x:h[0],y:h[1]},zoom,0,'whole').handle,'rotate');
}
assert.equal(hitPose([{points}],{x:-1000,y:-1000},1,0,'joint'),null);
assert.ok(transform(Array.from({length:18},()=>[2,2]),'se',{x:2,y:2},{x:4,y:4}).flat().every(Number.isFinite));
console.log('PASS: translation, aspect-preserving scale, rotation distances, immutable input, zoom-independent picking, handles, degenerate bounds');

