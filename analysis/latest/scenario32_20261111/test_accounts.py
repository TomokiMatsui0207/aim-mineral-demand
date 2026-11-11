from pathlib import Path
import unittest,importlib.util
import numpy as np,pandas as pd
spec=importlib.util.spec_from_file_location('accounts32',Path(__file__).with_name('calculate.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class AccountsTests(unittest.TestCase):
 def test_retirement_is_delayed_and_causal(self):
  f=np.zeros((a.N,a.K));f[0,0]=10
  r=a.delayed_retirement(f,3,0)
  self.assertEqual(r[:3].sum(),0);self.assertEqual(r[3,0],10);self.assertEqual(r.sum(),10)
 def test_uniform_legacy_is_explicit_not_current_manufacturing(self):
  f=np.zeros((a.N,a.K));f[0,0]=10
  r=a.delayed_retirement(f,3,.5)
  np.testing.assert_allclose(r[:3,0],[5,5,5]);self.assertEqual(r[3,0],10)
 def test_pack_replacement_does_not_replace_vehicle_twice(self):
  oldacts,oldvectors,oldpack=a.acts,a.vehicle_vectors,a.pack
  body=np.zeros((a.N,a.K));body[:,a.J['Cu']]=2
  bp=np.zeros(a.K);bp[a.J['Li']]=3
  a.acts=pd.DataFrame([dict(Sc='synthetic',year=2020,vehicle_class='LDV',powertrain='BEV',new_vehicles_year=1000.)])
  a.vehicle_vectors=lambda c:({('LDV','BEV'):body+bp},{('LDV','BEV'):body})
  a.pack=lambda *args:bp
  try:g,r,extra=a.vehicle_flows('synthetic',dict(a.BASE,legacy=0.,battery_life=8))
  finally:a.acts,a.vehicle_vectors,a.pack=oldacts,oldvectors,oldpack
  self.assertEqual(g[:,a.J['Cu']].sum(),2.)
  self.assertEqual(g[:,a.J['Li']].sum(),6.)
  self.assertEqual(extra[:,a.J['Li']].sum(),3.)
  self.assertEqual(r[8,a.J['Li']],3.)
  self.assertEqual(r[12,a.J['Li']],3.)
  self.assertEqual(r[12,a.J['Cu']],2.)
  self.assertEqual(r[:,a.J['Li']].sum(),6.)
 def test_LCE_hypothesis_changes_only_affected_LDV_Li(self):
  x=a.pack('LDV','BEV',2030,a.CASES[0]);y=a.pack('LDV','BEV',2030,a.CASES[1])
  keep=[i for i,m in enumerate(a.M) if m!='Li'];np.testing.assert_allclose(x[keep],y[keep]);self.assertAlmostEqual(y[a.J['Li']]/x[a.J['Li']],a.CASES[1]['li_factor'])
 def test_rate_and_yield_bounds(self):
  self.assertTrue(((a.RATES>=0)&(a.RATES<=1)).all());self.assertTrue(((a.rr>0)&(a.rr<=1)).all())
if __name__=='__main__':unittest.main()
