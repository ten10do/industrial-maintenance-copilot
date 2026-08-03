# Predictive Generalization V2 实验预注册

状态：`LOCKED BEFORE V2 TRAINING`

本文件定义 Predictive Model V2 的实验规则。它必须先于任何 V2 模型训练提交；后续结果不得反向修改本文。若发现设计错误，只能新增带时间、原因、已查看结果范围的 V2.1 amendment，不能改写本文件。

## 1. 研究问题与边界

V2 研究跨轴承、跨工况的故障识别和 RUL 泛化，不以“调过门槛”为目标。V1 的特征、拆分、指标、报告和制品元数据保持不变，V2 使用独立的特征版本、CV 清单、配置和实验记录。

禁止使用深度模型、AutoML、大规模搜索，禁止修改真实标签、删除困难轴承、降低门槛或根据测试结果选择特征、模型、阈值和超参数。

## 2. 数据集和冻结策略

### 2.1 Paderborn fault classification

- 数据版本：`paderborn-snapshot-e513a6320d755ce5`。
- 标签唯一来源：`data/schemas/paderborn_labels.csv`。
- 26 个 Development bearings：V1 的 20 train 加 6 validation，即 `K001, K002, K003, K005, K006, KA01, KA04, KA05, KA06, KA07, KA08, KA09, KA15, KA16, KA30, KB23, KB24, KI03, KI05, KI07, KI08, KI14, KI16, KI17, KI18, KI21`。
- 6 个 Frozen Test bearings：`K004, KA03, KA22, KB27, KI01, KI04`。
- Frozen Test 在最终候选完全固定并提交前不得加载。禁用范围包括原始信号、处理后行、特征/标签分布、预测、指标、PCA/UMAP、归一化统计、类别表现和任何人工浏览。
- V2 工具必须要求显式 final-evaluation 授权和已提交配置 SHA 才能打开 Frozen Test。默认运行、域分析、消融和 CV 必须拒绝 test-bearing 行。
- 若 Development CV 没有候选通过安全门槛，Frozen Test 不访问，Fault V2 不注册、不晋级。
- 若有候选通过，先提交 `configs/ml/paderborn_fault_v2_final.yaml` 并记录配置 SHA，再仅执行一次冻结测试。测试后不再修改 V2 候选。

### 2.2 XJTU-SY RUL

- 数据版本：`xjtu-sy-snapshot-6364ef9cb50663c5`。
- V1 的 test 指标已经被查看，因此 15 个 bearing 全部定义为 V2 Development Dataset。
- V2 结果只能称为 **Cross-Bearing Generalization Estimate**，不得称为 unbiased final test。
- 15 个 bearing 均按完整 run 分组；同一 bearing 的窗口不得跨训练/验证边界。

### 2.3 可选外部数据

PRONOSTIA/FEMTO-ST 或其他数据只在官方来源、论文引用和许可证/使用条款均明确后考虑。许可证不明确时不下载、不再分发。外部集不得用于调参、选模或调阈值；只有 XJTU 候选冻结后才允许一次外部评估。特征或域不兼容时记录 `not directly comparable`，不强行映射。

## 3. Paderborn Development CV

- 固定 seed：`20260803`。
- 预先生成 `data/manifests/paderborn-v2-cv-folds.json` 并在训练前提交。
- 5-fold grouped stratified CV，group=`bearing_id`。每个 bearing 恰好作为 validation 一次。
- 分层键为官方 bearing-level `damage_origin`（healthy/artificial/real），并以 `fault_class` 作为次级平衡目标。
- 固定生成规则：按 `(damage_origin, fault_class)` 分层；每层使用 seed 派生的确定性顺序，将 bearing 逐个分配到当前该层数量最少、随后总 bearing 数最少、最后 fold index 最小的 fold。若 sklearn 的 `StratifiedGroupKFold` 产生的每折三类 damage origin 覆盖更完整，则仍必须在清单生成工具和测试中固定其版本、seed 和结果；生成后不得更换。
- 每个 fold 的训练数据独立拟合 scaler、condition baseline、重采样器（若有）、特征选择器和模型。validation 不参与任何拟合。
- 所有 Fault 消融和模型使用同一清单。

