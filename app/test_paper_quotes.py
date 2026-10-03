import unittest
from unittest.mock import Mock
from urllib.parse import urlparse,parse_qs
from paper_quotes import PaperQuotes

SOL='So11111111111111111111111111111111111111112';MINT='B'*32
def response():return dict(inputMint=SOL,outputMint=MINT,inAmount='100000000',outAmount='1000000',otherAmountThreshold='990000',priceImpactPct='0.1',routePlan=[dict(swapInfo=dict(ammKey=MINT,label='PumpSwap'))],transaction='must not keep',feeBps=100)
class QuoteTests(unittest.TestCase):
 def test_quote_is_unsigned_validated_and_rate_limited(self):
  fetch=Mock(return_value=response());q=PaperQuotes(fetch,clock=lambda:100)
  result=q.check(SOL,MINT,100000000,100);self.assertEqual(result['status'],'quoted');self.assertNotIn('transaction',result)
  params=parse_qs(urlparse(fetch.call_args.args[0]).query);self.assertNotIn('taker',params);self.assertNotIn('wallet',params)
  self.assertEqual(q.check(SOL,MINT,100000000,100)['status'],'rate_limited');self.assertEqual(fetch.call_count,1)
 def test_mismatch_or_bad_minimum_is_provider_failure(self):
  for change in [dict(inputMint=MINT),dict(otherAmountThreshold='1'),dict(outAmount='0'),dict(priceImpactPct='nan')]:
   q=PaperQuotes(Mock(return_value={**response(),**change}),clock=lambda:100);self.assertEqual(q.check(SOL,MINT,100000000,100)['status'],'provider_unavailable')
 def test_no_route_and_network_failure_are_distinct(self):
  self.assertEqual(PaperQuotes(Mock(return_value={**response(),'routePlan':[]}),clock=lambda:100).check(SOL,MINT,100000000,100)['status'],'no_route')
  self.assertEqual(PaperQuotes(Mock(side_effect=OSError()),clock=lambda:100).check(SOL,MINT,100000000,100)['status'],'provider_unavailable')
