# Product Requirement Document: Synthetic Claims Data Generator

## 1. 목적

`data_generator`는 실손형 의료보험 AI Agent 개발 및 테스트를 위한 합성 데이터를 생성한다. 생성 데이터는 실제 개인정보, 실제 보험계약, 실제 청구 이력을 포함하지 않아야 하며, Agent의 워크플로우, 약관 근거 검색, 지급액 계산, 예외 처리, 정답 라벨 평가를 검증하는 데 사용한다.

## 2. 배경

초기 개발 단계에서는 실제 보험 청구 데이터를 확보하기 어렵고, 개인정보 및 민감정보 처리 리스크도 크다. 따라서 가상의 실손형 의료보험 상품과 가상의 청구 데이터를 생성하고, 별도의 결정론적 룰엔진으로 정답 라벨을 자동 생성한다.

Agent는 약관 문서와 청구 입력만 보고 판단해야 한다. 정답 라벨과 라벨 생성 룰은 평가기에만 사용한다.

## 3. 범위

### 3.1 포함 범위

- 가상 실손형 의료보험 상품 정의 생성 또는 로딩
- 합성 청구 데이터 생성
- 정상, 일부 지급, 서류 누락, 부지급, 사람 심사, 이상청구 의심 시나리오 생성
- 정답 라벨 자동 생성
- 개발셋과 평가셋 분리
- 재현 가능한 seed 기반 생성
- JSON, JSONL, Markdown 산출물 저장
- 기본 데이터 품질 검증

### 3.2 제외 범위

- 실제 보험사 약관 복제
- 실제 고객 개인정보 또는 의료정보 사용
- 실제 fraud 탐지 모델 학습
- 운영 배포용 보험금 지급 판단
- 법률 또는 규제 적합성 최종 판단

## 4. 사용자

- AI Agent 개발자
- 보험 보상 자동심사 PoC 담당자
- 평가 harness 개발자
- 데이터 스키마 및 룰 검증 담당자

## 5. 핵심 산출물

Generator는 기본적으로 다음 파일을 생성해야 한다.

```text
data_generator/generated/products.json
data_generator/generated/policy_documents.md
data_generator/generated/claims_dev.jsonl
data_generator/generated/labels_dev.jsonl
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_eval.jsonl
data_generator/generated/evaluation_cases.jsonl
data_generator/generated/generation_report.json
```

샘플 산출물은 다음 경로를 기준으로 한다.

```text
data_generator/samples/products.json
data_generator/samples/policy_documents.md
data_generator/samples/generation_config.sample.json
data_generator/samples/claims_sample.jsonl
data_generator/samples/labels_sample.jsonl
data_generator/samples/evaluation_cases_sample.jsonl
```

## 6. 기능 요구사항

### FR-001 상품 정의 로딩

Generator는 `products.json` 또는 내부 기본 템플릿에서 상품 정의를 로딩해야 한다.

상품 정의에는 다음이 포함되어야 한다.

- 상품 ID
- 상품명
- 담보 코드
- 담보별 보장 유형
- 담보별 한도
- 자기부담금 규칙
- 필수서류
- 면책 조건
- 사람 심사 조건
- 라벨 우선순위

### FR-002 합성 청구 데이터 생성

Generator는 설정 파일에 따라 청구 데이터를 생성해야 한다.

각 청구건은 다음 정보를 포함해야 한다.

- claim_id
- policy_id
- product_id
- claimant
- policy
- claim
- documents
- claim_history
- signals
- scenario_type

생성되는 고객, 계약, 청구, 영수증 식별자는 모두 합성 식별자여야 한다.

### FR-003 시나리오 기반 생성

Generator는 단순 무작위가 아니라 시나리오 기반으로 데이터를 생성해야 한다.

필수 시나리오는 다음과 같다.

- 정상 급여 통원
- 정상 비급여 통원
- 처방조제비
- 정상 입원
- 한도 초과 일부 지급
- 자기부담금 경계값
- 필수서류 누락
- 계약 실효
- 보장개시일 이전 사고
- 미용 목적 치료
- 고액 입원 사람 심사
- 반복 도수치료 사람 심사
- 동일 영수증 중복청구 의심
- 진단코드와 치료항목 불일치
- 사고일과 최초 진료일 차이 과다

