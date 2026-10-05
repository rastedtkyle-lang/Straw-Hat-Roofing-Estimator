"""Run with python -m unittest test_estimator (no live credentials needed)."""
import io
from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

APP = Path(__file__).resolve().parent / 'app.py'
REPORT = '''Premium Report 9/30/2026 123 Main St Report: TEST-1
Total Area (All Pitches) = 2000 sq ft
Predominant Pitch = 6/12
Ridges = 40 ft Hips = 20 ft Valleys = 51 ft
Rakes = 60 ft Eaves/Starter = 100 ft
Drip Edge (Eaves + Rakes) = 160 ft
Flashing = 10 ft Step flashing = 20 ft Total Penetrations = 3'''


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def run_app(inputs=None, source=None):
    inputs = inputs or {}
    st = MagicMock()
    st.session_state = State()
    st.number_input.side_effect = lambda label, **kw: inputs.get(label, kw['value'])
    st.selectbox.side_effect = lambda label, options, **kw: inputs.get(label, list(options)[0])
    st.text_input.side_effect = lambda label, **kw: kw.get('value', '')
    st.text_area.side_effect = lambda label, value, **kw: value
    st.file_uploader.return_value = io.BytesIO(b'job-one')
    def columns(count):
        result = [MagicMock() for _ in range(count)]
        for column in result:
            column.number_input.side_effect = st.number_input.side_effect
        return result
    st.columns.side_effect = columns
    pdf = ModuleType('pypdf')
    pdf.PdfReader = lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: REPORT)])
    with patch.dict(sys.modules, {'streamlit': st, 'pypdf': pdf}):
        if source is None:
            result = runpy.run_path(str(APP))
        else:
            result = {}
            exec(compile(source, 'remote_app.py', 'exec'), result)
    return result, st


