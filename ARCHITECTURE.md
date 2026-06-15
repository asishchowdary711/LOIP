# LOIP Architecture

## System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        DemoUI["Demo UI<br/>/apply"]
        AdminUI["Admin Dashboard<br/>/ui"]
        API["REST API<br/>/onboard, /review, /vcip"]
    end

    subgraph "Web Layer — FastAPI"
        Router["API Router<br/>9 route modules"]
        Auth["Auth & Rate Limiting<br/>slowapi"]
        Templates["Jinja2 Templates<br/>5 HTML templates"]
    end

    subgraph "Pipeline Orchestration"
        Pipeline["OnboardingPipeline<br/>loip/pipelines/onboarding.py"]
    end

    subgraph "Domain Processors"
        DocIntel["Document Intelligence<br/>5 ML models"]
        IdTrust["Identity Trust<br/>3 ML models + 2 API clients"]
        IncIntel["Income Intelligence<br/>XGBoost + reconciliation"]
        Afford["Affordability<br/>LightGBM + EMI calc"]
        Fraud["Fraud Intelligence<br/>GraphSAGE + Neo4j"]
        Risk["Risk Decisioning<br/>XGBoost ensemble"]
        Explain["Explainability<br/>SHAP + LIME + Copilot"]
        Review["Human Review<br/>Queue + Override"]
        Comply["Compliance<br/>DPDP + AML + KFS"]
        MLOps["MLOps<br/>Registry + Drift"]
    end

    subgraph "Infrastructure"
        PG["PostgreSQL 16<br/>Decisions, Audit"]
        MinIO["MinIO<br/>Document Storage"]
        Kafka["Kafka<br/>8 Domain Events"]
        Neo4j["Neo4j 5<br/>Identity Graph"]
        OS["OpenSearch<br/>Full-Text Search"]
        Redis["Redis 7<br/>Cache"]
        MLflow["MLflow<br/>Model Registry"]
        Ollama["Ollama<br/>Local LLM Inference"]
    end

    subgraph "Monitoring"
        Prom["Prometheus"]
        Graf["Grafana"]
    end

    DemoUI --> Router
    AdminUI --> Router
    API --> Router
    Router --> Auth
    Router --> Templates
    Router --> Pipeline

    Pipeline --> DocIntel
    Pipeline --> IdTrust
    Pipeline --> IncIntel
    Pipeline --> Afford
    Pipeline --> Fraud
    Pipeline --> Risk
    Pipeline --> Explain
    Pipeline --> Review

    DocIntel --> Ollama
    IdTrust --> Neo4j
    Fraud --> Neo4j
    Pipeline --> Kafka
    Pipeline --> PG
    Pipeline --> MinIO
    Explain --> Ollama

    Prom --> Graf
