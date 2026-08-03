# Bearing dataset workflow

Only manifests and schemas are tracked. `raw/`, `interim/`, and `processed/` are
ignored because the source datasets are large and have independent usage terms.

1. Read the official terms linked from the relevant manifest.
2. Download the archive manually from the official/author source.
3. Register the local archive without committing it:

   `python scripts/download_dataset.py --dataset paderborn --source-file <archive>`

4. Extract the archive under `data/raw/<dataset>/`.
5. For Paderborn, populate a private copy of
   `data/schemas/paderborn_labels.csv` from official bearing metadata. Labels are
   deliberately not inferred from filename prefixes.
6. Prepare features from the repository root, for example:

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
