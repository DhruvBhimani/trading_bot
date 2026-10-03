import unittest
from discovery import Discovery
from live_store import LiveStore

class ObservationQueueTests(unittest.TestCase):
 def test_creation_census_is_independent_of_tracked_cards_and_bounded(self):
  live=LiveStore();d=Discovery(live)
  try:
   for i in range(2100):d.ingest(dict(type='observation',mint='mint'+str(i),received=i,kind='token',name='a'*4096))
   self.assertEqual(len(d.observations),2048);self.assertEqual(d.observation_drops,52)
   self.assertEqual(len(d.observations[-1]['name']),128)
   self.assertEqual(live.db.execute('SELECT COUNT(*) FROM launch_events').fetchone()[0],0)
   d.ingest(dict(type='observation',generation=99,mint='wrong-generation',received=1))
   self.assertNotEqual(d.observations[-1]['mint'],'wrong-generation')
  finally:live.close()
