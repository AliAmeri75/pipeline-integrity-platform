import unittest
import numpy as np
import pandas as pd
from reliability_flags import flag_probabilities,annotate_pof_figure
from reliability_analysis import profile_figure,result_map
from assessment_project import sample_project,reliability_project


class ReliabilityFlagTests(unittest.TestCase):
    def test_strict_threshold_and_either_mode(self):
        data=pd.DataFrame(dict(burst_pf=[.001,.002,0.,np.nan],leak_pf=[.01,0.,.02,np.nan]))
        flagged=flag_probabilities(data,.001,.01)
        self.assertEqual(flagged.action_required.tolist(),[False,True,True,False])
        self.assertEqual(flagged.screening_status.iloc[-1],'Assessment incomplete')
        self.assertIn('Leakage',flagged.screening_reason.iloc[2])
        self.assertNotIn('action_required',data)

    def test_chart_circles_and_map_labels_on_every_layer(self):
        p=sample_project()
        features,_,sections=reliability_project(p,100)
        sections['burst_pf']=0.
        sections.loc[8,'burst_pf']=.01
        sections=flag_probabilities(sections,.001,.01)
        figure=annotate_pof_figure(profile_figure(sections,[('burst_pf','Burst')],'POF','Pf'),sections,.001,.01)
        self.assertEqual(figure.data[-1].marker.symbol,'circle-open')
        self.assertEqual(list(figure.data[-1].x),[8.5])
        self.assertEqual(figure.data[-1].text[0],'→ Immediate action!')
        for column in ['burst_pf','leak_pf','total_risk','burst_consequence']:
            rendered=result_map(p['route'],features,sections,column,column).get_root().render()
            self.assertIn('Immediate action!',rendered)
            self.assertIn('background:white',rendered)
            self.assertIn('Segment 9',rendered)

    def test_new_threshold_reclassifies_without_new_simulation(self):
        data=pd.DataFrame(dict(burst_pf=[.002],leak_pf=[0.]))
        self.assertTrue(flag_probabilities(data,.001,.01).action_required.iloc[0])
        self.assertFalse(flag_probabilities(data,.003,.01).action_required.iloc[0])


if __name__=='__main__':
    unittest.main()
