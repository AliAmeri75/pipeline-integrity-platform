"""Threat-specific presentation; model registries live in the model modules."""
from copy import deepcopy
import hashlib
import html
import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium
from assessment_project import project_signature,assessment_geometry
from academic_figures import academic_style
from map_presentation import readable_map_overlays
from profile_map import point_at_chainage,route_length_km


def threat_project(project,threat):
    """Subset only the defect register; leave route/property segments unchanged."""
    p=deepcopy(project)
    types=['Corrosion','Corrosion / metal loss'] if threat=='Corrosion' else [threat]
    p['summary']=p['summary'][p['summary']['Defect type'].isin(types)].copy()
    ids=set(p['summary']['Profile ID'].astype(str))
    p['profiles']={k:v for k,v in p['profiles'].items() if str(k) in ids}
    p['source']=project['source']+' · '+threat+' records only'
    return p


def _csv(label,table,name):
    st.download_button(label,table.to_csv(index=False),name,'text/csv',key=name)


def _curve(data,x,y,title,ylabel):
    figure=go.Figure(go.Scatter(x=data[x],y=data[y],mode='lines+markers',name=ylabel))
    figure.update_layout(title=title,xaxis_title='Distance from route start (km)',yaxis_title=ylabel)
    return academic_style(figure)


def _corrosion_results(project,assessed,joints,sections,signature):
    from reliability_analysis import profile_figure,result_map
    unit=project['consequence_unit'] or 'UNKNOWN unit'
    st.caption('Assessment-condition POF, not annual failure probability. Pipe properties and pressure are shared '
        'within each joint/property group; sizing draws and different groups are independent. '
        'Joint probability uses sample-wise unions, preserving multiple defects in one joint. '
        'These are isolated-defect pressure calculations, not physical interaction calculations. '
        'No growth, inspection or repair is simulated. Zero observed events does not prove zero probability; '
        'the approximate 95% upper bound with zero events is 3/N.')
    for columns,title,label in [
        ([('burst_pf','Burst'),('leak_pf','Leakage')],'Corrosion POF versus distance','Assessment-condition probability'),
        ([('burst_consequence','Burst'),('leak_consequence','Leakage')],'Consequence versus distance','Conditional loss ('+unit+')'),
        ([('burst_risk','Burst'),('leak_risk','Leakage'),('total_risk','Total')],'Corrosion risk versus distance','Expected loss ('+unit+' per assessment)')]:
        st.plotly_chart(profile_figure(sections,columns,title,label),width='stretch',theme=None)
    st.caption('Risk = burst Pf × burst consequence + leakage Pf × leakage consequence. '
        'Section values describe event probability, not expected incident counts. '
        'No recorded corrosion gives zero modeled contribution, not demonstrated safety. '
        'Zero POF is omitted on logarithmic plots; values remain in tables.')
    if sections[['burst_consequence','leak_consequence']].isna().any().any():
        st.warning('Missing conditional consequences remain UNKNOWN; corresponding risks are not set to zero.')
    view=st.radio('Corrosion map view',['POF','Consequence','Risk'],horizontal=True,key='corr_map_view')
    modes=['Burst','Leakage','Total'] if view=='Risk' else ['Burst','Leakage']
    mode=st.selectbox('Corrosion map failure mode',modes,key='corr_map_mode_'+view)
    column={'Burst':'burst','Leakage':'leak','Total':'total'}[mode]+'_'+{'POF':'pf','Consequence':'consequence','Risk':'risk'}[view]
    st.caption('Map colours are relative to the selected layer, not regulatory categories. Grey = UNKNOWN.')
    st_folium(result_map(project['route'],assessed,sections,column,'Corrosion '+mode+' '+view),
        height=450,width=1100,returned_objects=[],key='corrosion_map_'+signature+column)
    for name,table in [('defects',assessed),('joint_segments',joints),('segments',sections)]:
        st.markdown('**Corrosion '+name.replace('_',' ')+'**')
        st.dataframe(table,hide_index=True,width='stretch')
        _csv('Download corrosion '+name,table,'corrosion_'+name+'.csv')


