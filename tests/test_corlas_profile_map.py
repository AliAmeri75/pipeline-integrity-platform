import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from education.pof_model import POFInputs,corlas_failure_pressure
from corlas_profile_map import evaluate_profile_grid,minimum_grid_result,corlas_depth_pressure_figure


class CorlasProfileMapTests(unittest.TestCase):
    def setUp(self):
        self.profile=pd.DataFrame({'Axial offset (mm)':[0.,10.,0.,10.],
            'Circumferential offset (mm)':[0.,0.,5.,5.],'Depth (%WT)':[10.,20.,30.,40.]})
        self.base=POFInputs()

    def test_each_depth_matches_direct_corlas(self):
        cells=evaluate_profile_grid(self.profile,self.base,6.35,508.,40.)
        self.assertEqual(len(cells),4)
        self.assertTrue((cells.Status=='Calculated').all())
        for _,row in cells.iterrows():
            expected=corlas_failure_pressure(replace(self.base,diameter_in=20.,wall_thickness_mm=6.35,
                flaw_length_mm=40.,flaw_depth_mm=row['Measured depth (mm)']))['failure_pressure_psi']
            self.assertAlmostEqual(row['Burst resistance pressure (psi)'],expected)
            self.assertAlmostEqual(row.FPR,expected/self.base.operating_pressure_psi)
        self.assertTrue((cells['Profile length used (mm)']==40.).all())
        self.assertAlmostEqual(minimum_grid_result(cells)['FPR'],cells.FPR.min())

    def test_pressure_changes_fpr_not_resistance(self):
        a=evaluate_profile_grid(self.profile,self.base,6.35,508.,40.)
        b=evaluate_profile_grid(self.profile,replace(self.base,operating_pressure_psi=2*self.base.operating_pressure_psi),6.35,508.,40.)
        np.testing.assert_allclose(a['Burst resistance pressure (psi)'],b['Burst resistance pressure (psi)'])
        np.testing.assert_allclose(a.FPR,2*b.FPR)

    def test_invalid_and_through_wall_points_are_not_fabricated(self):
        self.profile['Depth (%WT)']=[0.,100.,-1.,np.nan]
        cells=evaluate_profile_grid(self.profile,self.base,6.35,508.,40.)
        self.assertTrue(cells['Burst resistance pressure (psi)'].isna().all())
        self.assertIsNone(minimum_grid_result(cells))
        self.assertIn('Through-wall depth: CorLAS not applicable',cells.Status.tolist())
        self.assertIn('No finite measurement',cells.Status.tolist())

    def test_heatmaps_use_same_coordinates_and_numeric_pressure(self):
        cells=evaluate_profile_grid(self.profile,self.base,6.35,508.,40.)
        figure=corlas_depth_pressure_figure(cells,'C1')
        depth,pressure=figure.data[:2]
        self.assertEqual(list(depth.x),list(pressure.x))
        self.assertEqual(list(depth.y),list(pressure.y))
        self.assertEqual(np.asarray(pressure.z).shape,(2,2))
        self.assertEqual(len(figure.data),4)  # Two heatmaps and their minimum markers.

    def test_geometry_required(self):
        for wall in (None,0.,np.nan):
            with self.assertRaises(ValueError):
                evaluate_profile_grid(self.profile,self.base,wall,508.,40.)
