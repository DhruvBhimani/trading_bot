"""Bounded public on-chain names. Never fetch token-supplied URLs."""
import base64
import json
import subprocess
import time
import threading
import unicodedata
from collections import OrderedDict
from pathlib import Path

PROGRAM='metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s'
TOKEN_2022='TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'

def clean(value,limit):
    if not isinstance(value,str):return ''
    return ''.join(c for c in value if not unicodedata.category(c).startswith('C'))[:limit].strip()

def parse_metadata(account,mint_hex):
    if not account or account.get('owner')!=PROGRAM or account.get('executable'):return None
    data=account.get('data')
    if not isinstance(data,list) or len(data)!=2 or data[1]!='base64' or len(data[0])>4096:return None
    try:
        raw=base64.b64decode(data[0],validate=True)
        if len(raw)<73 or raw[0]!=4 or raw[33:65]!=bytes.fromhex(mint_hex):return None
        offset=65;values=[]
        for limit in (32,10):
            length=int.from_bytes(raw[offset:offset+4],'little');offset+=4
            if length>limit or offset+length>len(raw):return None
            values.append(clean(raw[offset:offset+length].decode('utf-8'),limit));offset+=length
        return dict(name=values[0],symbol=values[1]) if values[0] else None
    except (ValueError,UnicodeError):return None

def extension_name(account,mint):
    if not account or account.get('owner')!=TOKEN_2022 or account.get('executable'):return None
    data=account.get('data',{})
    if not isinstance(data,dict):return None
    parsed=data.get('parsed',{})
    if parsed.get('type')!='mint':return None
    for ext in parsed.get('info',{}).get('extensions',[]):
        state=ext.get('state',{})
        if ext.get('extension')=='tokenMetadata' and state.get('mint')==mint:
            name=clean(state.get('name'),64)
            if name:return dict(name=name,symbol=clean(state.get('symbol'),20))
    return None

class TokenNames:
    def __init__(self,rpc):self.lock=threading.RLock();self.rpc=rpc;self.cache=OrderedDict();self.retry=OrderedDict()
    def get(self,mint):return self.cache.get(mint,{})
    def remember(self,mint,value):
        name=clean(value.get('name'),64);symbol=clean(value.get('symbol'),20)
        if not name:return
        with self.lock:
            self.cache[mint]=dict(name=name,symbol=symbol);self.cache.move_to_end(mint)
            while len(self.cache)>256:self.cache.popitem(last=False)
    def enrich(self,mints,accept=lambda:True):
        now=time.time();batch=[m for m in dict.fromkeys(mints) if m not in self.cache and self.retry.get(m,0)<=now][:20]
        if not batch:return
        for mint in batch:self.retry[mint]=now+60;self.retry.move_to_end(mint)
        while len(self.retry)>256:self.retry.popitem(last=False)
        helper=subprocess.run(['node','--max-old-space-size=48',str(Path(__file__).with_name('metadata_addresses.cjs'))],input=json.dumps(batch),text=True,capture_output=True,timeout=5,check=True)
        addresses=json.loads(helper.stdout)
        response=self.rpc('getMultipleAccounts',[[x['address'] for x in addresses],{'encoding':'base64','commitment':'confirmed'}])
        accounts=response.get('value',[])
        if len(accounts)!=len(batch):raise ValueError('Incomplete token-name response')
        if not accept():return
        for item,account in zip(addresses,accounts):
            value=parse_metadata(account,item['hex'])
            if value:self.remember(item['mint'],value)
        # Token-2022 can keep its metadata in the mint instead of a Metaplex PDA.
        missing=[m for m in batch if m not in self.cache]
        if missing:
            response=self.rpc('getMultipleAccounts',[missing,{'encoding':'jsonParsed','commitment':'confirmed'}])
            accounts=response.get('value',[])
            if len(accounts)!=len(missing):raise ValueError('Incomplete Token-2022 name response')
            if not accept():return
            for mint,account in zip(missing,accounts):
                value=extension_name(account,mint)
                if value:self.remember(mint,value)
