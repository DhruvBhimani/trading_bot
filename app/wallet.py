"""Real liquidity routing and manually signed swaps. No private keys or auto-signing."""
from contextlib import nullcontext
import base64
import json
import math
import os
import subprocess
import time
import uuid
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from feeds import WATCHLIST,ADDRESS
from store import encode

ROOT=Path(__file__).resolve().parents[1]
SOL='So11111111111111111111111111111111111111112'
USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
ASSETS=[dict(symbol='SOL',token=SOL,decimals=9),dict(symbol='USDC',token=USDC,decimals=6)]+[{**a,'decimals':d} for a,d in zip(WATCHLIST,[5,6,9])]
API='https://api.jup.ag/swap/v2'


def fetch(url,body=None,headers=None):
    request=Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
    with urlopen(request,timeout=20) as response:raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('Response too large')
    return json.loads(raw)


def amount_text(raw,decimals):return format(Decimal(str(raw))/(Decimal(10)**decimals),'f')


class Wallet:
    def __init__(self,bot,enabled=False):
        self.bot=bot;self.enabled=enabled;self.rpc_url=os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')
        self.last_quote=None
        with bot.lock,bot.db:
            bot.db.execute('CREATE TABLE IF NOT EXISTS wallet_orders(id TEXT PRIMARY KEY,created REAL NOT NULL,wallet TEXT,status TEXT NOT NULL,quote TEXT NOT NULL,signature TEXT,result TEXT)')

    def rpc(self,method,params):
        data=fetch(self.rpc_url,{'jsonrpc':'2.0','id':1,'method':method,'params':params})
        if data.get('error'):raise ValueError('Solana RPC rejected the request')
        return data['result']

    def headers(self):
        key=os.environ.get('JUPITER_API_KEY')
        return {'x-api-key':key} if key else {}

    def status(self):
        with self.bot.lock:
            orders=self.bot.store.rows('SELECT id,created,wallet,status,signature,result FROM wallet_orders ORDER BY created DESC LIMIT 30')
        return dict(enabled=self.enabled,assets=ASSETS,orders=orders,network='Solana mainnet',
                    execution='Manual wallet approval only',max_trade_usd=5,api_key_configured=bool(os.environ.get('JUPITER_API_KEY')))

    def balance(self,wallet):
        if not isinstance(wallet,str) or not ADDRESS.fullmatch(wallet):raise ValueError('Invalid public wallet address')
        result=self.rpc('getBalance',[wallet,{'commitment':'confirmed'}])
        return dict(wallet=wallet,sol=result['value']/1e9,slot=result['context']['slot'])

    def quote(self,body):
        with self.bot.lock:
            if self.last_quote is not None and time.monotonic()-self.last_quote<2:raise ValueError('Wait two seconds between route requests')
            self.last_quote=time.monotonic()
        assets={a['token']:a for a in ASSETS};inp=body.get('input_mint');out=body.get('output_mint')
        if inp not in assets or out not in assets or inp==out:raise ValueError('Choose two different supported tokens')
        text=body.get('amount')
        if not isinstance(text,str) or len(text)>30:raise ValueError('Enter a decimal amount')
        try:amount=Decimal(text);raw=amount*(Decimal(10)**assets[inp]['decimals'])
        except InvalidOperation:raise ValueError('Invalid amount') from None
        if not amount.is_finite() or amount<=0 or raw!=raw.to_integral_value() or raw>2**64-1:raise ValueError('Invalid amount or precision')
        bps=body.get('slippage_bps',100)
        if type(bps) is not int or not 1<=bps<=100:raise ValueError('Slippage must be 1–100 basis points')
        wallet=body.get('wallet')
        if wallet and (not isinstance(wallet,str) or not ADDRESS.fullmatch(wallet)):raise ValueError('Invalid wallet address')
        params=dict(inputMint=inp,outputMint=out,amount=str(int(raw)),slippageBps=bps,excludeRouters='jupiterz')
        if wallet:params['taker']=wallet
        q=fetch(API+'/order?'+urlencode(params),headers=self.headers())
        if q.get('inputMint')!=inp or q.get('outputMint')!=out or q.get('inAmount')!=str(int(raw)) or q.get('slippageBps')!=bps:raise ValueError('Quote does not match requested trade')
        if q.get('swapType')!='aggregator' or not q.get('routePlan'):raise ValueError('No liquidity-pool route returned')
        try:
            value=float(q['inUsdValue']);impact=abs(float(q['priceImpactPct']))
            output=int(q['outAmount']);minimum=int(q['otherAmountThreshold'])
        except (KeyError,TypeError,ValueError):raise ValueError('Quote missing cost or output data') from None
        if not math.isfinite(value) or not 0<value<=5:raise ValueError('Initial wallet adapter is limited to $5 per trade')
        if not math.isfinite(impact) or impact>1:raise ValueError('Price impact exceeds the 1% execution cap')
        if not 0<minimum<=output or minimum<int(output*(1-bps/10000))-1:raise ValueError('Invalid minimum output')
        if wallet and q.get('taker')!=wallet:raise ValueError('Quote wallet mismatch')
        identifier=str(uuid.uuid4());created=time.time()
        q['_created']=created;q['_expires']=created+20;q['_wallet']=wallet
        with self.bot.lock,self.bot.db:
            self.bot.db.execute('INSERT INTO wallet_orders VALUES (?,?,?,?,?,?,?)',(identifier,created,wallet,'quoted',encode(q),None,None))
        return dict(id=identifier,expires=q['_expires'],input_symbol=assets[inp]['symbol'],output_symbol=assets[out]['symbol'],
                    input_amount=text,output_amount=amount_text(output,assets[out]['decimals']),minimum_output=amount_text(minimum,assets[out]['decimals']),
                    input_usd=value,price_impact_pct=impact,slippage_bps=bps,fee_bps=q.get('feeBps'),fee_mint=q.get('feeMint'),
                    network_fees={k:q.get(k) for k in ('signatureFeeLamports','prioritizationFeeLamports','rentFeeLamports')},
                    route=[dict(pool=r['swapInfo']['ammKey'],venue=r['swapInfo']['label'],percent=r.get('percent')) for r in q['routePlan']],
                    transaction=q.get('transaction') if wallet else None,wallet=wallet,enabled=self.enabled,
                    build_error=q.get('errorMessage'),request_id=q.get('requestId'))

    def execute(self,body,permit=None):
        if not self.enabled:raise ValueError('Real execution disabled. Restart with --enable-live-swaps only when you intend to trade real funds.')
        identifier=body.get('id');signed=body.get('signed_transaction')
        if not isinstance(signed,str) or len(signed)>20000:raise ValueError('Invalid signed transaction')
        with self.bot.lock:
            row=self.bot.db.execute('SELECT * FROM wallet_orders WHERE id=?',(identifier,)).fetchone()
            if not row:raise ValueError('Unknown quote')
            if row['status']!='quoted':raise ValueError('Order already submitted or expired; check its status instead of sending again')
            q=json.loads(row['quote'])
        if not q.get('transaction') or not q.get('_wallet'):raise ValueError('Quote has no wallet transaction')
        if time.time()>q['_expires']:raise ValueError('Quote expired. Request a new route; no transaction was sent.')
        if q.get('lastValidBlockHeight') and self.rpc('getBlockHeight',[{'commitment':'confirmed'}])>q['lastValidBlockHeight']:raise ValueError('Blockhash expired')
        guarded=subprocess.run(['node',str(ROOT/'app/wallet_guard.cjs')],input=json.dumps(dict(original=q['transaction'],signed=signed,wallet=q['_wallet'])),text=True,capture_output=True,timeout=10)
        if guarded.returncode:raise ValueError('Signed transaction failed exact-message/wallet-signature validation')
        signature=json.loads(guarded.stdout)['signature']
        simulation=self.rpc('simulateTransaction',[signed,{'encoding':'base64','sigVerify':True,'commitment':'processed'}])
        if simulation['value'].get('err'):raise ValueError('On-chain simulation failed; no transaction was submitted')
        with (permit() if permit else nullcontext()),self.bot.lock,self.bot.db:
            if time.time()>q['_expires']:raise ValueError('Quote expired during review. No transaction was submitted.')
            changed=self.bot.db.execute("UPDATE wallet_orders SET status='submitting',signature=? WHERE id=? AND status='quoted'",(signature,identifier)).rowcount
            if changed!=1:raise ValueError('Submission already started')
        try:
            result=fetch(API+'/execute',dict(signedTransaction=signed,requestId=q['requestId']),self.headers())
            status='submitted' if result.get('status')=='Success' else 'unknown'
        except Exception:
            result={'message':'Submission outcome unknown. Check confirmation; do not resend blindly.'};status='unknown'
        with self.bot.lock,self.bot.db:
            self.bot.db.execute('UPDATE wallet_orders SET status=?,result=? WHERE id=?',(status,encode(result),identifier))
        return dict(id=identifier,status=status,signature=signature,result=result)

    def confirm(self,identifier):
        with self.bot.lock:
            row=self.bot.db.execute('SELECT signature FROM wallet_orders WHERE id=?',(identifier,)).fetchone()
        if not row or not row['signature']:raise ValueError('Order has no submitted signature')
        value=self.rpc('getSignatureStatuses',[[row['signature']],{'searchTransactionHistory':True}])['value'][0]
        status='unknown'
        if value:status='failed' if value.get('err') else ('confirmed' if value.get('confirmationStatus') in ('confirmed','finalized') else 'submitted')
        receipt=None
        if status=='confirmed':
            tx=self.rpc('getTransaction',[row['signature'],{'encoding':'json','commitment':'confirmed','maxSupportedTransactionVersion':0}])
            if tx and tx.get('meta'):
                meta=tx['meta']
                if meta.get('err'):status='failed'
                receipt={k:meta.get(k) for k in ('fee','err','preBalances','postBalances','preTokenBalances','postTokenBalances')}
                receipt['slot']=tx.get('slot')
        with self.bot.lock,self.bot.db:
            previous=self.bot.db.execute('SELECT result FROM wallet_orders WHERE id=?',(identifier,)).fetchone()
            result=json.loads(previous['result']) if previous['result'] else {}
            result['chain_receipt']=receipt
            self.bot.db.execute('UPDATE wallet_orders SET status=?,result=? WHERE id=?',(status,encode(result),identifier))
        return dict(id=identifier,status=status,signature=row['signature'],confirmation=value,chain_receipt=receipt)
