"""Samples and uploaded registers must survive exploration-to-analysis transfer."""
import unittest
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from assessment_project import sample_project,validate_project,project_signature
from exploration_datasets import (sample_corrosion_workbook,corrosion_project,sample_dent_register,
    dent_project,dent_workbook,read_dent_register)
from profile_data import parse_profile_workbook
from corrosion_assessment_model import deterministic_corrosion,corrosion_reliability,corrosion_specs
from dent_assessment_model import dent_geometry,dent_reliability


class ExplorationDatasetTests(unittest.TestCase):
    def test_corrosion_workbook_has_separate_profiles_and_valid_model_geometry(self):
        content=sample_corrosion_workbook();summary,profiles=parse_profile_workbook(content)
        self.assertEqual(summary['Profile ID'].tolist(),['SYN-COR-001','SYN-COR-002','SYN-COR-003'])
        self.assertEqual(len(profiles),3)
        self.assertTrue((summary['Profile width (mm)']<=summary['Profile length (mm)']).all())
        self.assertTrue(summary['Maximum depth (mm)'].lt(summary['Wall thickness (mm)']).all())
        p=validate_project(corrosion_project(content))
        self.assertEqual(p['summary']['Segment ID'].tolist(),[1,5,9])
        self.assertTrue(deterministic_corrosion(p).Status.eq('Calculated').all())
        a,_,_=corrosion_reliability(p,corrosion_specs(p),100)
        self.assertTrue(a.burst_pf.between(0,1).all())

    def test_dent_csv_and_excel_roundtrip_preserve_booleans_and_signed_radii(self):
        expected=sample_dent_register()
        for content,name in [(expected.to_csv(index=False).encode(),'dents.csv'),
            (dent_workbook(expected),'dents.xlsx')]:
            actual=read_dent_register(content,name)
            pd.testing.assert_frame_equal(actual,expected,check_dtype=False)
            self.assertFalse(actual.associated_crack_or_metal_loss.any())
            self.assertTrue(actual.circumferential_radius_mm.lt(0).all())

    def test_dent_only_dataset_needs_no_placeholder_cracks(self):
        p=validate_project(dent_project(sample_dent_register()))
        self.assertTrue(p['summary'].empty);self.assertEqual(p['profiles'],{})
        self.assertEqual(len(dent_geometry(p)),3)
        a,_,_=dent_reliability(p,samples=100)
        self.assertEqual(a.strain_criterion_probability.tolist(),[0.,0.,1.])
        self.assertIsInstance(project_signature(p),str)

    def test_upload_missing_fields_bad_boolean_and_outside_route_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing dent columns'):
            read_dent_register(b'dent_id,chainage_m\nD1,1\n','bad.csv')
        table=sample_dent_register();table['associated_crack_or_metal_loss']='unknown'
        with self.assertRaisesRegex(ValueError,'true/false'):
            read_dent_register(table.to_csv(index=False).encode(),'bad.csv')
        table=sample_dent_register();table.loc[0,'chainage_m']=11000.
        # Draft may load before its route is adjusted; Save must still reject it.
        with self.assertRaisesRegex(ValueError,'route'):validate_project(dent_project(table))

    def test_dent_upload_reuses_active_pipe_properties_without_changing_them(self):
        base=validate_project(sample_project());base['segments']['wall_thickness_mm']=15.
        p=dent_project(sample_dent_register(),base)
        self.assertTrue((p['segments'].wall_thickness_mm==15).all())
        self.assertEqual(len(base['summary']),3)

    def test_sample_choices_save_without_reverting_on_rerun(self):
        for choice,expected in [('Sample corrosion profiles','Corrosion'),('Sample dent data','Dent')]:
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run().switch_page('data_integration.py').run()
            app.radio[0].set_value(choice).run()
            self.assertEqual(len(app.exception),0)
            next(b for b in app.button if b.label=='Save shared dataset for all analyses').click().run()
            self.assertEqual(len(app.exception),0)
            saved=app.session_state['assessment_project']
            sig=project_signature(saved)
            app.run()
            self.assertEqual(sig,project_signature(app.session_state['assessment_project']))
            if expected=='Dent':
                self.assertTrue(saved['summary'].empty);self.assertEqual(len(saved['dent_register']),3)
            else:self.assertTrue(saved['summary']['Defect type'].eq('Corrosion / metal loss').all())


if __name__=='__main__':unittest.main()
