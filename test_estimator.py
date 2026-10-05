"""Run with python -m unittest test_estimator (no live credentials needed)."""
import io
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

APP = Path(__file__).resolve().parent / 'app.py'
PRICES = dict(zip(
    ['shingles_price', 'starter_price', 'ridge_cap_price', 'underlayment_price',
     'ice_water_price', 'drip_edge_price', 'step_flashing_price', 'shingle_nails_price',
     'ridge_hip_nails_price', 'wet_patch_price', 'hidden_valley_price', 'w_valley_price',
     'delivery_price', 'sheathing_price', 'cap_staples_price', 'staples_price'],
    [39.50, 79.50, 87.50, 77.50, 77.50, 44.50, .58, 35, 2.50, 12, 74.50, 45.50,
     150, 13, 50, 12],
), misc_roof_penetrations_price=None)
REPORT = '''Premium Report 9/30/2026 123 Main St Report: TEST-1
Total Area (All Pitches) = 2000 sq ft
Predominant Pitch = 6/12
Ridges = 40 ft Hips = 20 ft Valleys = 51 ft
Rakes = 60 ft Eaves/Starter = 100 ft
Drip Edge (Eaves + Rakes) = 160 ft
Flashing = 10 ft Step flashing = 20 ft Total Penetrations = 3'''


class StopApp(BaseException):
    pass


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def run_app(inputs=None, rows=None, failure=None, upload=b'job-one'):
    inputs = inputs or {}
    st = MagicMock()
    st.session_state = State()
    st.secrets = {'SUPABASE_URL': 'https://example.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY': 'test-only-placeholder'}
    st.cache_data.side_effect = lambda **kw: lambda f: f
    st.number_input.side_effect = lambda label, **kw: inputs.get(label, kw['value'])
    st.selectbox.side_effect = lambda label, options, **kw: inputs.get(label, list(options)[0])
    st.text_input.side_effect = lambda label, **kw: kw.get('value', '')
    st.text_area.side_effect = lambda label, value, **kw: value
    st.file_uploader.return_value = io.BytesIO(upload)
    st.columns.return_value = [MagicMock() for _ in range(4)]
    st.stop.side_effect = StopApp
    pdf = ModuleType('pypdf')
    pdf.PdfReader = lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: REPORT)])
    sb = ModuleType('supabase')
    sb.create_client = MagicMock()
    query = sb.create_client.return_value.table.return_value.select.return_value
    query.execute.return_value = SimpleNamespace(data=[PRICES.copy()] if rows is None else rows)
    query.execute.side_effect = failure
    with patch.dict(sys.modules, {'streamlit': st, 'pypdf': pdf, 'supabase': sb}):
        try:
            result = runpy.run_path(str(APP))
        except StopApp:
            result = None
    return result, st, sb


