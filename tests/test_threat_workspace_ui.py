"""Exercise complete new workspaces through Streamlit reruns."""
import unittest
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from assessment_project import sample_project,validate_project


class ThreatWorkspaceUITests(unittest.TestCase):
    def app(self,project,threat):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'preliminary_analysis.py'),default_timeout=60)
        app.session_state['assessment_project']=project
        app.run();app.radio[0].set_value(threat).run()
        return app

    def test_corrosion_calculations_render_without_crack_records(self):
        p=validate_project(sample_project())
        p['summary']['Defect type']='Corrosion / metal loss'
        p['summary']['Maximum depth (mm)']=2.
        p['uncertainties']['distribution']='Deterministic';p['uncertainties']['std']=0.
        app=self.app(p,'Corrosion')
        self.assertTrue(any('DNV-RP-F101-based' in x.value for x in app.markdown))
        app.checkbox(key='corr_applicable').check().run()
        app.checkbox(key='corr_uncertainty_review').check().run()
        app.number_input(key='corr_n').set_value(100).run()
        next(b for b in app.button if b.label=='Run Corrosion Deterministic Analysis').click().run()
        next(b for b in app.button if b.label=='Run Corrosion Reliability Analysis').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertIn('corrosion_rel',app.session_state)
        self.assertTrue(app.session_state['corrosion_rel'][1][0].defect_type.eq('Corrosion').all())

    def test_dent_calculations_render_and_missing_loss_remains_unknown(self):
        p=validate_project(sample_project())
        p['dent_register']=pd.DataFrame([dict(dent_id='D1',chainage_m=1000.,dent_depth_mm=15.,
            axial_length_mm=600.,circumferential_width_mm=300.,circumferential_radius_mm=-1500.,
            axial_radius_mm=2500.,associated_crack_or_metal_loss=False)])
        app=self.app(p,'Dent')
        self.assertTrue(any('not a rupture-pressure model' in x.value for x in app.markdown))
        app.checkbox(key='dent_confirmed').check().run()
        app.number_input(key='dent_n').set_value(100).run()
        next(b for b in app.button if b.label=='Run Dent Reliability Analysis').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertIn('dent_rel',app.session_state)
        assessed=app.session_state['dent_rel'][1][0]
        self.assertIn('strain_criterion_probability',assessed)
        self.assertNotIn('burst_pf',assessed)


if __name__=='__main__':unittest.main()
