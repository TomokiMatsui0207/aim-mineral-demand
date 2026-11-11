from pathlib import Path as _SnapshotPath
import unittest
import numpy as np
import pandas as pd
from pathlib import Path
from optimise import load, build_problem, constraints, MINERALS, BASECASE
O = Path(__file__).resolve().parent

class Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.inputs = load()
        cls.p = build_problem('300C', cls.inputs)

    def test_only_future_years_and_complete_calendar(self):
        self.assertEqual(min((g['start'] for g in self.p.groups)), 2026)
        self.assertEqual(max((g['end'] for g in self.p.groups)), 2100)
        a = self.p.reconstruct(np.array([r['reference_share'] for r in self.p.records]))
        self.assertEqual(set(a.year), set(range(2026, 2101)))

    def test_variable_replacement_current_components_reconstruct_exactly(self):
        totals = self.p.fixed.copy()
        for g in self.p.groups:
            totals += g['current'].sum(axis=0)
        np.testing.assert_allclose(totals, self.p.before, rtol=1e-12, atol=0.0001)

    def test_candidate_vectors_never_contain_negative_or_missing_mass(self):
        for g in self.p.groups:
            self.assertTrue(np.isfinite(g['options']).all())
            self.assertTrue((g['options'] >= 0).all())
            self.assertAlmostEqual(sum(g['p']), 1)

    def test_grid_electrical_equivalent_is_conserved(self):
        i = MINERALS.index('Cu')
        j = MINERALS.index('Al')
        for g in self.p.groups:
            if g['name'] != 'grid_CuAl':
                continue
            old = g['current'][:, i] + 2 * g['current'][:, j]
            for v in g['options']:
                np.testing.assert_allclose(v[:, i] + 2 * v[:, j], old)

    def test_seven_conditional_references_never_become_constraints(self):
        refs, *_ = constraints(self.p, self.inputs[-1])
        self.assertEqual(len(refs), 33)
        self.assertFalse(set(refs.mineral) & {'C', 'Ge', 'Hf', 'Mg', 'Sc', 'Ta', 'Si'})

    def test_sodium_cap_is_calendar_based_and_only_before2035(self):
        for g in self.p.groups:
            if g['name'] == 'LDV_battery':
                self.assertEqual(g['na_cap'] is not None, g['end'] < 2035)

    def test_reference_chemical_mix_equals_its_own_current_component(self):
        for g in self.p.groups:
            if g['name'].startswith(('LDV_battery', 'TRUCK_', 'BUS_')):
                np.testing.assert_allclose(np.einsum('i,iyk->yk', g['p'], g['options']), g['current'], atol=1e-06)

    def test_after_solve_all_sums_constraints_and_shortage_flag(self):
        ratios = pd.read_csv(O / 'reserve_pressure_40_NOT_shortage_verdict.csv')
        shares = pd.read_csv(O / 'technology_shares_before_after.csv')
        np.testing.assert_allclose(shares.groupby(['Sc', 'policy', 'group', 'start', 'end']).optimized_share.sum(), 1, atol=1e-06)
        self.assertFalse(ratios.shortage_verdict_ready.any())
        solver = pd.read_csv(O / 'solver_summary.csv')
        self.assertTrue((solver.realized_normalized_excess <= solver.reference_normalized_excess + 1e-06).all())

    def test_no_additional_sodium_case_really_blocks_extra_option(self):
        s = pd.read_csv(O / 'technology_shares_before_after.csv')
        n = s[s.policy.eq('no_additional_Na') & s.group.eq('LDV_battery') & s.candidate.eq('Na-ion')]
        self.assertTrue((n.optimized_share.abs() < 1e-07).all())

    def test_no_recalibration_of_fixed_other_or_historical_totals(self):
        a = pd.read_csv(O / 'all_sectors_with_substitution_CONDITIONAL.csv.gz')
        for (sol, policy), g in a.groupby(['solution', 'policy']):
            np.testing.assert_allclose(g.loc[g.year.lt(2026), 'technology_substitution_delta_t_year'], 0)
            np.testing.assert_allclose(g.other_low_t_year + g.selected_explicit_sum_t_year, g.conditional_total_low_t_year)
            np.testing.assert_allclose(g.alternative_total_low_t_year, g.conditional_total_low_t_year + g.technology_substitution_delta_t_year)
            cols = ['alternative_power_t_year', 'alternative_grid_t_year', 'alternative_vehicles_t_year', 'alternative_hydrogen_t_year', 'alternative_stationary_battery_t_year', 'alternative_other_t_year']
            np.testing.assert_allclose(g[cols].sum(axis=1), g.alternative_total_low_t_year)
if __name__ == '__main__':
    unittest.main()
