"""Isolated read-only feed soak, temporary paper records, deliberate worker restart."""
import argparse,json,os,sys,tempfile,threading,time
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from discovery import Discovery
from live_store import LiveStore
from market import Market
from live_paper import LivePaper
from wallet import fetch
from usd_reference import UsdReference

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=180);parser.add_argument('--report',default='/tmp/db-bot-scanner-check.json');args=parser.parse_args()
 rpc=lambda method,params:fetch(os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),{'jsonrpc':'2.0','id':1,'method':method,'params':params})['result']
 with tempfile.TemporaryDirectory() as tmp:
  live=LiveStore();market=Market(live,rpc);d=Discovery(live,market);usd=UsdReference();usd.refresh();paper=LivePaper(Path(tmp)/'paper.sqlite3',d,usd=usd);stop=threading.Event();errors=deque(maxlen=30);durations=deque(maxlen=1000);samples=[];restarted=False;old_pid=None
  def reference():
   while not stop.wait(30):usd.refresh()
  reference_thread=threading.Thread(target=reference);reference_thread.start()
  def enrich():
   while not stop.is_set():
    d.metadata_changed.wait(2);d.metadata_changed.clear()
    if stop.wait(.5):break
    try:d.maintain();market.enrich();d.changed.set()
    except Exception as e:errors.append(type(e).__name__)
  t=threading.Thread(target=enrich);t.start();d.start();paper.control('start');start=time.monotonic()
  try:
   while time.monotonic()-start<args.seconds:
    d.changed.wait(.5);d.changed.clear()
    if stop.wait(.2):break
    tick=time.monotonic();paper.tick();durations.append(1000*(time.monotonic()-tick));elapsed=time.monotonic()-start
    if not restarted and elapsed>=args.seconds/2 and d.process:
     old_pid=d.process.pid;d.process.terminate();restarted=True
    if int(elapsed)//30>len(samples):
     s=paper.status();sample=dict(seconds=round(elapsed),running=s['running'],pools=s['feed']['pools'],fresh=s['feed']['fresh_pools'],cache_mib=round(s['memory']['used_bytes']/1048576,2),worker_rss_mib=round(s['feed'].get('worker_memory',{}).get('rss',0)/1048576,1),restarts=d.restarts,closed=sum(a['closed'] for a in s['accounts']),open=sum(len(a['positions']) for a in s['accounts']));samples.append(sample);print(json.dumps(sample),flush=True)
   s=paper.status();ordered=sorted(durations)
   report=dict(samples=samples,errors=list(errors),tick_ms_p50=ordered[len(ordered)//2],tick_ms_p95=ordered[int(len(ordered)*.95)],restart_recovered=bool(old_pid and d.process and d.process.pid!=old_pid and d.process.poll() is None and d.restarts),paper_running=s['running'],entry_timing=[{k:t.get(k) for k in ('mint','signal_to_entry_seconds','entry_wait_before_queue_seconds','entry_delay_seconds','entry_event_to_evaluation_seconds','entry_move_pct')} for t in s['trades']],entry_delays_seconds=[t['signal_to_entry_seconds'] for t in s['trades'] if t.get('signal_to_entry_seconds') is not None],opportunities=s['opportunities'],size_usd=s['config'].get('size_usd'),note='Temporary accounts; evaluation time is not chain-to-fill latency; no guarantee all pools were observed.')
   Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
  finally:stop.set();d.close();t.join(25);reference_thread.join();paper.close();live.close()
if __name__=='__main__':main()
