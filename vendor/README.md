# Offline Wheel Cache

This directory stores pre-downloaded wheels so the exporter can be installed on
machines without internet access. Each subfolder corresponds to a target runtime
(e.g. windows-amd64-cp313). Populate the folder by running
scripts/prepare_offline_bundle.py on a connected workstation, then copy the
endor/ directory to the airgapped environment.

When ready to install, run:

`ash
pip install --no-index --find-links <path-to-vendor-subdir> -r requirements.txt
`

Replace <path-to-vendor-subdir> with the folder that matches your Python
version and platform.
