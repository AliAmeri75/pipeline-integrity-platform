# Journal 2 data guide

The Journal 2 interface keeps calculation code in GitHub and obtains the large
Monte Carlo POF arrays separately. Python code is never downloaded or executed
from Google Drive.

## Google Drive option

The default folder is:

<https://drive.google.com/drive/folders/1Y_yZDyOBnGlCrx5KVRRidEH_Hy8Hufcg?usp=drive_link>

The folder must allow **Anyone with the link — Viewer** access. The platform
recursively lists the folder and downloads only the 15 files required by the
current three crack templates. Files are held in temporary storage on the
Streamlit server and may need to be downloaded again after the app restarts.

The platform has read-only behavior: it does not upload, rename, edit, or delete
anything in Google Drive. Users who need to add datasets must have upload/edit
permission granted by the folder owner and use the normal Google Drive page.

## Required filenames

For each crack template id `0`, `1`, and `2`:

- `prior_analysis{id}.npz`
- `Samples_HPC{id}_.npz`
- `name_Pfx_burst_leak{id}.npz`
- `name_Pfx3_burst_leak{id}.npz`
- `name_Pfy3_burst_leak{id}_e1.npz`

The prior files may be located in a nested Drive folder. The application matches
files recursively by exact filename and stages them into one temporary
`Data_CC` directory.

## Direct upload fallback

If Drive is rate-limited or unavailable, select all 15 NPZ files in the direct
upload control. Each current file is below the configured 100 MB per-file limit.
The application validates filenames and required array names before enabling the
analysis.

## Privacy and capacity

Do not place confidential operator or ILI data in a public Drive folder. Use
synthetic, published, or explicitly approved research datasets. Large downloads
consume Streamlit memory, network bandwidth, and temporary disk space; production
use should move the arrays to controlled object storage with authenticated access.
