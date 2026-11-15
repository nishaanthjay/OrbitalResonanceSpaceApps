// DOM-level integration with real shipped datasets. This is not visual/browser verification.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('node:vm');
const web=path.resolve(__dirname,'..'),E=require('../evidence-core.js');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.style={};this.value='';this.open=false;this.disabled=false;this._text='';}
  set textContent(s){this._text=String(s);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent||'').join(' ');}
  append(...children){this.children.push(...children);}replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(k,v){this.attributes[k]=String(v);}getAttribute(k){return this.attributes[k]??null;}
  addEventListener(){}focus(){}show(){this.open=true;}close(){this.open=false;}scrollIntoView(){}
  getContext(){return {fillRect(){},drawImage(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){}};}
}
test('environment UI presents unavailable data honestly, opens a real patch and uses dated image files',async()=>{
  const elements=new Map(),listeners=new Map(),id=s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s);};
  const document={getElementById:id,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),activeElement:new Element('button'),addEventListener:(type,fn)=>{const a=listeners.get(type)||[];a.push(fn);listeners.set(type,a);},dispatchEvent:event=>{for(const fn of listeners.get(event.type)||[])fn(event);}};
  const big=JSON.parse(fs.readFileSync(path.join(web,'data/explore/big/big.json'))),lost=JSON.parse(fs.readFileSync(path.join(web,'data/explore/big/lost.geojson'))),imagePaths=[];
  class Image {set src(src){imagePaths.push(src);assert.ok(fs.existsSync(path.join(web,src)));this.naturalWidth=603;this.naturalHeight=607;queueMicrotask(()=>this.onload());}}
  const context=vm.createContext({EvidenceCore:E,document,window:{},Image,Option:function(text,value){this.textContent=text;this.value=value;},fetch:async p=>{const file=path.join(web,p);return {ok:fs.existsSync(file),json:async()=>JSON.parse(fs.readFileSync(file))};},state:{bigMeta:big},openLost:async item=>{const feature=lost.features.find(f=>f.properties.id===item);document.dispatchEvent({type:'evidence:selection',detail:{feature,kind:'lost',point:[feature.properties.centroid_lon,feature.properties.centroid_lat],dates:big.dates}});},addEventListener(){},queueMicrotask,setTimeout,clearTimeout,Promise,console});
  vm.runInContext(fs.readFileSync(path.join(web,'environment.js'),'utf8'),context);
  await new Promise(resolve=>setTimeout(resolve,40));
  assert.equal(id('env-imerg-state').textContent,'Not available');assert.equal(id('env-smap-state').textContent,'Not available');assert.equal(id('env-fire-toggle').disabled,true);assert.equal(id('env-imerg-chart').children.length,0);assert.equal(id('env-smap-chart').children.length,0);assert.equal(id('env-date').children.length,9);assert.equal(id('invest-example').disabled,false);
  await id('invest-example').onclick();await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(id('investigation').open,true);assert.match(id('invest-title').textContent,/2236/);assert.match(id('invest-category').textContent,/agreement/);assert.match(id('invest-radar').textContent,/37 ha/);assert.equal(id('invest-optical').children.length,2);assert.equal(imagePaths.length,2);assert.match(id('invest-environment').textContent,/Rainfall: not available/);assert.match(id('invest-optical-note').textContent,/unassessed/);assert.equal(id('env-date').value,'2026-08-13');id('invest-close').onclick();assert.equal(id('investigation').open,false);
});
