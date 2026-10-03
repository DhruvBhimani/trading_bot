// Only validates a wallet-signed copy of an exact server-issued transaction.
const {VersionedTransaction,PublicKey}=require('@solana/web3.js');
const crypto=require('node:crypto');
let input='';process.stdin.on('data',c=>input+=c);process.stdin.on('end',()=>{try{
 const p=JSON.parse(input),original=VersionedTransaction.deserialize(Buffer.from(p.original,'base64')),
 signed=VersionedTransaction.deserialize(Buffer.from(p.signed,'base64')),
 key=new PublicKey(p.wallet);
 if(!Buffer.from(original.message.serialize()).equals(Buffer.from(signed.message.serialize())))throw Error('Transaction message changed');
 if(!signed.message.staticAccountKeys[0].equals(key))throw Error('Wallet must be the fee payer');
 const pub=crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),key.toBuffer()]),format:'der',type:'spki'});
 if(!crypto.verify(null,Buffer.from(signed.message.serialize()),pub,Buffer.from(signed.signatures[0])))throw Error('Wallet signature invalid');
 const alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';let n=BigInt('0x'+Buffer.from(signed.signatures[0]).toString('hex')),out='';while(n){out=alphabet[Number(n%58n)]+out;n/=58n;}for(const b of signed.signatures[0]){if(b)break;out='1'+out;}
 console.log(JSON.stringify({signature:out}));
 }catch(e){console.error(e.message);process.exitCode=1;}});
