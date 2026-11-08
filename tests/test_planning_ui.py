"""Run the shared-data planner and verify saved edits invalidate its results."""
import unittest
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

    def test_comparison_uses_shared_data_then_invalidates_changed_snapshot(self):
        project = validate_project(sample_project())
        before = project_signature(project)
        app = self.app(project)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('Connected to the saved' in e.value for e in app.success))
        self.assertFalse(any(n.label == 'Pipe length (km)' for n in app.number_input))
        for label,value in [('Monte Carlo samples',100),('Analysis horizon (years)',5),
                            ('Last excavation interval (years)',5),('Last ILI interval (years)',5)]:
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
        self.assertEqual(project_signature(app.session_state['assessment_project']), before)
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


if __name__=='__main__': unittest.main()