### FR-004 정답 라벨 자동 생성

Generator는 청구 데이터와 상품 정의를 입력으로 받아 정답 라벨을 자동 생성해야 한다.

라벨은 LLM이 아니라 결정론적 룰엔진으로 생성한다.

지원 라벨은 다음과 같다.

- pay
- partial_pay
- request_documents
- deny
- human_review

이상청구 의심은 최종 결정값이 아니라 별도 플래그로 표현한다.

```json
{
  "expected_decision": "human_review",
  "fraud_suspected": true
}
```

### FR-005 라벨 우선순위

여러 조건이 동시에 발생하면 다음 우선순위를 적용한다.

1. 허위, 위조, 중복청구 등 이상청구 신호
2. 계약 실효 또는 보장기간 외
3. 필수서류 누락
4. 명확한 면책 조건
5. 고액, 반복청구, 문서 불일치 등 사람 심사 필요 조건
6. 한도 및 자기부담금 적용
7. 정상 보장 여부

### FR-006 지급액 계산

Generator는 담보별 한도와 자기부담금을 적용하여 지급예상금액을 계산해야 한다.

기본 공식은 다음과 같다.

```text
eligible_amount = min(claimed_amount, applicable_limit)
deductible_amount = deductible_rule(eligible_amount)
payable_amount = max(0, eligible_amount - deductible_amount)
```

통원 및 처방조제비처럼 최소 공제금액과 자기부담률이 함께 있으면 다음 공식을 적용한다.

```text
deductible_amount = max(fixed_amount, eligible_amount * rate)
```

금액은 원 단위 정수로 반올림한다.

### FR-007 개발셋과 평가셋 분리

Generator는 설정에 따라 개발셋과 평가셋을 생성해야 한다.

기본 비율은 다음과 같다.

```text
dev: 80%
eval: 20%
```

분리 시 다음 필드를 기준으로 분포가 과도하게 깨지지 않도록 한다.

- expected_decision
- coverage_code
- scenario_type

### FR-008 재현성

Generator는 seed를 입력받아 동일 설정과 동일 seed에서 동일 산출물을 생성해야 한다.

### FR-009 데이터 품질 검증

Generator는 산출 후 다음 검증을 수행해야 한다.

- 모든 claim_id가 고유한지 확인
- 모든 label이 존재하는 claim_id를 참조하는지 확인
- 모든 claim에 product_id가 존재하는지 확인
- 필수 필드 누락 여부 확인
- label 결정값이 허용 목록에 포함되는지 확인
- payable_amount가 음수가 아닌지 확인
- request_documents 라벨에 missing_documents가 비어 있지 않은지 확인
- fraud_suspected가 true이면 requires_human_review도 true인지 확인
- generated report에 라벨 분포와 시나리오 분포를 기록

## 7. 비기능 요구사항

### NFR-001 개인정보 안전성

생성 데이터는 실제 개인을 식별할 수 없어야 한다.

- 실명 사용 금지
- 실제 주민등록번호 사용 금지
- 실제 전화번호 사용 금지
- 실제 계좌번호 사용 금지
- 실제 병원명 사용 금지
- 실제 영수증 번호 형식과 혼동될 수 있는 값 사용 금지

### NFR-002 결정론

정답 라벨 생성은 동일 입력에 대해 항상 동일 결과를 반환해야 한다.

### NFR-003 설명 가능성

각 라벨에는 최소한 다음 설명 필드를 포함해야 한다.

- reason_codes
- expected_explanation
- calculation
- missing_documents
- coverage_code

### NFR-004 확장성

향후 자동차보험, 여행자보험, 상해보험 등 다른 상품군을 추가할 수 있도록 상품 정의와 룰엔진을 분리해야 한다.

### NFR-005 Agent 비노출 원칙

Agent 입력 데이터에는 정답 라벨, expected_decision, expected_payable_amount, reason_codes를 포함하지 않는다.