def render_corrosion_workspace(project):
    from corrosion_assessment_model import (CORROSION_MODELS,deterministic_corrosion,
        corrosion_specs,corrosion_reliability,PARAMETERS)
    from consequence_assessment import render_consequence_assessment
    p=threat_project(project,'Corrosion')
    st.info('Using the saved route, corrosion profiles and their segment properties from Data Exploration.')
    model=st.selectbox('Corrosion resistance model',list(CORROSION_MODELS),
        format_func=lambda model_id: 'Isolated longitudinal metal loss — nominal pressure screening'
            if model_id=='isolated_metal_loss' else model_id)
    st.caption('Nominal pressure equation used in DNV-RP-F101 literature; this is not a full DNV assessment. '
        'Isolated, blunt longitudinal metal loss under internal differential pressure only; '
        'no cracks, dents, interacting defects, additional loads, code factors or acceptance decision. '
        'Depth ≤85% WT. Confirm axial length and applicability before running.')
    st.markdown('[Model equation and scope](https://equinor.github.io/neqsim/process/mechanical_design/dnv_rp_f101_corroded_pipeline) '
        '· [DNV publisher scope](https://www.dnv.com/energy/standards-guidelines/dnv-rp-f101-corroded-pipelines/)')
    applicable=st.checkbox('I confirm these are isolated longitudinal metal-loss defects without associated cracks or dents, '
        'and the pressure/geometry inputs are appropriate for this screening model.',key='corr_applicable')
    det,rel,fatigue,con=st.tabs(['Deterministic Analysis','Risk & Reliability','SCADA & Fatigue','Consequence Assessment'])
    with det:
        if p['summary'].empty:
            st.info('No corrosion profiles are saved. Upload metal-loss profiles in Data Exploration, '
                'review the defect types, then save the shared dataset.')
        else:
            st.dataframe(p['summary'],hide_index=True,width='stretch')
            if st.button('Run Corrosion Deterministic Analysis',disabled=not applicable):
                st.session_state.corrosion_det=(project_signature(p)+model,deterministic_corrosion(p,model))
            saved=st.session_state.get('corrosion_det')
            if applicable and saved and saved[0]==project_signature(p)+model:
                result=saved[1]
                good=result[result.Status=='Calculated']
                st.dataframe(result,hide_index=True,width='stretch')
                st.caption('FPR = nominal burst resistance / operating differential pressure. '
                    'FPR > 1 is not a code acceptance or safety decision. Out-of-domain profiles remain unavailable.')
                if not good.empty:
                    st.metric('Minimum calculated corrosion FPR',f'{good.FPR.min():.3f}')
                    st.plotly_chart(_curve(good.sort_values('Distance from start (km)'),
                        'Distance from start (km)','FPR','Corrosion FPR versus distance','FPR'),width='stretch',theme=None)
                _csv('Download corrosion deterministic results',result,'corrosion_deterministic.csv')
            selected=st.selectbox('Corrosion profile — 2D/3D',p['summary']['Profile ID'].astype(str),key='corr_profile')
            summary,profiles=assessment_geometry(p)
            row=summary[summary['Profile ID'].astype(str)==selected].iloc[0]
            from profile_visuals import measured_profile_on_pipe_figure,render_linked_measured_profile
            st.plotly_chart(measured_profile_on_pipe_figure(profiles[selected],row['Wall thickness (mm)'],
                row['Outside diameter (mm)'],selected,'Corrosion / metal loss'),width='stretch',key='corrosion_pipe')
            with st.expander('Linked measured 2D and 3D corrosion profile'):
                render_linked_measured_profile(profiles[selected],row['Wall thickness (mm)'],selected)
    with rel:
        if p['summary'].empty:
            st.info('Save corrosion records in Data Exploration to assess reliability and risk.')
        else:
            st.caption('Review the shared pipe and sizing distributions. Their defaults originated in the research '
                'crack workflow and are NOT corrosion calibration. The corrosion model factor starts at 1.0, '
                'deterministic: the CorLAS bias/SD is not reused. UTS controls this model; Charpy energy, '
                'yield strength and elastic modulus are not used by it.')
            specs=corrosion_specs(p)
            settings=[]
            for sid,rows in specs.items():
                for n in PARAMETERS:
                    item=rows[n]
                    settings.append(dict(section_id=sid,parameter=n,mean=item.get('mean',np.nan),
                        distribution=item['distribution'],std=item['std']))
            with st.expander('Review shared inputs and corrosion model uncertainty',expanded=True):
                st.dataframe(pd.DataFrame(settings),hide_index=True,width='stretch')
                factor_mean=st.number_input('Corrosion model factor mean',min_value=.001,value=1.,key='corr_factor_mean')
                factor_sd=st.number_input('Corrosion model factor standard deviation',min_value=0.,value=0.,key='corr_factor_sd')
                factor_distribution=st.selectbox('Corrosion model factor distribution',
                    ['Deterministic','Normal','Lognormal','Gumbel'],key='corr_factor_dist')
                st.caption('Model factor multiplies nominal resistance. Supply a justified calibration; 1.0 is uncalibrated.')
            for rows in specs.values():
                rows['model_factor']=dict(mean=factor_mean,std=factor_sd,distribution=factor_distribution)
            reviewed=st.checkbox('I have reviewed the corrosion sizing/pipe distributions and model-factor assumptions.',key='corr_uncertainty_review')
            samples=st.number_input('Corrosion Monte Carlo samples',100,10000,1000,100,key='corr_n')
            seed=st.number_input('Corrosion random seed',0,1000000,7,key='corr_seed')
            signature=hashlib.sha256((project_signature(p)+repr((specs,samples,seed,model))).encode()).hexdigest()
            if st.button('Run Corrosion Reliability Analysis',disabled=not (applicable and reviewed)):
                try:
                    with st.spinner('Evaluating corrosion reliability…'):
                        st.session_state.corrosion_rel=(signature,corrosion_reliability(p,specs,int(samples),int(seed),model))
                except (ValueError,KeyError,TypeError) as error: st.error(str(error))
            saved=st.session_state.get('corrosion_rel')
            if applicable and reviewed and saved and saved[0]==signature:
                _corrosion_results(p,*saved[1],signature)
            elif saved:
                st.info('Inputs or applicability changed. Run the corrosion reliability analysis again.')
    with con:
        render_consequence_assessment(project['route'],segment_table=project['segments'])


