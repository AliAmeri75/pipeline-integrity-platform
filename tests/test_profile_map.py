import unittest

import pandas as pd

from profile_map import locate_profiles_on_route, point_at_chainage, route_length_km


class ProfileMapTests(unittest.TestCase):
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