## 4. Paderborn 标签架构

主安全分类器固定为两阶段架构的 Stage 1：`healthy` vs `damaged`，其中 damaged 来自所有非 healthy 官方类别。分类阈值固定为 damaged probability `0.50`。

Stage 2 只能使用官方 `fault_location`、`fault_type` 或 `damage_origin`。某个 Stage 2 目标只有在每一类别至少有 5 个 Development bearings，且固定五折的每个训练 fold 都至少有 2 个 bearing/类时才允许训练和报告；否则明确记为 N/A，并由 Diagnosis Agent + RAG 处理 subtype。Stage 2 不参与 Stage 1 promotion。

## 5. Fault 特征族与消融

`bearing-features-v1` 原样保留。新增 `bearing-features-v2`，所有频域计算仅使用当前窗口，所有统计保持有限值。

- F0：V1 全部特征，作为基线。
- F1：F0 + envelope RMS、kurtosis、peak、energy、spectral entropy，以及低/中/高三段 envelope band energy 和 ratio。
- F2：F0 + condition-normalized V1 核心特征（RMS、kurtosis、crest factor、spectral centroid、三段 band energy/ratio）。baseline 仅由当前 train fold 的 healthy bearings 按 operating condition 计算 median 和 IQR；同工况无 healthy train 样本时回退到该 fold 全部 healthy 样本。输出 robust z-score `(x - median) / max(IQR, 1e-12)`。
- F3：F0 + F1 envelope + F2 condition normalization。
- F4：F3 + 经审计确认在 Development 数据中真实存在、可稳定解析并具有一致物理含义的额外通道。否则固定记为 N/A。不得伪造通道。

Paderborn 多通道审计只读取 26 个 Development bearings。轴承 BPFO/BPFI/BSF/FTF 特征保持禁用，除非官方材料同时提供真实轴承几何参数与轴速；缺一不可。PCA/UMAP 仅用于 Development 域分析，不得作为模型输入。

每个消融报告五折的 mean/std/worst-fold macro recall、PR-AUC、healthy recall、damaged recall 和 FNR，并保留逐折结果。

## 6. Fault 候选与有限搜索空间

以下候选均用 seed `20260803`，仅在固定 Development CV 内比较：

- LogisticRegression：`C ∈ {0.1, 1.0, 10.0}`，`class_weight=balanced`，`max_iter=2000`。
- RandomForestClassifier：`n_estimators=300`，`max_depth ∈ {8, 12, null}`，`min_samples_leaf ∈ {1, 2, 5}`，`max_features=sqrt`，`class_weight=balanced_subsample`，`n_jobs` 受本地资源上限约束。
- HistGradientBoostingClassifier：`max_iter=150`，`learning_rate ∈ {0.03, 0.05, 0.10}`，`max_leaf_nodes ∈ {15, 31}`，`l2_regularization ∈ {0, 1}`；class weight 在当前 sklearn 支持时使用 fold-local balanced sample weights。

本轮不使用 LinearSVC 和 oversampling，以控制多重比较和依赖范围。不得在整份 Development 数据上预先重采样。

## 7. Fault 选择和停止规则

指标按 window 计算，同时报告 bearing-macro 诊断；安全 gate 使用五折合并 out-of-fold 预测以及逐折统计：

- 必须满足 OOF binary macro recall `>= 0.70`。
- 必须满足 OOF healthy recall `>= 0.60`。
- 固定阈值 `0.50`，不做结果驱动的 threshold search。
- 主排序分数：`mean fold macro recall - 0.5 * std fold macro recall`，越高越好。
- 依次平局裁决：mean fold macro recall、worst-fold macro recall、mean fold PR-AUC、较少特征、较简单模型。

