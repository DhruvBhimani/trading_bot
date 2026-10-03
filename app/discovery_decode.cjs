const bs58=require('bs58');
const schemas=require('./protocols/pump-create-events.json');
function decode(program,raw){
 const b=Buffer.from(raw,'base64'),schema=schemas.find(s=>s.program===program&&b.subarray(0,8).equals(Buffer.from(s.discriminator)));if(!schema)return null;
 let offset=8,out={};function take(n){if(offset+n>b.length)throw Error('Truncated event');const v=b.subarray(offset,offset+n);offset+=n;return v;}
 // Read stable event prefix only. Later protocol fields may be appended independently.
 const last=schema.event==='CreateEvent'?'token_total_supply':schema.event==='CreatePoolEvent'?'pool':'holder_rewards';
 for(const f of schema.fields){let v;switch(f.type){case 'string':{const n=take(4).readUInt32LE();if(n>4096)throw Error('Oversized metadata');v=take(n).toString('utf8');break;}case 'pubkey':v=bs58.encode(take(32));break;case 'u64':v=take(8).readBigUInt64LE().toString();break;case 'i64':v=take(8).readBigInt64LE().toString();break;case 'u16':v=take(2).readUInt16LE();break;case 'u8':v=take(1)[0];break;case 'bool':{const n=take(1)[0];if(n>1)throw Error('Invalid boolean');v=!!n;break;}default:if(f.type?.vec?.defined?.name==='Shareholder'){const n=take(4).readUInt32LE();if(n>100)throw Error('Too many shareholders');v=[];for(let i=0;i<n;i++)v.push({address:bs58.encode(take(32)),share_bps:take(2).readUInt16LE()});}else throw Error('Unsupported prefix');}out[f.name]=v;if(f.name===last)break;}
 return {kind:schema.event==='CreateEvent'?'token':schema.event==='TradeEvent'?'trade':['BuyEvent','SellEvent'].includes(schema.event)?'pool_trade':schema.event==='CompletePumpAmmMigrationEvent'?'migration':'pool',program,event_name:schema.event,...out};
}
function events(logs){
 const stack=[],out=[];
 for(let i=0;i<logs.length;i++){
  const l=logs[i],invoke=/^Program (\w+) invoke \[\d+\]$/.exec(l),exit=/^Program (\w+) (success|failed:)/.exec(l);
  if(invoke)stack.push({program:invoke[1],events:[]});
  else if(exit){
   if(stack.at(-1)?.program!==exit[1]){stack.length=0;continue;}
   const frame=stack.pop();if(exit[2]==='success')(stack.at(-1)?.events||out).push(...frame.events);
  }else if(l.startsWith('Program data: ')&&schemas.some(s=>s.program===stack.at(-1)?.program)){
   try{const e=decode(stack.at(-1).program,l.slice(14));if(e)stack.at(-1).events.push({...e,event_index:i,raw:l.slice(14)});}catch{}
  }
 }
 return out;
}
module.exports={events,decode,schemas};
