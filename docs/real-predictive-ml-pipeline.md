# 真实数据驱动的预测性维护 ML 链路

## 边界与结论

本升级保留既有设备资产、遥测模拟器、规则异常检测、Operational Health
Score、Diagnosis Agent、RAG、智能工单、调度、备件、审批、维修验证和知识沉淀。
新增链路负责确定性的故障分类、未来采集窗口风险和 RUL 推理。LLM 只能解释已经
记录的概率、RUL、特征贡献和 RAG 证据，不能生成或改写这些数值。

现有 `deterministic-rules-v1` 是业务规则风险估计，在没有已晋升生产的 ML 模型时
继续可用，但不得称为机器学习结果。API 在没有对应 production model 时返回明确的
409，不会静默把规则输出伪装成 ML inference。

Operational Health Score（0–100）与 ML Degradation Indicator（0–1）是两个字段和
两个概念。前者用于实时业务状态，后者仅由 RUL 模型及其训练元数据派生，不能在
Dashboard 合成一个数。

## 经核实的数据源

### Paderborn University Bearing Data Center

- 官方数据页：<https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter/data-sets-and-download>
- 官方论文：<https://mb.uni-paderborn.de/fileadmin-mb/kat/PDF/Veroeffentlichungen/20160703_PHME16_CM_bearing.pdf>
- 数据许可：CC BY-NC 4.0，非商业学术使用需署名；商业使用需联系作者。
- 仅用于学习、研究和作品集实验，不得据此宣称可直接商业使用。
- 数据包含 6 个健康、12 个人工损伤、14 个寿命试验产生的真实损伤状态；测试台
  同步测量电流、振动、转速、扭矩、径向力和温度。
- 官方论文描述电流和振动以 64 kHz 采样；每种工况有 20 次、每次 4 秒测量。
- 本项目用于轴承状态/故障分类。类别必须来自官方元数据映射，不从文件名猜测，
  也不为 UI 人工创造类别。

Paderborn 的 4 秒状态测量不是 run-to-failure 时间线，因此配置中的 horizon 明确是
“当前 4 秒测量状态”，不是“未来 7/30 天故障”。它不能单独支持诚实的日历故障
时间预测。

### XJTU-SY

- 作者数据页：<https://biaowang.tech/xjtu-sy-bearing-datasets/>
- 作者数据仓库：<https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets>
- 论文 DOI：<https://doi.org/10.1109/TR.2018.2882682>
- 作者页面描述 15 个轴承、3 种工况的完整 run-to-failure 数据；每分钟采集一次，
  25.6 kHz、1.28 秒、32768 点，含水平和垂直振动。
- 作者仓库要求引用 Wang 等人的 IEEE Transactions on Reliability 论文。
- 截至 2026-08-03，作者仓库没有 LICENSE 文件或明确 SPDX 条款。本项目因此不
  假定可再分发，只提供人工下载/本地登记流程。

RUL ground truth 定义为“当前采集到该 bearing run 最后一次可观测采集的剩余小时”。
最后一次记录作为 observable run endpoint 是实验假设，所有模型元数据都会保留该
说明。未来故障风险标签可定义为“距离该 endpoint 不超过后续 N 次一分钟采集”，N
来自实验配置，不能改写成未经支持的日历天数。

AI4I、C-MAPSS、模拟器数据和 CI synthetic fixture 都没有被描述为真实现场轴承数据。

## 可追溯数据与目录

```text
data/manifests/       官方 URL、引用、许可、版本和待本地填充的 checksum
data/schemas/         标签/schema 模板
data/raw/             gitignored
data/interim/         gitignored
data/processed/       gitignored
artifacts/            gitignored（仅 README 被跟踪）
```

原始文件完成授权下载后，通过 `scripts/download_dataset.py` 复制到 ignored 目录并
生成本地 receipt（SHA256、时间、大小）。源 manifest 的 `sha256: null` 和
`raw_files: 0` 是“尚未下载”的诚实状态，不是虚构 checksum。注册模型后可按
`ModelVersion → TrainingRun → DatasetVersion / feature schema / config SHA / Git SHA`
反查全链路。

## 预处理与共享特征

```text
Raw signal → validation/单位归一 → deterministic windowing
           → shared feature extraction → feature validation
                                      ↙                  ↘
                                 offline training     online inference
```

校验覆盖 sampling rate、信号长度、时间顺序、重复 timestamp、NaN/Inf、缺失比例、
可选物理幅值上限和振动单位。允许阈值内 NaN 线性插值；Inf、重复时间、超阈值缺失
和未知单位会失败。`g` 会按 9.80665 转成 `m/s²`。

