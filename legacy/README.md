# Legacy material (2019–2020) — preserved unchanged

This folder holds the original work of the Belt Marking Machine project
(AIBO Mechatronics, 08/12/2019 – 31/01/2020). Files are kept **byte-for-byte
unchanged**. Nothing here is built or used by the new system; it is the
reference that the upgrade was derived from. See
[`docs/LEGACY_ANALYSIS.md`](../docs/LEGACY_ANALYSIS.md) for the analysis.

| Path | What it is | Where it came from |
|---|---|---|
| `README_original.md` | The original repository README (BOM, costs, features) | repo root before the upgrade |
| `machine_working.mp4` | 52 s video of the machine marking labels, with the original PC UI | repo root |
| `control_panel_design/` | SolidWorks parts/assemblies, STL (3D printed) and STEP/PDF (laser cut) of the **control cabinet** | repo root (an identical duplicate under `laser_machine_code/` was dropped) |
| `machine_codes/makine_kodu.ino` | Arduino Mega firmware, variant A | restored from git history, commit `a309b27^` |
| `machine_codes/makine_kodu/makine_kodu.ino` | Arduino Mega firmware, variant B (2 lines differ, see analysis) | restored from git history, commit `a309b27^` |
| `interface_design_coodes/KONTROL_KODU.pde` (+ `.java`, images) | Processing 3 / ControlP5 operator UI that ran on a Windows PC | restored from git history, commit `8d642b6^` |
| `docs/project_clarifications.pdf` | Project summary PDF (same content as the original README) | restored from git history, commit `2f95bac^` |

Not restored (still available in git history at commit `8d642b6^`): the exported
Windows builds `application.windows32/` and `application.windows64/`
(`KONTROL_KODU.exe` plus the Processing/JOGL/ControlP5 runtime `.jar`/`.dll`
files, ~10 MB of third-party binaries that can be regenerated from the `.pde`).
Recover them with:

```bash
git checkout 8d642b6^ -- laser_machine_code/interface_design_coodes/application.windows64
```
