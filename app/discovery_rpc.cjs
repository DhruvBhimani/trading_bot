// Small bounded HTTP client; the scanner does not load the wallet SDK/fetch stack.
const https=require('node:https'),http=require('node:http');
const agents={https:new https.Agent({keepAlive:true,maxSockets:1}),http:new http.Agent({keepAlive:true,maxSockets:1})};
function rpc(url,method,params){return new Promise((resolve,reject)=>{
 const secure=new URL(url).protocol==='https:',transport=secure?https:http;
 const req=transport.request(url,{method:'POST',agent:secure?agents.https:agents.http,headers:{'Content-Type':'application/json'}},res=>{
  if(res.statusCode!==200){res.destroy();reject(Error('RPC unavailable'));return;}
  const chunks=[];let size=0;
  res.on('data',chunk=>{size+=chunk.length;if(size>200000){req.destroy(Error('Oversized RPC response'));return;}chunks.push(chunk);});
  res.on('error',reject);res.on('end',()=>{try{const x=JSON.parse(Buffer.concat(chunks).toString());if(x.error)throw Error('RPC rejected');resolve(x.result);}catch(e){reject(e);}});
 });
 req.setTimeout(8000,()=>req.destroy(Error('RPC timeout')));req.on('error',reject);
 req.end(JSON.stringify({jsonrpc:'2.0',id:1,method,params}));
});}
module.exports={rpc};
