import math
import unittest
from dataclasses import replace
import numpy as np
from consequence_model import (PIR,THERMAL,RADIUS,HazardScenario,potential_impact_radius,
    thermal_radius,assess_consequences,consequence_risk_inputs,scenario_radius)
from reliability_model import consequence_template,fixed_section_risk,import_feature_reliability
import pandas as pd


class ConsequenceTests(unittest.TestCase):
    def setUp(self):
        self.route = [[53.5,-113.5],[53.5,-113.48]]
        self.data = consequence_template(self.route)[['section_id','start_km','end_km']]
        self.data['population_density_per_km2'] = 1000.
        self.data['asset_value_per_m2'] = 10.
        self.data['burst_fixed_cost'],self.data['leak_fixed_cost'] = 100.,50.
        self.burst = HazardScenario(model=RADIUS,radius_m=100.,ignition_probability=.5,damage_fraction=.2)
        self.leak = HazardScenario(model=RADIUS,radius_m=20.,ignition_probability=0.)

    def test_pir_formula_and_units(self):
        self.assertAlmostEqual(potential_impact_radius(1000,20),.69*20*math.sqrt(1000)*.3048)
        self.assertAlmostEqual(potential_impact_radius(4000,20),2*potential_impact_radius(1000,20))

    def test_thermal_power_and_flux_units(self):
        self.assertAlmostEqual(thermal_radius(100,.2,5),math.sqrt(.2*100000/(4*math.pi*5)))
        self.assertAlmostEqual(thermal_radius(400,.2,5),2*thermal_radius(100,.2,5))

    def test_density_ignition_and_cost(self):
        results = assess_consequences(self.route,self.data,self.burst,self.leak)
        r = results.iloc[0]
        self.assertAlmostEqual(r.burst_people_in_footprint,1000*math.pi*100**2/1e6)
        self.assertAlmostEqual(r.burst_exposure_consequence,.5*r.burst_people_in_footprint)
        self.assertAlmostEqual(r.burst_economic_consequence,100+.5*math.pi*100**2*10*.2)
        self.assertEqual(r.leak_exposure_consequence,0.)
        self.assertEqual(r.leak_economic_consequence,50.)
        self.assertIn('burst_radius_m',results)

    def test_per_section_overrides_and_risk_connection(self):
        self.data['burst_radius_m'] = [100.,200.]
        results = assess_consequences(self.route,self.data,self.burst,self.leak)
        self.assertAlmostEqual(results.burst_exposure_consequence.iloc[1],4*results.burst_exposure_consequence.iloc[0])
        consequences = consequence_risk_inputs(results,'exposure')
        features = pd.DataFrame(dict(feature_id=['C1'],defect_type=['Crack'],chainage_km=[.5],burst_pf=[.1],leak_pf=[.01]))
        assessed,_ = import_feature_reliability(features,self.route,12)
        risk = fixed_section_risk(self.route,assessed,consequences,.001,.01)
        self.assertAlmostEqual(risk.total_risk.iloc[0],.1*results.burst_exposure_consequence.iloc[0])
        self.assertEqual(risk.total_risk.iloc[1],0.)

    def test_invalid_applicability_and_inputs(self):
        for config,mode in [(HazardScenario(natural_gas=False),'burst'),(HazardScenario(),'leak')]:
            with self.assertRaises(ValueError):
                scenario_radius(config,mode)
        with self.assertRaises(ValueError):
            thermal_radius(100,.2,0)
        for invalid in [self.data.assign(population_density_per_km2=np.nan),
                        self.data.assign(asset_value_per_m2=-1),self.data.iloc[:1],
                        self.data.assign(start_km=100),self.data.assign(burst_radius_m=np.inf)]:
            with self.assertRaises(ValueError):
                assess_consequences(self.route,invalid,self.burst,self.leak)
        with self.assertRaises(ValueError):
            assess_consequences(self.route,self.data,replace(self.burst,ignition_probability=1.1),self.leak)
