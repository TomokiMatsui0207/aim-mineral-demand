from pathlib import Path as _SnapshotPath
import unittest
import numpy as np
import pandas as pd
from extend_road_vehicles import annualize, classify, bus_inventory, ROOT, EXPECTED

class RoadTests(unittest.TestCase):

    def fixtures(self):
        d = pd.DataFrame([{'Sc': 's', 'region': 'JPN', 'sector': 'PSR', 'technology': 'TPPCOG_BEV', 'year': 2030, 'stock_native': 10.0, 'new_rate_native': 2.0, 'replacement_rate_native': 1.0, 'activity_native': 4.0, 'model_time_interval': 5.0, 'lifetime_tn_years': 12.0, 'stock_inflow_over_interval_native': 15.0}])
        o = pd.DataFrame([dict(Sc='s', region='JPN', sector='PSR', technology='TPPCOG_BEV', year=2030, service=j, raw_output_coefficient=10.0, output_change_phi=0.1, effective_output_per_activity=11.0) for j in ['TPPG', 'TPPD']])
        scales = pd.DataFrame([{'vehicle_class': c, 'vehicles_per_native_unit': 100.0, 'status': 'synthetic_test_only'} for c in EXPECTED])
        return (d, o, scales)

    def test_classification_no_bus_in_ldv_or_double_zev(self):
        self.assertEqual(classify('TPBSOI_HEV'), ('BUS', 'HEV'))
        self.assertEqual(classify('TFTSOI_NGV'), ('TRUCK_SMALL', 'ICE'))
        self.assertEqual(classify('TFTLOI_FCV'), ('TRUCK_LARGE', 'FCV'))
        with self.assertRaises(ValueError):
            classify('TFRLEL_BEV')

    def test_multiple_service_outputs_do_not_double_vehicle_additions(self):
        d, o, s = self.fixtures()
        a = annualize(d, o, s, 2026, 2030)
        self.assertEqual(len(a), 5)
        self.assertAlmostEqual(a.new_vehicles_year.sum(), 1500)

    def test_missing_scale_is_not_zero_or_default_million(self):
        d, o, s = self.fixtures()
        s.loc[s.vehicle_class.eq('LDV'), 'vehicles_per_native_unit'] = np.nan
        a = annualize(d, o, s, 2026, 2030)
        self.assertTrue(a.new_vehicles_year.isna().all())
        self.assertTrue(a.annual_additions_native.eq(3).all())

    def test_overlapping_periods_rejected(self):
        d, o, s = self.fixtures()
        d2 = d.copy()
        d2['year'] = 2029
        o2 = o.copy()
        o2['year'] = 2029
        with self.assertRaises(ValueError):
            annualize(pd.concat([d, d2]), pd.concat([o, o2]), s, 2026, 2030)

    def test_missing_output_and_incomplete_time_rejected(self):
        d, o, s = self.fixtures()
        with self.assertRaises(ValueError):
            annualize(d, o.iloc[:0], s, 2026, 2030)
        with self.assertRaises(ValueError):
            annualize(d, o, s, 2025, 2030)

    def test_bus_materials_not_pure_copper_or_neodymium(self):
        mat = pd.read_csv(ROOT / 'input/road_vehicle_extension/bus_BEV_selected_materials.csv')
        p, q = bus_inventory(mat)
        q = q.set_index('mineral')
        self.assertAlmostEqual(q.loc['Cu', 'known_kg_per_vehicle'], 24.583)
        self.assertTrue(np.isnan(q.loc['Nd', 'known_kg_per_vehicle']))
        self.assertTrue(np.isnan(q.loc['Li', 'known_kg_per_vehicle']))
        self.assertFalse(q.traction_battery_included.any())

    def test_no_source_component_twice(self):
        mat = pd.read_csv(ROOT / 'input/road_vehicle_extension/bus_BEV_selected_materials.csv')
        with self.assertRaises(ValueError):
            bus_inventory(pd.concat([mat, mat.iloc[:1]]))
if __name__ == '__main__':
    unittest.main()
