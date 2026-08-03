# Model artifacts

Actual model bundles are ignored by Git. Each bundle contains:

- `model.joblib`
- `preprocessor.joblib`
- `feature_schema.json`
- `metadata.json`
- `metrics.json`
- `integrity.json`

The registry records the bundle SHA256. Online inference refuses missing bundles,
hash mismatches, feature-schema mismatches, and model-version mismatches. Joblib
artifacts must only be loaded from a trusted training pipeline because joblib is a
pickle-based format.
