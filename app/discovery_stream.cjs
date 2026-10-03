// Official Solana WebSocket logs; no third-party token list or synthetic fallback.
const {events,schemas}=require('./discovery_decode.cjs');
const WebSocket=require('ws'),{rpc}=require('./discovery_rpc.cjs');
const endpoint=process.env.SOLANA_WS_URL||(process.env.SOLANA_RPC_URL||'https://api.mainnet-beta.solana.com').replace(/^http/,'ws');
const {DiscoverySession}=require('./discovery_session.cjs'),session=new DiscoverySession({focused:true});
const {PoolResolver}=require('./discovery_pools.cjs');
const programs=[...new Set(schemas.map(s=>s.program))];
let commands='';process.stdin.on('data',chunk=>{commands+=chunk;if(commands.length>50000){commands='';return;}let end;while((end=commands.indexOf('\n'))>=0){try{const c=JSON.parse(commands.slice(0,end));session.command(c);if(c.type==='reset'||(c.type==='memory-pressure'&&c.enabled)){resolver.pending.clear();resolver.retry.clear();}}catch{}commands=commands.slice(end+1);}});
let socket,timer,heartbeat,last=Date.now(),stopping=false,attempt=0;
let dropped=false;
const emit=x=>{if(process.stdout.writableLength>1000000){dropped=true;return;}if(dropped){dropped=false;process.stdout.write(JSON.stringify({type:'status',status:'Feed backlog: some events were dropped; totals are incomplete'})+'\n');}process.stdout.write(JSON.stringify(x)+'\n');};
const EVENT_FIELDS=['user','type','kind','program','event_name','signature','event_index','slot','received','generation','mint','base_mint','quote_mint','pool','name','symbol','base_mint_decimals','token_total_supply','timestamp','sol_amount','token_amount','is_buy','real_sol_reserves','real_token_reserves','virtual_token_reserves','fee','creator_fee','lp_fee','source','canonical_migration','stage','remaining_reserve_ratio'];
function deliver(e){if(['token','pool','migration'].includes(e.kind))emit({type:'observation',generation:session.generation,mint:e.mint||e.base_mint,received:e.received,kind:e.kind,name:e.name,symbol:e.symbol,pool:e.pool,stage:e.stage});const event=session.event(e);if(!event)return false;const compact=Object.fromEntries(EVENT_FIELDS.filter(k=>event[k]!==undefined).map(k=>[k,event[k]]));
 if(event.stage==='near_migration'){const item=session.window.items.get(event.mint);if(item&&!item.announced){item.announced=true;emit({...compact,type:'event',kind:'token',source:'Observed remaining / virtual reserve ratio <= 10%; migration not guaranteed'});}}
 emit({type:'event',...compact});return true;}

const resolver=new PoolResolver((method,params)=>rpc(process.env.SOLANA_RPC_URL||'https://api.mainnet-beta.solana.com',method,params),session,deliver);
const telemetry=setInterval(()=>{session.maintain();emit({type:'telemetry',generation:session.generation,memory:process.memoryUsage(),tracked:session.tracked.size,mints:[...session.tracked],stages:Object.fromEntries(session.window.items),counters:session.window.counters,pools:session.pools.size,pending_pools:resolver.pending.size});},5000);
const poolTimer=setInterval(async()=>{await resolver.tick();if(resolver.status.includes('unavailable'))emit({type:'status',status:resolver.status});},3000);
function connect(){
 emit({type:'status',status:'Connecting to Solana WebSocket'});let subscriptions=0;
 try{socket=new WebSocket(endpoint,{perMessageDeflate:false,maxPayload:262144});}catch{emit({type:'status',status:'Invalid WebSocket endpoint'});return;}
 socket.onopen=()=>{last=Date.now();programs.forEach((program,i)=>socket.send(JSON.stringify({jsonrpc:'2.0',id:i+1,method:'logsSubscribe',params:[{mentions:[program]},{commitment:'confirmed'}]})));};
 socket.onmessage=m=>{last=Date.now();if(m.data.length>262144){emit({type:'status',status:'Oversized feed message dropped; coverage incomplete'});return;}try{const p=JSON.parse(typeof m.data==='string'?m.data:m.data.toString('utf8'));if(p.error){emit({type:'status',status:'RPC rejected subscription; retrying'});socket.close();return;}if(p.id&&p.result!==undefined){subscriptions++;if(subscriptions===programs.length){attempt=0;emit({type:'status',status:'Live · confirmed Pump.fun and PumpSwap events'});}return;}if(p.method!=='logsNotification')return;const r=p.params.result;if(r.value.err)return;for(const decoded of events(r.value.logs||[])){if(decoded.kind==='pool_trade')session.window.counters.pool_trades_seen++;const e={type:'event',signature:r.value.signature,slot:r.context.slot,received:Date.now()/1000,...decoded};const pool=session.pools.get(e.pool);if(e.kind==='pool_trade'&&(!pool||pool.quote_mint==='11111111111111111111111111111111'))resolver.add(e);else deliver(e);}}catch{emit({type:'status',status:'Unrecognized provider message'});}};
 socket.onerror=()=>socket.close();socket.onclose=()=>{clearInterval(heartbeat);if(stopping)return;emit({type:'status',status:'Disconnected · reconnecting; events during downtime may be missing'});timer=setTimeout(connect,Math.min(30000,1000*2**Math.min(attempt++,5)));};
 heartbeat=setInterval(()=>{if(Date.now()-last>60000)socket.close();},10000);
}
function shutdown(){stopping=true;clearTimeout(timer);clearInterval(heartbeat);clearInterval(poolTimer);clearInterval(telemetry);socket?.close();process.exit(0);}
process.on('SIGTERM',shutdown);process.stdin.on('end',shutdown);process.stdout.on('error',shutdown);connect();