`app/ml/features.py` 是唯一的训练/在线特征实现，包含：

- 14 个时间域特征：mean、std、variance、RMS、max、min、peak-to-peak、absolute
  mean、skewness、kurtosis、crest/shape/impulse/clearance factor；
- FFT dominant frequency、spectral centroid/RMS/entropy、低中高频带能量与比例；
- rolling mean/std/RMS、RMS/kurtosis/envelope energy slope、degradation rate、
  recent-vs-baseline delta；
- 数据源确实提供时才加入 speed/load/torque/radial force context。

没有轴承滚动体数量、节圆直径、滚动体直径和接触角时，不计算 BPFO/BPFI/BSF/FTF。

## 防泄漏、训练与评估

所有 fault 与 RUL 实验都按 `bearing_id` / bearing run 使用
`GroupShuffleSplit`；测试 bearing 从未出现在训练或验证。提供 `GroupKFold` 工具用于
交叉验证。Scaler 只 `fit(train)`，随后 transform validation/test；候选模型只用
validation 选择，test 只在选定模型后评估。

Fault/classification baseline 是 LogisticRegression，candidate 是
RandomForestClassifier，可选 HistGradientBoostingClassifier。选择策略先强制最低
Recall，再比较 PR-AUC、Recall、F1 和 FNR。评估同时记录 precision、ROC-AUC、
PR-AUC、confusion matrix、FPR、Brier score 和 calibration curve。

RUL baseline 是 Ridge，candidate 是 RandomForestRegressor，可选
HistGradientBoostingRegressor。选择按 MAE、RMSE、late prediction error，并可设置
最大 late-error。评估同时记录 median AE、R²、relative、early 和 late error。V1
没有引入 LSTM/Transformer 或重量级 ML 平台。

模型全局解释使用 validation set permutation importance。在线解释对线性模型使用
标准化特征乘系数，对树模型使用标准化特征幅值乘模型 importance，记录 top
contributing features；LLM 不参与计算 importance。

## 命令行

从 `apps/api` 运行（路径按该工作目录配置）：

```powershell
python -m app.ml.train_fault_model --dataset paderborn --task fault_classification --config ../../configs/ml/fault_v1.yaml
python -m app.ml.train_fault_model --dataset xjtu-sy --task failure_risk --config ../../configs/ml/failure_risk_v1.yaml
python -m app.ml.train_rul_model --dataset xjtu-sy --config ../../configs/ml/rul_v1.yaml
```

输出包含 dataset、train/validation/test 样本数、算法、validation/test metrics、
artifact path 和 model version。真实数据未下载时命令明确失败，不回退到模拟数据。

训练完成且数据库 schema 已升级后，可注册候选模型：

```powershell
python -m app.ml.register_model --artifact ../../artifacts/<model-version> --manifest ../../data/manifests/xjtu_sy_bearing_v1.json --status candidate
```

管理员通过 `/api/v1/ml/models/{id}/status` 将 candidate 晋升到 staging/production；
只有训练阶段按配置生成且通过的 promotion decision 才能进入 production；晋升时同
任务旧 production 自动 archived。数据库 partial unique index 同时强制每个 task 只有
一个 active production。`/api/v1/ml/models/rollback`
回滚到指定历史版本，同一 task 始终只保留一个 active production。在线
`/api/v1/ml/inference` 会校验文件存在、bundle SHA256、model version 和 feature
schema，记录 `PredictionRecord`。默认推理只选择 active production；本地验收可显式
传入 `model_version_id` 调用同任务 staging 模型，但 staging 结果只写
`PredictionRecord`，不会进入现有 `RiskPrediction` 业务列表。只有 production 的
分类/风险输出会进入该业务列表，避免实验模型改变运维决策状态。

joblib 是 pickle-based 格式，因此只能加载受信训练流程产生的 bundle。

## 当前真实限制

- 仓库没有提交 Paderborn/XJTU-SY 原始数据，也没有声称已有真实数据训练指标。
- CI 使用代码生成的、明确标记 synthetic-only 的小样本，仅验证链路，不代表工业
  性能或泛化能力。
- 没有真实 PLC、传感器或现场数据接入，主要设备模型仍是电机/轴承。
- 现有数据库没有历史 Alembic revision 链，新增表继续走幂等兼容迁移入口。
- 生产模型晋升、生产数据库迁移和生产部署不属于本次变更，必须独立预演与审批。
