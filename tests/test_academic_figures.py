import unittest
import pandas as pd
from academic_figures import FONT
from reliability_analysis import profile_figure
from reliability_flags import annotate_pof_figure
from deterministic_flags import fpr_distance_figure


class AcademicFigureTests(unittest.TestCase):
    def test_pof_zero_not_substituted_and_positive_interval_retained(self):
        sections=pd.DataFrame(dict(section_id=[1,2,3],start_km=[0,1,2],end_km=[1,2,3],
            burst_pf=[0,.01,0],leak_pf=[0,0,0]))
        figure=profile_figure(sections,[('burst_pf','Burst'),('leak_pf','Leak')],'POF','Pf')
        self.assertEqual(figure.layout.yaxis.type,'log')
        self.assertEqual(list(figure.data[0].x),[1,2,None])
        self.assertEqual(list(figure.data[0].y),[.01,.01,None])
        self.assertEqual(len(figure.data[1].y),0)
        self.assertEqual(sections.burst_pf.tolist(),[0,.01,0])
        annotate_pof_figure(figure,sections,.001,.01)
        self.assertAlmostEqual(figure.layout.annotations[0].y,-3)
        self.assertEqual(figure.layout.annotations[0].bgcolor,'white')

    def test_fpr_white_serif_and_linear(self):
        data=pd.DataFrame({'Profile ID':['A'],'FPR':[1.05],'Status':['Calculated'],
            'Defect depth (mm)':[6.],'Wall thickness (mm)':[10.],'Distance from start (km)':[1.]})
        figure=fpr_distance_figure(data)
        self.assertEqual(figure.layout.yaxis.type,'linear')
        self.assertEqual(figure.layout.font.family,FONT)
        self.assertEqual(figure.layout.plot_bgcolor,'white')
        self.assertEqual(figure.layout.paper_bgcolor,'white')

    def test_risk_and_consequence_remain_linear(self):
        data=pd.DataFrame(dict(start_km=[0],end_km=[1],total_risk=[0.]))
        figure=profile_figure(data,[('total_risk','Risk')],'Risk','CAD')
        self.assertNotEqual(figure.layout.yaxis.type,'log')
        self.assertEqual(figure.layout.font.family,FONT)
        self.assertEqual(list(figure.data[0].y),[0.,0.])


if __name__=='__main__':
    unittest.main()
