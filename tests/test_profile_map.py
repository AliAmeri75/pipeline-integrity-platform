import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd

from profile_map import locate_profiles_on_route, point_at_chainage, route_length_km,profile_from_map_click


class ProfileMapTests(unittest.TestCase):
    def test_cached_two_argument_map_helper_is_refreshed(self):
        import profile_map
        from streamlit.testing.v1 import AppTest
        def legacy_renderer(summary,selected_profile_id):
            raise AssertionError('Old map helper should be refreshed before use')
        with patch.object(profile_map,'render_profile_location_map',legacy_renderer):
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'data_integration.py'),default_timeout=60).run()
            self.assertEqual(len(app.exception),0)
            self.assertIn('Pipeline and defect locations',[s.value for s in app.subheader])
            self.assertEqual(app.session_state.exploration_selected_profile,'SYN-001')

    def test_click_selection_distinguishes_same_location_markers(self):
        mapped=pd.DataFrame({'Profile ID':['A','B'],'Joint ID':['Joint 1','Joint 1'],
                             'Latitude':[53.5,53.5],'Longitude':[-113.5,-113.5]})
        event=dict(last_object_clicked=dict(lat=53.5,lng=-113.5),last_object_clicked_tooltip='Profile B — Joint 1')
        self.assertEqual(profile_from_map_click(mapped,event),'B')
        event['last_object_clicked_tooltip']='Pipeline centreline'
        self.assertIsNone(profile_from_map_click(mapped,event))
        self.assertIsNone(profile_from_map_click(mapped,dict(last_object_clicked=dict(lat=53.6,lng=-113.5))))

    def test_map_precedes_views_and_click_updates_selection_without_replay(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'data_integration.py'),default_timeout=60).run()
        self.assertEqual(len(app.exception),0)
        headings=[s.value for s in app.subheader]
        self.assertLess(headings.index('Pipeline and defect locations'),headings.index('Selected profile'))
        row=app.session_state.prepared_profile_map.iloc[1]
        event=dict(all_drawings=[],last_object_clicked=dict(lat=float(row.Latitude),lng=float(row.Longitude)),
            last_object_clicked_tooltip=f"Profile {row['Profile ID']} — {row['Joint ID']}",last_object_clicked_count=1)
        with patch('profile_map.st_folium',return_value=event):
            app.run()
            self.assertEqual(app.session_state.exploration_selected_profile,str(row['Profile ID']))
            next(s for s in app.selectbox if s.label=='Feature profile').select_index(2).run()
            # An old marker event must not undo a later dropdown choice.
            self.assertEqual(app.session_state.exploration_selected_profile,'SYN-003')
            event['last_object_clicked_count']=2
            app.run()
            self.assertEqual(app.session_state.exploration_selected_profile,str(row['Profile ID']))
        self.assertEqual(len(app.exception),0)

    def setUp(self):
        self.route = [[53.5, -113.5], [53.5, -113.3]]

    @staticmethod
    def _summary(locations):
        return pd.DataFrame(
            [
                {
                    "Profile ID": f"P-{index}",
                    "Feature ID": f"F-{index}",
                    "Defect type": "Crack",
                    "Feature location (m)": location,
                    "Maximum depth (%WT)": 30.0,
                    "Maximum depth (mm)": 3.0,
                    "Profile length (mm)": 40.0,
                }
                for index, location in enumerate(locations, start=1)
            ]
        )

    def test_two_features_in_same_twelve_metre_interval_share_joint(self):
        mapped, outside, metadata = locate_profiles_on_route(
            self._summary([3.0, 9.0, 13.0]),
            self.route,
            route_start_chainage_m=0.0,
            joint_length_m=12.0,
        )

        self.assertTrue(outside.empty)
        self.assertEqual(
            mapped["Joint ID"].tolist(),
            ["Joint 00001", "Joint 00001", "Joint 00002"],
        )
        self.assertEqual(mapped["Features in joint"].tolist(), [2, 2, 1])
        self.assertEqual(metadata["defect_containing_joints"], 2)

    def test_route_start_chainage_controls_mapping_range(self):
        mapped, outside, metadata = locate_profiles_on_route(
            self._summary([900.0, 1010.0, 1020.0]),
            self.route,
            route_start_chainage_m=1000.0,
            joint_length_m=12.0,
        )

        self.assertEqual(mapped["Profile ID"].tolist(), ["P-2", "P-3"])
        self.assertEqual(outside["Profile ID"].tolist(), ["P-1"])
        self.assertEqual(metadata["mapped_features"], 2)

    def test_point_at_chainage_returns_route_midpoint(self):
        total = route_length_km(self.route)
        midpoint = point_at_chainage(self.route, total / 2)

        self.assertAlmostEqual(midpoint[0], 53.5, places=6)
        self.assertAlmostEqual(midpoint[1], -113.4, places=5)


if __name__ == "__main__":
    unittest.main()
