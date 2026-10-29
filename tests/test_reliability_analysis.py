import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from education.pof_model import POFInputs, UncertaintyInputs
from profile_map import route_length_km
from reliability_model import (demo_data,calculate_crack_reliability,
    import_feature_reliability,sliding_sections,consequence_template,fixed_section_risk)


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.route = [[53.5,-113.5],[53.5,-113.46]]
        self.features = pd.DataFrame(dict(feature_id=['A','B'],defect_type=['Crack','Crack'],
            chainage_km=[.961,.962],depth_mm=[1.,2.],length_mm=[30.,40.]))

    def test_demo_and_shared_joint(self):
        route,features = demo_data()
        self.assertAlmostEqual(route_length_km(route),100.)
        features['burst_pf'],features['leak_pf'] = .006,0.
        data,joints = import_feature_reliability(features,route,12.)
        self.assertEqual(len(joints),10)
        self.assertEqual(data.joint_number.iloc[0],data.joint_number.iloc[1])

    def test_window_combines_nearby_features(self):
        self.features['burst_pf'],self.features['leak_pf'] = .0006,0.
        data,joints = import_feature_reliability(self.features,self.route,12.)
        windows,spatial = sliding_sections(self.route,data,joints,12.,.001,.01)
        self.assertAlmostEqual(windows.burst_pf.max(),1-.9994**2)
        self.assertIn('High',windows.category.values)
        self.assertTrue(np.allclose(windows.end_km-windows.start_km,1.))
        self.assertAlmostEqual(windows.end_km.iloc[-1],route_length_km(self.route))
        self.assertEqual(spatial.features.sum(),2)

    def test_deterministic_cracks_and_through_wall(self):
        self.features.loc[0,'depth_mm'] = 8.
        data,joints = calculate_crack_reliability(self.features,self.route,12.,
            POFInputs(),UncertaintyInputs(0,0,0,0,0),samples=100)
        self.assertEqual(data.leak_pf.iloc[0],1.)
        self.assertEqual(data.burst_pf.iloc[0],0.)
        self.assertEqual(data.leak_pf.iloc[1],0.)
        self.assertEqual(joints.leak_pf.iloc[0],1.)

    def test_reject_corrosion_calculation_but_allow_import(self):
        self.features.loc[0,'defect_type'] = 'Corrosion'
        with self.assertRaisesRegex(ValueError,'CorLAS'):
            calculate_crack_reliability(self.features,self.route,12.,POFInputs(),UncertaintyInputs(),100)
        self.features['burst_pf'],self.features['leak_pf'] = .001,.002
        data,_ = import_feature_reliability(self.features,self.route,12.)
        self.assertEqual(data.defect_type.iloc[0],'Corrosion')

    def test_invalid_import_and_chainage(self):
        self.features['burst_pf'],self.features['leak_pf'] = np.nan,.1
        with self.assertRaises(ValueError):
            import_feature_reliability(self.features,self.route,12.)
        self.features['burst_pf'] = .1
        self.features.loc[0,'chainage_km'] = 1000
        with self.assertRaisesRegex(ValueError,'Chainages'):
            import_feature_reliability(self.features,self.route,12.)

    def test_model_factor_changes_burst_probability(self):
        inputs = POFInputs()
        zero = UncertaintyInputs(0,0,0,0,0)
        weak,_ = calculate_crack_reliability(self.features,self.route,12.,
            replace(inputs,model_factor=.01),zero,100)
        strong,_ = calculate_crack_reliability(self.features,self.route,12.,
            replace(inputs,model_factor=10.),zero,100)
        self.assertTrue((weak.burst_pf == 1).all())
        self.assertTrue((strong.burst_pf == 0).all())

    def test_short_route_and_probability_one(self):
        route = [[53.5,-113.5],[53.5,-113.4999]]
        features = self.features.iloc[:1].copy()
        features['chainage_km'],features['burst_pf'],features['leak_pf'] = .001,1.,0.
        data,joints = import_feature_reliability(features,route,12.)
        windows,_ = sliding_sections(route,data,joints,12.,.001,.01)
        self.assertEqual(len(windows),1)
        self.assertEqual(windows.burst_pf.iloc[0],1.)
        self.assertLess(windows.end_km.iloc[0],1.)

    def test_fixed_sections_do_not_duplicate_joint_crossing_boundary(self):
        self.features['chainage_km'] = [.999,1.001]
        self.features['burst_pf'],self.features['leak_pf'] = [.1,.2],[.01,.02]
        data,joints = import_feature_reliability(self.features,self.route,12.)
        self.assertEqual(len(joints),1)
        consequences = consequence_template(self.route)
        consequences['burst_consequence'],consequences['leak_consequence'] = 1000.,100.
        result = fixed_section_risk(self.route,data,consequences,.001,.01)
        np.testing.assert_allclose(result.burst_pf,[.1,.2,0.])
        np.testing.assert_allclose(result.total_risk,[101.,202.,0.])
        self.assertEqual(result.feature_count.sum(),2)
        self.assertLess(result.end_km.iloc[-1]-result.start_km.iloc[-1],1.)

    def test_fixed_section_sampling_keeps_same_joint_dependence(self):
        self.features['chainage_km'] = [.999,1.001]
        self.features['depth_mm'] = [8.,1.]
        data,_ = calculate_crack_reliability(self.features,self.route,12.,POFInputs(),
            UncertaintyInputs(0,0,0,0,0),100)
        c = consequence_template(self.route,sample=True)
        result = fixed_section_risk(self.route,data,c,.001,.01)
        self.assertEqual(result.leak_pf.iloc[0],1.)
        self.assertEqual(result.leak_pf.iloc[1],0.)

    def test_consequence_validation_and_endpoint_assignment(self):
        self.features['chainage_km'] = [1.,route_length_km(self.route)]
        self.features['burst_pf'],self.features['leak_pf'] = .1,.01
        data,_ = import_feature_reliability(self.features,self.route,12.)
        self.assertEqual(data.section_id.tolist(),[2,3])
        c = consequence_template(self.route,sample=True)
        for invalid in [c.iloc[:-1],pd.concat([c,c.iloc[:1]]),c.assign(burst_consequence=-1),
                        c.assign(leak_consequence=np.nan),c.assign(start_km=50)]:
            with self.assertRaises(ValueError):
                fixed_section_risk(self.route,data,invalid,.001,.01)
        self.assertEqual(fixed_section_risk(self.route,data,c.iloc[::-1],.001,.01).section_id.tolist(),[1,2,3])
