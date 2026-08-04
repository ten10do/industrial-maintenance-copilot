# External RUL Benchmark License Audit

Audit date: 2026-08-04

## Candidate

- Dataset: FEMTO-ST PRONOSTIA / IEEE PHM 2012 Prognostic Challenge / FEMTO Bearing Data Set.
- Intended role: optional one-time external generalization benchmark after an XJTU V2 candidate is frozen; never training, tuning, model selection, or threshold selection.

## Primary and repository sources checked

1. FEMTO-ST author publication: [PRONOSTIA: An Experimental Platform for Bearings Accelerated Degradation Tests](https://publiweb.femto-st.fr/tntnet/entries/1528/documents/author/data). It establishes provenance, platform ownership, sensor setup, and the research citation.
2. PHM Society Data Repository NASA mirror: [FEMTO Bearing](https://data.phmsociety.org/nasa/). It identifies FEMTO-ST as provider and publishes download and citation links.
3. IEEE PHM 2012 Challenge details, as linked/circulated with the dataset. The document states that the challenge datasets are publicly available and requests citation of Nectoux et al. (2012).

## License finding

The official/author sources establish provenance and permitted public research access in practice, but the inspected pages and challenge document do not state a standard data license or explicit terms granting automated acquisition, redistribution, derivative-cache publication, or commercial use. A download link and a citation request are not equivalent to an explicit license grant.

Third-party mirrors are not accepted as authority for licensing. One commonly indexed mirror labels the license as unknown, which reinforces rather than resolves the ambiguity.

## Decision

- License status: **unclear for automated download and redistribution**.
- Download performed: **no**.
- External evaluation performed: **no**.
- Data/artifacts redistributed: **no**.
- Result: `external benchmark not executed`.

Reconsideration requires an explicit license or written terms from FEMTO-ST/PHM Society covering the intended research use. If that is obtained later, the model/config must first be frozen from XJTU Development only, and PRONOSTIA may then be accessed once without tuning.