若无候选同时通过两个 gate，立即停止 Fault 最终化：不创建 final config、不访问 Frozen Test、不注册。若通过，完全冻结 feature set、estimator、hyperparameters、threshold、scaler/baseline policy，并提交 final config。Frozen Test 的最终 gate 仍为 macro recall `>= 0.70` 且 healthy recall `>= 0.60`；失败则不得 candidate → staging。

最终测试（若获准）报告 macro precision/recall/F1、ROC-AUC、PR-AUC、FNR、FPR、Brier、healthy/damaged recall、per-class recall 和 confusion matrix。

## 8. XJTU V2 评估协议

- 外层：15-fold Leave-One-Bearing-Out；每折恰好一个完整 bearing 作为评估组。
- 内层：剩余 14 bearings 上确定性的 3-fold grouped CV；按 operating condition 轮转平衡，group=`bearing_id`，seed=`20260803`。
- 所有 preprocessing、healthy/early-life baseline、scaler、degradation transform 和模型选择只拟合外层训练数据；超参数只由内层 mean MAE 选择。
- 每个 feature family 独立完成相同 outer splits；聚合 15 个 outer OOF bearing 的结果形成 Cross-Bearing Generalization Estimate。
- 资源降级仅允许预先固定的 5-fold outer grouped CV amendment；必须在查看 V2 指标前记录原因，不能静默替换 LOBO。

## 9. RUL 特征消融

- R0：V1 horizontal-only 特征，作为基线。
- R1：双通道当前窗口。horizontal 与 vertical 分别提取 RMS、std、kurtosis、crest factor、spectral centroid、spectral entropy、三段 band energies、envelope RMS 和 envelope kurtosis；增加 H/V RMS、energy、kurtosis、spectral-energy ratio 及通道 Pearson correlation。ratio 分母下限为 `1e-12`。
- R2：R1 + 严格因果多尺度历史。时间点为 `t, t-5m, t-15m, t-30m, t-60m`；对 RMS、kurtosis、envelope energy、spectral entropy、channel energy 计算只含当前及过去的 rolling mean/std/RMS 和 least-squares slope。序列开头只使用当时已存在的历史，不填未来值，不允许 centered window。
- R3：R2 + fold-local robust degradation indicator。每个 outer/inner train fold 对每个 bearing 的前 10%（至少 5 个 acquisition）定义 early-life reference，仅在 train bearings 上拟合 RobustScaler；degradation distance 为经该 scaler 变换后的选定健康状态特征到训练 early-life median 的 L2 距离。validation bearing 只 transform，不参与 baseline/scaler。

Feature cache key 固定包含 DatasetVersion、FeatureVersion、processing config SHA；不得因单个模型重做原始 FFT。缓存和实验支持中断后按完整 hash 恢复，且不提交完整 processed 数据。

## 10. RUL 候选与有限搜索空间

所有 tree 模型 `random_state=20260803`，并限制并行度：

- Ridge：`alpha ∈ {0.1, 1.0, 10.0}`。
- RandomForestRegressor：`n_estimators=300`，`max_depth ∈ {8, 12}`，`min_samples_leaf ∈ {1, 3}`。
- ExtraTreesRegressor：`n_estimators=300`，`max_depth ∈ {8, 12}`，`min_samples_leaf ∈ {1, 3}`。
- GradientBoostingRegressor：`n_estimators ∈ {100, 200}`，`learning_rate ∈ {0.03, 0.05}`，`max_depth=2`。
- HistGradientBoostingRegressor：`max_iter=150`，`learning_rate ∈ {0.03, 0.05}`，`max_leaf_nodes ∈ {15, 31}`，`l2_regularization ∈ {0, 1}`。

不启用未经验证的 monotonic constraints，不使用 LSTM/Transformer。内层以 mean MAE 最小选择；平局依次使用 RMSE、late error、较简单模型。

## 11. RUL 轨迹、平滑和 uncertainty

每个 bearing 按 acquisition 时间排序。对相邻 raw predictions：