class EstimatorTests(unittest.TestCase):
    def test_existing_takeoff_and_hidden_valley(self):
        result, st, sb = run_app()
        # Hand-calculated takeoff for the report above, including 6% waste.
        expected = (64*39.50 + 79.50 + 2*87.50 + 2*77.50 + 4*77.50
                    + 17*44.50 + 48*.58 + 2*35 + 4*2.50 + 2*12 + 2*74.50 + 150)
        self.assertAlmostEqual(result['material_total'], expected)
        self.assertEqual(result['labor_total'], 20*300 + 160*2)
        self.assertAlmostEqual(result['grand_total'], expected + 6320)
        self.assertEqual(result['misc_roof_penetrations_cost'], 0)
        sb.create_client.assert_called_once_with(st.secrets['SUPABASE_URL'],
                                                st.secrets['SUPABASE_PUBLISHABLE_KEY'])
        sb.create_client.return_value.table.assert_called_once_with('material_presets')

    def test_w_valley_staples_allowance_counted_once_in_export(self):
        baseline, _, _ = run_app()
        result, st, _ = run_app({'Valley material': 'W-Valley', 'Cap staples — quantity': 2,
                                'Regular staples — quantity': 3,
                                'Misc. Roof Penetration Allowance ($)': 123.45})
        delta = 6*45.50 - 2*74.50 + 2*50 + 3*12 + 123.45
        self.assertEqual(result['valley_material_quantity'], 6)
        self.assertAlmostEqual(result['grand_total'] - baseline['grand_total'], delta)
        self.assertEqual(result['material_cost_total'], result['material_total'])
        self.assertIn(f"Grand Total: ${result['grand_total']:,.2f}", result['proposal_html'])
        st.write.assert_any_call('Cap staples: 2 units — $100.00')
        st.write.assert_any_call('Regular staples: 3 units — $36.00')

    def test_zero_valley(self):
        for valley in ['Hidden Valley', 'W-Valley']:
            result, _, _ = run_app({'Valley LF': 0, 'Valley material': valley})
            self.assertEqual(result['valley_material_cost'], 0)

    def test_hidden_valley_rounding_and_breakdown(self):
        for feet, rolls in [(0, 0), (1, 1), (50, 1), (50.01, 2), (51, 2), (100, 2), (101, 3)]:
            with self.subTest(feet=feet):
                result, st, _ = run_app({'Valley LF': feet})
                self.assertEqual(result['valley_material_quantity'], rolls)
                self.assertEqual(result['valley_material_cost'], rolls * 74.50)
                st.write.assert_any_call(f'Hidden Valley: {rolls} rolls — ${rolls * 74.50:,.2f}')

    def test_hidden_valley_editable_price_and_default(self):
        baseline, _, _ = run_app()
        result, st, _ = run_app({'Hidden Valley flashing / 50 LF roll': 80.0})
        self.assertEqual(result['valley_material_cost'], 160.0)
        self.assertAlmostEqual(result['material_total'] - baseline['material_total'], 11.0)
        self.assertAlmostEqual(result['grand_total'] - baseline['grand_total'], 11.0)
        st.write.assert_any_call('Hidden Valley: 2 rolls — $160.00')
        for price in [None, 999]:
            result, _, _ = run_app(rows=[dict(PRICES, hidden_valley_price=price)])
            self.assertEqual(result['valley_material_cost'], 149.0)
        result, _, _ = run_app({'Valley material': 'W-Valley',
                                'Hidden Valley flashing / 50 LF roll': 80.0})
        self.assertEqual(result['valley_material_quantity'], 6)
        self.assertEqual(result['valley_material_cost'], 6 * 45.50)

    def test_selected_preset_and_sheathing_override(self):
        second = {key: value*2 if value is not None else None for key, value in PRICES.items()}
        baseline, _, _ = run_app()
        result, _, _ = run_app({'Material preset': 1}, rows=[PRICES, second])
        self.assertAlmostEqual(result['material_total'], baseline['material_total']*2 - 149.0)
        self.assertEqual(result['labor_total'], baseline['labor_total'])
        result, _, _ = run_app({"4'x8' sheathing sheets": 3, "4'x8' sheathing / sheet": 20,
                                "4'x8' roof sheathing replacement labor / sheet": 15})
        self.assertEqual(result['sheathing_cost'], 60)
        self.assertAlmostEqual(result['grand_total'] - baseline['grand_total'], 105)

    def test_missing_invalid_prices_and_connection_errors_stop_estimate(self):
        for value in [None, -1, 'bad', float('nan'), float('inf')]:
            result, st, _ = run_app(rows=[dict(PRICES, shingles_price=value)])
            self.assertIsNone(result)
            self.assertIn('shingles_price', str(st.error.call_args))
        result, st, _ = run_app(rows=[])
        self.assertIsNone(result)
        result, st, _ = run_app(failure=RuntimeError('sensitive-exception-details'))
        self.assertIsNone(result)
        self.assertNotIn('sensitive-exception-details', str(st.error.call_args))

    def test_allowance_is_independent_of_database_and_new_report(self):
        result, st, _ = run_app(rows=[dict(PRICES, misc_roof_penetrations_price=999)])
        self.assertEqual(result['misc_roof_penetrations_cost'], 0)
        _, other_st, _ = run_app(upload=b'job-two')
        def allowance_key(mock):
            return next(call.kwargs['key'] for call in mock.number_input.call_args_list
                        if call.args[0] == 'Misc. Roof Penetration Allowance ($)')
        self.assertNotEqual(allowance_key(st), allowance_key(other_st))


if __name__ == '__main__':
    unittest.main()

