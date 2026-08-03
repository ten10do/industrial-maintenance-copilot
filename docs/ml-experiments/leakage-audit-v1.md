# Real-bearing leakage audit v1

Leakage Audit: **PASS**

This report was generated before formal model training. Test metrics were not inspected when the splits were designed or audited.

## Paderborn

- Result: **PASS**
- Dataset version: `paderborn-snapshot-e513a6320d755ce5`
- Rows / bearings: 159140 / 32
- Train bearings: `['K001', 'K002', 'K003', 'K006', 'KA01', 'KA04', 'KA05', 'KA06', 'KA08', 'KA09', 'KA15', 'KA30', 'KB23', 'KI03', 'KI05', 'KI08', 'KI14', 'KI16', 'KI17', 'KI21']`
- Validation bearings: `['K005', 'KA07', 'KA16', 'KB24', 'KI07', 'KI18']`
- Test bearings: `['K004', 'KA03', 'KA22', 'KB27', 'KI01', 'KI04']`
- Intersections: `{'train_validation': [], 'train_test': [], 'validation_test': []}`
- Identity leakage check: PASS
- Source/window leakage check: PASS
- Label leakage check: PASS
- Preprocessing policy: PASS (scaler/model train-only; selection validation-only; test final-only)
- Future leakage check: PASS
- Condition distribution: `{'train': {'N09_M07_F10': 24826, 'N15_M01_F10': 24867, 'N15_M07_F04': 24906, 'N15_M07_F10': 24851}, 'validation': {'N09_M07_F10': 7466, 'N15_M01_F10': 7460, 'N15_M07_F04': 7453, 'N15_M07_F10': 7451}, 'test': {'N09_M07_F10': 7468, 'N15_M01_F10': 7463, 'N15_M07_F04': 7456, 'N15_M07_F10': 7473}}`
- Errors: `[]`
## XJTU-SY

- Result: **PASS**
- Dataset version: `xjtu-sy-snapshot-6364ef9cb50663c5`
- Rows / bearings: 9216 / 15
- Train bearings: `['Bearing1_2', 'Bearing1_3', 'Bearing1_5', 'Bearing2_2', 'Bearing2_3', 'Bearing2_5', 'Bearing3_2', 'Bearing3_3', 'Bearing3_5']`
- Validation bearings: `['Bearing1_1', 'Bearing2_4', 'Bearing3_1']`
- Test bearings: `['Bearing1_4', 'Bearing2_1', 'Bearing3_4']`
- Intersections: `{'train_validation': [], 'train_test': [], 'validation_test': []}`
- Identity leakage check: PASS
- Source/window leakage check: PASS
- Label leakage check: PASS
- Preprocessing policy: PASS (scaler/model train-only; selection validation-only; test final-only)
- Future leakage check: PASS
- Condition distribution: `{'train': {'35Hz12kN': 371, '37.5Hz11kN': 1033, '40Hz10kN': 2981}, 'validation': {'35Hz12kN': 123, '37.5Hz11kN': 42, '40Hz10kN': 2538}, 'test': {'35Hz12kN': 122, '37.5Hz11kN': 491, '40Hz10kN': 1515}}`
- Errors: `[]`

