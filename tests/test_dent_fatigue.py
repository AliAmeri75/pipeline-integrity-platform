import math
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from dent_fatigue_model import (read_scada,pressure_history,count_cycles,automatic_scf,fatigue_curve,A_MEAN,M)

SAMPLE=Path(__file__).resolve().parents[1]/'samples'/'ALIRIM_Synthetic_SCADA_7_Days.csv'

class FatigueTests(unittest.TestCase):
    def test_sample_and_units(self):
        data=read_scada(SAMPLE.read_bytes(),SAMPLE.name)
        h,y,c=pressure_history(data,'timestamp_utc','upstream_pressure_MPa_gauge')
        self.assertEqual(len(h),10080);self.assertEqual(c,60);self.assertAlmostEqual(y*365.25,7)
        psi=data.copy();psi['p']=psi.upstream_pressure_MPa_gauge/.006894757293168
        hp,_,_=pressure_history(psi,'timestamp_utc','p','psi')
        np.testing.assert_allclose(h.pressure_MPa,hp.pressure_MPa)

    def test_excel_upload_reader(self):
        from io import BytesIO
        from openpyxl import Workbook
        w=Workbook();sheet=w.active
        sheet.append(['timestamp_utc','pressure'])
        for timestamp,value in [('2026-01-01T00:00:00Z',4),('2026-01-01T00:01:00Z',5),('2026-01-01T00:02:00Z',4)]:
            sheet.append([timestamp,value])
        stream=BytesIO();w.save(stream)
        data=read_scada(stream.getvalue(),'upload.xlsx')
        h,_,_=pressure_history(data,'timestamp_utc','pressure')
        self.assertEqual(count_cycles(h.pressure_MPa)['count'].sum(),1)

    def test_invalid_history_not_bridged(self):
        data=read_scada(SAMPLE.read_bytes(),SAMPLE.name).iloc[:6].copy()
        for bad in [data.drop(index=2),data.iloc[::-1],pd.concat([data.iloc[:2],data.iloc[1:]])]:
            with self.assertRaises(ValueError):pressure_history(bad,'timestamp_utc','upstream_pressure_MPa_gauge')
        data.loc[2,'upstream_pressure_MPa_gauge']=np.nan
        with self.assertRaises(ValueError):pressure_history(data,'timestamp_utc','upstream_pressure_MPa_gauge')

    def test_rainflow_half_cycles(self):
        cycles=count_cycles([0,2,0,2,0])
        self.assertTrue((cycles.range_MPa==2).all());self.assertEqual(cycles['count'].sum(),2)
        self.assertTrue(count_cycles([1,1,1]).empty)
        self.assertTrue(count_cycles([0,2,0],3).empty)
        self.assertEqual(count_cycles([0,0,2,2,0])['count'].sum(),1)

    def test_hand_damage_probability_and_scale(self):
        c=count_cycles([0,2,0,2,0]);K=4;D=400;t=8
        result,rate=fatigue_curve(c,1,D,t,K,[0,1,2])
        expected=2*(K*2*D/(2*t))**M
        self.assertAlmostEqual(rate,expected)
        self.assertAlmostEqual(result.damage_at_mean_A.iloc[1],expected/A_MEAN)
        sa2=math.log1p(.45**2);sc2=math.log1p(.3**2)
        z=(math.log(expected)-math.log(A_MEAN)+(sa2+sc2)/2)/math.sqrt(sa2+sc2)
        self.assertAlmostEqual(result.cumulative_fatigue_probability.iloc[1],.5*math.erfc(-z/math.sqrt(2)))
        self.assertTrue((np.diff(result.cumulative_fatigue_probability)>=0).all())
        _,more=fatigue_curve(c,1,D,t,K*2,[0,1])
        self.assertAlmostEqual(more/rate,2**M)

    def test_published_example_beta(self):
        # He–Zhou Table4 Example1, discharge spectrum moment at year5, 5% OD dent.
        K=automatic_scf(406,7,.05*406)
        rate=13875*K**M*1.47e5
        variance=math.log1p(.45**2)+math.log1p(.3**2)
        beta=(math.log(3.61e13)-variance/2-math.log(5*rate))/math.sqrt(variance)
        self.assertAlmostEqual(beta,4.82,delta=.04)

    def test_scf_range_and_combination(self):
        self.assertAlmostEqual(automatic_scf(406,7,20.3),1+1.7169*(406/7)**.8*.05**.7)
        with self.assertRaises(ValueError):automatic_scf(914.4,11.8,30)
        with self.assertRaises(ValueError):automatic_scf(406,7,1)

    def test_zero_cycles_and_deterministic_capacity(self):
        c=count_cycles([1,1,1]);out,rate=fatigue_curve(c,1,400,8,4,[0,1,2])
        self.assertEqual(rate,0);self.assertTrue((out.cumulative_fatigue_probability==0).all())
        c=count_cycles([0,2,0]);_,rate=fatigue_curve(c,1,400,8,4,[0,1])
        out,_=fatigue_curve(c,1,400,8,4,[0,1,2],a_mean=rate,a_cov=0,critical_cov=0)
        self.assertEqual(out.cumulative_fatigue_probability.tolist(),[0,1,1])

class FatigueUITests(unittest.TestCase):
    def test_sample_workflow_and_upload_option(self):
        from streamlit.testing.v1 import AppTest
        from assessment_project import sample_project
        from exploration_datasets import sample_dent_register
        p=sample_project();p['dent_register']=sample_dent_register()
        script='from dent_fatigue_ui import render_dent_fatigue\nimport streamlit as st\nrender_dent_fatigue(st.session_state["p"])'
        app=AppTest.from_string(script,default_timeout=60);app.session_state['p']=p;app.run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('Automatic SCF requires' in x.value for x in app.warning))
        app.radio(key='fatigue_scf_method').set_value('Reviewed user-supplied SCF').run()
        app.text_input(key='fatigue_scf_source').set_value('Synthetic demonstration factor only').run()
        app.checkbox(key='fatigue_reviewed').check().run();app.checkbox(key='fatigue_stationary').check().run()
        app.button(key='fatigue_run').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any(m.label=='Cumulative fatigue probability at horizon' for m in app.metric))
        app.radio(key='fatigue_source').set_value('Upload SCADA CSV / Excel').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.metric),0) # previous result not shown with changed source

if __name__=='__main__':unittest.main()