정답 정보는 labels 파일과 평가 harness에서만 사용한다.

## 8. 설정 요구사항

Generator는 최소한 다음 설정을 지원해야 한다.

```json
{
  "seed": 20260616,
  "product_id": "SYN-MED-001",
  "dev_count": 1000,
  "eval_count": 200,
  "decision_distribution": {
    "pay": 0.35,
    "partial_pay": 0.25,
    "request_documents": 0.15,
    "deny": 0.12,
    "human_review": 0.10,
    "fraud_suspected_human_review": 0.03
  }
}
```

## 9. 출력 스키마

### 9.1 claims JSONL

각 줄은 하나의 청구건 JSON 객체다.

필수 필드:

- claim_id
- policy_id
- product_id
- scenario_type
- claimant
- policy
- claim
- documents
- claim_history
- signals

### 9.2 labels JSONL

각 줄은 하나의 정답 라벨 JSON 객체다.

필수 필드:

- claim_id
- expected_decision
- expected_payable_amount
- coverage_code
- missing_documents
- reason_codes
- requires_human_review
- fraud_suspected
- calculation
- expected_explanation

### 9.3 generation_report JSON

필수 필드:

- generated_at
- seed
- product_id
- counts
- decision_distribution_actual
- scenario_distribution_actual
- validation_summary

## 10. 인수 기준

Generator 개발은 다음 조건을 만족하면 완료로 본다.

- 샘플 파일과 동일한 스키마의 JSONL을 생성한다.
- `dev_count`와 `eval_count`를 설정으로 조정할 수 있다.
- 동일 seed로 생성하면 동일 결과가 나온다.
- 모든 청구건에 대응되는 라벨이 생성된다.
- 라벨 우선순위가 PRD의 순서를 따른다.
- 지급액 계산이 담보별 한도와 자기부담금을 반영한다.
- 생성 후 데이터 품질 검증 리포트가 생성된다.
- Agent 입력 파일에는 정답 라벨이 섞이지 않는다.

## 11. 권장 구현 구조

```text
data_generator/
  docs/
    PRD.md
  samples/
    products.json
    policy_documents.md
    generation_config.sample.json
    claims_sample.jsonl
    labels_sample.jsonl
    evaluation_cases_sample.jsonl
  src/
    __init__.py
    config.py
    schemas.py
    product_loader.py
    claim_generator.py
    adjudication_rules.py
    validators.py
    writer.py
    cli.py
  tests/
    test_adjudication_rules.py
    test_generation_reproducibility.py
    test_schema_validation.py
```

## 12. 개발 우선순위

1. 상품 정의와 샘플 스키마 고정
2. 룰엔진으로 단일 claim 라벨 생성
3. 시나리오별 claim factory 구현
4. JSONL writer 구현
5. seed 기반 재현성 구현
6. dev/eval split 구현
7. validation report 구현
8. 평가 harness와 연결

## 13. 리스크 및 대응

### 리스크 1: 합성 데이터가 실제 운영 데이터와 다름

대응: 합성 데이터는 Agent 구조 검증용으로만 사용하고, 운영 전에는 적법하게 확보한 실제 또는 가명처리 데이터로 추가 검증한다.

### 리스크 2: 라벨 생성 룰이 Agent에게 노출됨

대응: policy document와 hidden adjudication rules를 분리한다. Agent에는 `policy_documents.md`와 `claims_*.jsonl`만 제공한다.

### 리스크 3: 특정 라벨이 너무 적게 생성됨

대응: generation report에서 분포를 검증하고, 부족한 시나리오는 oversampling한다.

### 리스크 4: 실제 개인정보처럼 보이는 값 생성

대응: 모든 식별자는 `SYN`, `SAMPLE`, `POL`, `CLM` 접두사를 사용하고, 실제 주민등록번호, 전화번호, 계좌번호 형식은 생성하지 않는다.

## 14. Insured Profile and Privacy-Minimized Claim Context

Data Generator must generate claim payloads that can be reviewed by the Agent without exposing direct personal identifiers.

Required generation rules:

