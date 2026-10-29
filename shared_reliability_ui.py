"""Read-only asset inputs, shared with Data Exploration and deterministic FPR."""
import hashlib
import streamlit as st
from streamlit_folium import st_folium
from assessment_project import reliability_project,project_signature
from project_editor import get_project
from reliability_flags import flag_probabilities,annotate_pof_figure,ACTION_LABEL


def render_shared_reliability(*,embedded=False):
    from reliability_analysis import result_map,profile_figure
    project=get_project()
    st.subheader('Risk & Reliability')
    st.info('Using the saved Data Exploration dataset: '+project['source']+'. '
        'Route, defect dimensions, segment properties, distributions and consequences are defined there once.')
    st.caption('Assessment-condition probability of failure—not annual Pf. CorLAS evaluates cracks only. '
        'Leakage: sampled depth ≥ sampled WT. Burst: pressure ≥ θ × CorLAS resistance for a non-through-wall crack. '
        'No growth, initiation, inspection or repair is included. These screening results are not a code-compliance assessment.')
    with st.expander('Review the active shared dataset'):
        st.dataframe(project['summary'],hide_index=True,width='stretch')
        st.dataframe(project['segments'],hide_index=True,width='stretch')
        st.dataframe(project['uncertainties'],hide_index=True,width='stretch')
    c1,c2=st.columns(2)
    samples=c1.number_input('Monte Carlo samples per defect',100,10000,1000,100,key='shared_mc_samples')
    seed=c2.number_input('Monte Carlo random seed',0,1000000,7,key='shared_mc_seed')
    burst_limit=c1.number_input('Burst Pf map screening threshold',min_value=1e-10,max_value=1.,value=.001,format='%.6g')
    leak_limit=c2.number_input('Leakage Pf map screening threshold',min_value=1e-10,max_value=1.,value=.01,format='%.6g')
    st.caption('Pipe/material/load draws are shared by defects within the same nominal joint and property segment. '
        'Defect-size draws are independent. Different joint–segment groups are assumed independent; '
        'a property boundary crossing a joint splits that group. Physical joint IDs remain unchanged. '
        'Nonpositive samples are resampled, and valid strength ordering and pipe bore are enforced.')
    signature=hashlib.sha256((project_signature(project)+repr((samples,seed))).encode()).hexdigest()
    if st.button('Run Reliability Analysis',type='primary'):
        try:
            with st.spinner('Assessing the shared defects using their own segment properties…'):
                assessed,joints,sections=reliability_project(project,int(samples),int(seed))
                st.session_state.shared_reliability_output=(signature,assessed,joints,sections)
        except (ValueError,TypeError,KeyError) as error:
            st.error(str(error))
    saved=st.session_state.get('shared_reliability_output')
    if not saved:
        st.info('Run the assessment to see the same defects on the POF, consequence and risk profiles.')
        return
    if saved[0]!=signature:
        st.info('The shared dataset or simulation settings changed. Run Reliability Analysis again.')
        return
    _,assessed,joints,sections=saved
    assessed=flag_probabilities(assessed,burst_limit,leak_limit)
    joints=flag_probabilities(joints,burst_limit,leak_limit)
    sections=flag_probabilities(sections,burst_limit,leak_limit)
    critical=sections[sections.action_required]
    if not critical.empty:
        st.warning('→ '+ACTION_LABEL+' POF threshold exceeded in segment(s): '+
            ', '.join(str(int(s)) for s in critical.section_id)+'.')
    st.caption('Immediate action is your screening flag when burst POF > its threshold OR leakage POF > its threshold. '
        'Equality does not trigger it. This flags locations for engineering review; it is not a regulatory repair instruction.')
    unit=project['consequence_unit'] or 'UNKNOWN unit'
    st.subheader('POF, consequence and risk profiles')
    st.caption('Segments use the boundaries saved in Data Exploration, not a separate 1 km grid. '
        'Segment Pf is probability of at least one modeled mode event, combining joint–segment groups. '
        'Zero failures in Monte Carlo do not prove zero Pf. Unrecorded defects and other threats are not assessed; '
        'a segment with no listed defects has zero modeled contribution, not demonstrated safety. '
        'At zero observed failures, the approximate 95% upper bound is 3/N (about '+f'{3/samples:.4g}'+').')
    for columns,title,ylabel in [
        ([('burst_pf','Burst'),('leak_pf','Leakage')],'POF versus distance','Assessment-condition probability'),
        ([('burst_consequence','Burst'),('leak_consequence','Leakage')],'Consequence versus distance','Conditional consequence ('+unit+')'),
        ([('burst_risk','Burst'),('leak_risk','Leakage'),('total_risk','Total')],'Risk versus distance','Expected consequence ('+unit+' per assessment)')]:
        figure=profile_figure(sections,columns,title,ylabel)
        if title=='POF versus distance':
            figure=annotate_pof_figure(figure,sections,burst_limit,leak_limit)
        st.plotly_chart(figure,width='stretch',theme=None)
        if title=='POF versus distance':
            st.caption('The POF vertical axis is logarithmic. Zero estimates are omitted from this plot (gaps), '
                'not replaced with small positive values. All original values remain in the tables and downloads.')
            for probability,label in [('burst_pf','Burst'),('leak_pf','Leakage')]:
                if sections[probability].eq(0).all():
                    st.caption(label+': no failures observed in this simulation (POF estimates = 0). '
                        'No curve is visible on the log axis; this does not prove zero failure probability.')
    if sections[['burst_consequence','leak_consequence']].isna().any().any():
        st.warning('Some consequences are UNKNOWN. Their risk values remain unavailable—not zero. Complete them in Data Exploration.')
    st.caption('Risk = burst Pf × conditional burst loss + leakage Pf × conditional leakage loss. '
        'This is a segment-event screening metric, not the expected count of multiple incidents. '
        'The loss definitions must avoid double counting.')
    view=st.radio('Map view',['POF','Consequence','Risk'],horizontal=True)
    modes=['Burst','Leakage','Total'] if view=='Risk' else ['Burst','Leakage']
    failure_mode=st.selectbox('Map failure mode',modes)
    column={'Burst':'burst','Leakage':'leak','Total':'total'}[failure_mode]+'_'+{'POF':'pf','Consequence':'consequence','Risk':'risk'}[view]
    limit=(burst_limit if failure_mode=='Burst' else leak_limit) if view=='POF' else None
    st.caption('POF red marks the selected screening threshold; consequence/risk colours are relative. Grey means UNKNOWN. '
        'Red outlines and white-backed “Immediate action!” labels flag segments exceeding either POF threshold, '
        'regardless of the selected map layer. These colours are not regulatory risk categories.')
    st_folium(result_map(project['route'],assessed,sections,column,failure_mode+' '+view,limit),
        height=500,width=1100,returned_objects=[],key='shared_risk_map_'+signature+'_'+column+repr((burst_limit,leak_limit)))
    for label,table,filename in [('Defect probabilities',assessed,'defect_probabilities.csv'),
            ('Joint–segment probabilities',joints,'joint_segment_probabilities.csv'),
            ('Segment POF, consequence and risk',sections,'segment_risk.csv')]:
        st.markdown('**'+label+'**')
        st.dataframe(table,hide_index=True,width='stretch')
        st.download_button('Download '+label,table.assign(dataset_id=project_signature(project),
            probability_basis='Assessment-condition Pf',consequence_unit=unit).to_csv(index=False),filename,'text/csv')
