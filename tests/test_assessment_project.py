"""Shared asset data must stay consistent across assessment workflows."""
import unittest
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
from assessment_project import (sample_project,validate_project,deterministic_project,
    reliability_project,assessment_geometry,project_signature,default_uncertainties)
from profile_data import synthetic_sample_workbook,parse_profile_workbook
from profile_map import route_length_km


class SharedProjectTests(unittest.TestCase):
    def setUp(self):
        self.project=validate_project(sample_project())

    def deterministic_uncertainties(self,p):
        p['uncertainties']['distribution']='Deterministic'
        p['uncertainties']['std']=0.

    def test_ten_km_same_profiles_in_three_separate_segments(self):
        p=self.project
        self.assertAlmostEqual(route_length_km(p['route']),10.)
        self.assertEqual(len(p['segments']),10)
        self.assertEqual(p['summary']['Segment ID'].tolist(),[1,5,9])
        self.assertEqual(p['summary']['Feature location (m)'].tolist(),[500.,4500.,8500.])
        _,original=parse_profile_workbook(synthetic_sample_workbook())
        for name,grid in p['profiles'].items():
            pd.testing.assert_frame_equal(grid,original[name])

    def test_default_fpr_is_preserved(self):
        result=deterministic_project(self.project)
        self.assertAlmostEqual(result.FPR.iloc[2],1.0790279248728556)
        self.assertEqual(result['Segment ID'].tolist(),[1,5,9])
        self.assertTrue(result.Severe.iloc[2])

    def test_sample_uses_one_pipe_geometry_over_whole_route(self):
        p=self.project
        self.assertEqual(p['segments'].wall_thickness_mm.unique().tolist(),[11.8])
        self.assertEqual(p['segments'].diameter_in.unique().tolist(),[36.])
        self.assertTrue((p['summary']['Wall thickness (mm)']==11.8).all())
        self.assertTrue((p['summary']['Outside diameter (mm)']==914.4).all())
        result=deterministic_project(p)
        self.assertTrue((result['Wall thickness (mm)']==11.8).all())
        self.assertTrue((result['Outside diameter (mm)']==914.4).all())

    def test_segment_pressure_only_changes_its_own_fpr(self):
        before=deterministic_project(self.project)
        self.project['segments'].loc[self.project['segments'].section_id==5,'operating_pressure_psi']*=2
        after=deterministic_project(self.project)
        np.testing.assert_allclose(after.FPR,before.FPR*[1.,.5,1.])

    def test_measured_depth_is_not_rescaled_by_new_assessment_wall(self):
        p=self.project
        original=p['profiles']['SYN-001'].copy()
        depth=p['summary']['Maximum depth (mm)'].iloc[0]
        p['segments'].loc[0,'wall_thickness_mm']*=1.2
        summary,profiles=assessment_geometry(p)
        maximum=profiles['SYN-001']['Depth (%WT)'].max()/100*summary['Wall thickness (mm)'].iloc[0]
        self.assertAlmostEqual(maximum,depth)
        result=deterministic_project(p)
        self.assertAlmostEqual(result['Defect depth (mm)'].iloc[0],depth)
        pd.testing.assert_frame_equal(original,p['profiles']['SYN-001'])

    def test_arbitrary_segment_lengths_and_ids(self):
        p=self.project
        table=p['segments'].iloc[:3].copy()
        table['section_id']=[10,20,30]
        table['start_km']=[0.,2.,7.]
        table['end_km']=[2.,7.,10.]
        p['segments']=table
        p['uncertainties']=default_uncertainties(table)
        p=validate_project(p)
        self.assertEqual(p['summary']['Segment ID'].tolist(),[10,20,30])
        a,_,s=reliability_project(p,100)
        self.assertEqual(a.section_id.tolist(),[10,20,30])
        self.assertEqual(s.feature_count.tolist(),[1,1,1])

    def test_endpoint_and_boundary_assignment(self):
        p=self.project
        p['summary']['Feature location (m)']=[0.,1000.,10000.]
        result=validate_project(p)
        self.assertEqual(result['summary']['Segment ID'].tolist(),[1,2,10])

    def test_reject_gap_overlap_duplicate_id_and_outside_route(self):
        for field,value in [('start_km',.1),('end_km',1.1),('section_id',2)]:
            p=deepcopy(self.project)
            p['segments'].loc[0,field]=value
            with self.assertRaises(ValueError): validate_project(p)
        p=deepcopy(self.project)
        p['summary'].loc[0,'Feature location (m)']=10001.
        with self.assertRaises(ValueError): validate_project(p)

    def test_uncertainty_complete_per_segment(self):
        p=self.project
        p['uncertainties']=p['uncertainties'].iloc[:-1]
        with self.assertRaisesRegex(ValueError,'uncertainty row'): validate_project(p)

    def test_segment_specs_reach_reliability_engine(self):
        p=self.project
        self.deterministic_uncertainties(p)
        p['segments'].loc[:,'model_factor']=100.
        p['segments'].loc[p['segments'].section_id==5,'model_factor']=.001
        a,_,s=reliability_project(p,100)
        self.assertEqual(a.burst_pf.tolist(),[0.,1.,0.])
        self.assertEqual(s.loc[s.section_id==5,'burst_pf'].iloc[0],1.)

    def test_same_joint_features_are_not_new_joints(self):
        p=self.project
        p['summary'].loc[:1,'Feature location (m)']=[501.,502.]
        self.deterministic_uncertainties(p)
        a,j,_=reliability_project(p,100)
        self.assertEqual(a.joint_number.iloc[0],a.joint_number.iloc[1])
        self.assertEqual(len(j),2)

    def test_missing_consequences_are_unknown_not_zero(self):
        p=self.project
        p['segments']['burst_consequence']=np.nan
        _,_,s=reliability_project(p,100)
        self.assertTrue(s.total_risk.isna().all())
        self.assertTrue(s.burst_pf.notna().all())

    def test_corrosion_not_evaluated_with_crack_model(self):
        p=self.project
        p['summary'].loc[0,'Defect type']='Corrosion / metal loss'
        result=deterministic_project(p)
        self.assertTrue(pd.isna(result.FPR.iloc[0]))
        with self.assertRaisesRegex(ValueError,'corrosion-specific'): reliability_project(p,100)

    def test_signature_detects_uncertainty_and_profile_changes(self):
        p=self.project
        before=project_signature(p)
        p['uncertainties'].loc[0,'std']=1.
        self.assertNotEqual(before,project_signature(p))
        before=project_signature(p)
        p['profiles']['SYN-001'].loc[0,'Depth (%WT)']=1.
        self.assertNotEqual(before,project_signature(p))

    def test_heatmap_minimum_matches_shared_defect_fpr(self):
        from assessment_project import segment_inputs
        from corlas_profile_map import evaluate_profile_grid,minimum_grid_result
        p=self.project
        p['segments'].loc[8,'wall_thickness_mm']*=1.1
        summary,profiles=assessment_geometry(p)
        row=summary.iloc[2]
        cells=evaluate_profile_grid(profiles['SYN-003'],segment_inputs(p,9),
            row['Wall thickness (mm)'],row['Outside diameter (mm)'],row['Profile length (mm)'])
        expected=deterministic_project(p).FPR.iloc[2]
        self.assertAlmostEqual(minimum_grid_result(cells)['FPR'],expected)

    def test_navigation_retains_saved_joint_length_and_dataset(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        app.switch_page('data_integration.py').run()
        next(n for n in app.number_input if n.label=='Nominal pipe-joint length (m)').set_value(24.).run()
        next(b for b in app.button if b.label=='Save shared dataset for all analyses').click().run()
        signature=project_signature(app.session_state.assessment_project)
        app.switch_page('preliminary_analysis.py').run()
        next(b for b in app.button if b.label=='Run Deterministic Analysis').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(project_signature(app.session_state.assessment_project),signature)
        app.switch_page('data_integration.py').run()
        self.assertFalse(app.exception)
        self.assertEqual(next(n for n in app.number_input if n.label=='Nominal pipe-joint length (m)').value,24.)
        self.assertFalse(app.warning)

    def test_read_only_downstream_ui_runs(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'preliminary_analysis.py'),default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertNotIn('Defect source',[x.label for x in app.selectbox])
        next(b for b in app.button if b.label=='Run Deterministic Analysis').click().run()
        self.assertFalse(app.exception)
        results=app.session_state.deterministic_output[1]
        self.assertEqual(results['Distance from start (km)'].tolist(),[.5,4.5,8.5])
        next(n for n in app.number_input if n.label=='Monte Carlo samples per defect').set_value(100).run()
        next(b for b in app.button if b.label=='Run Reliability Analysis').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        assessed=app.session_state.shared_reliability_output[1]
        self.assertEqual(assessed.feature_id.tolist(),results['Profile ID'].tolist())


if __name__=='__main__':
    unittest.main()
