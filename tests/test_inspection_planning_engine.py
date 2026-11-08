"""Shared-project physics must use the imported joint, rather than 20-inch defaults."""
import unittest
from unittest.mock import patch
import numpy as np
from inspection_planning import engine


def inputs():
    joint = dict(name='Joint 42', count=1, cracks=[dict(mean_length=40., mean_depth=1.)],
        properties={}, birth_rate=0.)
    costs = dict(Cr1=.2, Cr2=.05, Cf_leak=2., Cf_burst=20.,
        inspection_cost_per_km=.015, pipe_length_km=10., rate=0.)
    sim = dict(dS=2., m=3., Di=508., FPR_rep1=1.25, D_rep1=3.175,
        FPR_rep2=1.1, D_rep2=4.445, lifetime_arr=[0,5,5], df_arr=[1,0,0],
        inspection_interval=1, resample_growth_each_step=False)
    return joint, costs, sim


class SharedEngineTests(unittest.TestCase):
    def test_corlas_uses_requested_outside_diameter(self):
        args = [40., 1., 11.8, 57200., 73920., 85., 210.]
        with patch.object(engine.CorlasP, 'CorLAS', return_value=[1000.,500.,1.,1.,1.]) as model:
            engine.limit_state_burst([], args, 1., 936., diameter_in=36.)
        self.assertEqual(model.call_args.args[6], 36.)

    def test_crack_sizing_distributions_and_deviations_are_independent(self):
        cracks = [dict(mean_length=40.,mean_depth=1.,length_distribution='Deterministic',
            depth_distribution='Deterministic',length_std=15.6,depth_std=.74),
            dict(mean_length=70.,mean_depth=2.,length_distribution='Normal',
            depth_distribution='Normal',length_std=2.,depth_std=.1)]
        length, depth = engine.sample_initial_cracks(cracks,100,seed=8)
        np.testing.assert_array_equal(length[0],40.)
        np.testing.assert_array_equal(depth[0],1.)
        self.assertGreater(np.std(length[1]),1.)
        self.assertGreater(np.std(depth[1]),.05)

    def test_initial_screening_uses_joint_diameter(self):
        props = engine.sample_individual_joint_properties([
            dict(cracks=[dict(mean_length=40.,mean_depth=1.)],properties={'OD':36.})],2)
        with patch.object(engine,'limit_state_burst',return_value=(1.,0,1.,1.,1.,1.)) as model:
            mask = engine.initial_system_survival_mask(np.array([[40.,1.],[40.,1.]]),props,[1])
        self.assertTrue(mask.all())
        self.assertTrue(all(call.kwargs['diameter_in']==36. for call in model.call_args_list))

    def test_growth_repair_and_cost_use_imported_joint(self):
        joint,costs,sim=inputs()
        joint.update(use_nominal_repair=True,maop_psi=800.,
            costs={'Cf_leak':3.,'Cf_burst':30.})
        joint['properties']={'OD':36., 'WT':{'mean':11.8,'std':0.,'distribution':'Deterministic'},
            'Pservice':{'mean':810.,'std':0.,'distribution':'Deterministic'}}
        sim.update(D_rep1_fraction=.5,D_rep2_fraction=.7)
        with patch.object(engine,'limit_state_burst',wraps=engine.limit_state_burst) as burst, \
             patch.object(engine,'simulate_cracks_vectorized',wraps=engine.simulate_cracks_vectorized) as growth:
            result=engine.run_flexible_simulation('equidistant',1,1,3,[joint],costs,sim,[0.,0.],
                10.,property_seed=7,track_debug=False,decision_mode='excavation')
        self.assertTrue(growth.called)
        self.assertTrue(all(abs(call.args[14]-36.*25.4)<1e-8 for call in growth.call_args_list))
        repairs=[c for c in burst.call_args_list if c.args[2]==1 and c.args[3]==1.1*800.]
        self.assertTrue(repairs)
        self.assertEqual(repairs[0].args[1][2],11.8)
        self.assertTrue(all(c.kwargs.get('diameter_in')==36. for c in burst.call_args_list))
        self.assertEqual(result[16]['requested_samples'],3)
        self.assertEqual(result[16]['retained_samples'],3)
        np.testing.assert_allclose(result[6],result[7]+result[8]+result[9])

    def test_ili_event_cost_uses_whole_mapped_length(self):
        _,costs,_=inputs()
        self.assertAlmostEqual(engine.ili_inspection_event_cost(costs),.15)

    def test_legacy_prior_and_ili_results_are_preserved_without_shared_overrides(self):
        # Recorded against standalone engine bb562e83c73ff64366f3ea606291ff29f22b8674,
        # using its Sampling_2 sampler. Both policies include deterioration and repairs.
        joint,costs,sim=inputs()
        joint['name']='Cracked'
        joint['cracks'][0]['mean_depth']=2.
        joint['birth_rate']=.01
        blank=dict(name='Crack-free',count=3,cracks=[],properties={},birth_rate=.01)
        costs.update(pipe_length_km=1.,rate=.04)
        sim['inspection_interval']=2
        expected={
            'ili':[0.,0.,.14330621301775145,0.,.021370104775743144,0.],
            'excavation':[0.,0.,.18491124260355024,0.,.17096083820594513,0.],
        }
        for mode in expected:
            np.random.seed(17)
            result=engine.run_flexible_simulation('equidistant',5,1,20,[joint,blank],
                costs,sim,[.74,15.6],1.,property_seed=7,track_debug=False,decision_mode=mode)
            np.testing.assert_allclose(result[6],expected[mode],atol=1e-12,rtol=1e-12)
            np.testing.assert_array_equal(result[1],np.zeros(6))
            np.testing.assert_array_equal(result[2],np.zeros(6))

    def test_already_failed_population_is_rejected(self):
        joint,costs,sim=inputs()
        with patch.object(engine,'initial_system_survival_mask',return_value=np.zeros(3,dtype=bool)):
            with self.assertRaisesRegex(RuntimeError,'failed at time zero'):
                engine.run_flexible_simulation('equidistant',1,1,3,[joint],costs,sim,
                    [0.,0.],1.,track_debug=False)

    def test_segment_consequence_changes_failure_cost_and_retained_count_is_visible(self):
        joint,costs,sim=inputs()
        joint['costs']={'Cf_burst':30.}
        safe=(1.,0,1000.,1.,1.,1.)
        failed=(-1.,1,100.,1.,1.,1.)
        with patch.object(engine,'initial_system_survival_mask',return_value=np.array([True,False,True])), \
             patch.object(engine,'limit_state_burst',side_effect=[safe,safe,failed,failed]):
            result=engine.run_flexible_simulation('equidistant',1,1,3,[joint],costs,sim,
                [0.,0.],1.,track_debug=False)
        self.assertEqual(result[7][-1],30.)
        self.assertEqual(result[16]['requested_samples'],3)
        self.assertEqual(result[16]['retained_samples'],2)


if __name__=='__main__':unittest.main()
