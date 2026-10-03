const {createHash}=require('node:crypto'),{ed25519}=require('@noble/curves/ed25519');
const bs58=require('bs58');
// Solana's standard PDA derivation; no wallet SDK or secret material.
function pda(seeds,program){
 for(let bump=255;bump>0;bump--){
  const bytes=createHash('sha256').update(Buffer.concat([...seeds,Buffer.from([bump]),bs58.decode(program),Buffer.from('ProgramDerivedAddress')])).digest();
  try{ed25519.ExtendedPoint.fromHex(bytes);}catch{return bytes;}
 }
 throw Error('No PDA bump');
}
function canonicalPool(pool,base,quote,creator,index){
 if(index!==0)return false;
 const authority=pda([Buffer.from('pool-authority'),bs58.decode(base)],'6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P');
 if(!authority.equals(creator))return false;
 const expected=pda([Buffer.from('pool'),Buffer.from([0,0]),authority,bs58.decode(base),bs58.decode(quote)],'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA');
 return bs58.encode(expected)===pool;
}
module.exports={pda,canonicalPool};
