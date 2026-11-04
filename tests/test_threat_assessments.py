"""Independent equation checks, threat isolation and correlated event unions."""
import unittest
from copy import deepcopy
import numpy as np
import pandas as pd
from assessment_project import sample_project,validate_project,project_signature
from corrosion_assessment_model import (isolated_metal_loss,deterministic_corrosion,
    corrosion_specs,corrosion_reliability)
from dent_assessment_model import geometric_dent_strain,dent_geometry,dent_reliability
from threat_workspaces import threat_project


class ThreatAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.p=validate_project(sample_project())

    def corrosion_project(self):
        p=deepcopy(self.p)
        p['summary']['Defect type']='Corrosion / metal loss'
        p['summary']['Maximum depth (mm)']=2.
        p['uncertainties']['distribution']='Deterministic'
        p['uncertainties']['std']=0.
        return p

    def dent_project(self):
        p=deepcopy(self.p)
        p['dent_register']=pd.DataFrame([dict(dent_id='D1',chainage_m=501.,dent_depth_mm=15.,
            axial_length_mm=600.,circumferential_width_mm=300.,circumferential_radius_mm=-1500.,
            axial_radius_mm=2500.,associated_crack_or_metal_loss=False)])
        return validate_project(p)

    def test_nominal_metal_loss_matches_published_example(self):
        # Equinor public reference: 508 mm D, 12.7 mm t, 4.5 mm d,
        # 200 mm L, UTS=535 MPa -> approximately 22.3466 MPa.
        mpa=isolated_metal_loss(508.,12.7,4.5,200.,535.)
        self.assertAlmostEqual(float(mpa),22.3466,places=4)
        self.assertGreater(isolated_metal_loss(508,12.7,2,200,535),mpa)
        self.assertGreater(isolated_metal_loss(508,12.7,4.5,100,535),mpa)
        with self.assertRaises(ValueError):isolated_metal_loss(508,12.7,12.,200,535)

    def test_filter_does_not_change_shared_route_or_original(self):
        p=self.corrosion_project();p['summary'].loc[0,'Defect type']='Crack'
        crack=threat_project(p,'Crack');corrosion=threat_project(p,'Corrosion')
        self.assertEqual(len(crack['summary']),1);self.assertEqual(len(corrosion['summary']),2)
        pd.testing.assert_frame_equal(crack['segments'],p['segments'])
        self.assertEqual(crack['route'],p['route'])
        self.assertEqual(len(p['summary']),3)

    def test_corrosion_mc_agrees_with_deterministic_limit_state(self):
        p=self.corrosion_project()
        p['segments']['operating_pressure_psi']=1.
        det=deterministic_corrosion(p)
        self.assertTrue((det.FPR>1).all())
        a,j,s=corrosion_reliability(p,corrosion_specs(p),100,7)
        self.assertTrue(a.burst_pf.eq(0).all())
        p['segments']['operating_pressure_psi']=1e6
        a,_,_=corrosion_reliability(p,corrosion_specs(p),100,7)
        self.assertTrue(a.burst_pf.eq(1).all());self.assertTrue(a.leak_pf.eq(0).all())

    def test_corlas_bias_not_copied_to_corrosion(self):
        p=self.corrosion_project();p['segments']['model_factor']=100.
        for spec in corrosion_specs(p).values():
            self.assertEqual(spec['model_factor']['mean'],1.)
            self.assertEqual(spec['model_factor']['std'],0.)

    def test_uncalculable_deep_draws_are_not_silent_safe_samples(self):
        p=self.corrosion_project();p['summary'].loc[0,'Maximum depth (mm)']=.9*11.8
        with self.assertRaisesRegex(ValueError,'85% WT'):corrosion_reliability(p,corrosion_specs(p),100)

    def test_same_joint_corrosion_uses_event_union_and_unknown_losses(self):
        p=self.corrosion_project();p['summary'].loc[:1,'Feature location (m)']=[501.,502.]
        p=validate_project(p);p['segments']['burst_consequence']=np.nan
        p['segments']['operating_pressure_psi']=1e6
        a,j,s=corrosion_reliability(p,corrosion_specs(p),100)
        self.assertEqual(a.joint_number.iloc[0],a.joint_number.iloc[1]);self.assertEqual(len(j),2)
        self.assertEqual(s.burst_pf.iloc[0],1.);self.assertTrue(s.total_risk.isna().all())

    def test_through_wall_corrosion_is_leakage_only(self):
        p=self.corrosion_project();p['summary']['Maximum depth (mm)']=12.
        a,_,_=corrosion_reliability(p,corrosion_specs(p),100)
        self.assertTrue(a.leak_pf.eq(1).all());self.assertTrue(a.burst_pf.eq(0).all())

    def test_known_circumferential_feature_rejected(self):
        p=self.corrosion_project();p['summary']['Profile width (mm)']=1e6
        self.assertFalse(deterministic_corrosion(p).Status.eq('Calculated').any())
        with self.assertRaisesRegex(ValueError,'width'):corrosion_reliability(p,corrosion_specs(p),100)

    def test_dent_strain_equations_against_hand_calculation(self):
        d,t,h,l,r1,r2=914.4,11.8,15.,600.,-1500.,2500.
        e1=.5*t*(2/d-1/r1);e2=-.5*t/r2;e3=.5*(h/l)**2
        expected=max(np.sqrt(e1**2-e1*(e2+e3)+(e2+e3)**2),
            np.sqrt(e1**2+e1*(-e2+e3)+(-e2+e3)**2))
        self.assertAlmostEqual(float(geometric_dent_strain(d,t,h,l,r1,r2)),expected)

    def test_dent_reliability_is_criterion_event_not_burst_probability(self):
        p=self.dent_project();r=dent_geometry(p)
        self.assertTrue(r.equivalent_strain_percent.notna().all())
        a,j,s=dent_reliability(p,criterion_percent=.01,samples=100)
        self.assertEqual(a.strain_criterion_probability.iloc[0],1.)
        self.assertNotIn('burst_pf',a);self.assertNotIn('FPR',a)
        a,_,_=dent_reliability(p,criterion_percent=90.,samples=100)
        self.assertEqual(a.strain_criterion_probability.iloc[0],0.)

    def test_dent_combined_defects_block_and_signature_detects_changes(self):
        p=self.dent_project();sig=project_signature(p)
        p['dent_register'].loc[0,'dent_depth_mm']=30.
        self.assertNotEqual(sig,project_signature(p))
        p['dent_register'].loc[0,'associated_crack_or_metal_loss']=True
        self.assertTrue(dent_geometry(p).equivalent_strain_percent.isna().all())
        with self.assertRaisesRegex(ValueError,'interaction'):dent_reliability(p,samples=100)

    def test_invalid_dent_location_is_rejected(self):
        p=self.dent_project();p['dent_register'].loc[0,'chainage_m']=11000.
        with self.assertRaisesRegex(ValueError,'route'):validate_project(p)


if __name__=='__main__':unittest.main()
