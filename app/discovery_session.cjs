// Small, bounded tracking state shared by the worker and offline regression tests.
const SOL='So11111111111111111111111111111111111111112';
const {CandidateWindow}=require('./discovery_candidates.cjs');
class DiscoverySession {
 constructor({focused=false,clock}={}){this.tracked=new Set();this.pins=new Set();this.protected=new Set();this.pools=new Map();this.generation=0;this.discarded=new Set();this.admissionPaused=false;this.protectedPools=new Set();this.focused=focused;this.window=new CandidateWindow(clock);}
 maintain(){if(!this.focused)return;const keep=new Set([...this.pins,...this.protected]);this.window.expire(keep);for(const m of this.tracked)if(!keep.has(m)&&!this.window.items.has(m))this.tracked.delete(m);for(const [p,v] of this.pools)if(!this.tracked.has(v.base_mint))this.pools.delete(p);}
 track(mint){this.tracked.delete(mint);this.tracked.add(mint);const poolMints=new Set([...this.pools.values()].map(p=>p.base_mint));while(this.tracked.size>210+this.protected.size){const available=[...this.tracked].filter(m=>!this.pins.has(m)&&!this.protected.has(m));const key=available.find(m=>poolMints.size>100?poolMints.has(m):!poolMints.has(m))||available[0];if(!key)break;this.tracked.delete(key);poolMints.delete(key);}for(const [pool,e] of this.pools)if(!this.tracked.has(e.base_mint))this.pools.delete(pool);}
 trimPools(){while(this.pools.size>420){const key=[...this.pools.keys()].find(k=>!this.pins.has(this.pools.get(k).base_mint)&&!this.protected.has(this.pools.get(k).base_mint));const victim=key===undefined?[...this.pools.keys()].find(k=>!this.protectedPools.has(k)):key;if(victim===undefined)break;this.pools.delete(victim);}}
 command(c){
  if(c.type==='memory-pressure')this.maintain(); // Old clients must not stop admission.
  if(c.type==='reject'){for(const m of c.mints.slice(0,80))if(!this.pins.has(m)&&!this.protected.has(m))this.window.reject(m);this.maintain();}
  if(c.type==='discard'){for(const mint of c.mints){if(this.pins.has(mint)||this.protected.has(mint))continue;this.discarded.add(mint);while(this.discarded.size>1000)this.discarded.delete(this.discarded.values().next().value);this.tracked.delete(mint);for(const [pool,e] of this.pools)if(e.base_mint===mint)this.pools.delete(pool);}}
  if(c.type==='reset'){for(const mint of this.window.items.keys())if(!c.mints.includes(mint)&&!this.protected.has(mint))this.window.reject(mint);this.generation=c.generation;this.pins=new Set(c.mints.slice(0,10));this.tracked=new Set([...this.pins,...this.protected]);for(const [pool,e] of this.pools)if(!this.pins.has(e.base_mint)&&!this.protected.has(e.base_mint))this.pools.delete(pool);}
  if(c.type==='pins'){this.pins=new Set(c.mints.slice(0,10));for(const m of this.pins)this.track(m);}
  if(c.type==='protected'){this.protected=new Set(c.mints.slice(0,8));this.protectedPools=new Set((c.pools||[]).slice(0,8).map(p=>p.pool));for(const m of this.protected){this.discarded.delete(m);this.track(m);}if(Array.isArray(c.pools))for(const p of c.pools)this.pools.set(p.pool,p);this.trimPools();}
  if(c.type==='track')for(const m of c.mints.slice(-210))this.track(m);
 }
 event(e){
  if(this.focused){
   const keep=new Set([...this.pins,...this.protected]),mint=e.mint||e.base_mint;
   if(e.kind==='token'&&!keep.has(mint)){this.window.counters.creations_skipped++;return null;}
   if(e.kind==='migration'){this.window.counters.migrations_seen++;if(!this.window.admit(mint,'migrated',keep,true))return null;}
   if(e.kind==='pool'&&!this.window.admit(mint,e.canonical_migration?'migrated':'active_pool',keep))return null;
   if(e.kind==='trade'){
    this.window.counters.curve_trades_seen++;
    const real=Number(e.real_token_reserves),virtual=Number(e.virtual_token_reserves);
    const near=!e.mayhem_mode&&[SOL,'11111111111111111111111111111111'].includes(e.quote_mint)&&real>0&&virtual>0&&real/virtual<=.1;
    if(!keep.has(mint)&&!near)return null;
    if(near&&!this.window.admit(mint,'near_migration',keep))return null;
    this.track(mint);e={...e,stage:'near_migration',remaining_reserve_ratio:real/virtual};
   }
   this.maintain();
  }
  if(this.discarded.has(e.mint||e.base_mint))return null;
  if(e.kind==='token')this.track(e.mint);
  if(e.kind==='migration'){this.track(e.mint);if(!this.pools.has(e.pool))this.pools.set(e.pool,{pool:e.pool,base_mint:e.mint,quote_mint:e.quote_mint});this.trimPools();}
  if(e.kind==='pool'){
   // A SOL base / non-SOL quote is not a token/SOL price feed.
   if(e.base_mint===SOL)return null;
   this.track(e.base_mint);this.pools.set(e.pool,e);
   this.trimPools();
  }
  if(e.kind==='pool_trade'){
   const pool=this.pools.get(e.pool);if(!pool||pool.quote_mint!==SOL||!this.tracked.has(pool.base_mint))return null;
   const buy=e.event_name==='BuyEvent';
   e={...e,kind:'trade',mint:pool.base_mint,quote_mint:SOL,is_buy:buy,sol_amount:buy?e.quote_amount_in:e.quote_amount_out,token_amount:buy?e.base_amount_out:e.base_amount_in,real_sol_reserves:e.pool_quote_token_reserves,real_token_reserves:e.pool_base_token_reserves,fee:e.protocol_fee,creator_fee:e.coin_creator_fee};
  }
  if(e.kind==='trade'&&!this.tracked.has(e.mint))return null;
  return {...e,generation:this.generation};
 }
}
module.exports={DiscoverySession};
