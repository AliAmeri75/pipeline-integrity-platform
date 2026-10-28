import unittest

import numpy as np

from profile_data import parse_profile_workbook, synthetic_sample_workbook
from profile_visuals import (
    linked_measured_profile_html,
    measured_depth_grid,
    measured_profile_figures,
    measured_profile_on_pipe_figure,
)


class ProfileVisualTests(unittest.TestCase):
    def setUp(self):
        self.summary, self.profiles = parse_profile_workbook(
            synthetic_sample_workbook()
        )
        self.profile_id = str(self.summary.loc[0, "Profile ID"])
        self.profile = self.profiles[self.profile_id]
        self.wall = float(self.summary.loc[0, "Wall thickness (mm)"])

    def test_measured_grid_converts_percent_wall_to_millimetres(self):
        _, _, depth_mm, unit = measured_depth_grid(self.profile, self.wall)

        self.assertEqual(unit, "mm")
        expected_maximum = (
            float(self.profile["Depth (%WT)"].max()) * self.wall / 100.0
        )
        self.assertAlmostEqual(float(np.nanmax(depth_mm)), expected_maximum)

    def test_measured_figures_use_exact_grid_and_linked_hover(self):
        heatmap, surface, x_values, y_values, depth, unit = measured_profile_figures(
            self.profile, self.wall, self.profile_id
        )
        html = linked_measured_profile_html(
            self.profile, self.wall, self.profile_id
        )

        self.assertEqual(heatmap.data[0].type, "heatmap")
        self.assertEqual(surface.data[0].type, "surface")
        self.assertEqual(depth.shape, (len(y_values), len(x_values)))
        self.assertEqual(unit, "mm")
        self.assertIn('mapDiv.on("plotly_hover"', html)
        self.assertIn('surfaceDiv.on("plotly_hover"', html)
        self.assertIn("Plotly.restyle(surfaceDiv", html)

    def test_measured_profile_can_be_shown_on_pipe_surface(self):
        figure = measured_profile_on_pipe_figure(
            self.profile,
            self.wall,
            float(self.summary.loc[0, "Outside diameter (mm)"]),
            self.profile_id,
            "Crack",
        )

        self.assertEqual([trace.type for trace in figure.data], ["surface", "surface"])
        self.assertIn("profile on pipe", figure.layout.title.text)


if __name__ == "__main__":
    unittest.main()
