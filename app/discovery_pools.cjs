// Pool identity only, verified against the official PumpSwap account prefix.
// Prices/reserves continue to come exclusively from observed swap events.
const bs58=require('bs58');
const {canonicalPool}=require('./discovery_address.cjs');
const AMM='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA';
const SOL='So11111111111111111111111111111111111111112';
const DISC=Buffer.from([241,154,109,4,17,177,109,188]);
function poolIdentity(pool,account){
 if(!account||account.owner!==AMM||account.executable||!Array.isArray(account.data)||account.data[1]!=='base64')return null;
 const b=Buffer.from(account.data[0],'base64');if(b.length<243||!b.subarray(0,8).equals(DISC))return null;
 const base_mint=bs58.encode(b.subarray(43,75)),quote_mint=bs58.encode(b.subarray(75,107));
 if(base_mint===SOL||quote_mint!==SOL)return null;
 const canonical_migration=canonicalPool(pool,base_mint,quote_mint,b.subarray(11,43),b.readUInt16LE(9));
 return {kind:'pool',pool,base_mint,quote_mint,canonical_migration,source:'Verified PumpSwap pool account; discovery is not a creation timestamp'};
}
class PoolResolver{
 constructor(rpc,session,deliver){this.rpc=rpc;this.session=session;this.deliver=deliver;this.pending=new Map();this.retry=new Map();this.busy=false;this.status='Pool identity lookup waiting';}
 add(event){
  const pool=event.pool;if(this.session.admissionPaused||!pool||this.retry.get(pool)>Date.now())return;
  let item=this.pending.get(pool);if(!item||item.generation!==this.session.generation)item={generation:this.session.generation,events:[],seen:0};
  item.seen++;item.events.push(event);item.events=item.events.slice(-8);this.pending.set(pool,item);
  while(this.pending.size>100){const victim=[...this.pending].sort((a,b)=>a[1].seen-b[1].seen || a[1].events.at(-1).received-b[1].events.at(-1).received)[0][0];this.pending.delete(victim);}
 }
 async tick(){
  if(this.busy||!this.pending.size)return;this.busy=true;
  const batch=[...this.pending.entries()].filter(([pool])=>!(this.retry.get(pool)>Date.now())).sort((a,b)=>b[1].seen-a[1].seen || b[1].events.at(-1).received-a[1].events.at(-1).received).slice(0,20);if(!batch.length){this.busy=false;return;}for(const [pool] of batch)this.pending.delete(pool);
  try{
   const accounts=await this.rpc('getMultipleAccounts',[batch.map(([pool])=>pool),{encoding:'base64',commitment:'confirmed'}]);
   if(accounts.value?.length!==batch.length)throw Error('Incomplete pool identity response');
   let mapped=0;
   for(let i=0;i<batch.length;i++){
    const [pool,item]=batch[i];if(item.generation!==this.session.generation)continue;
    const identity=poolIdentity(pool,accounts.value[i]);this.retry.set(pool,Date.now()+(identity?5000:60000));
    if(!identity)continue;const first=item.events[0];if(this.session.discarded.has(identity.base_mint))continue;
    if(this.deliver({...first,...identity})===false){this.retry.set(pool,Date.now()+60000);continue;}mapped++;
    for(const event of item.events)this.deliver(event);
   }
   this.status=`Pool identities: ${mapped} mapped in latest batch; ${this.pending.size} pending`;
  }catch{
   this.status='Pool identity RPC unavailable / rate limited; retrying with backoff';
   for(const [pool,item] of batch){this.retry.set(pool,Date.now()+15000);if(item.generation===this.session.generation&&!this.pending.has(pool))this.pending.set(pool,item);}
  }finally{
   while(this.pending.size>100)this.pending.delete(this.pending.keys().next().value);
   while(this.retry.size>500)this.retry.delete(this.retry.keys().next().value);
   this.busy=false;
  }
 }
}
module.exports={poolIdentity,PoolResolver};
