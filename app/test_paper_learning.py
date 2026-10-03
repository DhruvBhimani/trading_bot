import json,sqlite3,unittest,tempfile
from pathlib import Path
from paper_learning import PaperLearning
class LearningTests(unittest.TestCase):
 def test_database_restart_keeps_versions_and_progress(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'learning.sqlite3';db=sqlite3.connect(path);db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY,strategy TEXT,body TEXT)');learner=PaperLearning(db)
   for i in range(40):
    db.execute('INSERT INTO trades(strategy,body) VALUES (?,?)',('momentum',json.dumps(dict(mint=str(i),entry_time=100,exit_time=200,version='v',entry_features=dict(experimental_score=80 if i<20 else 30),pnl_sol=.02 if i<20 else -.03))))
   learner.update(500);before=learner.status()['versions'];db.commit();db.close()
   db=sqlite3.connect(path);db.row_factory=sqlite3.Row;learner=PaperLearning(db)
   self.assertEqual(learner.status()['versions'],before);learner.update(700);self.assertEqual(learner.status()['versions'],before);db.close()
 def test_versions_are_frozen_and_only_later_unseen_coins_are_evaluated(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY,strategy TEXT,body TEXT)');learner=PaperLearning(db)
  def add(mint,entry,exit,score,pnl):
   db.execute('INSERT INTO trades(strategy,body) VALUES (?,?)',('momentum',json.dumps(dict(mint=mint,entry_time=entry,exit_time=exit,version='v',entry_features=dict(experimental_score=score,pool_sol=5),pnl_sol=pnl))))
  for i in range(39):add(str(i),100,200,80 if i<20 else 30,.02 if i<20 else -.03)
  learner.update(500);self.assertFalse(learner.status()['versions'])
  add('39',100,200,30,-.03);learner.update(500);v=learner.status()['versions'][0];self.assertEqual(v['forward']['seen'],0)
  add('late-close',400,600,80,.1);add('0',501,600,80,.1);add('new',501,600,80,.01)
  learner.update(700);v2=learner.status()['versions'][0];self.assertEqual(v2['id'],v['id']);self.assertEqual(v2['forward']['seen'],1);self.assertEqual(v2['forward']['selected'],1)
  learner.update(800);self.assertEqual(learner.status()['versions'][0]['forward']['seen'],1);db.close()
