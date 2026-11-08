import unittest
import numpy as np
from education.pof_model import POFInputs,corlas_failure_pressure
from marshall_validation_model import load_marshall,compare_marshall

class MarshallReferenceTests(unittest.TestCase):
    def test_exact_source_transcription_and_unique_ids(self):
        x=load_marshall()
        self.assertEqual(x.source_row.tolist(),list(range(1,17)))
        self.assertEqual(x.ntsb_failure_pressure_psi.tolist(),[649,572,512,424,525,437,372,287,672,575,536,428,622,525,481,372])
        self.assertTrue(x.scenario_id.is_unique)
        self.assertEqual(x.published_run_label.tolist()[-3:],[12,12,12])
        self.assertEqual(x.effective_depth_in.iloc[7],.178)
        self.assertIn('0.055',x.source_notes.iloc[7])

    def test_all_published_pressures_within_one_psi(self):
        x=compare_marshall()
        self.assertLess(x.difference_psi.abs().max(),1)
        self.assertLess(x.difference_percent.abs().max(),.18)
        self.assertTrue(x.comparison_status.eq('Within selected tolerance').all())
        self.assertTrue(x.below_1_25_mop_alirim.equals(x.below_1_25_mop_ntsb))
        np.testing.assert_allclose(x.alirim_rectangular_psi,
            [649.360683493,571.889078666,511.498839025,423.265192061,
             524.952701863,436.350679166,371.401408120,286.563940461,
             672.086923293,575.491588793,536.472200332,428.124922984,
             622.026232536,524.723445626,480.940103868,371.817103845],atol=.001,rtol=0)

    def test_geometry_difference_visible_not_calibrated_away(self):
        x=compare_marshall()
        self.assertGreater(x.elliptical_difference_percent.abs().max(),40)
        self.assertGreater(x.alirim_elliptical_psi.iloc[0],x.alirim_rectangular_psi.iloc[0])
        strict=compare_marshall(tolerance_percent=.01)
        self.assertTrue(strict.comparison_status.eq('Outside selected tolerance').any())
        changed=compare_marshall(elastic_modulus_psi=210*145038.)
        self.assertTrue(changed.ntsb_failure_pressure_psi.equals(x.ntsb_failure_pressure_psi))
        self.assertFalse(changed.alirim_rectangular_psi.equals(x.alirim_rectangular_psi))

    def test_invalid_assumptions_blocked(self):
        for kwargs in [{'yield_strength_psi':66000},{'tolerance_percent':0},{'elastic_modulus_psi':float('nan')}]:
            with self.assertRaises(ValueError):compare_marshall(**kwargs)
        with self.assertRaises(ValueError):corlas_failure_pressure(POFInputs(),flaw_shape='Unknown')
        with self.assertRaises(ValueError):corlas_failure_pressure(POFInputs(),flow_stress_psi=-1)

    def test_current_elliptical_defaults_are_preserved(self):
        p=POFInputs()
        self.assertEqual(corlas_failure_pressure(p),corlas_failure_pressure(p,flaw_shape='Elliptical'))
        rect=corlas_failure_pressure(p,flaw_shape='Rectangular')
        self.assertLess(rect['failure_pressure_psi'],corlas_failure_pressure(p)['failure_pressure_psi'])

    def test_page_renders_details_and_sensitivity(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'validation_examples.py'),default_timeout=60).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.metric[0].value,'16 / 16')
        app.checkbox(key='marshall_show_ellipse').check().run()
        app.selectbox(key='marshall_selected').set_value('M2005-08').run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('0.055' in x.value for x in app.warning))
        app.number_input(key='marshall_tolerance').set_value(.01).run()
        self.assertNotEqual(app.metric[0].value,'16 / 16')
        self.assertEqual(len(app.exception),0)

if __name__=='__main__':unittest.main()