- Every generated claim must include `insured_profile`.
- `insured_profile.insured_id` is a synthetic token, not a resident registration number, name, phone number, address, or account number.
- `insured_profile.age_at_service` is calculated as the age at incident/treatment service time, not claim submission time.
- `insured_profile.age_band`, `sex`, and `policyholder_relation` must be generated for age/relationship-sensitive review scenarios.
- Legacy `claimant` may remain for backward compatibility, but `insured_profile` is the standard Agent input.
- Provider identity must use `claim.provider_id` token. Real hospital names or addresses must not be generated.
- Receipt matching must use `claim.receipt_hash` and `claim_history.prior_receipt_hashes`; raw receipt IDs are legacy compatibility fields.

Fraud-signal generation must use privacy-minimized behavior features:

- same insured token + same provider token repeated claims: `claim_history.same_insured_provider_claims_30d`
- provider-level aggregate volume: `claim_history.same_provider_claims_30d`
- duplicate receipt matching: `claim.receipt_hash` in `claim_history.prior_receipt_hashes`
- no direct name, resident registration number, phone, address, or bank account values

Age-based generation does not create automatic denial labels. Age edge cases may create `human_review` labels only when the hidden adjudication rule requires reviewer confirmation.

## 15. Fraud_Check Synthetic Data Extension

### 15.1 Purpose

The Data Generator must also create synthetic data for Fraud_Check Agent development and evaluation. This extension keeps the existing claim-review schema compatible with the AI Agent Template while adding fraud-specific context, medical-document PDFs, document metadata, and isolated fraud labels.

### 15.2 Required Outputs

Fraud_Check generation writes the following files under `data_generator/generated/`:

- `insureds.json`
- `providers.json`
- `historical_claims.jsonl`
- `document_metadata_dev.jsonl`
- `document_metadata_eval.jsonl`
- `claim_document_links_dev.jsonl`
- `claim_document_links_eval.jsonl`
- `fraud_labels_dev.jsonl`
- `fraud_labels_eval.jsonl`
- `fraud_context_seed_dev.jsonl`
- `fraud_context_seed_eval.jsonl`
- `documents/dev/{claim_id}/*.pdf`
- `documents/eval/{claim_id}/*.pdf`

Existing claim-review files remain unchanged in purpose:

- `claims_dev.jsonl`
- `claims_eval.jsonl`
- `labels_dev.jsonl`
- `labels_eval.jsonl`

### 15.3 Synthetic Safety Rules

- No real person, hospital, resident registration number, phone number, address, or account number may be generated.
- Synthetic IDs must use clear prefixes such as `INS-SYN-*`, `PROV-SYN-*`, `CLM-DEV-*`, `CLM-EVAL-*`, `DOC-SYN-*`, and `RCT-SYN-*`.
- Every readable PDF must contain `SYNTHETIC TEST DOCUMENT / 실제 사용 불가`.
- PDF metadata must mark the document as synthetic.
- dev/eval insured IDs, receipt lineage, and document fingerprints must not overlap.

### 15.4 Fraud Scenarios

The generator must guarantee at least one dev and one eval row for:

- normal clean claim
- exact duplicate receipt hash
- legacy duplicate receipt ID
- altered duplicate receipt
- forged amount
- forged date
- forged provider
- explicit fraudulent-document signal
- same insured/provider repeat boundary: 2 and 3 claims
- provider-volume boundary: 49 and 50 claims
- complex fraud combinations
- hard negatives
- missing document
- corrupted PDF
- low-OCR scan-like document
- unreadable/protected document simulation

Fraud-suspected labels must route to `human_review`; fraud suspicion must not be represented as automatic denial.

### 15.5 Label Isolation

`fraud_labels_dev.jsonl` and `fraud_labels_eval.jsonl` are evaluation-only files. Runtime claim payloads, claim history, document metadata, and PDFs must not contain `expected_*` fields or fraud answer reason codes. Fraud_Check runtime and claim-review workflow must not receive the fraud-label file path.

### 15.6 History Aggregation

`historical_claims.jsonl` must contain individual historical claim rows. Current claim `claim_history` aggregate values must be computed from those rows:

