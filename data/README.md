# Bearing dataset workflow

Only manifests and schemas are tracked. `raw/`, `interim/`, and `processed/` are
ignored because the source datasets are large and have independent usage terms.

1. Read the official terms linked from the relevant manifest.
2. For Paderborn, first verify that the current official index still contains the
   expected 32 archives:

   `python scripts/download_paderborn_dataset.py --list-only`

   The downloader supports `.partial` resume files, retries, atomic completion,
   and a SHA256/size manifest. Before the large download, install the official
   7-Zip command-line tool and ensure `7z` is on `PATH`; extraction is intentionally
   blocked when no legal RAR extractor is available.
3. XJTU-SY is only accepted from the official author page. If its folder links
   require browser interaction, download `XJTU-SY_Bearing_Datasets.zip` manually
   and save it as `data/raw/xjtu-sy/_archives/XJTU-SY_Bearing_Datasets.zip`.
4. Register other authorized local archives without committing them:

   `python scripts/download_dataset.py --dataset paderborn --source-file <archive>`

5. Extract the archive under `data/raw/<dataset>/`.
6. Run the independent audit before any feature preparation or training:

   `python scripts/audit_bearing_dataset.py paderborn --raw-dir data/raw/paderborn --labels data/schemas/paderborn_labels.csv`

   `python scripts/audit_bearing_dataset.py xjtu-sy --raw-dir data/raw/xjtu-sy`

   The Paderborn label mapping is sourced from official paper tables and is never
   inferred from filename prefixes. A failing audit must block downstream work.
7. Prepare features from the repository root only after the audit passes, for
   example:

   `python scripts/prepare_bearing_dataset.py paderborn --raw-dir data/raw/paderborn --labels data/schemas/paderborn_labels.csv --window-size 4096 --stride 4096 --output data/processed/paderborn_fault_v1.npz`

   `python scripts/prepare_bearing_dataset.py xjtu-sy --raw-dir data/raw/xjtu-sy --task rul --output data/processed/xjtu_sy_rul_v1.npz`

The registration command writes a local sidecar receipt containing the SHA256,
timestamp, and file size. It never changes the committed source manifest. XJTU-SY
has no explicit license in the author repository, so the workflow intentionally
does not implement unattended downloading or redistribution.

The preparer normalizes acceleration to SI units. Its conservative defaults are
`m/s2` for Paderborn and `g` for XJTU-SY; use `--signal-unit` if the specific
official archive/channel metadata states otherwise. Unit choice is an experiment
input and must be retained with the processed-data receipt.
