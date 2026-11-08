"""The planner must use the saved asset, without dropping or duplicating defects."""
from copy import deepcopy
import unittest
import pandas as pd
from assessment_project import sample_project, validate_project, project_signature
from planning_project import planning_handoff, planning_joints


class PlanningHandoffTests(unittest.TestCase):
    def setUp(self):
        self.project = validate_project(sample_project())

    def test_uniform_ten_km_asset_and_uncertainties_are_preserved(self):
        before = project_signature(self.project)
        h = planning_handoff(self.project)
        self.assertEqual((h['total_joints'], h['initial_cracks'], h['cracked_joints']), (834, 3, 3))
        self.assertEqual(sum(j['count'] for j in h['joints']), 834)
        self.assertEqual(h['defect_register']['Profile ID'].tolist(), ['SYN-001','SYN-002','SYN-003'])
        for j in h['joints']:
            self.assertEqual(j['properties']['OD']['mean'], 36.)
            self.assertEqual(j['properties']['WT']['mean'], 11.8)
            self.assertEqual(j['costs'], {'Cf_burst':1., 'Cf_leak':.1})
            self.assertTrue(j['use_nominal_repair'])
        self.assertEqual(before, project_signature(self.project))
        first = h['joints'][0]['cracks'][0]
        self.assertEqual(first['depth_distribution'], 'Normal')
        self.assertEqual(first['depth_std'], .74)
        self.assertEqual(first['mean_depth'], self.project['summary'].iloc[0]['Maximum depth (mm)'])

    def test_multiple_cracks_are_one_physical_joint(self):
        self.project['summary']['Feature location (m)'] = [500., 501., 8500.]
        h = planning_handoff(self.project)
        self.assertEqual(h['cracked_joints'], 2)
        joint = next(j for j in h['joints'] if j['name']=='Joint 42')
        self.assertEqual(len(joint['cracks']), 2)
        self.assertEqual(joint['count'], 1)
        self.assertEqual(sum(j['count'] for j in h['joints']), 834)
        self.assertEqual(len({c['profile_id'] for c in joint['cracks']}), 2)

    def test_joint_boundaries_and_final_endpoint(self):
        self.project['summary']['Feature location (m)'] = [11.999, 12., 10000.]
        h = planning_handoff(self.project)
        self.assertEqual(h['defect_register']['Joint number'].tolist(), [1,2,834])

    def test_distinct_aligned_segment_properties_and_sd(self):
        p = self.project
        # Two segments meeting at a real 12 m joint boundary.
        p['segments'] = p['segments'].iloc[[0,1]].copy()
        p['segments']['section_id'] = [1,2]
        p['segments']['start_km'] = [0.,4.8]
        p['segments']['end_km'] = [4.8,10.]
        p['segments'].loc[p['segments'].section_id==2,'wall_thickness_mm'] = 12.5
        p['uncertainties'] = p['uncertainties'].query('section_id in [1,2]').copy()
        mask = (p['uncertainties'].section_id==2)&(p['uncertainties'].parameter=='wall_thickness_mm')
        p['uncertainties'].loc[mask,'distribution'] = 'Deterministic'
        h = planning_handoff(p)
        j = next(j for j in h['joints'] if j['name']=='Joint 709')
        self.assertEqual(j['properties']['WT']['mean'], 12.5)
        self.assertEqual(j['properties']['WT']['std'], 0.)
        self.assertEqual(j['properties']['WT']['distribution'], 'Deterministic')

    def test_incompatible_properties_inside_same_joint_are_not_silently_averaged(self):
        self.project['segments'].loc[1,'wall_thickness_mm'] = 13.
        with self.assertRaisesRegex(ValueError, 'cuts a.*physical joint'):
            planning_handoff(self.project)

    def test_other_threats_are_blocked_instead_of_discarded(self):
        self.project['summary'].loc[0,'Defect type'] = 'Corrosion / metal loss'
        with self.assertRaisesRegex(ValueError,'cracks only'):
            planning_handoff(self.project)

    def test_missing_loss_stays_unknown_and_planning_does_not_change_saved_data(self):
        self.project['segments']['burst_consequence'] = float('nan')
        h = planning_handoff(self.project)
        self.assertNotIn('Cf_burst', h['joints'][0]['costs'])
        copied = planning_joints(h, {'alpha':{'mean':.1, 'std':.02, 'distribution':'Normal'}}, .00008)
        self.assertNotIn('alpha',h['joints'][0]['properties'])
        self.assertNotIn('birth_rate',h['joints'][0])
        self.assertEqual(copied[0]['birth_rate'], .00008)
        self.assertNotIn('costs', copied[0])
        opted_in = planning_joints(h, {}, 0., use_segment_costs=True)
        self.assertEqual(opted_in[0]['costs'], {'Cf_leak':.1})

    def test_dataset_id_changes_when_route_defect_or_property_changes(self):
        before = planning_handoff(self.project)['dataset_id']
        self.project['summary'].loc[0,'Feature location (m)'] += 1
        self.assertNotEqual(before,planning_handoff(self.project)['dataset_id'])


if __name__ == '__main__': unittest.main()