- `prior_receipt_ids`
- `prior_receipt_hashes`
- `same_insured_provider_claims_30d`
- `same_provider_claims_30d`
- `same_diagnosis_claims_90d`
- `manual_therapy_count_180d`

The aggregation must include exactly-30-day claims, exclude claims older than 30 days for 30-day counters, and exclude future-dated claims.

## 16. Medical Code and Causality Data Extension

The Data Generator must be extendable to create synthetic data for medical review, KCD/EDI code mapping, and medical causality analysis. This supports the AI Agent Template's future specialist agents while preserving the current runtime label-isolation principle.

### 16.1 Purpose

Synthetic medical-review data must help evaluate whether a claim's diagnosis, treatment, documents, and prior medical context are medically coherent. The goal is not to make automatic medical denial decisions. The goal is to generate review cases where the Agent can recommend coverage analysis, additional documents, or human medical review.

### 16.2 Runtime Medical Evidence Fields

Generated claims now include an optional `medical_evidence` object that is compatible with the AI Agent Template input schema. This is runtime-safe evidence, not an answer label.

The object contains:

- KCD diagnosis-code candidates with confidence and provenance
- EDI treatment/procedure-code candidates with confidence and provenance
- ambiguity flag and ambiguity reason
- prior diagnosis evidence within 180 days
- prior surgery evidence within 365 days
- prior test evidence within 180 days
- treatment-continuity days
- pre-existing-condition indicators
- insurer-style medical routing rules with rule ID, version, routing, reason code, confidence, and evidence references

These fields must remain compatible with `ai_agent_template` input schemas. If new runtime fields are required, the AI Agent Template schema must be versioned first and the Data Generator must follow that version.

### 16.3 Label Isolation

Medical-review labels must be separated from runtime payloads in the same way as claim-review labels and fraud labels.

Evaluation-only files include:

- `medical_labels_dev.jsonl`
- `medical_labels_eval.jsonl`
- `code_mapping_labels_dev.jsonl`
- `code_mapping_labels_eval.jsonl`
- `policy_coverage_labels_dev.jsonl`
- `policy_coverage_labels_eval.jsonl`
- `insurer_medical_routing_rules.json`

Runtime claim files, document metadata, and PDF contents must not contain `expected_medical_decision`, `expected_causality`, `expected_kcd_code`, `expected_edi_code`, `medical_scenario`, `policy_coverage_scenario`, or label-only answer fields.

`medical_evidence.insurer_medical_routing_rules` may include reviewer-routing evidence such as `human_review` or `request_documents`, but it must not include hidden scenario names or `expected_*` fields.

The bundled `insurer_medical_routing_rules.json` is synthetic and must be replaceable with insurer-approved rules. Production rules must include owner, version, effective date, approval status, reason code, routing, and confidence guidance.

### 16.4 Required Scenario Families

The future generator should support at least:

- clear KCD mapping
- ambiguous KCD mapping requiring human review
- clear EDI mapping
- ambiguous EDI mapping requiring human review
- diagnosis and treatment are compatible
- diagnosis and treatment are weakly related
- diagnosis and treatment are not clinically related
- prior medical history suggests possible pre-existing condition
- repeated treatment suggests possible excessive treatment
- high-cost treatment with sufficient medical evidence
- high-cost treatment with insufficient medical evidence
- document OCR/text extraction failure requiring human review

Medical suspicion must not be represented as automatic denial. Suspicious, ambiguous, or low-evidence medical cases should generate `human_review` or `request_documents` labels depending on the hidden adjudication rule.

### 16.5 Document Understanding Data

Generated medical documents should be extendable beyond receipts and statements to include:

- diagnosis certificate
- detailed medical bill
- procedure or surgery record
- test result summary
- physician note
- prior-treatment summary

For each document, metadata should support text-based extraction and VLM/document-understanding evaluation:

- document type
- extraction mode: `text_pdf`, `ocr_text`, `scan_image`, `vlm_required`
- extraction confidence bucket
- table-extraction status
- field-level extraction status
- synthetic marker

The Data Generator must keep synthetic markers in every generated document and must not use real medical records.
