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
# The newer GitHub version retained by this reconciliation.
REMOTE_BASE = 'f53051af8ec9f97fac9968704d440e41ed2594f0'
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
    def test_hidden_valley_rounding_and_breakdown(self):
        for feet, cost in [(0, 0), (1, 74.50), (50, 74.50), (50.01, 149),
                           (51, 149), (100, 149), (101, 223.50)]:
            with self.subTest(feet=feet):
                result, st = run_app({'Valley LF': feet})
                self.assertEqual(result['valley_cost'], cost)
                st.write.assert_any_call(f'Hidden Valley: {feet:.0f} LF - ${cost:,.2f}')

    def test_hidden_valley_default_and_totals(self):
        result, st = run_app()
        other_materials = (64*39.50 + 79.50 + 2*87.50 + 2*77.50 + 4*77.50
                           + 17*12 + 48*.58 + 2*35 + 4*2.50 + 2*12)
        self.assertAlmostEqual(result['material_total'], other_materials + 149 + 150)
        # Preserve the current version's delivery handling in the proposal.
        self.assertAlmostEqual(result['material_cost_total'], other_materials + 149)
        self.assertEqual(result['labor_total'], 20*325 + 40*4 + 20*4 + 51*5 + 160*2 + 10*5 + 20*5)
        self.assertAlmostEqual(result['grand_total'], result['labor_total'] + other_materials + 149)
        self.assertIn(f"Materials: ${result['material_cost_total']:,.2f}", result['proposal_html'])
        self.assertIn(f"Grand Total: ${result['grand_total']:,.2f}", result['proposal_html'])
        price_input = next(call for call in st.number_input.call_args_list
                           if call.args[0] == 'Hidden Valley flashing / 50 LF roll')
        self.assertEqual(price_input.kwargs['value'], 74.50)
        self.assertEqual(price_input.kwargs['min_value'], 0.0)

    def test_hidden_valley_edited_price_reaches_all_totals(self):
        baseline, _ = run_app()
        for price in [0.0, 80.0, 99.99]:
            with self.subTest(price=price):
                result, st = run_app({'Hidden Valley flashing / 50 LF roll': price})
                self.assertEqual(result['valley_cost'], 2*price)
                for total in ['material_total', 'material_cost_total', 'grand_total']:
                    self.assertAlmostEqual(result[total] - baseline[total], 2*price - 149)
                self.assertEqual(result['labor_total'], baseline['labor_total'])
                st.write.assert_any_call(f'Hidden Valley: 51 LF - ${2*price:,.2f}')

    def test_w_valley_rounding_and_price_unchanged(self):
        for feet, cost in [(0, 0), (1, 30), (10, 30), (11, 60), (51, 180)]:
            with self.subTest(feet=feet):
                result, st = run_app({'Valley LF': feet, 'Valley material': 'W-Valley',
                                      'Hidden Valley flashing / 50 LF roll': 999.0})
                self.assertEqual(result['valley_cost'], cost)
                st.write.assert_any_call(f'W-Valley: {feet:.0f} LF - ${cost:,.2f}')

    def test_newer_github_calculations_preserved(self):
        source = subprocess.check_output(['git', 'show', f'{REMOTE_BASE}:app.py'], cwd=APP.parent).decode('utf-8')
        for valley in ['Hidden Valley', 'W-Valley']:
            with self.subTest(valley=valley):
                inputs = {'Valley material': valley}
                previous, _ = run_app(inputs, source=source)
                current, _ = run_app(inputs)
                # Compare every numeric calculation from GitHub, allowing only
                # the requested Hidden Valley addition to customer totals.
                for name, value in previous.items():
                    if isinstance(value, (int, float)):
                        delta = 149 if valley == 'Hidden Valley' and name in ['material_cost_total', 'grand_total'] else 0
                        self.assertAlmostEqual(current[name], value + delta, msg=name)
                self.assertEqual(current['lines'], previous['lines'])
                self.assertEqual(current['d'], previous['d'])
                if valley == 'W-Valley':
                    self.assertEqual(current['proposal_html'], previous['proposal_html'])


if __name__ == '__main__':
    unittest.main()
