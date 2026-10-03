import {VersionedTransaction,PublicKey} from '@solana/web3.js';
window.DBWallet={
 provider(){const p=window.phantom?.solana;if(!p?.isPhantom)throw Error('Open in a browser with Phantom installed. The app never needs your seed phrase.');return p;},
 async connect(){const p=this.provider();await p.connect();return p.publicKey.toString();},
 async disconnect(){await this.provider().disconnect();},
 async sign(base64,wallet){const p=this.provider();if(p.publicKey?.toString()!==wallet)throw Error('Wallet changed. Request a fresh route.');const tx=VersionedTransaction.deserialize(Uint8Array.from(atob(base64),c=>c.charCodeAt(0)));if(!tx.message.staticAccountKeys[0].equals(new PublicKey(wallet)))throw Error('Unexpected fee payer');const signed=await p.signTransaction(tx);return btoa(String.fromCharCode(...signed.serialize()));}
};
