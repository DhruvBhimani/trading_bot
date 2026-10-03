"""Rate-limited route checks. Never supplies a wallet, signs or submits."""
import json
import math
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from feeds import ADDRESS

API='https://api.jup.ag/swap/v2/order'
def read_quote(url,headers):
    with urlopen(Request(url,headers=headers),timeout=8) as response:raw=response.read(200001)
    if len(raw)>200000:raise ValueError('Oversized quote')
    return json.loads(raw)

class PaperQuotes:
    def __init__(self,fetch=read_quote,clock=time.time):self.fetch=fetch;self.clock=clock;self.lock=threading.Lock();self.last=None
    def check(self,inp,out,amount,slippage):
        if not all(isinstance(m,str) and ADDRESS.fullmatch(m) for m in (inp,out)) or inp==out:raise ValueError('Invalid quote mints')
        if type(amount) is not int or not 0<amount<2**64 or type(slippage) is not int or not 1<=slippage<=1000:raise ValueError('Invalid quote size')
        with self.lock:
            now=self.clock()
            if self.last is not None and now-self.last<3:return dict(status='rate_limited',checked=now)
            self.last=now
        params=dict(inputMint=inp,outputMint=out,amount=str(amount),slippageBps=slippage,excludeRouters='jupiterz')
        key=os.environ.get('JUPITER_API_KEY');headers={'x-api-key':key} if key else {}
        try:
            q=self.fetch(API+'?'+urlencode(params),headers)
            if not isinstance(q,dict):raise ValueError('Invalid response')
            if q.get('inputMint')!=inp or q.get('outputMint')!=out or q.get('inAmount')!=str(amount):raise ValueError('Quote mismatch')
            if not q.get('routePlan'):return dict(status='no_route',checked=self.clock(),note='Provider returned no route; not proof of a rug')
            if not isinstance(q['routePlan'],list) or len(q['routePlan'])>32:raise ValueError('Invalid route size')
            output=int(q['outAmount']);minimum=int(q['otherAmountThreshold']);impact=float(q['priceImpactPct'])
            if not 0<minimum<=output<2**64 or not math.isfinite(impact):raise ValueError('Invalid output')
            if minimum<int(output*(1-slippage/10000))-1:raise ValueError('Minimum output mismatch')
            route=[dict(pool=r['swapInfo']['ammKey'],venue=str(r['swapInfo']['label'])[:80]) for r in q['routePlan'][:8]]
            if any(not isinstance(r['pool'],str) or not ADDRESS.fullmatch(r['pool']) for r in route):raise ValueError('Invalid pool address')
            def number(key):
                v=q.get(key)
                try:n=int(v)
                except (TypeError,ValueError):return None
                return n if not isinstance(v,bool) and 0<=n<2**64 else None
            return dict(status='quoted',checked=self.clock(),out_raw=output,minimum_raw=minimum,price_impact_pct=impact,route=route,fee_bps=number('feeBps'),network_lamports={k:number(k) for k in ('signatureFeeLamports','prioritizationFeeLamports','rentFeeLamports')},note='Unsigned route quote; landing, rent and exit execution are not guaranteed')
        except HTTPError as exc:return dict(status='provider_unavailable',checked=self.clock(),note='Quote service unavailable / authentication / rate limit',http_status=exc.code)
        except Exception:return dict(status='provider_unavailable',checked=self.clock(),note='Quote request failed or response could not be validated')
