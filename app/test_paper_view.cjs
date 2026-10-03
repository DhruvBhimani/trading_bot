// Run the actual row updater with a small DOM harness; no live dashboard needed.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/app.js','utf8');
const document={activeElement:null,createElement:()=>new Row()};
class Row{
 constructor(){this.dataset={};this.writes=0;}
 set innerHTML(html){this.writes++;this.html=html;const summary={focus:()=>{document.activeElement=summary;}};this.details={open:false,querySelector:()=>summary};this.summary=summary;}
 querySelector(selector){return selector==='details'?this.details:this.summary;}
 remove(){const index=this.parent.children.indexOf(this);this.parent.children.splice(index,1);}
}
const table={children:[],insertBefore(row,before){if(row.parent)row.remove();const index=before?this.children.indexOf(before):this.children.length;this.children.splice(index,0,row);row.parent=this;}};
const context={document};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function updatePaperRows'),source.indexOf('function renderLivePaper')),context);
const render=items=>context.updatePaperRows(table,items);
render([{id:1,html:'old trade'}]);const row=table.children[0];row.details.open=true;document.activeElement=row.summary;
for(let i=0;i<100;i++)render([{id:1,html:'old trade'}]);
assert.equal(row.writes,1);assert.equal(row.details.open,true);assert.equal(document.activeElement,row.summary);
render([{id:2,html:'new trade'},{id:1,html:'old trade'}]);assert.equal(table.children[1],row);assert.equal(row.details.open,true);
render([{id:2,html:'new trade'},{id:1,html:'resolved coin name'}]);assert.equal(row.details.open,true);assert.equal(document.activeElement,row.summary);
row.details.open=false;render([{id:2,html:'new trade'},{id:1,html:'another metadata change'}]);assert.equal(row.details.open,false);
for(let i=3;i<1000;i++)render([{id:i,html:'replacement'}]);assert.equal(table.children.length,1);
console.log('Paper row polling, arrival, metadata update, user collapse, and bounded retention passed');
// Exercise the complete renderer against IDs from the real page.
const index=fs.readFileSync('frontend/index.html','utf8');
const ids=new Set([...index.matchAll(/id="([^"]+)"/g)].map(m=>m[1]));
const nodes=new Map();
const root=()=>({children:[],insertBefore:table.insertBefore});
context.$=id=>{assert(ids.has(id),'Missing UI element '+id);if(!nodes.has(id))nodes.set(id,root());return nodes.get(id);};
context.h=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
context.sign=n=>n>=0?'positive':'negative';context.when=()=> '12:00';context.livePaperState=null;
vm.runInContext(source.slice(source.indexOf('function paperCoin'),source.indexOf('async function refreshLivePaper')),context);
const pos={mint:'mint',name:'Example',symbol:'EX',entry_fdv_usd:70000,current_fdv_usd:75000,pnl_usd:1.23,pnl_pct:5,stale:false,status:'Open',exit_plan:{target_pct:25,stop_pct:12,trail_pct:10,remaining_seconds:100}};
const trade={id:1,mint:'mint',name:'Example',strategy:'momentum',entry_fdv_usd:70000,exit_fdv_usd:75000,pnl_sol:.01,pnl_usd:1.5,holding_seconds:10,exit_reason:'Take profit',entry_reason:'Momentum',signal_to_entry_seconds:1.2,entry_move_pct:2};
const p={run_id:'run',usd_reference:{rate:150,status:'fresh'},running:true,version:'v',accounts:[{strategy:'momentum',positions:[pos],pending:[],net_pnl_sol:.01,max_drawdown_pct:1,closed:1}],trades:[trade],candidates:[],decisions:[],analysis:[],feed:{},storage:{bytes:100,max_bytes:100000}};
context.renderLivePaper(p);
assert(nodes.get('live-paper-positions').children[0].html.includes('$70K'));
assert(nodes.get('live-paper-positions').children[0].html.includes('$1.23'));
assert(!nodes.get('live-paper-positions').children[0].html.includes('SOL'));
const closed=nodes.get('live-paper-trades').children[0];closed.details.open=true;
context.renderLivePaper(p);assert.equal(closed.details.open,true);
p.usd_reference={rate:150,status:'stale'};pos.pnl_usd=null;pos.current_fdv_usd=null;pos.current_fdv_sol=null;pos.stale=true;
context.renderLivePaper(p);assert(nodes.get('live-paper-positions').children[0].html.includes('Price stale'));
console.log('Complete USD desk rendering and real element IDs passed');
p.learning={models:{minimum_trades:200,minimum_coins:80,progress:[{strategy:'momentum',status:'collecting',trades:12,coins:10}],trial:{id:'abcdef012345',strategy:'momentum'},comparisons:[]}};
p.accounts.push({...p.accounts[0],strategy:'ml_candidate',positions:[]});
context.renderLivePaper(p);
assert(nodes.get('live-paper-accounts').innerHTML.includes('ML candidate'));
assert(nodes.get('live-paper-learning').innerHTML.includes('12 / 200 trades'));
assert(nodes.get('live-paper-learning').innerHTML.includes('separate balances'));
console.log('ML progress and separate comparison accounts render correctly');
pos.exit_plan.remaining_seconds=null;p.config={size_usd:50};
p.writeoffs=[{mint:'old',name:'Retired coin',strategy:'momentum',pnl_sol:-.5,pnl_usd:-50}];
p.postmortem=[{axis:'exit',bucket:'Unresolved paper write-off',losses:1,count:1,pnl_sol:-.5}];
context.renderLivePaper(p);
assert(nodes.get('live-paper-status').textContent.includes('$50 per entry'));
assert(nodes.get('live-paper-positions').children[0].html.includes('No time limit'));
assert(nodes.get('live-paper-positions').children[0].html.includes('Retire as paper loss'));
assert(nodes.get('live-paper-writeoffs').innerHTML.includes('No sale · unresolved'));
assert(nodes.get('live-paper-postmortem').innerHTML.includes('Unresolved paper write-off'));
console.log('USD sizing, disabled timer, unresolved write-offs and loss review render correctly');
