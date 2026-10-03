import unittest
from unittest.mock import Mock
from usd_reference import UsdReference

class ReferenceTests(unittest.TestCase):
    def test_freshness_rate_limit_and_invalid_responses(self):
        now=[1000];reader=Mock(return_value={'data':dict(base='SOL',currency='USD',amount='150')})
        ref=UsdReference(reader,lambda:now[0]);self.assertIsNone(ref.rate());ref.refresh()
        self.assertEqual(ref.rate(),150);ref.refresh();self.assertEqual(reader.call_count,1)
        now[0]=1091;self.assertIsNone(ref.rate());self.assertEqual(ref.snapshot()['status'],'stale')
        for value in ('NaN','inf','-1','0'):
            reader.return_value={'data':dict(base='SOL',currency='USD',amount=value)};now[0]+=31;ref.refresh();self.assertIsNone(ref.rate())
        reader.return_value={'data':dict(base='BTC',currency='USD',amount='150')};now[0]+=31;ref.refresh();self.assertIsNone(ref.rate())
