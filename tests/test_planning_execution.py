"""Batching must preserve pooling, conditioning, costs, and resumability."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from inspection_planning import engine
from inspection_planning.execution import run_batched_flexible_simulation, effective_batch_size
from tests.test_inspection_planning_engine import inputs


def fake_result(requested, retained, probabilities, cost):
    times = np.arange(3)
    joint = np.array(probabilities, dtype=float)
    debug = dict(joint_names=['A','B'], joint_leak_pofs=joint, joint_burst_pofs=joint / 2,
                 requested_samples=requested, retained_samples=retained)
    output = [None] * 17
    output[:6] = [times, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(3), np.array([2.])]
    for index in [6,7,8,9,12,13,14]:
        output[index] = np.array([0., cost, cost * 2])
    output[10:12] = [True, []]
    output[15:17] = [[], debug]
    return tuple(output)


class BatchedPlanningTests(unittest.TestCase):
    def setUp(self):
        self.joint, self.costs, self.sim = inputs()
        self.joints = [dict(name='A',count=2,cracks=[]),dict(name='B',count=1,cracks=[])]
        self.sim.update(max_annual_leak_pof=.02, max_annual_burst_pof=.01)

    def run_fake(self, nx, **kwargs):
        return run_batched_flexible_simulation('equidistant',2,1,nx,self.joints,self.costs,
            self.sim,[0.,0.],1.,**kwargs)

    def test_pool_joint_counts_before_nonlinear_system_pof_and_safety(self):
        first = fake_result(2,2,[[0,.5,.5],[0,0,0]],2.)
        second = fake_result(1,1,[[0,1,1],[0,1,1]],8.)
        with patch.object(engine,'run_flexible_simulation',side_effect=[first,second]) as run:
            result = self.run_fake(3,batch_size=2)
        self.assertEqual([call.args[3] for call in run.call_args_list],[2,1])
        expected_joint = np.array([[0,2/3,2/3],[0,1/3,1/3]])
        expected_system = 1 - (1 - expected_joint[0])**2 * (1 - expected_joint[1])
        np.testing.assert_allclose(result[16]['joint_leak_pofs'], expected_joint)
        np.testing.assert_allclose(result[1], expected_system)
        np.testing.assert_allclose(result[3],[0,expected_system[1]/10,0])
        np.testing.assert_allclose(result[6],[0,4.,8.])
        self.assertFalse(result[10])  # both fake batches individually said Safe
        self.assertEqual(len(result[11]),1)
        self.assertEqual(result[16]['retained_samples'],3)
        self.assertEqual(result[15],[])

    def test_weight_by_retained_samples_not_requested_samples(self):
        first = fake_result(3,1,[[0,1,1],[0,0,0]],10.)
        second = fake_result(2,2,[[0,0,0],[0,0,0]],1.)
        with patch.object(engine,'run_flexible_simulation',side_effect=[first,second]):
            result = self.run_fake(5,batch_size=3)
        np.testing.assert_allclose(result[6],[0,4.,8.])
        self.assertEqual(result[16]['requested_samples'],5)
        self.assertEqual(result[16]['retained_samples'],3)
        self.assertAlmostEqual(result[16]['joint_leak_pofs'][0,1],1/3)

    def test_zero_survivor_batch_is_skipped_but_total_rejection_is_reported(self):
        error = RuntimeError('All Monte Carlo samples failed at time zero.')
        with patch.object(engine,'run_flexible_simulation',side_effect=[error,
                fake_result(1,1,[[0,0,0],[0,0,0]],1.)]):
            result = self.run_fake(3,batch_size=2)
        self.assertEqual(result[16]['retained_samples'],1)
        with patch.object(engine,'run_flexible_simulation',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'failed at time zero'):
                self.run_fake(3,batch_size=2)

    def test_resume_does_not_repeat_a_finished_batch_and_rejects_changed_inputs(self):
        class Interrupted(Exception):
            pass
        state = {}
        first = fake_result(2,2,[[0,.5,.5],[0,0,0]],2.)
        second = fake_result(1,1,[[0,1,1],[0,1,1]],8.)
        with patch.object(engine,'run_flexible_simulation',side_effect=[first,Interrupted()]):
            with self.assertRaises(Interrupted):
                self.run_fake(3,batch_size=2,state=state)
        self.assertEqual(state['processed'],2)
        with patch.object(engine,'run_flexible_simulation',return_value=second) as run:
            result = self.run_fake(3,batch_size=2,state=state)
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[3],1)
        self.assertEqual(result[16]['retained_samples'],3)
        with self.assertRaisesRegex(ValueError,'different planning inputs'):
            self.run_fake(4,batch_size=2,state=state)

    def test_single_batch_matches_existing_engine_for_the_same_random_stream(self):
        for mode in ['excavation','ili']:
            np.random.seed(7)
            expected = engine.run_flexible_simulation('equidistant',5,1,25,[self.joint],
                self.costs,self.sim,[.74,15.6],1.,property_seed=7,track_debug=False,decision_mode=mode)
            result = run_batched_flexible_simulation('equidistant',5,1,25,[self.joint],
                self.costs,self.sim,[.74,15.6],1.,property_seed=7,batch_size=100,decision_mode=mode)
            for index in list(range(10))+[12,13,14]:
                np.testing.assert_allclose(result[index],expected[index],rtol=1e-12,atol=1e-12)
            self.assertEqual(result[10],expected[10])
            self.assertEqual(result[16]['retained_samples'],expected[16]['retained_samples'])

    def test_deterministic_multiple_batches_match_one_batch(self):
        joint = deepcopy(self.joint)
        joint['properties'] = {name: dict(mean=spec['mean'],std=0.,distribution='Deterministic')
            for name,spec in engine.DEFAULT_PROPERTY_SPECS.items()}
        joint['properties']['OD'] = dict(mean=20.,std=0.,distribution='Deterministic')
        joint['cracks'] = [dict(mean_length=40.,mean_depth=1.,length_std=0.,depth_std=0.,
            length_distribution='Deterministic',depth_distribution='Deterministic')]
        for mode in ['ili','excavation']:
            arguments = ('equidistant',2,1,12,[joint],self.costs,self.sim,[0.,0.],0.)
            full = run_batched_flexible_simulation(*arguments,batch_size=12,decision_mode=mode)
            small = run_batched_flexible_simulation(*arguments,batch_size=5,decision_mode=mode)
            for index in list(range(10))+[12,13,14]:
                np.testing.assert_allclose(full[index],small[index],rtol=1e-12,atol=1e-12)

    def test_rejects_threshold_and_debug_histories_and_reduces_large_group_batches(self):
        with self.assertRaisesRegex(ValueError,'fixed/equidistant'):
            run_batched_flexible_simulation('threshold',2,1,3,self.joints,self.costs,self.sim,[0,0],1.)
        with self.assertRaisesRegex(ValueError,'sample histories'):
            self.run_fake(3,track_debug=True)
        size = effective_batch_size([dict(cracks=[],birth_rate=.01)]*1000,30,1,250)
        self.assertLess(size,250)
        self.assertGreaterEqual(size,1)


if __name__ == '__main__':
    unittest.main()
