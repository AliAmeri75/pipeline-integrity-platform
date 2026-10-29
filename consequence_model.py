"""Transparent consequence screening: hazard radius, exposure and direct cost.

PIR: 49 CFR 192.903, natural gas only, p=MAOP psi and d=nominal inches.
Point source: NISTIR 6546 Eq. 7, Q in MW and incident flux in kW/m².
Population and economic overlays are explicit uniform-density approximations,
not lethality, dispersion, release-rate or comprehensive QRA models.
"""
from dataclasses import dataclass, replace
import math
import numpy as np
import pandas as pd
from reliability_model import consequence_template

PIR = 'Natural-gas PIR'
THERMAL = 'Point-source thermal radiation'
RADIUS = 'User-defined radius'
PIR_SOURCE = 'https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-D/part-192/subpart-O/section-192.903'
THERMAL_SOURCE = 'https://www.govinfo.gov/content/pkg/GOVPUB-C13-fa5a24c9e669a385816318793faac823/pdf/GOVPUB-C13-fa5a24c9e669a385816318793faac823.pdf'


def number(value, name, *, minimum=0., maximum=None):
    try:
        value = float(value)
    except (TypeError,ValueError) as error:
        raise ValueError(f'{name} must be numeric.') from error
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{name} is outside its valid range.')
    return value


def potential_impact_radius(maop_psi, diameter_in):
    p = number(maop_psi,'MAOP',minimum=1e-12)
    d = number(diameter_in,'Nominal diameter',minimum=1e-12)
    return .69*d*math.sqrt(p)*.3048


def thermal_radius(heat_release_mw, radiant_fraction, threshold_kw_m2):
    q = number(heat_release_mw,'Heat-release rate')*1000
    chi = number(radiant_fraction,'Radiant fraction',maximum=1.)
    threshold = number(threshold_kw_m2,'Heat-flux threshold',minimum=1e-12)
    return math.sqrt(chi*q/(4*math.pi*threshold))


@dataclass(frozen=True)
class HazardScenario:
    model: str = PIR
    natural_gas: bool = True
    maop_psi: float = 936.
    diameter_in: float = 20.
    heat_release_mw: float = 100.
    radiant_fraction: float = .2
    threshold_kw_m2: float = 5.
    radius_m: float = 50.
    ignition_probability: float = 1.
    damage_fraction: float = 1.


def scenario_radius(scenario, mode):
    if scenario.model == PIR:
        if mode != 'burst' or not scenario.natural_gas:
            raise ValueError('Natural-gas PIR is available only for natural-gas burst/rupture screening.')
        return potential_impact_radius(scenario.maop_psi,scenario.diameter_in),PIR_SOURCE
    if scenario.model == THERMAL:
        return thermal_radius(scenario.heat_release_mw,scenario.radiant_fraction,scenario.threshold_kw_m2),THERMAL_SOURCE
    if scenario.model == RADIUS:
        return number(scenario.radius_m,'User-defined radius'),'User-specified footprint; no physical radius model'
    raise ValueError('Choose a supported hazard-radius model.')


def assess_consequences(route, section_inputs, burst, leak, segment_table=None):
    """Conditional exposure/cost for one representative midpoint event per segment.

    Ignition probability weights the selected ignited scenario conditional on a
    mode failure. Fixed incident response cost is not ignition-weighted. Uniform
    local density applies to the entire impact circle, which can extend beyond
    its pipeline section. Section exposure counts must NOT be summed as unique
    residents. All inputs and model/source metadata are preserved in exports.
    """
    expected = (segment_table if segment_table is not None else consequence_template(route))[['section_id','start_km','end_km']]
    data = section_inputs.copy()
    required = {'section_id','population_density_per_km2','asset_value_per_m2','burst_fixed_cost','leak_fixed_cost'}
    if not required.issubset(data):
        raise ValueError('Provide section_id, population_density_per_km2, asset_value_per_m2, burst_fixed_cost and leak_fixed_cost.')
    ids = pd.to_numeric(data.section_id,errors='coerce')
    if ids.duplicated().any() or set(ids) != set(expected.section_id):
        raise ValueError('Provide exactly one input row for every section in the route template.')
    data['section_id'] = ids
    data = data.set_index('section_id').loc[expected.section_id].reset_index()
    for field in ('start_km','end_km'):
        if field in data and not np.allclose(pd.to_numeric(data[field],errors='coerce'),expected[field],atol=1e-7,rtol=0):
            raise ValueError('Uploaded section distances must match the current route.')
    rows = []
    override_fields = ['maop_psi','diameter_in','heat_release_mw','radiant_fraction',
                       'threshold_kw_m2','radius_m','ignition_probability','damage_fraction']
    for i,row in data.iterrows():
        density = number(row.population_density_per_km2,'Population density')
        asset_value = number(row.asset_value_per_m2,'Asset value per m²')
        record = expected.iloc[i].to_dict()
        record.update(population_density_per_km2=density,asset_value_per_m2=asset_value,
                      event_chainage_km=(record['start_km']+record['end_km'])/2)
        for mode,config in [('burst',burst),('leak',leak)]:
            overrides = {field:number(row[f'{mode}_{field}'],f'{mode} {field}')
                         for field in override_fields if f'{mode}_{field}' in data}
            scenario = replace(config,**overrides)
            radius,source = scenario_radius(scenario,mode)
            ignition = number(scenario.ignition_probability,'Ignition probability',maximum=1.)
            damage = number(scenario.damage_fraction,'Damage fraction',maximum=1.)
            fixed = number(row[f'{mode}_fixed_cost'],'Fixed incident cost')
            area = math.pi*radius**2
            exposed = density*area/1e6
            record.update({f'{mode}_radius_m':radius,f'{mode}_area_m2':area,
                f'{mode}_people_in_footprint':exposed,
                f'{mode}_exposure_consequence':ignition*exposed,
                f'{mode}_economic_consequence':fixed+ignition*area*asset_value*damage,
                f'{mode}_fixed_cost':fixed,f'{mode}_model':scenario.model,
                f'{mode}_source':source,f'{mode}_ignition_probability':ignition,
                f'{mode}_damage_fraction':damage})
            for field in override_fields:
                # Preserve the actual values used for reproducibility.
                if field != 'radius_m':
                    record[f'{mode}_{field}'] = getattr(scenario,field)
        rows.append(record)
    return pd.DataFrame(rows)


def consequence_risk_inputs(results, measure):
    if measure not in ('exposure','economic'):
        raise ValueError('Select exposure or economic consequences.')
    data = results[['section_id','start_km','end_km']].copy()
    for mode in ('burst','leak'):
        data[f'{mode}_consequence'] = results[f'{mode}_{measure}_consequence']
    return data
