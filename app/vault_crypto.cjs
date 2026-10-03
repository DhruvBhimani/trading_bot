// Secrets travel only over stdin/stdout pipes to the local server, never argv/logs.
const crypto=require('node:crypto');
const {Keypair,VersionedTransaction}=require('@solana/web3.js');
const bs58=require('bs58');
function key(password,salt){if(typeof password!=='string'||password.length<12||password.length>256)throw Error('Use a passphrase of 12–256 characters');return crypto.scryptSync(password,salt,32,{N:32768,r:8,p:1,maxmem:64*1024*1024});}
function seal(pair,password){const salt=crypto.randomBytes(16),iv=crypto.randomBytes(12),k=key(password,salt),c=crypto.createCipheriv('aes-256-gcm',k,iv);try{const ciphertext=Buffer.concat([c.update(pair.secretKey),c.final()]);return {version:1,salt:salt.toString('base64'),iv:iv.toString('base64'),tag:c.getAuthTag().toString('base64'),ciphertext:ciphertext.toString('base64')};}finally{k.fill(0);}}
function open(v,password){if(v.version!==1)throw Error('Unsupported vault');const k=key(password,Buffer.from(v.salt,'base64'));try{const d=crypto.createDecipheriv('aes-256-gcm',k,Buffer.from(v.iv,'base64'));d.setAuthTag(Buffer.from(v.tag,'base64'));const raw=Buffer.concat([d.update(Buffer.from(v.ciphertext,'base64')),d.final()]);try{return Keypair.fromSecretKey(Uint8Array.from(raw));}finally{raw.fill(0);}}finally{k.fill(0);}}
function act(p){let pair;try{
 if(p.action==='create'){if(p.secret){let bytes=p.secret.trim().startsWith('[')?Uint8Array.from(JSON.parse(p.secret)):bs58.decode(p.secret.trim());try{pair=Keypair.fromSecretKey(Uint8Array.from(bytes));}finally{bytes.fill(0);}}else pair=Keypair.generate();return {address:pair.publicKey.toBase58(),vault:seal(pair,p.password)};}
 pair=open(p.vault,p.password);if(pair.publicKey.toBase58()!==p.address)throw Error('Wallet mismatch');
 if(p.action==='unlock')return {address:p.address};
 if(p.action==='export')return {secret:bs58.encode(pair.secretKey)};
 if(p.action==='sign'){const tx=VersionedTransaction.deserialize(Buffer.from(p.transaction,'base64'));if(tx.message.staticAccountKeys[0].toBase58()!==p.address||tx.message.header.numRequiredSignatures!==1)throw Error('Unexpected signer');tx.sign([pair]);return {signed:Buffer.from(tx.serialize()).toString('base64')};}
 throw Error('Unknown action');
 }finally{if(pair)pair._keypair.secretKey.fill(0);}}
module.exports={act};
if(require.main===module){let input='';process.stdin.on('data',c=>{input+=c;if(input.length>50000)process.exit(1);});process.stdin.on('end',()=>{try{process.stdout.write(JSON.stringify(act(JSON.parse(input))));}catch{process.stdout.write(JSON.stringify({error:'Vault operation failed. Check passphrase, wallet and transaction.'}));process.exitCode=1;}});}
