import copy
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from education.pof_model import POFInputs,UncertaintyInputs,corlas_failure_pressure
from reliability_inputs import DEFAULT_SPECS
from probabilistic_reliability_model import positive_samples,calculate_crack_reliability


class ReliabilityUncertaintyTests(unittest.TestCase):
    def setUp(self):
        self.route=[[53.5,-113.5],[53.5,-113.48]]
        self.features=pd.DataFrame(dict(feature_id=['A','B'],defect_type=['Crack','Crack'],
            chainage_km=[.101,.102],depth_mm=[1.,1.],length_mm=[40.,40.]))

    def test_sampling_mean_and_standard_deviation(self):
        for distribution in ['Normal','Lognormal','Gumbel']:
            values=positive_samples(np.random.default_rng(10),100.,10.,distribution,100000)
            self.assertAlmostEqual(values.mean(),100.,delta=.2)
            self.assertAlmostEqual(values.std(),10.,delta=.2)
        self.assertTrue((positive_samples(np.random.default_rng(1),20,10,'Deterministic',100)==20).all())

    def test_fixed_inspection_default_values(self):
        self.assertEqual(DEFAULT_SPECS['operating_pressure_psi']['distribution'],'Gumbel')
        self.assertAlmostEqual(DEFAULT_SPECS['operating_pressure_psi']['std'],20.0304)
        self.assertEqual(DEFAULT_SPECS['charpy_energy']['distribution'],'Lognormal')
        self.assertAlmostEqual(DEFAULT_SPECS['yield_strength_psi']['std'],2002.)

    def test_configurable_diameter_and_material_reach_mechanics_and_share_joint(self):
        specs=copy.deepcopy(DEFAULT_SPECS)
        for spec in specs.values():
            spec['distribution']='Deterministic'
            spec['std']=0.
        for name in ['diameter_in','yield_strength_psi','elastic_modulus_gpa','operating_pressure_psi']:
            specs[name]['distribution']='Normal'
            specs[name]['std']=.01*specs[name]['mean']
        captured=[]
        def observe(inputs):
            captured.append(inputs)
            return corlas_failure_pressure(inputs)
        with patch('probabilistic_reliability_model.corlas_failure_pressure',side_effect=observe):
            result,joints=calculate_crack_reliability(self.features,self.route,12.,POFInputs(),UncertaintyInputs(),
                100,7,variable_specs=specs)
        # First mechanics call validates mean inputs; subsequent calls evaluate the two cracks.
        first,second=captured[1:101],captured[101:201]
        self.assertEqual(len(first),100)
        self.assertEqual(len(second),100)
        for name in ['diameter_in','yield_strength_psi','elastic_modulus_gpa','operating_pressure_psi']:
            a=np.array([getattr(case,name) for case in first])
            b=np.array([getattr(case,name) for case in second])
            self.assertGreater(a.std(),0)
            np.testing.assert_array_equal(a,b)
        self.assertEqual(len(joints),1)
        self.assertTrue(result.burst_pf.between(0,1).all())
        self.assertEqual(result.attrs['variable_specs'],specs)

    def test_invalid_distribution_and_geometry_fail_clearly(self):
        with self.assertRaises(ValueError):
            positive_samples(np.random.default_rng(1),20,-1,'Normal',100)
        specs=copy.deepcopy(DEFAULT_SPECS)
        specs['diameter_in']=dict(distribution='Deterministic',mean=.1,std=0.)
        with self.assertRaisesRegex(ValueError,'geometry'):
            calculate_crack_reliability(self.features,self.route,12.,POFInputs(),UncertaintyInputs(),100,7,variable_specs=specs)

    def test_same_seed_reproducible(self):
        args=(self.features,self.route,12.,POFInputs(),UncertaintyInputs(),100,42)
        a,_=calculate_crack_reliability(*args,variable_specs=DEFAULT_SPECS)
        b,_=calculate_crack_reliability(*args,variable_specs=DEFAULT_SPECS)
        np.testing.assert_array_equal(a.burst_pf,b.burst_pf)
