# Protein-Peptide Binding Site Constrained Structure Prediction Platform

## Role

你是一位資深 Computational Biology、Protein Structure Prediction、AI Drug Discovery 與 Full-Stack Web Development 專家，熟悉：

- AlphaFold 3
- Chai-1
- Boltz-1
- Boltz-2
- Protein-Peptide Docking
- Contact Restraints
- Pocket Restraints
- Residue Constraints
- GPU-based Structure Prediction Pipelines
- GitHub OAuth
- Scientific Web Platform Architecture

你的任務是協助設計並實作一個 Protein-Peptide Binding Site Constrained Structure Prediction Platform。

---

## Background

我希望建立一個 Protein-Peptide 結構模擬平台。

平台主要目標是利用支援 Binding Site Constraints 的 AlphaFold 衍生模型，讓使用者能夠指定特定蛋白質位點作為 peptide 的預期結合區域。

### Chain Definition (Mandatory)

| Molecule | Chain |
|-----------|-----------|
| Protein | Chain A |
| Peptide | Chain B |

所有 Constraints 必須以：

```text
Chain A ↔ Chain B
```

形式定義。

例如：

```text
Chain A Residues 120-140
must contact
Chain B
```

### Existing Technologies

目前已知下列模型具備類似 AlphaFold 3 的 Constraint 機制：

- Chai-1
- Boltz-1
- Boltz-2

其支援：

- Pocket Constraints
- Contact Constraints
- Residue-Level Constraints
- Binding Site Guidance

例如：

```text
Chain A Residue Y120
must contact
Chain B
```

或

```text
Distance(A:Y120, Chain B) < 8 Å
```

因此我希望利用現有的開源模型作為後端引擎，而非自行訓練新的深度學習模型。

---

## Objective

建立一個研究級 Protein-Peptide Complex Prediction Platform。

使研究人員可以：

1. 執行 Protein-Peptide Structure Prediction
2. 指定 Protein（Chain A）上的 Binding Site
3. 強制或引導 Peptide（Chain B）於指定區域進行結合
4. 執行大量 Batch Prediction
5. 取得 Protein-Peptide Complex Structure
6. 提供結果可視化與下載功能

---

# Functional Requirements

## A. Protein Input (Chain A)

Protein 一律視為 Chain A。

支援：
- Protein Sequence
- PDB ID
- PDB/mmCIF Upload

## B. Peptide Input (Chain B)

Peptide 一律視為 Chain B。

支援：
- Single Peptide
- Multiple Peptides
- CSV Upload

## C. Binding Site Constraints

Constraint 對象永遠為 Chain A (Protein)，限制 Chain B (Peptide) 必須與指定位置產生接觸。

### Mode 1: Specific Residues

```text
A:Y45
A:K48
A:D52
```

### Mode 2: Residue Range

```text
A:120-140
```

### Mode 3: Multiple Binding Regions

```text
A:120-140
A:220-235
A:300-315
```

### Mode 4: Constraint-Free Prediction

若無限制則使用原生預測流程。

## D. GUI-Based Residue Selection

建議支援：

- Mol*
- NGL Viewer
- 3Dmol.js

## E. Batch Prediction

CSV 範例：

| Protein | Peptide | Binding Site |
|----------|----------|----------|
| ProteinA | RPKLGYAA | A:120-140 |
| ProteinA | AKMTRFLP | A:120-140 |
| ProteinA | YLQKGHGI | A:220-235 |

## F. GitHub-Based User Interface

支援：

- GitHub OAuth
- GitHub Repository Integration
- GitHub Actions Workflow Trigger
- CSV Upload
- Structure Upload
- Optional GitHub Issues Submission

# Technical Requirements

請優先評估：

1. Chai-1
2. Boltz-2
3. Boltz-1

分析：

- Contact Restraints Support
- Pocket Constraints Support
- Residue Constraints Support
- Protein-Peptide Prediction
- GPU Requirement
- Docker Deployment
- API Integration
- Batch Processing Support

# Desired Architecture

## Frontend

- GitHub Login
- Job Submission
- Constraint Editor
- Protein Structure Viewer
- Result Visualization

## Backend

- Job Queue
- Constraint Parser
- Prediction Engine
- Result Manager

## Infrastructure

- Docker
- Kubernetes
- GPU Cluster
- Cloud Deployment

# Expected Output

## 1. Feasibility Analysis

分析 Chai-1、Boltz-1、Boltz-2 作為後端引擎的可行性。

## 2. Technology Comparison Table

| Feature | Chai-1 | Boltz-1 | Boltz-2 |
|----------|----------|----------|----------|

## 3. Recommended Architecture

提供：

- Mermaid System Diagram
- Mermaid Data Flow Diagram

## 4. Database Schema

- Users
- Projects
- Jobs
- Proteins
- Peptides
- Constraints
- Predictions
- Results

## 5. API Design

- POST /jobs
- POST /jobs/batch
- GET /jobs/{id}
- GET /results/{id}

## 6. Development Roadmap

- Phase 1 (MVP)
- Phase 2 (Constraint-aware Prediction)
- Phase 3 (Large-scale Batch Processing)
- Phase 4 (Production Deployment)

# Additional Requirements

## A. Constraint Mapping

如何將 Chain A 殘基限制轉換到：

- Chai-1
- Boltz-1
- Boltz-2

## B. Batch Processing

如何管理 Protein (Chain A) + Multiple Peptides (Chain B) 的大量預測。

## C. GPU Queue Architecture

支援 Thousands 到 Tens of Thousands of Jobs。

## D. GUI-Based Constraint Selection

支援點選、框選與 Surface Selection，自動轉換為 Constraint Format。

## E. Site-Directed Docking Strategy

若原生 Constraint 功能不足，請提出：

1. Multi-Round Screening
2. Contact Filtering
3. Distance-Based Ranking
4. Pocket-Guided Sampling
5. Post-processing Rescoring

# Final Deliverable

請提供：

1. 完整技術可行性分析
2. 最佳後端模型建議
3. 生產級系統架構設計
4. Mermaid 系統圖
5. Database Schema
6. API 規格
7. Docker/Kubernetes 部署策略
8. GPU Cluster 設計
9. Batch Processing 設計
10. MVP → Production Roadmap

以可直接進入開發階段的工程規格文件形式撰寫。
