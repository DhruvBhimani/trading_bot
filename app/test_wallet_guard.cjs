const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {Keypair,PublicKey,SystemProgram,TransactionMessage,VersionedTransaction}=require('@solana/web3.js');
const wallet=Keypair.generate(),recipient=Keypair.generate();
function tx(amount){return new VersionedTransaction(new TransactionMessage({payerKey:wallet.publicKey,recentBlockhash:PublicKey.default.toBase58(),instructions:[SystemProgram.transfer({fromPubkey:wallet.publicKey,toPubkey:recipient.publicKey,lamports:amount})]}).compileToV0Message());}
const original=tx(1),signed=tx(1);signed.sign([wallet]);
function guard(changed,publicKey=wallet.publicKey){return spawnSync('node',[__dirname+'/wallet_guard.cjs'],{input:JSON.stringify({original:Buffer.from(original.serialize()).toString('base64'),signed:Buffer.from(changed.serialize()).toString('base64'),wallet:publicKey.toBase58()}),encoding:'utf8'});}
assert.equal(guard(signed).status,0);
assert.notEqual(guard(original).status,0);
const altered=tx(2);altered.sign([wallet]);assert.notEqual(guard(altered).status,0);
assert.notEqual(guard(signed,recipient.publicKey).status,0);
console.log('4 wallet signature/message validation checks passed; no RPC or funds used.');
