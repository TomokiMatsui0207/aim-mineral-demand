"""Public-only checks: no private inventory fixtures or model outputs required."""
from pathlib import Path
import ast,importlib.util,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('latest_runner',ROOT/'scripts/run_latest.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class LatestSnapshotTests(unittest.TestCase):
    def test_missing_input_is_reported_without_running_model(self):
        with tempfile.TemporaryDirectory() as directory:
            _,missing,ambiguous=runner.check_inputs({'required':['data.csv']},Path(directory))
            self.assertEqual(missing,['data.csv']);self.assertEqual(ambiguous,[])
    def test_ambiguous_workbook_is_not_chosen_arbitrarily(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['a.xlsx','b.xlsx']:(root/name).touch()
            found,missing,ambiguous=runner.check_inputs({'required':['*.xlsx']},root)
            self.assertEqual(found,{});self.assertEqual(missing,[]);self.assertEqual(ambiguous,['*.xlsx'])
    def test_all_stage_entrypoints_are_shipped(self):
        import json
        config=json.loads((ROOT/'config/latest_stages.json').read_text())
        for stage,spec in config['stages'].items():
            with self.subTest(stage=stage):self.assertTrue((ROOT/'analysis/latest'/spec['entry']).is_file())
    def test_no_execution_machine_absolute_paths(self):
        for path in (ROOT/'analysis/latest').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Constant) and isinstance(node.value,str):
                    self.assertFalse(node.value.startswith('/workspace/'),str(path))
if __name__=='__main__':unittest.main()
