const assert=require('node:assert/strict'),{events,decode,schemas}=require('./discovery_decode.cjs'),{Keypair}=require('@solana/web3.js');
const s=schemas[0];let parts=[Buffer.from(s.discriminator)];for(const f of s.fields){if(f.type==='string'){const text=Buffer.from(f.name==='name'?'<script>hostile metadata</script>':'test');const n=Buffer.alloc(4);n.writeUInt32LE(text.length);parts.push(n,text);}else if(f.type==='pubkey')parts.push(Keypair.generate().publicKey.toBuffer());else if(f.type==='u64'){const n=Buffer.alloc(8);n.writeBigUInt64LE(1000000000000000n);parts.push(n);}else if(f.type==='i64'){const n=Buffer.alloc(8);n.writeBigInt64LE(100n);parts.push(n);}if(f.name==='token_total_supply')break;}
const raw=Buffer.concat(parts).toString('base64');assert.equal(decode(s.program,raw).kind,'token');assert.equal(events([`Program ${s.program} invoke [1]`,`Program data: ${raw}`,`Program ${s.program} success`]).length,1);assert.equal(events([`Program data: ${raw}`]).length,0);assert.equal(events(['Program fake invoke [1]',`Program data: ${raw}`]).length,0);assert.equal(decode(s.program,Buffer.alloc(8).toString('base64')),null);assert.throws(()=>decode(s.program,Buffer.from(s.discriminator).toString('base64')));


assert.equal(events([`Program ${s.program} invoke [1]`,`Program data: ${raw}`,`Program ${s.program} failed: error`]).length,0);
assert.equal(events(['Program outer invoke [1]',`Program ${s.program} invoke [2]`,`Program data: ${raw}`,`Program ${s.program} success`,'Program outer failed: error']).length,0);

console.log('8 creation-event decoding/provenance checks passed.');