```

## End-to-End Loan Onboarding Flow

```mermaid
flowchart TD
    A[Applicant submits form + documents<br/>POST /apply/submit] --> B[Document Intelligence]

    subgraph B["Stage 1: Document Intelligence"]
        B1[LayoutLMv3 Classification<br/>PAN / Aadhaar / Salary Slip / Bank Statement]
        B2[Dual OCR<br/>PaddleOCR primary → Surya fallback]
        B3[Field Extraction<br/>Qwen2.5-VL primary → Donut fallback]
        B1 --> B2 --> B3
    end

    B --> C[Identity Trust Verification]

    subgraph C["Stage 2: Identity Trust"]
        C1[NSDL PAN Verification]
        C2[Aadhaar Verhoeff Checksum]
        C3[UIDAI OTP Verification]
        C4[ArcFace Face Match]
        C5[MiniFASNet Liveness]
        C6[BGE-M3 Name Cross-Check]
        C7[Document Metadata Tamper Check]
    end

    C --> D[Income Intelligence]

    subgraph D["Stage 3: Income Reconciliation"]
        D1[Parse Salary Slip → net_pay]
        D2[Parse ITR → total_income<br/>Current FY + Prior FY]
        D3[Parse GST Returns → turnover × margin]
        D4[Parse Bank Statement → salary credits]
        D5[Source-Trust Weighted Average]
        D6[XGBoost Income Confidence]
        D1 & D2 & D3 & D4 --> D5 --> D6
    end

    D --> E[Affordability Assessment]

    subgraph E["Stage 4: Affordability"]
        E1[EMI Calculation<br/>principal × rate formula]
        E2[FOIR Computation<br/>obligations / income]
        E3[Disposable Income]
        E4[LightGBM Affordability Score]
        E1 --> E2 --> E3 --> E4
    end

    E --> F[CIBIL Bureau Pull]
    F --> G[Fraud Detection]

    subgraph G["Stage 5: Fraud Intelligence"]
        G1[Liveness / Spoof Detection]
        G2[Passport MRZ Validation<br/>ICAO 9303]
        G3[Neo4j Graph Fraud Rings<br/>PAN farming, synthetic identity,<br/>address rings]
        G4[GraphSAGE Anomaly Score]
    end

    G --> H{Risk Decision Engine}

    H -->|Hard Reject| I[REJECT<br/>fraud > 0.80, CIBIL < 650,<br/>FOIR > 0.60, KYC failed]
    H -->|Review Flags| J[REVIEW<br/>marginal scores,<br/>anomalies detected]
    H -->|Score ≥ 0.70| K[APPROVE<br/>XGBoost ensemble pass]

    I --> L[Explainability]
    J --> L
    K --> L

    subgraph L["Stage 6: Explainability"]
        L1[SHAP Waterfall<br/>Top positive/negative features]
        L2[LIME Token Attribution]
        L3[Qwen3 Copilot Narrative]
    end

    L --> M{Decision Routing}
    M -->|Review/Reject| N[Human Review Queue<br/>Case creation + assignment]
    M -->|Approve| O[Store Decision<br/>PostgreSQL + MinIO]
    N --> O

    O --> P[Kafka Domain Events<br/>8 topics published]
    O --> Q[JSON Response to Applicant]
```

## KYC Verification Flow

```mermaid
flowchart TD
    Start[Document Images Uploaded] --> Extract[Extract Fields<br/>Qwen2.5-VL / Donut]

    Extract --> PAN{PAN Card?}
    Extract --> AAD{Aadhaar Card?}
    Extract --> SELF{Selfie Available?}

    PAN -->|Yes| PAN1[Extract PAN Number + Name + DOB]
    PAN1 --> PAN2[Validate PAN Format<br/>XXXXX0000X regex]
    PAN2 --> PAN3[NSDL API Verification<br/>pan_number + full_name + dob]
    PAN3 -->|Match| PAN4[pan_verified = true]
    PAN3 -->|Format Invalid| PAN5[Flag: PAN_FORMAT_INVALID]
    PAN3 -->|Inactive| PAN6[Flag: PAN_NSDL_INACTIVE]

    AAD -->|Yes| AAD1[Extract Aadhaar Number]
    AAD1 --> AAD2[Verhoeff Checksum<br/>12 digits, not starting 0/1]
    AAD2 -->|Invalid| AAD3[Flag: AADHAAR_FORMAT_INVALID]
    AAD2 -->|Valid| AAD4{OTP Available?}
    AAD4 -->|Yes| AAD5[UIDAI OTP Verification]
    AAD5 -->|Failed| AAD6[Flag: AADHAAR_OTP_FAILED]

    SELF -->|Yes| SELF1[MiniFASNet Liveness Detection]
    SELF1 -->|Score < 0.50| SELF2[Flag: SPOOF_DETECTED]
    SELF1 -->|Score ≥ 0.50| SELF3[ArcFace Face Match<br/>Selfie vs Document Photo]
    SELF3 -->|Similarity < 0.60| SELF4[Flag: FACE_MISMATCH]

    PAN4 & AAD4 & SELF3 --> CROSS[Cross-Document Checks]
    CROSS --> NAME[BGE-M3 Name Similarity<br/>PAN name vs Aadhaar name vs App name]
    NAME -->|Similarity < 0.85| NAME1[Flag: NAME_PAN_AADHAAR_MISMATCH]
    CROSS --> DOB[DOB Match Check]
    DOB -->|Mismatch| DOB1[Flag: DOB_MISMATCH]
    CROSS --> META[PDF Metadata Check]
    META -->|Photoshop detected| META1[Flag: DOCUMENT_METADATA_ANOMALY]

    PAN4 & PAN5 & PAN6 & AAD3 & AAD6 & SELF2 & SELF4 & NAME1 & DOB1 & META1 --> CONF[Identity Confidence Score<br/>1.0 − penalties per flag]
