import unittest
import folium
from assessment_project import sample_project,reliability_project
from reliability_analysis import result_map
from map_presentation import readable_map_overlays


class MapPresentationTests(unittest.TestCase):
    def test_styles_are_scoped_and_high_contrast(self):
        m=folium.Map()
        rendered=readable_map_overlays(m).get_root().render()
        self.assertIn('#'+m.get_name()+' .legend',rendered)
        self.assertIn('background: #ffffff !important',rendered)
        self.assertIn('fill: #111827 !important',rendered)
        self.assertIn('.leaflet-tooltip',rendered)
        self.assertNotIn('SELECTOR',rendered)

    def test_all_risk_map_legends_keep_their_caption_and_background(self):
        p=sample_project()
        features,_,sections=reliability_project(p,100)
        for column,label,limit in [('burst_pf','Burst POF',.001),
                ('leak_pf','Leakage POF',.01),('burst_consequence','Burst Consequence',None),
                ('total_risk','Total Risk',None)]:
            rendered=result_map(p['route'],features,sections,column,label,limit).get_root().render()
            self.assertIn(label,rendered)
            self.assertIn('selected Pf limit' if limit else 'relative colour scale',rendered)
            self.assertIn('background: #ffffff !important',rendered)


if __name__=='__main__':
    unittest.main()
