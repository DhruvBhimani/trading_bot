// A short observation window, not an ever-growing launch catalogue.
class CandidateWindow{
 constructor(clock=()=>Date.now()/1000){this.clock=clock;this.items=new Map();this.cooldowns=new Map();this.counters={creations_skipped:0,curve_trades_seen:0,pool_trades_seen:0,migrations_seen:0,rotated:0,rejected:0};}
 reject(mint,seconds=60){this.items.delete(mint);this.cooldowns.delete(mint);this.cooldowns.set(mint,this.clock()+seconds);while(this.cooldowns.size>256)this.cooldowns.delete(this.cooldowns.keys().next().value);this.counters.rejected++;}
 admit(mint,stage,protectedMints,priority=false){
  const now=this.clock();if(this.cooldowns.get(mint)>now&&!priority&&!protectedMints.has(mint))return false;
  const previous=this.items.get(mint);if(previous){if(previous.stage!=='migrated')previous.stage=stage;return true;}
  const group=stage==='near_migration'?'curve':'pool';const limit=group==='curve'?16:64;
  const members=[...this.items].filter(([m,v])=>(v.stage==='near_migration'?'curve':'pool')===group&&!protectedMints.has(m));
  if(members.length>=limit){
   const victim=members.find(([,v])=>now-v.since>=60)|| (priority?members[0]:null);
   if(!victim)return false;
   this.reject(victim[0]);this.counters.rotated++;
  }
  this.items.set(mint,{stage,since:now});return true;
 }
 expire(protectedMints){const now=this.clock();for(const [m,v] of this.items)if(!protectedMints.has(m)&&now-v.since>=120){this.reject(m);this.counters.rotated++;}for(const [m,t] of this.cooldowns)if(t<=now)this.cooldowns.delete(m);}
}
module.exports={CandidateWindow};