class EstimatorTests(unittest.TestCase):
    def test_default_subtotal_tax_and_export(self):
        result, st = run_app()
        subtotal = (64*39.50 + 79.50 + 2*87.50 + 2*77.50 + 4*77.50
                    + 17*12 + 48*.58 + 2*35 + 4*2.50 + 2*12 + 149 + 150)
        self.assertAlmostEqual(result['material_subtotal'], subtotal)
        self.assertEqual(result['material_sales_tax'], 305.73)
        self.assertEqual(result['material_total'], 4188.07)
        self.assertEqual(result['material_cost_total'], 4188.07)
        self.assertEqual(result['grand_total'], result['labor_total'] + 4188.07)
        st.write.assert_any_call('Material Subtotal: $3,882.34')
        st.write.assert_any_call('Material Sales Tax (7.875%): $305.73')
        for text in ['Material Subtotal: $3,882.34', 'Material Sales Tax (7.875%): $305.73',
                     'Total Material Cost (including tax): $4,188.07']:
            self.assertIn(text, result['proposal_html'])

    def test_hidden_valley_boundaries(self):
        for feet, count in [(0, 0), (1, 1), (50, 1), (50.01, 2), (51, 2), (100, 2), (101, 3)]:
            with self.subTest(feet=feet):
                result, st = run_app({'Valley LF': feet})
                self.assertEqual(result['valley_quantity'], count)
                self.assertEqual(result['valley_cost'], count*74.50)
                st.write.assert_any_call(f'Hidden Valley: {feet:.0f} LF - ${count*74.50:,.2f}')

    def test_w_valley_overlap_boundaries(self):
        for feet, count in [(0, 0), (1, 1), (10, 1), (10.01, 2), (19.5, 2),
                            (19.51, 3), (29, 3), (29.01, 4), (50, 6)]:
            with self.subTest(feet=feet):
                result, _ = run_app({'Valley LF': feet, 'Valley material': 'W-Valley',
                                     'Hidden Valley flashing / 50 LF roll': 999})
                self.assertEqual(result['valley_quantity'], count)
                self.assertEqual(result['valley_cost'], count*44.50)

    def test_every_editable_price_and_no_duplicate_inputs(self):
        baseline, st = run_app({'Cap staples quantity': 2, 'Regular staples quantity': 3,
                                 'Material sales tax (%)': 0.0})
        cases = [
            ('Shingles / bundle', 39.50, 64, 'shingle_cost'),
            ('Hip & Ridge / bundle', 87.50, 2, 'ridge_cap_cost'),
            ('Starter / 100-LF bundle', 79.50, 1, 'starter_cost'),
            ('Eave Guard / Ice & Water / 65-LF roll', 77.50, 4, 'ice_water_cost'),
            ('Synthetic underlayment / 10-square roll', 77.50, 2, 'underlayment_cost'),
            ('Hidden Valley flashing / 50 LF roll', 74.50, 2, 'valley_cost'),
            ('1-1/4" shingle nails / box', 35, 2, 'shingle_nail_cost'),
            ('Cap staples / unit', 50, 2, 'cap_staples_cost'),
            ('Regular staples / unit', 12, 3, 'staples_cost'),
            ('Henry Wet Patch / tube', 12, 2, 'henry_cost'),
            ('Delivery / job', 150, 1, 'delivery_cost'),
        ]
        for label, default, count, variable in cases:
            with self.subTest(label=label):
                calls = [call for call in st.number_input.call_args_list if call.args[0] == label]
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].kwargs['value'], default)
                result, _ = run_app({label: default+10, 'Cap staples quantity': 2,
                                     'Regular staples quantity': 3, 'Material sales tax (%)': 0.0})
                self.assertEqual(result[variable], count*(default+10))
                self.assertAlmostEqual(result['material_total']-baseline['material_total'], count*10)
                self.assertAlmostEqual(result['grand_total']-baseline['grand_total'], count*10)
        result, _ = run_app({'Valley material': 'W-Valley', 'W-Valley / 10-ft piece': 60})
        self.assertEqual(result['valley_cost'], 360)
        self.assertEqual(baseline['cap_staples_cost'], 100)
        self.assertEqual(baseline['staples_cost'], 36)

    def test_coverage_and_existing_quantity_rules(self):
        for feet, rolls in [(0, 0), (65, 1), (65.01, 2), (130, 2), (130.01, 3)]:
            result, _ = run_app({'Eave/Starter LF': feet, 'Valley LF': 0})
            self.assertEqual(result['ice_water_rolls'], rolls)
        result, _ = run_app({'Eave/Starter LF': 0, 'Valley LF': 32.5})
        self.assertEqual(result['ice_water_rolls'], 1)
        for squares, nails, henry, synthetic in [(0, 0, 0, 0), (10, 1, 1, 1),
                                                (15, 1, 2, 2), (15.01, 2, 2, 2), (30, 2, 3, 3)]:
            result, _ = run_app({'Squares': squares})
            self.assertEqual(result['shingle_nail_boxes'], nails)
            self.assertEqual(result['henry_tubes'], henry)
            self.assertEqual(result['underlayment_rolls'], synthetic)

    def test_tax_overrides_and_zero_prices(self):
        for valley in ['Hidden Valley', 'W-Valley']:
            for rate in [0.0, 5.0, 7.875]:
                result, _ = run_app({'Valley material': valley, 'Material sales tax (%)': rate})
                expected_tax = round(result['material_subtotal']*rate/100, 2)
                self.assertEqual(result['material_sales_tax'], expected_tax)
                self.assertEqual(result['material_cost_total'], round(result['material_subtotal']+expected_tax, 2))
                self.assertEqual(result['grand_total'], result['labor_total']+result['material_cost_total'])
        baseline, _ = run_app()
        inputs = {label: 0.0 for _, label, _ in baseline['MATERIAL_PRICES']}
        inputs.update({label: 0.0 for _, label in baseline['fields']})
        result, _ = run_app(inputs)
        self.assertEqual(result['material_subtotal'], 0)
        self.assertEqual(result['material_sales_tax'], 0)
        self.assertEqual(result['material_total'], 0)

    def test_labor_and_unrelated_features_preserved(self):
        source = subprocess.check_output(['git', 'show', '81a40f7:app.py'], cwd=APP.parent).decode('utf-8')
        previous, _ = run_app(source=source)
        current, _ = run_app()
        for key in ['lines', 'labor_total', 'd', 'scope', 'shingle_bundles', 'starter_bundles',
                    'ridge_cap_bundles', 'underlayment_rolls', 'drip_edge_cost', 'step_flashing_cost',
                    'ridge_nail_cost', 'henry_tubes', 'shingle_nail_boxes']:
            self.assertEqual(current[key], previous[key], key)


if __name__ == '__main__':
    unittest.main()
