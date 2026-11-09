import sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'analysis'))
from model import annual,stock_flows,strict_material_demand,MINERALS
from resolve_solar_overlap_v5 import convert_capacity
class PublicToolsTests(unittest.TestCase):
    def test_interpolation_refuses_extrapolation(self):
        with self.assertRaises(ValueError):annual(pd.Series([1.,2.],index=[2030,2050]),2020,2100)
    def test_repeat_replacement_for_constant_stock(self):
        d=stock_flows(pd.Series(100.,index=range(2020,2061)),10)
        self.assertAlmostEqual(d['new'].sum(),400.)
        np.testing.assert_allclose(d.balance_residual,0,atol=1e-9)
    def test_missing_mineral_is_not_zero(self):
        a=pd.DataFrame([dict(Sc='test',year=2020,component='one',unit='GW',quantity=1.)])
        c=pd.DataFrame([dict(component='one',unit='GW',mineral='Cu',t_per_unit=10.)])
        _,t=strict_material_demand(a,c)
        self.assertEqual(len(t),40)
        self.assertTrue(t.loc[t.mineral.eq('Dy'),'complete_demand_t'].isna().all())
        self.assertEqual(t.loc[t.mineral.eq('Cu'),'complete_demand_t'].iloc[0],10)
    def test_capacity_basis_unknown_rejected(self):
        with self.assertRaises(ValueError):convert_capacity(1,'unknown','DC')
        with self.assertRaises(ValueError):convert_capacity(1,'AC','DC')
        self.assertAlmostEqual(convert_capacity(10,'AC','DC',1.28),12.8)
if __name__=='__main__':unittest.main()
