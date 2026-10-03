// Derive public metadata addresses only. No RPC, wallet, or signing code.
const {pda}=require('./discovery_address.cjs'),bs58=require('bs58');
const program='metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s';
let input='';process.stdin.on('data',chunk=>{input+=chunk;if(input.length>4096)process.exit(1);});
process.stdin.on('end',()=>{
 const mints=JSON.parse(input);if(!Array.isArray(mints)||mints.length>20)throw Error('Invalid batch');
 process.stdout.write(JSON.stringify(mints.map(mint=>{
  const bytes=bs58.decode(mint);if(bytes.length!==32)throw Error('Invalid mint');
  return {mint,hex:bytes.toString('hex'),address:bs58.encode(pda([Buffer.from('metadata'),bs58.decode(program),bytes],program))};
 })));
});