```

## Fraud Detection Pipeline

```mermaid
flowchart TD
    Input[Application Data + Identity Result + Extracted Documents] --> R1

    subgraph "Rule-Based Checks"
        R1[Liveness Verification Failed?]
        R1 -->|Yes| S1[Signal: DOCUMENT_FORGERY<br/>severity=0.9]
        R2[Passport MRZ Checksum<br/>ICAO 9303 TD3 Validation]
        R2 -->|Invalid| S2[Signal: DOCUMENT_FORGERY<br/>severity=0.9]
    end

    Input --> NEO

    subgraph NEO["Neo4j Graph Fraud Detection"]
        G1[Ingest Application<br/>Person → PAN, Aadhaar, Phone,<br/>Email, Device, Employer,<br/>BankAccount, Address]
        G1 --> G2[PAN Farming Detection<br/>One phone/email linked to<br/>multiple distinct PANs]
        G1 --> G3[Synthetic Identity Ring<br/>One device shared across<br/>multiple persons]
        G1 --> G4[Address Inconsistency Ring<br/>One address shared by<br/>≥3 applications]
        G2 -->|Detected| S3[Signal: PAN_FARMING<br/>severity=0.6+0.1×count]
        G3 -->|Detected| S4[Signal: SYNTHETIC_IDENTITY_RING<br/>severity=0.7+0.1×count]
        G4 -->|Detected| S5[Signal: ADDRESS_INCONSISTENCY_RING<br/>severity=0.5+0.1×count]
    end

    Input --> GS

    subgraph GS["GraphSAGE ML Anomaly"]
        GS1[Build Node Features<br/>PAN + Aadhaar]
        GS1 --> GS2[GraphSAGE Prediction<br/>Anomaly probability]
        GS2 -->|Score > 0.8| S6[Signal: SYNTHETIC_IDENTITY_RING<br/>severity=score]
    end

    S1 & S2 & S3 & S4 & S5 & S6 --> AGG[Aggregate Fraud Score<br/>max severity across all signals]
    AGG -->|Score > 0.80| HARD[HARD REJECT<br/>Immediate rejection]
    AGG -->|Score ≤ 0.80| PASS[Pass to Risk Decision Engine<br/>Fraud score as input feature]
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Docker Compose Stack"
        subgraph "Application"
            App["FastAPI App<br/>uvicorn :8000"]
        end

        subgraph "Databases"
            PG["PostgreSQL 16<br/>:5432<br/>Decisions, Audit, Consent"]
            Neo4j["Neo4j 5 Community<br/>:7474 / :7687<br/>Identity Graph"]
        end

        subgraph "Storage & Messaging"
            MinIO["MinIO<br/>:9000 / :9001<br/>11 document buckets"]
            MinIOInit["MinIO Init<br/>Creates buckets on startup"]
            Kafka["Kafka<br/>:9092<br/>8 domain event topics"]
            ZK["Zookeeper<br/>:2181"]
            KafkaInit["Kafka Init<br/>Creates topics on startup"]
        end

        subgraph "Search & Cache"
            OS["OpenSearch 2.15<br/>:9200"]
            Redis["Redis 7<br/>:6379"]
        end

        subgraph "ML & Monitoring"
            Ollama["Ollama<br/>:11434<br/>qwen2.5vl:3b"]
            MLflow["MLflow<br/>:5000<br/>Model Registry"]
            Prom["Prometheus<br/>:9090"]
            Graf["Grafana<br/>:3000"]
        end
    end

    App --> PG
    App --> MinIO
    App --> Kafka
    App --> Neo4j
    App --> Ollama
    MLflow --> PG
    MLflow --> MinIO
    Kafka --> ZK
    MinIOInit --> MinIO
    KafkaInit --> Kafka
    Prom --> Graf

    subgraph "Volumes (Persistent)"
        V1["postgres_data"]
        V2["minio_data"]
        V3["neo4j_data"]
        V4["kafka_data"]
        V5["opensearch_data"]
        V6["redis_data"]
        V7["ollama_data"]
        V8["prometheus_data"]
        V9["grafana_data"]
    end
