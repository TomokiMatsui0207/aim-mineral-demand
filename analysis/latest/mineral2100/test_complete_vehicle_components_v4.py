from pathlib import Path as _SnapshotPath
import unittest
import numpy as np
import pandas as pd
from complete_vehicle_components_v4 import ROOT, build_hev, build_fcv, totals, map_native, plated_partition, battery_recipe_coefficients, fcv_stainless_chromium_bounds, split_high_power_battery
import json

class VehicleCompletionTests(unittest.TestCase):

    def test_hev_competing_scopes_not_simultaneously_quantified(self):
        p, removed, cases = build_hev()
        for row in cases.itertuples():
            q = p.loc[p.case.eq(row.case) & p.quantified_kg_per_vehicle.notna()]
            if row.ownership_mode == 'teardown':
                self.assertFalse(q.scope.str.startswith('vehicle.transmission').any())
                self.assertFalse(q.scope.eq('vehicle.powertrain.powertrain_electrical').any())
                self.assertTrue(q.scope.str.startswith('vehicle.power_electronics.').any())
            else:
                self.assertFalse(q.scope.str.startswith('vehicle.traction_motor').any())
                self.assertFalse(q.scope.str.startswith('vehicle.generator').any())
                self.assertFalse(q.scope.str.startswith('vehicle.power_electronics').any())
                self.assertTrue(q.scope.str.startswith('vehicle.transmission').any())

    def test_fcv_unknown_battery_no_added_pack_or_motor(self):
        p, m, b, c = build_fcv()
        self.assertTrue(p.loc[p.scope.eq('vehicle.battery'), 'quantified_kg_per_vehicle'].isna().all())
        self.assertTrue(p.loc[p.scope.eq('vehicle.electric_machines_control'), 'quantified_kg_per_vehicle'].isna().all())
        self.assertFalse(p.scope.str.contains('magnet|traction_motor').any())
        self.assertEqual(len(c), 12)
        inv = totals(p)
        self.assertTrue(inv.loc[inv.mineral.eq('C'), 'known_subtotal_kg_per_vehicle'].isna().all())
        self.assertTrue(inv.loc[inv.mineral.eq('Fe'), 'known_subtotal_kg_per_vehicle'].isna().all())

    def test_pt_mass_nested_not_added_to_other_parent(self):
        p, m, b, c = build_fcv()
        for row in c.itertuples():
            t = p.loc[p.case.eq(row.case) & p.mineral.eq('Pt')].quantified_kg_per_vehicle
            if np.isnan(row.Pt_g_per_stack):
                self.assertTrue(t.isna().all())
            else:
                self.assertAlmostEqual(t.sum(), row.Pt_g_per_stack / 1000)
                parent = m.loc[m.case.eq(row.case) & m.scope.eq('vehicle.powertrain.fuel_cell_stack_BOP') & m.material.eq('Other')].material_kg.iloc[0]
                remaining = b.loc[b.case.eq(row.case) & b.quantity.eq('stack_other_remaining_after_Pt')].mass_kg.iloc[0]
                self.assertAlmostEqual(parent, remaining + t.sum())

    def test_na_retained_at_positive_activity_and_zero_only_for_zero_activity(self):
        inv = pd.DataFrame({'case': ['x', 'x'], 'mineral': ['Cu', 'C'], 'known_subtotal_kg_per_vehicle': [10.0, np.nan]})
        meta = pd.DataFrame({'case': ['x'], 'vehicle_type': ['TP_FCV']})
        activity = pd.DataFrame({'Sc': ['s', 's'], 'year': [2020, 2021], 'vehicle_type': ['TP_FCV'] * 2, 'native_vehicle_additions_year': [0.0, 100.0]})
        a = map_native(activity, inv, meta)
        self.assertTrue(a.loc[a.year.eq(2020)].known_subtotal_t_year.eq(0).all())
        self.assertTrue(a.loc[a.year.eq(2021) & a.mineral.eq('C')].active_unknown_coefficient.all())
        self.assertTrue(a.loc[a.year.eq(2021) & a.mineral.eq('C')].known_subtotal_t_year.isna().all())
        self.assertAlmostEqual(a.loc[a.year.eq(2021) & a.mineral.eq('Cu')].known_subtotal_t_year.iloc[0], 1.0)

    def test_plating_coupled_mass_balance_and_bad_fraction(self):
        for f, g in [([0, 0, 0], 0), ([1, 1, 1], 1), ([0.1, 0.2, 0.3], 0.4)]:
            r = plated_partition([1.55, 0.92, 0.23], 0.23, f, g)
            self.assertAlmostEqual(sum(r.values()), 2.93)
        with self.assertRaises(ValueError):
            plated_partition([1.55], 0.23, [1.1], 0)

    def test_chromium_is_lower_bound_not_point_or_pure_steel_fe(self):
        cfg = json.loads((ROOT / 'input/vehicle_completion_v4/references.json').read_text())
        p, m, b, c = build_fcv()
        cr = fcv_stainless_chromium_bounds(m, cfg)
        self.assertTrue(cr.point_estimate_kg.isna().all())
        self.assertTrue((cr.Cr_minimum_in_selected_material_kg > 0).all())
        self.assertTrue(np.allclose(cr.Cr_minimum_in_selected_material_kg, 0.105 * cr.selected_stainless_material_kg))

    def test_no_implicit_battery_split(self):
        cfg = json.loads((ROOT / 'input/vehicle_completion_v4/references.json').read_text())
        with self.assertRaises(ValueError):
            split_high_power_battery(30, None, cfg)
        with self.assertRaises(ValueError):
            split_high_power_battery(30, 31, cfg)
        out = split_high_power_battery(30, 10, cfg)
        self.assertAlmostEqual(out['Pb'], 6.9)
        self.assertAlmostEqual(out['Cu'], 3.6)

    def test_nmc_stoichiometry_and_no_graphite_assignment(self):
        cfg = json.loads((ROOT / 'input/vehicle_completion_v4/references.json').read_text())
        c = battery_recipe_coefficients(cfg)
        self.assertEqual(c['Cu'], 0.18)
        self.assertNotIn('C', c)
        self.assertAlmostEqual(c['Ni'] / 58.6934, c['Co'] / 58.933194)
        self.assertAlmostEqual(c['Ni'] / 58.6934, c['Mn'] / 54.938044)
        self.assertGreater(c['Li'], 0.19 * 6.94 / (6.94 + (58.6934 + 54.938044 + 58.933194) / 3 + 2 * 15.999))
if __name__ == '__main__':
    unittest.main()
