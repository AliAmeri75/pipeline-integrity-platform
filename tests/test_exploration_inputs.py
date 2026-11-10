"""Editable defect counts/sizes must reach maps and analyses without losing grids."""
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from assessment_project import (
    assessment_geometry, deterministic_project, project_signature, sample_project, validate_project,
)
from exploration_inputs import (
    apply_route, defect_register, project_from_register, read_defect_register,
    read_route, register_workbook, snap_to_route,
)
from planning_project import planning_handoff
from profile_map import point_at_chainage, route_length_km
from profile_visuals import measured_profile_figures, linked_measured_profile_html
from profile_data import summary_xlsx


class EditableInputTests(unittest.TestCase):
    def setUp(self):
        self.project = validate_project(sample_project())

    def test_unchanged_sizes_and_location_only_edits_preserve_measured_grids(self):
        table = defect_register(self.project)
        table.loc[0, 'chainage_m'] = 501.
        result = validate_project(project_from_register(self.project, table))
        for name, original in self.project['profiles'].items():
            pd.testing.assert_frame_equal(original, result['profiles'][name])
            self.assertFalse(result['profiles'][name].attrs.get('illustrative', False))
        self.assertEqual(result['summary']['Feature location (m)'].iloc[0], 501.)
        self.assertEqual(self.project['summary']['Feature location (m)'].iloc[0], 500.)

    def test_resize_add_delete_and_same_joint_reach_planning(self):
        table = defect_register(self.project).iloc[:2].copy()
        table.loc[0, ['chainage_m', 'depth_mm', 'length_mm']] = [501., 6., 150.]
        table.loc[1, 'chainage_m'] = 502.
        table.loc[len(table)] = ['C-new', 'Crack', 503., 2., 80., np.nan]
        result = validate_project(project_from_register(self.project, table))
        self.assertEqual(len(result['summary']), 3)
        self.assertNotIn('SYN-003', result['profiles'])
        self.assertTrue(result['profiles']['SYN-001'].attrs['illustrative'])
        self.assertFalse(result['profiles']['SYN-002'].attrs.get('illustrative', False))
        shared = planning_handoff(result)
        self.assertEqual(shared['cracked_joints'], 1)
        joint = next(j for j in shared['joints'] if j['cracks'])
        self.assertEqual(len(joint['cracks']), 3)
        self.assertEqual(joint['cracks'][0]['mean_depth'], 6.)
        self.assertEqual(joint['cracks'][0]['mean_length'], 150.)
        self.assertEqual(shared['total_joints'], 834)
        self.assertNotEqual(project_signature(result), project_signature(self.project))

    def test_illustrative_profile_agrees_with_entered_size_and_assessment_wall(self):
        table = defect_register(self.project)
        table.loc[0, ['depth_mm', 'length_mm']] = [5., 120.]
        result = validate_project(project_from_register(self.project, table))
        grid = result['profiles']['SYN-001']
        self.assertAlmostEqual(grid['Axial offset (mm)'].max(), 120.)
        self.assertAlmostEqual(grid['Depth (%WT)'].max() / 100 * 11.8, 5.)
        result['segments'].loc[0, 'wall_thickness_mm'] = 15.
        summary, profiles = assessment_geometry(result)
        row = summary.iloc[0]
        self.assertAlmostEqual(profiles['SYN-001']['Depth (%WT)'].max() / 100 * row['Wall thickness (mm)'], 5.)
        self.assertTrue(profiles['SYN-001'].attrs['illustrative'])
        figures = measured_profile_figures(grid, 11.8, 'SYN-001')
        self.assertIn('Illustrative', figures[0].layout.title.text)
        self.assertIn('Linked illustrative-profile', linked_measured_profile_html(grid, 11.8, 'SYN-001'))
        result['segments'].loc[0, 'wall_thickness_mm'] = 11.8
        assessed = deterministic_project(result)
        self.assertAlmostEqual(assessed['Defect depth (mm)'].iloc[0], 5.)

    def test_csv_excel_and_previous_static_planner_gps_format(self):
        expected = defect_register(self.project)
        for content, name in [
                (expected.to_csv(index=False).encode(), 'defects.csv'),
                (register_workbook(expected), 'defects.xlsx')]:
            parsed = read_defect_register(content, name, self.project['route'])
            pd.testing.assert_frame_equal(parsed, expected, check_dtype=False)
        locations = [point_at_chainage(self.project['route'], distance) for distance in [.501, .502]]
        gps = pd.DataFrame({'crack_id': ['001', '002'],
            'latitude': [p[0] for p in locations], 'longitude': [p[1] for p in locations],
            'depth_mm': [3., 4.], 'length_mm': [50., 60.]})
        parsed = read_defect_register(gps.to_csv(index=False).encode(), 'old_cracks.csv', self.project['route'])
        self.assertEqual(parsed.defect_id.tolist(), ['001', '002'])
        np.testing.assert_allclose(parsed.chainage_m, [501., 502.], atol=.01)
        self.assertLess(parsed.attrs['maximum_gps_offset_m'], .01)
        handoff = planning_handoff(validate_project(project_from_register(self.project, parsed)))
        self.assertEqual(handoff['cracked_joints'], 1)

    def test_register_rejects_duplicate_ids_incomplete_sizes_and_outside_chainages(self):
        for column, value in [('defect_id', 'SYN-002'), ('depth_mm', -1.),
                              ('length_mm', np.nan), ('chainage_m', 10001.)]:
            data = defect_register(self.project)
            data.loc[0, column] = value
            with self.assertRaises(ValueError):
                project_from_register(self.project, data)
        self.assertEqual(len(self.project['summary']), 3)

    def test_summary_export_handles_blank_metadata_and_an_empty_table(self):
        table = pd.DataFrame({'Profile ID': ['C1'], 'GW ID': [np.nan]})
        for data in [table, table.iloc[:0]]:
            self.assertTrue(summary_xlsx(data).startswith(b'PK'))

    def test_corrosion_width_required_and_depth_kept_separate_from_dent_displacement(self):
        table = defect_register(self.project).iloc[:1].copy()
        table['defect_type'] = 'Corrosion / metal loss'
        with self.assertRaisesRegex(ValueError, 'width'):
            project_from_register(self.project, table)
        table['width_mm'] = 20.
        result = validate_project(project_from_register(self.project, table))
        self.assertEqual(result['summary']['Profile width (mm)'].iloc[0], 20.)
        table['defect_type'] = 'Dent'
        with self.assertRaisesRegex(ValueError, 'Dent register'):
            project_from_register(self.project, table)

    def test_route_imports_manual_tables_geojson_and_feature_collection(self):
        route = self.project['route']
        geometry = dict(type='LineString', coordinates=[[lon, lat] for lat, lon in route])
        feature = dict(type='Feature', properties={}, geometry=geometry)
        for doc in [geometry, feature, dict(type='FeatureCollection', features=[feature])]:
            self.assertEqual(read_route(json.dumps(doc).encode(), 'route.geojson'), route)
        table = pd.DataFrame(route, columns=['latitude', 'longitude'])
        self.assertEqual(read_route(table.to_csv(index=False).encode(), 'route.csv'), route)
        output = io.BytesIO()
        table.to_excel(output, sheet_name='Route', index=False)
        parsed = read_route(output.getvalue(), 'route.xlsx')
        np.testing.assert_allclose(parsed, route)
        with self.assertRaises(ValueError):
            read_route(b'latitude,longitude\n999,0\n1,0', 'bad.csv')
        with self.assertRaises(ValueError):
            read_route(b'latitude,longitude\n1,0\n1,0', 'bad.csv')

    def test_new_route_preserves_properties_and_fits_coverage_without_moving_defects(self):
        route = deepcopy(self.project['route'])
        route.append([53.6, -113.3])
        result = validate_project(apply_route(self.project, route))
        self.assertAlmostEqual(result['segments'].end_km.iloc[-1], route_length_km(route))
        self.assertEqual(result['segments'].wall_thickness_mm.tolist(), self.project['segments'].wall_thickness_mm.tolist())
        self.assertEqual(result['summary']['Feature location (m)'].tolist(), [500., 4500., 8500.])
        self.assertEqual(len(self.project['route']), len(route) - 1)
        chainage, offset = snap_to_route(route, *point_at_chainage(route, .5))
        self.assertAlmostEqual(chainage, 500., places=3)
        self.assertLess(offset, .01)


class EditableInputUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'),
                                default_timeout=60).run().switch_page('data_integration.py').run()

    def test_add_save_navigate_and_reopen_keeps_count_and_sizes(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio[0].value, 'Enter / edit defects')
        next(n for n in app.number_input if n.label == 'New defect depth (mm)').set_value(6.)
        next(n for n in app.number_input if n.label == 'New defect length (mm)').set_value(150.)
        next(n for n in app.number_input if n.label == 'New defect distance from pipeline start (m)').set_value(501.)
        next(b for b in app.button if b.label == 'Add defect at this distance').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.project_draft['summary']), 4)
        next(b for b in app.button if b.label == 'Save shared dataset for all analyses').click().run()
        self.assertFalse(app.exception)
        saved = app.session_state.assessment_project
        sig = project_signature(saved)
        handoff = planning_handoff(saved)
        self.assertEqual(handoff['initial_cracks'], 4)
        self.assertEqual(handoff['cracked_joints'], 3)
        added = saved['summary'].iloc[-1]
        self.assertEqual(added['Maximum depth (mm)'], 6.)
        self.assertEqual(added['Profile length (mm)'], 150.)
        app.switch_page('inspection_project.py').run()
        self.assertFalse(app.exception)
        app.switch_page('data_integration.py').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.project_draft['summary']), 4)
        self.assertEqual(project_signature(app.session_state.assessment_project), sig)

    def test_table_edits_and_deletions_change_map_and_save(self):
        app = self.app()
        token = app.session_state.project_source_token
        key = f'project_defect_register_{token}_0'
        app.session_state[key] = {'edited_rows': {0: {'depth_mm': 5., 'length_mm': 140.}},
                                  'added_rows': [], 'deleted_rows': [1]}
        app.run()
        self.assertFalse(app.exception)
        draft = app.session_state.project_draft
        self.assertEqual(len(draft['summary']), 2)
        self.assertEqual(draft['summary']['Maximum depth (mm)'].iloc[0], 5.)
        self.assertEqual(len(app.session_state.prepared_profile_map), 2)
        next(b for b in app.button if b.label == 'Save shared dataset for all analyses').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(planning_handoff(app.session_state.assessment_project)['initial_cracks'], 2)

    def test_pin_add_is_processed_once_and_uses_current_dimensions(self):
        app = self.app()
        lat, lon = point_at_chainage(app.session_state.project_draft['route'], .501)
        event = dict(all_drawings=[dict(type='Feature', geometry=dict(type='Point', coordinates=[lon, lat]))])
        with patch('profile_map.st_folium', return_value=event):
            # The new map revision clears the drawn pin in a browser. Supply it
            # once here, followed by the clean component state after the rerun.
            with patch('profile_map.st_folium', side_effect=[event, {}]):
                app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.project_draft['summary']), 4)
        app.run()
        self.assertEqual(len(app.session_state.project_draft['summary']), 4)


if __name__ == '__main__':
    unittest.main()
