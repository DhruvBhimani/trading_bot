"""On-chain balances and explicitly scoped app-order analytics. No invented marks."""
import json
import time
from decimal import Decimal
from wallet import SOL,ASSETS

PROGRAMS=['TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb']
class Portfolio:
    def __init__(self,bot,wallet,vault):self.bot=bot;self.wallet=wallet;self.vault=vault
    def read(self,identifier):
        r=self.vault.row(identifier);address=r['address'];balance=self.wallet.balance(address);holdings={};symbols={a['token']:a['symbol'] for a in ASSETS}
        for program in PROGRAMS:
            data=self.wallet.rpc('getTokenAccountsByOwner',[address,{'programId':program},{'encoding':'jsonParsed','commitment':'confirmed'}])
            for item in data['value']:
                info=item['account']['data']['parsed']['info'];a=info['tokenAmount'];mint=info['mint'];raw=int(a['amount'])
                if not raw:continue
                h=holdings.setdefault(mint,dict(mint=mint,symbol=symbols.get(mint,'Unknown token'),raw=0,decimals=a['decimals']))
                h['raw']+=raw
        for h in holdings.values():h['quantity']=str(Decimal(h.pop('raw'))/Decimal(10)**h['decimals'])
        with self.bot.lock:orders=self.bot.store.rows('SELECT created,status,quote,result,signature FROM wallet_orders WHERE wallet=? ORDER BY created',(address,))
        # Known-cost FIFO is limited to app orders with complete receipts and SOL pairs.
        lots={};realized=Decimal(0);closed=0;wins=0;fees=0;unknown=0;confirmed=0
        for order in orders:
            if order['status']!='confirmed':continue
            confirmed+=1;q=json.loads(order['quote']);res=json.loads(order['result'] or '{}');receipt=res.get('chain_receipt')
            if not receipt or receipt.get('err'):unknown+=1;continue
            fees+=receipt.get('fee') or 0
            pre=receipt.get('preBalances') or [];post=receipt.get('postBalances') or []
            if not pre or not post:unknown+=1;continue
            inp=q.get('inputMint');out=q.get('outputMint')
            if SOL not in (inp,out):unknown+=1;continue
            mint=out if inp==SOL else inp
            def total(key):return sum(Decimal(b['uiTokenAmount']['amount'])/(Decimal(10)**b['uiTokenAmount']['decimals']) for b in receipt.get(key,[]) if b.get('owner')==address and b['mint']==mint)
            delta=total('postTokenBalances')-total('preTokenBalances');sol=Decimal(post[0]-pre[0])/Decimal(10)**9
            if inp==SOL and delta>0 and sol<0:lots.setdefault(mint,[]).append([delta,-sol])
            elif out==SOL and delta<0 and sol>0:
                qty=-delta;available=sum(l[0] for l in lots.get(mint,[]))
                if available<qty:unknown+=1;lots.pop(mint,None);continue
                cost=Decimal(0)
                while qty>0:
                    lot=lots[mint][0];take=min(qty,lot[0]);part=lot[1]*take/lot[0];cost+=part;lot[0]-=take;lot[1]-=part;qty-=take
                    if lot[0]==0:lots[mint].pop(0)
                pnl=sol-cost;realized+=pnl;closed+=1;wins+=pnl>0
            else:unknown+=1
        return dict(wallet=address,as_of=time.time(),sol=balance['sol'],slot=balance['slot'],holdings=list(holdings.values()),orders=len(orders),confirmed=confirmed,known_closed=closed,known_wins=wins,recorded_pnl_sol=str(realized) if closed else None,network_fees_sol=str(Decimal(fees)/Decimal(10)**9),unreconciled=unknown,unrealized_pnl=None,note='App-recorded SOL-pair cash-flow P&L only, including native fees/rent changes. External transfers and prior history are not indexed; cost basis can be incomplete. No USD valuation or unrealized P&L is estimated.')
