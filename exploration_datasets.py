"""Public synthetic datasets and strict dent-register uploads; no operator data."""
from copy import deepcopy
import io
import numpy as np
import pandas as pd
from openpyxl import Workbook
from profile_data import parse_profile_workbook,summary_for_defect_type
from dent_assessment_model import DENT_COLUMNS,validate_dents


def sample_corrosion_workbook():
    """Three smooth metal-loss profiles on the same nominal 36-inch pipe."""
    book=Workbook();summary=book.active;summary.title='Summary'
    summary.append(['SAMPLE DATA FOR CORROSION PROFILE']);summary.append([])
    summary.append(['File Name','GW ID','CLS ID','TCPL Chainage (m)','Clock Position (hh:mm)',
        'Outside Diameter (mm)','Wall Thickness (mm)','Peak Depth (%wt)','Length (mm)'])
    for i,(chainage,length,width,peak) in enumerate([
        (500.,180.,80.,20.),(4500.,600.,200.,35.),(8500.,1800.,350.,50.)],start=1):
        pid=f'SYN-COR-{i:03d}';fid=f'COR-{i:03d}';sheet=book.create_sheet(pid)
        sheet['A1']='SAMPLE DATA FOR CORROSION PROFILE'
        sheet['E1']='Columns: Longitudinal Coordinate (mm) / Rows: Circumferential Coordinate (mm) / Cells: Metal-loss Depth (%WT)'
        nx,ny=25,17;dx=length/nx;dy=width/ny
        for x in range(nx):sheet.cell(1,x+6,chainage*1000+dx*x)
        for y in range(ny):
            sheet.cell(y+2,5,100+dy*y)
            for x in range(nx):
                depth=round(peak*np.exp(-.5*(((x-12)/6)**2+((y-8)/4)**2)),3)
                sheet.cell(y+2,x+6,depth)
        for cell,label,value in [(4,'Feature ID',fid),(5,'Outside Diameter (mm)',914.4),
            (6,'Wall Thickness (mm)',11.8),(18,'Peak Depth (%wt)',peak),
            (19,'Total Length (mm)',length),(20,'Total Width (mm)',width)]:
            sheet.cell(cell,2,label);sheet.cell(cell,3,value)
        summary.append([pid,f'DEMO-COR-GW-{i:02d}',fid,chainage,'03:00',914.4,11.8,peak,length])
        sheet.freeze_panes='F2';sheet.column_dimensions['B'].width=25
        sheet.column_dimensions['C'].width=18
    summary.freeze_panes='A4'
    out=io.BytesIO();book.save(out);return out.getvalue()


def sample_dent_register():
    rows=[]
    for i,(chainage,depth,length,width,r1,r2) in enumerate([
        (500.,15.,600.,300.,-1500.,2500.),
        (4500.,30.,350.,250.,-600.,600.),
        (8500.,50.,200.,180.,-150.,300.)],start=1):
        rows.append(dict(zip(DENT_COLUMNS,[f'SYN-DENT-{i:03d}',chainage,depth,length,width,r1,r2,False])))
    return pd.DataFrame(rows)


def dent_workbook(table):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        table.to_excel(writer,sheet_name='Dents',index=False)
        sheet=writer.sheets['Dents'];sheet.freeze_panes='A2'
        for column in sheet.columns:sheet.column_dimensions[column[0].column_letter].width=26
    return out.getvalue()


def read_dent_register(content,filename):
    """Keep identifiers as strings and parse False correctly (never bool('False'))."""
    try:
        if filename.lower().endswith('.csv'):
            data=pd.read_csv(io.BytesIO(content),dtype={'dent_id':str})
        elif filename.lower().endswith('.xlsx'):
            with pd.ExcelFile(io.BytesIO(content),engine='openpyxl') as book:
                sheet='Dents' if 'Dents' in book.sheet_names else book.sheet_names[0]
                data=pd.read_excel(book,sheet_name=sheet,dtype={'dent_id':str})
        else:raise ValueError('Upload a CSV or .xlsx dent register.')
    except Exception as error:
        # pandas/openpyxl raise several different exceptions for malformed files.
        raise ValueError('Could not read the dent CSV/Excel file: '+str(error)) from error
    data.columns=[str(c).strip() for c in data.columns]
    missing=set(DENT_COLUMNS)-set(data.columns)
    if missing:raise ValueError('Missing dent columns: '+', '.join(sorted(missing)))
    if data.empty:raise ValueError('Provide at least one measured dent.')
    boolean=data['associated_crack_or_metal_loss'].astype(str).str.strip().str.lower()
    if not boolean.isin(['true','false','1','0','yes','no']).all():
        raise ValueError('associated_crack_or_metal_loss must be true/false, yes/no or 1/0.')
    data['associated_crack_or_metal_loss']=boolean.isin(['true','1','yes'])
    return data[DENT_COLUMNS]


def dent_project(register,base=None,source='Uploaded dent register'):
    """Dent-only projects have no invented crack/corrosion profiles."""
    from assessment_project import sample_project
    p=deepcopy(sample_project() if base is None else base)
    p['summary']=p['summary'].iloc[:0].copy();p['profiles']={};p['workbook']=b''
    # Keep this as a draft: route coverage can be adjusted after an upload.
    # validate_project/validate_dents enforce all dimensions and route bounds at Save.
    p['dent_register']=register.copy();p['source']=source
    return p


def corrosion_project(content=None):
    from assessment_project import sample_project
    p=sample_project();content=sample_corrosion_workbook() if content is None else content
    summary,profiles=parse_profile_workbook(content)
    p.update(summary=summary_for_defect_type(summary,'Corrosion / metal loss'),profiles=profiles,
        workbook=content,source='Synthetic 10 km corrosion demonstration')
    # Illustrative sizing SDs for this dataset, not calibrated ILI performance.
    p['uncertainties'].loc[p['uncertainties'].parameter=='flaw_depth_mm','std']=.25
    p['uncertainties'].loc[p['uncertainties'].parameter=='flaw_length_mm','std']=10.
    return p