def _dent_map(project,results,column,label,sections=None):
    from branca.colormap import LinearColormap
    m=folium.Map(location=project['route'][0],tiles='OpenStreetMap')
    folium.PolyLine(project['route'],color='#667085',weight=5,tooltip='Shared pipeline route').add_to(m)
    values=pd.to_numeric((sections if sections is not None else results)[column],errors='coerce')
    maximum=float(values.max())
    scale=LinearColormap(['#287049','#dfb649','#b42318'],vmin=0,
        vmax=maximum if np.isfinite(maximum) and maximum>0 else 1.,caption=label+' — relative colour scale')
    scale.add_to(m)
    if sections is not None:
        vertices=[route_length_km(project['route'][:i+1]) for i in range(1,len(project['route']))]
        for row in sections.itertuples():
            value=float(getattr(row,column))
            chainages=[row.start_km]+[v for v in vertices if row.start_km<v<row.end_km]+[row.end_km]
            folium.PolyLine([point_at_chainage(project['route'],d) for d in chainages],
                weight=7,color=scale(value) if np.isfinite(value) else '#94a3b8',
                tooltip=f'Segment {row.section_id}: '+label+' = '+(f'{value:.4g}' if np.isfinite(value) else 'UNKNOWN')).add_to(m)
    for row in results.itertuples():
        value=float(getattr(row,column))
        colour=scale(value) if np.isfinite(value) else '#94a3b8'
        name=html.escape(str(row.dent_id))
        folium.CircleMarker(point_at_chainage(project['route'],row.chainage_m/1000),radius=8,
            color=colour,fill=True,tooltip=f'{name}: {label} = {value:.4g}' if np.isfinite(value) else f'{name}: UNKNOWN').add_to(m)
    m.fit_bounds(project['route'])
    return readable_map_overlays(m)