- positive jump=`max(pred[t] - pred[t-1], 0)`。
- significant oscillation：positive jump `> 0.5 h`。
- oscillation count：significant oscillation 数。
- oscillation rate：count / `max(n_acquisitions - 1, 1)`；总体使用各 bearing rate 的算术平均，避免长 run 支配结果。
- mean/max positive jump：分别对全部正 jump 求均值/最大值；没有正 jump 时为 0。

因果 EWMA 固定 `alpha=0.20`，每个 bearing 的首值为首个 raw prediction，只递归使用当前和过去 raw prediction。raw 与 smoothed prediction、指标和轨迹统计必须同时保存；promotion 只使用 raw 指标，不能用平滑隐藏不稳定性。

树 ensemble 只有在可取得每棵树的独立预测时才报告 10%/90% empirical dispersion interval，并明确它不是校准后的概率区间。其他模型的 uncertainty 记为 unavailable，不伪造区间。

全局解释使用 training-fold permutation importance。样本级贡献只在模型有可靠原生线性贡献时报告 `scaled_feature * coefficient`；其他模型记为 unavailable，不冒充 SHAP。

## 12. RUL promotion 和停止规则

候选必须在 15 个 outer OOF bearings 的 **raw** predictions 上同时满足：

- MAE `<= 5.0 h`；
- R² `> 0`；
- mean late prediction error `<= 3.0 h`；
- mean per-bearing significant oscillation rate `<= 0.10`。

特征族最终选择先过滤全部 gate，通过者按 MAE、RMSE、mean late error、oscillation rate、较简单特征族/模型排序。没有候选通过则拒绝 promotion，不降低门槛。XJTU 没有新的 final test；通过只允许 candidate → staging，不允许 production。

## 13. 域分析和实验记录

Paderborn 域分析仅使用 26 个 Development bearings，覆盖 healthy/artificial/real、fault class、bearing、operating condition，以及 RMS、kurtosis、crest factor、spectral centroid、band energy 的分布和重叠。PCA 仅用于可视化/定量诊断 bearing identity、condition 和 damage origin 的可分性，不作为输入。

每个运行生成 ExperimentRun，至少记录：`experiment_id, dataset_version, feature_version, fold_manifest, algorithm, hyperparameters, seed, git_sha, started_at, finished_at, metrics, artifact_hash`。报告位于 `docs/ml-experiments/v2/`，小型 JSON/CSV 可提交；原始 RAR/MAT/CSV、完整 processed 数据、joblib、SQLite 和大型二进制图不提交。

最终生成 `docs/ml-experiments/v2-comparison.md`。Paderborn V1 validation/test 与 V2 CV、XJTU V1 test 与 V2 LOBO 的制度不同，必须明确不是 apples-to-apples。

## 14. 工程和治理门槛

自动测试至少覆盖 grouped stratification、fold determinism、Frozen Test protection、train-only condition baseline、envelope、dual-channel、causal rolling/future leakage、CV reproducibility、hierarchical classifier、per-class recall、oscillation、raw/smoothed、promotion、ExperimentRun 和 V1/V2 schema isolation。CI 只使用 deterministic fixture，不加载 9GB+ 真实数据。

最终执行 Ruff format/lint、MyPy strict、Pytest/coverage、ESLint、TypeScript strict、Jest、Next.js build 和 Playwright。只有真正通过 policy 的 staging 模型才允许非生产在线推理和编排 Agent 联动；ML 输出 immutable，不能绕过人工审批。禁止 production promotion 和生产部署。

## 15. 预注册停止条件

1. Paderborn：完成 Development 域分析、固定折消融和候选搜索。无 gate 合格者即停止且保持 Test 未访问；有合格者按“一次 final test”流程停止于注册/拒绝结论。
2. XJTU：完成 R0-R3 LOBO estimate 与 policy 判定后停止；外部 benchmark 仅在许可与 schema 均明确时执行。
3. 两项均必须保留负结果，生成 failure analysis 和仅供建议的 V3 proposal；不得自动启动 V3。
4. 本研究 PR 始终保持 Draft，不 merge，不执行生产部署。

## 16. Amendments

预注册提交时：无 amendment。
