"""Run the shared-data planner and verify saved edits invalidate its results."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from assessment_project import sample_project, validate_project, project_signature


class PlanningUITests(unittest.TestCase):
    def app(self, project):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'), default_timeout=60)
        app.session_state['assessment_project'] = project
        app.run().switch_page('inspection_project.py').run()
        return app

    @staticmethod
    def number(app, label):
        return next(n for n in app.number_input if n.label == label)

    @staticmethod
    def choice(app, label):
        return next(s for s in app.selectbox if s.label == label)

    def test_introduction_and_editable_controls_are_easy_to_find(self):
        app = self.app(validate_project(sample_project()))
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([t.label for t in app.tabs][:2], ['Introduction', 'Planning & Results'])
        self.assertEqual(app.session_state['static_planning_view'], 'Introduction')
        content = '\n'.join(item.value for item in app.markdown)
        self.assertIn('Mohammadali Ameri', content)
        self.assertIn('Yong Li', content)
        self.assertIn('uncertain crack initiation', content)
        self.assertIn('What the application does', content)
        self.assertIn('Static Multiple Inspection and Excavation Planning', content)
        required = {'Monte Carlo samples', 'Mean depth growth, α (mm/year)',
            'Type 1 depth criterion (%WT)', 'Type 2 pressure factor',
            'Recoat growth factor, df1', 'Sleeve effective period (years)'}
        self.assertTrue(required.issubset({n.label for n in app.main.number_input}))
        self.assertTrue({'Pipeline class', 'POD model'}.issubset({s.label for s in app.main.selectbox}))
        self.assertEqual(len(app.sidebar.number_input), 0)
        next(b for b in app.button if b.label == 'Open Planning and VoI Simulation').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state['static_planning_view'], 'Planning & Results')

    def test_settings_survive_introduction_and_data_exploration_roundtrip(self):
        app = self.app(validate_project(sample_project()))
        self.number(app, 'Monte Carlo samples').set_value(200)
        self.number(app, 'Mean depth growth, α (mm/year)').set_value(.15)
        self.number(app, 'Type 1 depth criterion (%WT)').set_value(55.)
        self.choice(app, 'Pipeline class').set_value('Class 3')
        self.choice(app, 'POD model').set_value('depth_length')
        app.run()
        self.number(app, 'Length coefficient, qL (1/mm)').set_value(.03).run()
        for tab in ['Planning & Results', 'Introduction', 'Planning & Results']:
            app.session_state['static_planning_view'] = tab
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(self.number(app, 'Monte Carlo samples').value, 200)
            self.assertEqual(self.number(app, 'Mean depth growth, α (mm/year)').value, .15)
        app.switch_page('data_integration.py').run()
        app.switch_page('inspection_project.py').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.number(app, 'Monte Carlo samples').value, 200)
        self.assertEqual(self.number(app, 'Mean depth growth, α (mm/year)').value, .15)
        self.assertEqual(self.number(app, 'Type 1 depth criterion (%WT)').value, 55.)
        self.assertEqual(self.choice(app, 'Pipeline class').value, 'Class 3')
        self.assertEqual(self.choice(app, 'POD model').value, 'depth_length')
        self.assertEqual(self.number(app, 'Length coefficient, qL (1/mm)').value, .03)

    def test_exploration_continue_opens_planning_with_the_saved_cracks(self):
        project = validate_project(sample_project())
        project['summary']['Feature location (m)'] = [500., 501., 8500.]
        app = self.app(project)
        app.switch_page('data_integration.py').run()
        next(b for b in app.button if b.label ==
            'Continue to Inspection Planning with this saved dataset').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state['static_planning_view'], 'Planning & Results')
        self.assertTrue(any('Connected to the saved' in e.value for e in app.success))
        # Selecting another source in Exploration only creates a draft. The
        # Continue button must still use the last saved two-cracked-joint asset.
        self.assertEqual(app.session_state['assessment_project']['summary']
            ['Feature location (m)'].tolist(), [500., 501., 8500.])

    def test_changed_controls_reach_the_planning_engine(self):
        from inspection_planning.engine import run_flexible_simulation
        app = self.app(validate_project(sample_project()))
        values = {'Monte Carlo samples': 100, 'Analysis horizon (years)': 5,
            'Last fixed excavation interval (years)': 5, 'Last fixed ILI interval (years)': 5,
            'Mean depth growth, α (mm/year)': .12, 'Std. α': .02,
            'Type 1 depth criterion (%WT)': 60., 'Type 2 pressure factor': 1.15,
            'Recoat growth factor, df1': .2, 'Recoat effective period (years)': 4,
            'Sleeve growth factor, df2': .1, 'Sleeve effective period (years)': 7,
            'Depth coefficient, qd (1/mm)': 1.5}
        for label, value in values.items():
            self.number(app, label).set_value(value)
        self.choice(app, 'Pipeline class').set_value('Class 2')
        self.choice(app, 'POD model').set_value('depth_length')
        app.run()
        self.number(app, 'Length coefficient, qL (1/mm)').set_value(.04).run()
        with patch('inspection_planning.engine.run_flexible_simulation',
                   wraps=run_flexible_simulation) as simulate:
            next(b for b in app.button if b.label == 'Run prior + pre-posterior comparison').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(simulate.call_count, 2)
        self.assertEqual({call.kwargs['decision_mode'] for call in simulate.call_args_list}, {'ili', 'excavation'})
        for call in simulate.call_args_list:
            self.assertEqual(call.args[3], 100)
            self.assertEqual(call.args[1], 5)
            joints, sim = call.args[4], call.args[6]
            self.assertEqual(joints[0]['properties']['alpha']['mean'], .12)
            self.assertEqual(joints[0]['properties']['alpha']['std'], .02)
            self.assertEqual(sim['max_annual_leak_pof'], .001)
            self.assertEqual(sim['max_annual_burst_pof'], .0001)
            self.assertEqual(sim['pod_model'], 'depth_length')
            self.assertEqual(sim['pod_depth_coefficient'], 1.5)
            self.assertEqual(sim['pod_length_coefficient'], .04)
            self.assertEqual(sim['D_rep1_fraction'], .6)
            self.assertEqual(sim['FPR_rep2'], 1.15)
            self.assertEqual(sim['df_arr'], [1, .2, .1])
            self.assertEqual(sim['lifetime_arr'], [0, 4, 7])

    def test_comparison_uses_shared_data_then_invalidates_changed_snapshot(self):
        project = validate_project(sample_project())
        before = project_signature(project)
        app = self.app(project)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('Connected to the saved' in e.value for e in app.success))
        self.assertFalse(any(n.label == 'Pipe length (km)' for n in app.number_input))
        for label,value in [('Monte Carlo samples',100),('Analysis horizon (years)',5),
                            ('Last fixed excavation interval (years)',5),('Last fixed ILI interval (years)',5)]:
            next(n for n in app.number_input if n.label==label).set_value(value)
        app.run()
        next(b for b in app.button if b.label=='Run prior + pre-posterior comparison').click().run()
        self.assertEqual(len(app.exception),0)
        study = app.session_state['integrated_planning_comparison']
        self.assertEqual(study['dataset_id'], before)
        self.assertEqual(study['joint_count'],834)
        self.assertEqual(len(study['prior_results']),1)
        self.assertEqual(len(study['ili_results']),1)
        self.assertTrue(any(s.value=='Cost-optimal and safe scheduling results' for s in app.subheader))
        self.assertTrue(any(e.label=='Why a plan is Safe or Unsafe' for e in app.expander))
        self.assertTrue(any('Peak annual whole-pipeline PfB' in d.value.columns for d in app.dataframe))
        self.assertEqual(project_signature(app.session_state['assessment_project']), before)
        original = study['ili_results'][0]['total_cpp']
        with patch('inspection_planning.engine.run_flexible_simulation',
                   side_effect=AssertionError('Changing prices must reuse the simulated events')):
            self.number(app, 'ILI ($M per km per run)').set_value(1.).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Scenario safe plan' in d.value.columns for d in app.dataframe))
            next(b for b in app.button if b.label == 'Restore original costs').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['integrated_planning_comparison']['ili_results'][0]['total_cpp'], original)
        changed = deepcopy(project)
        changed['summary'].loc[0,'Feature location (m)'] += 1
        app.session_state['assessment_project'] = changed
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('saved dataset or planning settings changed' in e.value for e in app.info))
        self.assertFalse(any(s.value=='Cost-optimal and safe scheduling results' for s in app.subheader))

    def test_corrosion_is_not_silently_treated_as_a_crack(self):
        project = validate_project(sample_project())
        project['summary']['Defect type'] = 'Corrosion / metal loss'
        app = self.app(project)
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('cracks only' in e.value for e in app.error))
        self.assertFalse(any(b.label=='Run prior + pre-posterior comparison' for b in app.button))

    def test_large_run_has_no_app_workload_gate_or_ten_thousand_sample_cap(self):
        app = self.app(validate_project(sample_project()))
        self.number(app, 'Monte Carlo samples').set_value(11000)
        self.number(app, 'Analysis horizon (years)').set_value(100)
        app.run()
        self.assertFalse(app.exception)
        run = next(b for b in app.button if b.label == 'Run prior + pre-posterior comparison')
        self.assertFalse(run.disabled)
        self.assertNotIn('I understand this larger run may take several minutes.',
                         [box.label for box in app.checkbox])

    def test_resume_keeps_completed_intervals_and_batches(self):
        from inspection_planning import engine
        app = self.app(validate_project(sample_project()))
        for label, value in {'Monte Carlo samples':100, 'Samples per batch':50,
            'Analysis horizon (years)':5, 'First fixed excavation interval (years)':1,
            'Last fixed excavation interval (years)':2, 'Fixed excavation interval step (years)':1,
            'First fixed ILI interval (years)':1, 'Last fixed ILI interval (years)':1}.items():
            self.number(app,label).set_value(value)
        app.run()
        original, calls = engine.run_flexible_simulation, []
        def interrupt(*args, **kwargs):
            calls.append(args[3])
            if len(calls) == 4:
                raise RuntimeError('Test interruption between batches')
            return original(*args, **kwargs)
        with patch.object(engine,'run_flexible_simulation',side_effect=interrupt):
            next(b for b in app.button if b.label=='Run prior + pre-posterior comparison').click().run()
        job = app.session_state['integrated_planning_job']
        self.assertEqual(len(job['prior_results']),1)
        self.assertEqual(job['checkpoints']['excavation:fixed:2']['processed'],50)
        app.run()
        with patch.object(engine,'run_flexible_simulation',wraps=original) as resumed:
            next(b for b in app.button if b.label=='Resume prior + pre-posterior comparison').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(resumed.call_count,3)
        study = app.session_state['integrated_planning_comparison']
        self.assertEqual([r['interval'] for r in study['prior_results']],[1,2])
        self.assertEqual([r['interval'] for r in study['ili_results']],[1])
        self.assertTrue(app.session_state['integrated_planning_job']['complete'])


if __name__=='__main__': unittest.main()