```

## Domain Event Flow (Kafka)

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant K as Kafka
    participant C as Consumer (Future)

    P->>K: document.classified
    Note over K: doc classes identified
    P->>K: identity.verified
    Note over K: identity_confidence, tamper_flags
    P->>K: income.reconciled
    Note over K: verified_monthly_income
    P->>K: affordability.computed
    Note over K: foir, disposable_income
    P->>K: consent.captured
    Note over K: credit_bureau_pull consent
    P->>K: fraud.scored
    Note over K: fraud_score
    P->>K: risk.decided
    Note over K: decision, risk_score, reason_codes
    P->>K: review.assigned
    Note over K: review/reject cases only
```

## Evidence Traceability Model

Every field that contributes to the final decision carries an **evidence chain** linking it back to its source document:

```mermaid
graph LR
    Decision["OnboardingDecision<br/>approve/review/reject"] --> EC1["EvidenceChain<br/>claim: foir=0.42"]
    Decision --> EC2["EvidenceChain<br/>claim: salary_slip_net_pay=50000"]
    Decision --> EC3["EvidenceChain<br/>claim: pan_verification_passed"]

    EC2 --> EF1["ExtractedField<br/>field: net_pay<br/>value: 50000<br/>confidence: 0.90"]
    EF1 --> SL1["SourceLocation<br/>document_id: salary-slips/abc.png<br/>extraction_method: QWEN2_5_VL"]

    EC3 --> API1["APIVerificationResult<br/>provider: NSDL<br/>matched: true"]
    API1 --> EV1["EvidenceNode<br/>type: api_verification"]
```

## Data Flow: Mock vs Real Mode

```mermaid
flowchart LR
    subgraph "mock_mode=True (Default)"
        M1[Canned responses<br/>No weights downloaded<br/>Fast, deterministic<br/>CI-safe]
    end

    subgraph "LOIP_DEMO_REAL_MODELS=1"
        R1[OnboardingPipeline<br/>mock_mode=True]
        R2[doc_processor swapped<br/>DocumentIntelligenceProcessor<br/>mock_mode=False]
        R3[External clients stay mocked<br/>CIBIL, NSDL, UIDAI]
        R1 --> R2
        R1 --> R3
        R2 --> R4[Qwen2.5-VL via Ollama<br/>Real document reading]
    end

    subgraph "Full Real Mode (Future)"
        F1[All processors real<br/>Requires configured endpoints<br/>for CIBIL/NSDL/UIDAI/DigiLocker]
    end
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.11+ |
| **Web Framework** | FastAPI + Uvicorn |
| **Templates** | Jinja2 |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Validation** | Pydantic v2 + pydantic-settings |
| **Database** | PostgreSQL 16 (asyncpg) |
| **Object Storage** | MinIO (S3-compatible) |
| **Message Broker** | Kafka (aiokafka) |
| **Graph Database** | Neo4j 5 (neo4j-driver) |
| **Search** | OpenSearch 2.15 |
| **Cache** | Redis 7 |
| **ML Inference** | Ollama (local), HuggingFace Transformers |
| **ML Tracking** | MLflow |
| **Monitoring** | Prometheus + Grafana |
| **CI/CD** | GitHub Actions |
| **Containerization** | Docker Compose |
