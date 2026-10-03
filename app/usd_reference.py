"""Small, cached public SOL/USD reference for display and paper sizing; never executes swaps."""
import json
import math
import time
from urllib.request import Request,urlopen

URL='https://api.coinbase.com/v2/prices/SOL-USD/spot'
def fetch():
    with urlopen(Request(URL,headers={'User-Agent':'DBBot/1.0'}),timeout=5) as response:raw=response.read(16385)
    if len(raw)>16384:raise ValueError('Oversized reference')
    return json.loads(raw)

class UsdReference:
    def __init__(self,reader=fetch,clock=time.time):self.reader=reader;self.clock=clock;self.quote=None;self.attempt=None
    def refresh(self):
        now=self.clock()
        if self.attempt is not None and now-self.attempt<30:return
        self.attempt=now
        try:
            data=self.reader()['data'];rate=float(data['amount'])
            if data.get('base')!='SOL' or data.get('currency')!='USD' or not math.isfinite(rate) or rate<=0:raise ValueError('Invalid reference')
            self.quote=dict(rate=rate,received=self.clock(),source='Coinbase SOL/USD spot')
        except Exception:pass
    def snapshot(self):
        q=self.quote
        if not q:return dict(rate=None,status='unavailable')
        age=max(0,self.clock()-q['received'])
        return dict(**q,age_seconds=age,status='fresh' if age<=90 else 'stale',rate_available=age<=90)
    def rate(self):
        q=self.snapshot();return q['rate'] if q['status']=='fresh' else None
