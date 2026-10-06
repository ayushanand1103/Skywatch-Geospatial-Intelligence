import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from app.flight_sessions import group_positions
class SessionTests(unittest.TestCase):
 def observations(self,values):
  start=datetime(2026,10,7,tzinfo=timezone.utc)
  return [SimpleNamespace(position=object(),created_at=start+timedelta(minutes=m),on_ground=ground) for m,ground in values]
 def test_tracking_gap_separates_sessions(self):
  groups=group_positions(self.observations([(0,None),(20,None),(180,None),(200,None)]))
  self.assertEqual([len(g) for g in groups],[2,2])
 def test_new_takeoff_separates_reused_aircraft(self):
  groups=group_positions(self.observations([(0,False),(20,True),(40,True),(60,False),(80,False)]))
  self.assertEqual([len(g) for g in groups],[3,2])
 def test_midnight_alone_does_not_split_flight(self):
  groups=group_positions(self.observations([(1430,False),(1450,False)]))
  self.assertEqual(len(groups),1)
if __name__=='__main__': unittest.main()
