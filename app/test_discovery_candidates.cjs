const assert=require('node:assert/strict'),{DiscoverySession}=require('./discovery_session.cjs');
const SOL='So11111111111111111111111111111111111111112';let now=1000;
const s=new DiscoverySession({focused:true,clock:()=>now});
assert.equal(s.event({kind:'token',mint:'early'}),null);
assert.equal(s.event({kind:'trade',mint:'early',quote_mint:SOL,real_token_reserves:'700',virtual_token_reserves:'1000'}),null);
assert(s.event({kind:'trade',mint:'older-near',quote_mint:SOL,real_token_reserves:'80',virtual_token_reserves:'1000'}));
assert.equal(s.window.items.get('older-near').stage,'near_migration');
s.command({type:'protected',mints:['held'],pools:[{pool:'held-pool',base_mint:'held',quote_mint:SOL}]});
let admitted=0;
for(let i=0;i<10000;i++){
 now+=.1;
 if(s.event({kind:'pool',pool:'p'+i,base_mint:'m'+i,quote_mint:SOL}))admitted++;
 s.event({kind:'token',mint:'early'+i});s.maintain();
 assert(s.window.items.size<=80);assert(s.window.cooldowns.size<=256);assert(s.tracked.size<=95);assert(s.pools.size<=95);
 assert(s.tracked.has('held'));assert(s.pools.has('held-pool'));
}
assert(admitted>500);assert(s.window.counters.rotated>400);
s.event({kind:'migration',mint:'migrating',pool:'migration-pool',quote_mint:SOL});assert(s.tracked.has('migrating'));
s.command({type:'reject',mints:['migrating','held']});assert(!s.tracked.has('migrating'));assert(s.tracked.has('held'));
assert.equal(s.event({kind:'pool',pool:'migration-pool',base_mint:'migrating',quote_mint:SOL}),null);
now+=61;assert(s.event({kind:'pool',pool:'migration-pool',base_mint:'migrating',quote_mint:SOL}));
console.log('10,000-candidate rotation: bounded cohorts/cooldowns, early skips, older near-migration discovery, protected positions and reconsideration passed.');