def render_dent_workspace(project):
    from dent_assessment_model import DENT_MODELS,empty_dent_register,dent_geometry,dent_reliability,dent_shape_figure
    from consequence_assessment import render_consequence_assessment
    p=deepcopy(project)
    st.info('Dents use the same saved route and segment OD/WT. Their displacement and measured curvature radii '
        'are entered in Data Exploration → Shared dataset → Dent register.')
    st.caption('Dent displacement is not metal loss. The starting model estimates geometric strain, not residual '
        'burst pressure. A separate SCADA fatigue tab is available for plain, smooth, unrestrained dents; re-rounding and interacting crack/corrosion models are not included.')
    st.markdown('[PHMSA Mechanical Damage report, section 7.2.3, equations 2–6 (PDF p.97)]'
        '(https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/technical-resources/pipeline/gas-distribution-integrity-management/65991/mechanicaldamagefinalreport.pdf)')
    model=st.selectbox('Dent assessment model',list(DENT_MODELS),format_func=lambda model_id:
        'PHMSA geometric dent-strain screening' if model_id=='phmsa_geometric_strain' else model_id)
    criterion=st.number_input('Selected strain criterion (%)',.01,99.,6.,.1,key='dent_criterion')
    st.caption('6% is a historical strain-screening example, not an automatically applicable acceptance criterion '
        'or measured material failure capacity. Choose the criterion and uncertainty for your assessment.')
    confirmed=st.checkbox('I confirm the signed radii follow the referenced convention and the plain-dent '
        'geometry/criterion assumptions have been reviewed.',key='dent_confirmed')
    det,rel,fatigue,con=st.tabs(['Deterministic Analysis','Risk & Reliability','SCADA & Fatigue','Consequence Assessment'])
    dents=p.get('dent_register',empty_dent_register())
    with det:
        st.subheader('Dent strain and geometry')
        if dents.empty:
            st.info('No dents are saved. Add measured dent records in Data Exploration, then save the shared dataset.')
            template=pd.DataFrame([dict(dent_id='EXAMPLE-DENT-001',chainage_m=1000.,dent_depth_mm=15.,
                axial_length_mm=600.,circumferential_width_mm=300.,circumferential_radius_mm=-1500.,
                axial_radius_mm=2500.,associated_crack_or_metal_loss=False)])
            st.caption('The CSV below illustrates the column format; its numbers are synthetic, not measured geometry.')
            _csv('Download dent register column template',template,'dent_register_template.csv')
        elif confirmed:
            try:
                result=dent_geometry(p,criterion,model)
                st.dataframe(result,hide_index=True,width='stretch')
                valid=result.equivalent_strain_percent.dropna()
                if not valid.empty:st.metric('Maximum calculated equivalent dent strain',f'{valid.max():.3f}%')
                st.caption('FPR and burst pressure are unavailable for this strain model. Below-criterion '
                    'geometry does not demonstrate fatigue life or pipe acceptance. Combined defects are not evaluated.')
                selected=st.selectbox('Selected dent — idealized 3D view',result.dent_id,key='dent_selected')
                row=result.loc[result.dent_id==selected].iloc[0]
                st.plotly_chart(dent_shape_figure(row),width='stretch',key='dent_3d')
                st.caption('Illustrative Gaussian surface depression from depth, axial length and width; '
                    'it is not a reconstruction of the measured curvature field. Strain calculations use the '
                    'entered signed curvature radii independently. Denting does not remove wall material.')
                st.plotly_chart(_curve(result.assign(chainage_km=result.chainage_m/1000),'chainage_km',
                    'equivalent_strain_percent','Dent strain versus distance','Equivalent strain (%)'),width='stretch',theme=None)
                st_folium(_dent_map(p,result,'equivalent_strain_percent','Equivalent strain (%)'),
                    height=420,width=1100,returned_objects=[],key='dent_geom_map_'+project_signature(p)+str(criterion))
                _csv('Download dent deterministic results',result,'dent_deterministic.csv')
            except (ValueError,KeyError,TypeError) as error: st.error(str(error))
        else: st.info('Review the model applicability and signed curvature inputs to see calculated dent strains.')
    with rel:
        st.subheader('Dent limit-state reliability')
        st.caption('g = selected strain criterion − calculated strain demand. The Monte Carlo result is '
            'P(g ≤ 0): a strain-criterion exceedance probability. It is NOT calibrated burst/leakage POF or annual Pf. '
            'No separate burst or leakage numbers are invented.')
        cov=st.number_input('Dent geometry measurement coefficient of variation',0.,1.,0.,.01,key='dent_cov')
        capacity_sd=st.number_input('Strain criterion standard deviation (percentage points)',0.,50.,0.,.1,key='dent_capacity_sd')
        st.caption('Measurement uncertainty is positive lognormal with the chosen COV for D, WT, depth, length '
            'and radius magnitudes; curvature signs are preserved. Zero COV means deterministic geometry. '
            'OD/WT and criterion draws are shared within a nominal joint/property group; geometry draws are independent '
            'across dents. Other uncertainty families/correlations need a replacement sampling model.')
        samples=st.number_input('Dent Monte Carlo samples',100,10000,1000,100,key='dent_n')
        seed=st.number_input('Dent random seed',0,1000000,7,key='dent_seed')
        signature=hashlib.sha256((project_signature(p)+repr((model,criterion,cov,capacity_sd,samples,seed))).encode()).hexdigest()
        if st.button('Run Dent Reliability Analysis',disabled=not confirmed or dents.empty):
            try:
                st.session_state.dent_rel=(signature,dent_reliability(p,criterion,cov,capacity_sd,int(samples),int(seed),model))
            except (ValueError,KeyError,TypeError) as error:st.error(str(error))
        saved=st.session_state.get('dent_rel')
        if confirmed and saved and saved[0]==signature:
            assessed,joints,sections=saved[1]
            st.dataframe(assessed,hide_index=True,width='stretch')
            st.plotly_chart(_curve(assessed.assign(chainage_km=assessed.chainage_m/1000),
                'chainage_km','strain_criterion_probability','Dent strain-criterion probability versus distance',
                'Strain-criterion exceedance probability'),width='stretch',theme=None)
            st.caption('Zero observed exceedances do not prove zero probability (approximate 95% upper bound 3/N). '
                'A section without recorded dents has no modeled dent contribution, not demonstrated safety.')
            # This separate loss input must match the modeled event, not inherit burst or leakage losses.
            consequence=sections[['section_id','start_km','end_km']].copy()
            consequence['criterion_event_consequence']=np.nan
            st.markdown('**Consequence of the modeled strain-criterion event**')
            st.caption('Optional proxy only: supply a conditional consequence for this specific event. '
                'Do not substitute a rupture/leakage loss without a model linking strain exceedance to that outcome. '
                'Blank = UNKNOWN. This is not the burst/leakage risk used in the other workspaces.')
            consequence=st.data_editor(consequence,hide_index=True,width='stretch',
                disabled=['section_id','start_km','end_km'],key='dent_losses_'+signature)
            unit=st.text_input('Dent criterion-event consequence unit',value=p['consequence_unit'] or '',key='dent_loss_unit')
            loss=pd.to_numeric(consequence.criterion_event_consequence,errors='coerce')
            invalid=(consequence.criterion_event_consequence.notna()&loss.isna()).any() or np.isinf(loss).any() or (loss.dropna()<0).any()
            if invalid or (loss.notna().any() and not unit.strip()):
                st.error('Enter nonnegative finite consequences (or blank) and their unit.')
            else:
                sections=sections.copy()
                sections['criterion_event_consequence']=loss.to_numpy()
                sections['criterion_expected_consequence']=sections.strain_criterion_probability*loss.to_numpy()
                st.dataframe(sections,hide_index=True,width='stretch')
                for col,title in [('criterion_event_consequence','Dent criterion-event consequence'),
                    ('criterion_expected_consequence','Dent criterion expected-consequence proxy')]:
                    st.plotly_chart(_curve(sections,'start_km',col,title,unit or 'UNKNOWN unit'),width='stretch',theme=None)
                _csv('Download dent section proxy results',sections.assign(probability_basis='Strain criterion exceedance',
                    consequence_unit=unit,model_id=model),'dent_section_proxy.csv')
                options={'Strain-criterion probability':'strain_criterion_probability',
                    'Criterion-event consequence':'criterion_event_consequence',
                    'Expected-consequence proxy':'criterion_expected_consequence'}
                view=st.radio('Dent map view',list(options),horizontal=True,key='dent_map_view')
                column=options[view]
                plotted=assessed.copy()
                if column!='strain_criterion_probability':
                    plotted[column]=plotted.section_id.map(sections.set_index('section_id')[column])
                st.caption('Map colours are relative to this layer, not regulatory categories. '
                    'Grey means UNKNOWN. This remains a strain-criterion assessment, not a rupture risk map.')
                st_folium(_dent_map(p,plotted,column,view,sections),height=420,width=1100,
                    returned_objects=[],key='dent_map_'+signature+column+repr(loss.tolist()))
            _csv('Download dent probabilities',assessed,'dent_criterion_probabilities.csv')
            _csv('Download dent joint-segment probabilities',joints,'dent_joint_segment_probabilities.csv')
        elif saved: st.info('Dent inputs changed; rerun the reliability assessment.')
    with fatigue:
        from dent_fatigue_ui import render_dent_fatigue
        render_dent_fatigue(p)
    with con:
        st.caption('These burst/leakage release-consequence tools are available for future dent failure models. '
            'Their outputs are not automatically multiplied by strain-criterion exceedance probability.')
        render_consequence_assessment(project['route'],segment_table=project['segments'])
