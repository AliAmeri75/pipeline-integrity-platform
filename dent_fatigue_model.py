"""SCADA rainflow + API1156 S-N/He–Zhou lognormal fatigue reliability.

He & Zhou (2021), doi:10.1016/j.jpse.2021.08.004, equations 10,15–23.
Research assessment of plain, smooth, unrestrained dents, not release POF.
"""
from io import BytesIO
import math
import numpy as np
import pandas as pd
import rainflow

M = 2.971
A_MEAN = math.exp(43.944) * (145.033 / 2) ** (-M)
UNITS = {'MPa':1., 'bar':.1, 'psi':.006894757293168}


def read_scada(content, filename):
    if len(content)>25*1024*1024: raise ValueError('SCADA file must be at most 25 MB.')
    try:
        data = pd.read_csv(BytesIO(content)) if filename.lower().endswith('.csv') else pd.read_excel(BytesIO(content))
    except Exception as error:
        raise ValueError('Cannot read the CSV/Excel file.') from error
    if not 3<=len(data)<=200000: raise ValueError('Use 3–200,000 rows; select one pipeline/time series before uploading.')
    return data


def pressure_history(data, time_column, pressure_column, unit='MPa'):
    """Strict chronology, complete regular observations; no silent interpolation.

    Timestamps lacking offsets are interpreted as UTC, disclosed in UI.
    Exposure includes one median sample interval (interval-start records).
    """
    if time_column==pressure_column or unit not in UNITS: raise ValueError('Select distinct time/pressure columns and a supported unit.')
    if 'pipeline_id' in data and data.pipeline_id.nunique(dropna=False)>1:
        raise ValueError('Select one pipeline_id before analysis; do not combine pressure histories.')
    if len(data)<3:raise ValueError('At least three pressure observations are required.')
    times=pd.to_datetime(data[time_column],utc=True,errors='coerce',format='mixed')
    pressure=pd.to_numeric(data[pressure_column],errors='coerce').to_numpy(dtype=float)*UNITS[unit]
    if times.isna().any() or not np.isfinite(pressure).all() or (pressure<0).any():
        raise ValueError('Complete valid timestamps and nonnegative finite pressure readings are required. Clean invalid/quality-flagged records first.')
    dt=times.diff().dt.total_seconds().to_numpy()[1:]
    if (dt<=0).any():raise ValueError('Timestamps must be unique and strictly increasing; sort and resolve duplicates first.')
    cadence=float(np.median(dt))
    if not np.allclose(dt,cadence,rtol=.01,atol=.001):
        raise ValueError('Missing or irregular intervals detected. Provide one continuous, regularly sampled record; gaps are not bridged.')
    exposure=(times.iloc[-1]-times.iloc[0]).total_seconds()+cadence
    return pd.DataFrame({'timestamp_utc':times,'pressure_MPa':pressure}), exposure/(365.25*86400),cadence


def count_cycles(pressure,minimum_range_mpa=0.):
    if not np.isfinite(minimum_range_mpa) or minimum_range_mpa<0:raise ValueError('Minimum cycle range must be finite and nonnegative.')
    values=np.asarray(pressure,dtype=float)
    if values.ndim!=1 or len(values)<3 or not np.isfinite(values).all():raise ValueError('A finite pressure vector with at least 3 points is required.')
    # Residual half cycles are retained, no rounding/binning before damage calculation.
    table=pd.DataFrame(list(rainflow.extract_cycles(values)),columns=['range_MPa','mean_MPa','count','start_index','end_index'])
    return table.loc[(table.range_MPa>0)&(table.range_MPa>=minimum_range_mpa)].reset_index(drop=True)


def automatic_scf(diameter_mm,wall_mm,depth_mm):
    if not np.isfinite([diameter_mm,wall_mm,depth_mm]).all() or min(diameter_mm,wall_mm,depth_mm)<=0:
        raise ValueError('Positive finite diameter, wall thickness and dent depth are required.')
    ratio=diameter_mm/wall_mm; depth=depth_mm/diameter_mm
    if not 20<=ratio<=60 or not .02<=depth<=.12:
        raise ValueError('Automatic SCF requires 20 ≤ D/t ≤ 60 and 2% ≤ d/D ≤ 12%. Supply a reviewed SCF for other geometry; no automatic extrapolation.')
    return 1+1.7169*ratio**.8*depth**.7


def fatigue_curve(cycles,exposure_years,diameter_mm,wall_mm,scf,years,
                  a_mean=A_MEAN,a_cov=.45,critical_mean=1.,critical_cov=.30,initial_damage=0.):
    """Independent lognormal A and Dcrit. Geometry/SCF/spectrum fixed.

    D(T)=D0 + T*sum[n_i*(K*delta_sigma_i)^m]/(record_years*A).
    Initial damage is a deterministic dimensionless fraction in this S-N model.
    For nonzero D0 evaluate P(Dcrit <= D0 + B/A) using deterministic
    Gauss-Hermite integration over lognormal A. Zero D0 uses exact lognormal product.
    """
    vals=[exposure_years,diameter_mm,wall_mm,scf,a_mean,a_cov,critical_mean,critical_cov,initial_damage]
    if not np.isfinite(vals).all() or min(exposure_years,diameter_mm,wall_mm,a_mean,critical_mean)<=0 or scf<1 or min(a_cov,critical_cov,initial_damage)<0 or diameter_mm<=2*wall_mm:
        raise ValueError('Invalid fatigue geometry, SCF, resistance or uncertainty inputs.')
    t=np.asarray(years,dtype=float)
    if t.ndim!=1 or len(t)==0 or not np.isfinite(t).all() or (t<0).any() or (np.diff(t)<=0).any():raise ValueError('Use nonnegative, increasing assessment times.')
    ranges=cycles.range_MPa.to_numpy(dtype=float); counts=cycles['count'].to_numpy(dtype=float)
    if not np.isfinite(ranges).all() or not np.isfinite(counts).all() or (ranges<0).any() or (counts<0).any():raise ValueError('Invalid cycle spectrum.')
    rate=float(np.sum(counts*(scf*ranges*diameter_mm/(2*wall_mm))**M)/exposure_years)
    sa=math.sqrt(math.log1p(a_cov*a_cov));sc=math.sqrt(math.log1p(critical_cov*critical_cov))
    ma=math.log(a_mean)-sa*sa/2;mc=math.log(critical_mean)-sc*sc/2
    def cdf(z):return .5*math.erfc(-z/math.sqrt(2))
    def probability(b):
        if initial_damage==0:
            if b==0:return 0.
            sd=math.hypot(sa,sc)
            return cdf((math.log(b)-ma-mc)/sd) if sd else float(b>=a_mean*critical_mean)
        if sc==0:
            remaining=critical_mean-initial_damage
            if remaining<=0:return 1.
            if b==0:return 0.
            return cdf((math.log(b/remaining)-ma)/sa) if sa else float(b/a_mean>=remaining)
        if sa==0:return cdf((math.log(initial_damage+b/a_mean)-mc)/sc)
        nodes,weights=np.polynomial.hermite.hermgauss(80)
        return float(sum(w*cdf((math.log(initial_damage+b/math.exp(ma+math.sqrt(2)*sa*x))-mc)/sc)
                         for x,w in zip(nodes,weights))/math.sqrt(math.pi))
    pf=np.array([probability(rate*x) for x in t])
    return pd.DataFrame({'total_exposure_years':t,'damage_at_mean_A':initial_damage+t*rate/a_mean,
                         'cumulative_fatigue_probability':pf}),rate
