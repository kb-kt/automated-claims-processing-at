# Product Requirement Document: Insurance Claims Review AI Agent Template

## 1. 목적

`ai_agent_template`은 보험 청구 자동 심사 AI Agent MVP를 개발하기 전에 필요한 재사용 가능한 Agent 설계 표준을 정의한다. 이 Template은 실제 심사 Agent가 아니라, Agent의 역할, 입력/출력 계약, 판단 절차, 사용 가능한 도구, 안전장치, 평가 기준을 명확히 하는 설계 산출물이다.

이 Template은 `data_generator`에서 생성한 합성 실손형 의료보험 데이터와 가상 약관을 기준으로 우선 설계한다. 향후 실제 데이터와 실제 약관을 적용할 때도 동일한 구조를 유지하고, 데이터 adapter와 약관/룰 지식만 교체할 수 있게 하는 것을 목표로 한다.

## 2. 배경

보험 청구 자동 심사는 고객 권익에 직접 영향을 줄 수 있는 고위험 업무다. 따라서 초기 Agent는 최종 지급 결정을 자동으로 확정하지 않고, 심사자 보조 의견과 최종 지급 결정에 대한 권고안을 제시하는 역할로 제한한다.

현재 프로젝트는 다음 순서로 개발한다.

```text
Data Generator
→ AI Agent Template
→ AI Agent MVP
```

`Data Generator`는 합성 청구 데이터와 정답 라벨을 생성한다. `AI Agent Template`은 Agent가 어떤 방식으로 판단하고 어떤 형식으로 답해야 하는지 정의한다. `AI Agent MVP`는 이 Template을 실제 LLM, RAG, 룰 도구, 평가 harness와 연결한 실행체다.

## 3. 범위

### 3.1 포함 범위

- 보험 청구 심사 보조 Agent의 역할 정의
- Agent 입력 JSON 스키마 정의
- Agent 출력 JSON 스키마 정의
- 심사 판단 workflow 정의
- 사용 가능한 tool contract 정의
- 반드시 `human_review`로 보내야 하는 조건 정의
- 평가 지표 및 합격 기준 정의
- Data Generator 산출물과의 연결 방식 정의
- Agent MVP 구현 전 필요한 prompt, schema, workflow, eval 산출물 요구사항 정의

### 3.2 제외 범위

- 실제 LLM API 호출 구현
- 실제 RAG/vector DB 구현
- 실제 보험사 약관 또는 실제 고객 데이터 적용
- 실제 보험금 지급 자동 확정
- 운영 배포용 권한, 인증, 개인정보 처리 시스템 구현
- 법률, 규제, 보험업 감독 기준에 대한 최종 적합성 판단

## 4. Agent Template과 Agent의 차이

| 구분 | AI Agent Template | AI Agent MVP |
|---|---|---|
| 성격 | 설계도, 계약, 표준 | 실제 실행 가능한 Agent |
| 목적 | 판단 구조와 입출력 표준화 | 청구건을 입력받아 심사 의견 생성 |
| 모델 의존성 | 낮음 | 특정 LLM/API/runtime에 연결 |
| 도구 연결 | tool contract 정의 | 실제 tool 구현 및 호출 |
| 데이터 연결 | 샘플/합성 데이터 기준 | 합성 또는 실제 데이터 처리 |
| 결과 | 구현 기준 문서와 템플릿 파일 | Agent 출력 JSON 및 평가 결과 |

Template은 Agent가 아니다. Template은 Agent MVP를 만들기 위한 역할 정의, prompt, schema, workflow, tool contract, 평가 기준의 묶음이다.

## 5. 사용자

- AI Agent 개발자
- 보험 보상 심사 업무 설계자
- 평가 harness 개발자
- QA 및 리스크 검증 담당자
- 향후 실제 데이터 adapter 개발자

## 6. Agent 역할

Agent는 보험 청구 건에 대해 다음 역할을 수행한다.

- 청구 데이터의 구조적 완전성 확인
- 청구 유형에 맞는 담보 후보 식별
- 필수서류 누락 여부 확인
- 약관상 면책 가능성 확인
- 담보 한도와 자기부담금 기준의 지급예상금액 산정 요청
- 반복청구, 중복 영수증, 문서 불일치 등 위험 신호 확인
- 사람 심사 필요 여부 판단
- 최종 지급 결정에 대한 보조 의견 제시
- 심사자가 검토할 수 있는 근거와 설명 생성

Agent는 다음을 해서는 안 된다.

- 실제 보험금 지급을 최종 확정
- 약관 또는 도구 결과에 없는 근거를 생성
- 지급액 계산을 LLM 추론만으로 수행
- 필수 `human_review` 조건을 무시
- 출력 스키마를 벗어난 자유 형식 응답 반환

## 7. 입력 데이터 기준

초기 Template은 Data Generator 산출물을 기준으로 한다.

Agent 입력 가능 파일:

```text
data_generator/generated/policy_documents.md
data_generator/generated/claims_dev.jsonl
data_generator/generated/claims_eval.jsonl
```

평가 전용 파일:

```text
data_generator/generated/labels_dev.jsonl
data_generator/generated/labels_eval.jsonl
```

Agent는 `labels_*.jsonl`을 읽거나 참조해서는 안 된다. 정답 라벨은 평가 harness에서만 사용한다.

## 8. 입력 JSON 스키마

Agent는 `claims_*.jsonl`의 각 라인을 하나의 청구 심사 입력으로 받는다.

### 8.1 필수 필드

```json
{
  "claim_id": "string",
  "policy_id": "string",
  "product_id": "string",
  "scenario_type": "string",
  "claimant": {
    "synthetic_person_id": "string",
    "age": "integer",
    "gender": "F | M"
  },
  "policy": {
    "status": "active | lapsed | terminated | pending",
    "coverage_start_date": "YYYY-MM-DD",
    "coverage_end_date": "YYYY-MM-DD"
  },
  "claim": {
    "care_setting": "outpatient | inpatient | pharmacy",
    "benefit_category": "covered | noncovered | special_noncovered",
    "treatment_code": "string",
    "diagnosis_code": "string",
    "incident_date": "YYYY-MM-DD",
    "treatment_start_date": "YYYY-MM-DD",
    "treatment_end_date": "YYYY-MM-DD",
    "claim_date": "YYYY-MM-DD",
    "claimed_amount": "integer",
    "receipt_id": "string",
    "provider_type": "medical_institution | pharmacy | non_medical_provider"
  },
  "documents": ["string"],
  "claim_history": {
    "same_diagnosis_claims_90d": "integer",
    "manual_therapy_count_180d": "integer",
    "prior_receipt_ids": ["string"]
  },
  "signals": {
    "cosmetic_purpose": "boolean",
    "pre_existing_condition": "boolean",
    "intentional_injury": "boolean",
    "non_medical_provider": "boolean",
    "suspected_duplicate_receipt": "boolean",
    "document_claim_mismatch": "boolean"
  }
}
```

### 8.2 입력 제약

- `claimed_amount`는 0 이상의 KRW 정수여야 한다.
- 모든 날짜는 ISO date 형식이어야 한다.
- Agent 입력에는 `expected_decision`, `expected_payable_amount`, `reason_codes`, `calculation` 등 정답 라벨 필드가 포함되면 안 된다.
- 실제 개인정보, 주민등록번호, 전화번호, 계좌번호, 실제 병원명은 포함하지 않는다.

## 9. 출력 JSON 스키마

Agent는 각 claim에 대해 반드시 하나의 JSON 객체만 출력한다.

### 9.1 필수 필드

```json
{
  "claim_id": "string",
  "recommended_decision": "pay | partial_pay | request_documents | deny | human_review",
  "recommended_payable_amount": "integer",
  "coverage_code": "string",
  "coverage_name": "string",
  "missing_documents": ["string"],
  "reason_codes": ["string"],
  "requires_human_review": "boolean",
  "fraud_suspected": "boolean",
  "confidence": "number",
  "calculation": {
    "claimed_amount": "integer",
    "eligible_amount": "integer",
    "limit_applied": "boolean",
    "deductible_amount": "integer",
    "payable_amount": "integer"
  },
  "policy_basis": [
    {
      "source": "policy_documents.md",
      "section": "string",
      "summary": "string"
    }
  ],
  "review_summary": "string",
  "reviewer_notes": ["string"]
}
```

### 9.2 출력 규칙

- `recommended_decision`은 허용 목록 중 하나여야 한다.
- `recommended_payable_amount`는 `calculation.payable_amount`와 같아야 한다.
- `request_documents`인 경우 `missing_documents`는 비어 있으면 안 된다.
- `fraud_suspected=true`이면 `requires_human_review=true`여야 한다.
- `requires_human_review=true`이면 `recommended_decision`은 `human_review`여야 한다.
- 지급액 계산은 `payable_calculator` 도구 결과를 사용해야 한다.
- `confidence`는 0.0 이상 1.0 이하 숫자여야 한다.
- `review_summary`는 심사자 보조 의견이어야 하며, 최종 지급 확정 문구를 사용하지 않는다.

## 10. 판단 순서

Agent는 다음 순서를 따른다.

1. 입력 스키마 검증
2. 약관 문서 및 상품 기준 확인
3. 청구 유형 기반 담보 후보 식별
4. 계약 상태 및 보장기간 확인
5. 중복청구, 허위서류, 비정상 신호 확인
6. 필수서류 누락 여부 확인
7. 명확한 면책 조건 확인
8. 지급액 계산 도구 호출
9. 사람 심사 필요 조건 확인
10. 최종 보조 의견 생성
11. 출력 JSON 스키마 검증

판단 우선순위는 다음과 같다.

```text
1. fraud 또는 duplicate signal → human_review
2. 계약 실효 또는 보장기간 외 → deny
3. 필수서류 누락 → request_documents
4. 명확한 면책 조건 → deny
5. 고액, 반복청구, 문서 불일치 등 사람 심사 조건 → human_review
6. 한도 초과 또는 자기부담금 적용 → partial_pay 또는 pay
7. 정상 보장 → pay
```

## 11. 사용 가능한 도구

Template은 실제 도구 구현이 아니라 tool contract를 정의한다. Agent MVP 단계에서 아래 도구를 실제 함수, API, 룰엔진, 검색 모듈로 구현한다.

### 11.1 `policy_search`

목적: 약관/담보/면책/심사 기준 검색

입력:

```json
{
  "product_id": "string",
  "query": "string"
}
```

출력:

```json
{
  "matches": [
    {
      "section": "string",
      "summary": "string",
      "source": "policy_documents.md"
    }
  ]
}
```

### 11.2 `coverage_resolver`

목적: 청구 건이 어떤 담보에 해당하는지 매칭

입력:

```json
{
  "claim": "claim object",
  "product_id": "string"
}
```

출력:

```json
{
  "coverage_code": "string",
  "coverage_name": "string",
  "confidence": "number"
}
```

### 11.3 `document_checker`

목적: 담보별 필수서류 누락 확인

입력:

```json
{
  "coverage_code": "string",
  "submitted_documents": ["string"]
}
```

출력:

```json
{
  "missing_documents": ["string"],
  "submitted_documents": ["string"],
  "documents_complete": "boolean"
}
```

### 11.4 `exclusion_checker`

목적: 면책 조건 해당 여부 확인

입력:

```json
{
  "claim": "claim object",
  "policy": "policy object",
  "signals": "signals object"
}
```

출력:

```json
{
  "excluded": "boolean",
  "exclusion_reason_codes": ["string"],
  "explanation": "string"
}
```

### 11.5 `payable_calculator`

목적: 담보 한도와 자기부담금을 적용한 지급예상금액 계산

입력:

```json
{
  "coverage_code": "string",
  "claimed_amount": "integer",
  "claim": "claim object"
}
```

출력:

```json
{
  "claimed_amount": "integer",
  "eligible_amount": "integer",
  "limit_applied": "boolean",
  "deductible_amount": "integer",
  "payable_amount": "integer"
}
```

### 11.6 `risk_checker`

목적: 사람 심사 필요 여부 판단

입력:

```json
{
  "claim": "claim object",
  "claim_history": "claim_history object",
  "signals": "signals object"
}
```

출력:

```json
{
  "requires_human_review": "boolean",
  "risk_reason_codes": ["string"]
}
```

### 11.7 `fraud_signal_checker`

목적: 중복청구, 허위서류, 비정상 패턴 탐지

입력:

```json
{
  "claim": "claim object",
  "claim_history": "claim_history object",
  "signals": "signals object"
}
```

출력:

```json
{
  "fraud_suspected": "boolean",
  "fraud_reason_codes": ["string"]
}
```

### 11.8 `decision_validator`

목적: Agent 최종 출력이 스키마와 정책을 지키는지 검증

입력:

```json
{
  "agent_output": "agent output object"
}
```

출력:

```json
{
  "valid": "boolean",
  "errors": ["string"],
  "warnings": ["string"]
}
```

## 12. 반드시 human_review로 보내는 조건

다음 중 하나라도 해당하면 Agent는 반드시 `recommended_decision=human_review`, `requires_human_review=true`를 출력해야 한다.

- 동일 영수증 번호 재사용
- 허위 또는 위조 서류 의심
- fraud signal 존재
- 통원 청구금액 1,000,000원 이상
- 입원 청구금액 10,000,000원 이상
- 최근 90일 내 동일 진단코드 3회 이상 청구
- 최근 180일 내 도수치료 관련 청구 20회 이상
- 사고일과 최초 진료일 차이 30일 초과
- 진단코드와 치료항목 불일치
- 서류 발급일, 진료일, 청구일 순서 비정상
- 비급여 비중이 80% 이상이고 청구금액이 고액
- 담보 매칭 confidence가 기준 미만
- 약관 근거를 찾지 못했지만 지급/부지급 판단이 필요한 경우
- 도구 호출 실패로 지급액, 면책, 서류 누락 여부를 확정할 수 없는 경우

## 13. Reason Code 기준

Agent 출력의 `reason_codes`는 평가와 추적을 위해 표준화한다.

예상 reason code:

```text
COVERED_INCIDENT
DOCUMENTS_COMPLETE
MISSING_REQUIRED_DOCUMENT
DEDUCTIBLE_APPLIED
PER_CLAIM_LIMIT_APPLIED
LAPSED_POLICY
INCIDENT_BEFORE_COVERAGE_START
INCIDENT_AFTER_COVERAGE_END
COSMETIC_TREATMENT_EXCLUDED
PRE_EXISTING_CONDITION_EXCLUDED
INTENTIONAL_INJURY_EXCLUDED
NON_MEDICAL_PROVIDER_EXCLUDED
UNSUPPORTED_TREATMENT_EXCLUDED
DUPLICATE_RECEIPT_SUSPECTED
FRAUD_SIGNAL
HIGH_OUTPATIENT_AMOUNT
HIGH_INPATIENT_AMOUNT
REPEATED_SAME_DIAGNOSIS
FREQUENT_MANUAL_THERAPY
LATE_FIRST_TREATMENT
DOCUMENT_CLAIM_MISMATCH
HUMAN_REVIEW_REQUIRED
PROVISIONAL_CALCULATION_AVAILABLE
TOOL_FAILURE
LOW_CONFIDENCE_COVERAGE_MATCH
```

## 14. 평가 지표

평가는 Agent 출력과 `labels_*.jsonl`을 비교해 수행한다.

### 14.1 기본 정확도 지표

- `decision_accuracy`: `recommended_decision`이 `expected_decision`과 일치하는 비율
- `coverage_accuracy`: `coverage_code`가 정답과 일치하는 비율
- `payable_amount_exact_match`: 지급예상금액이 정확히 일치하는 비율
- `payable_amount_mae`: 지급예상금액 평균 절대 오차
- `missing_document_exact_match`: 누락서류 목록이 정확히 일치하는 비율
- `reason_code_overlap`: 정답 reason code와 Agent reason code의 교집합 비율
- `schema_validity`: 출력 JSON이 스키마를 만족하는 비율

### 14.2 라벨별 지표

- `pay_precision`, `pay_recall`
- `partial_pay_precision`, `partial_pay_recall`
- `request_documents_precision`, `request_documents_recall`
- `deny_precision`, `deny_recall`
- `human_review_precision`, `human_review_recall`

### 14.3 보험 심사 리스크 지표

- `false_denial_rate`: 실제 지급 또는 일부 지급 대상인데 Agent가 부지급으로 권고한 비율
- `false_payment_rate`: 부지급 또는 서류요청 대상인데 Agent가 지급으로 권고한 비율
- `underpayment_rate`: 지급액을 정답보다 낮게 산정한 비율
- `overpayment_rate`: 지급액을 정답보다 높게 산정한 비율
- `human_review_miss_rate`: 사람 심사 대상인데 Agent가 자동 판단한 비율
- `fraud_suspected_recall`: 이상청구 의심 건을 놓치지 않은 비율

### 14.4 권장 MVP 합격 기준

초기 합성 데이터 기준 권장 기준은 다음과 같다.

```text
schema_validity = 100%
decision_accuracy >= 90%
coverage_accuracy >= 95%
payable_amount_exact_match >= 95%
missing_document_exact_match >= 95%
human_review_recall >= 98%
fraud_suspected_recall >= 98%
false_denial_rate <= 1%
human_review_miss_rate <= 1%
```

위 기준은 합성 데이터 기반 MVP 기준이며, 실제 데이터 적용 시 별도 리스크 검토 후 조정한다.

## 15. Template 산출물

AI Agent Template 개발 완료 시 다음 파일이 생성되어야 한다.

```text
ai_agent_template/
  docs/
    PRD.md
    TECH_SPEC.md
    CONFIGURATION.md
    EVALUATION.md
  prompts/
    system_prompt.md
    claim_review_prompt.md
    output_format_prompt.md
  schemas/
    claim_review_input.schema.json
    claim_review_output.schema.json
    tool_contracts.schema.json
  workflows/
    claim_review_workflow.yaml
  examples/
    sample_claim_input.json
    sample_agent_output.json
  eval/
    metrics.md
    evaluation_plan.md
```

## 16. 비기능 요구사항

### NFR-001 안전성

Agent는 심사자 보조 의견만 제공한다. 출력에는 자동 지급 확정, 자동 부지급 확정처럼 오해될 수 있는 문구를 사용하지 않는다.

### NFR-002 설명 가능성

모든 출력은 `policy_basis`, `reason_codes`, `review_summary`를 포함해야 한다.

### NFR-003 계산 신뢰성

금액 계산은 LLM 추론이 아니라 `payable_calculator` 도구 결과를 사용한다.

### NFR-004 스키마 안정성

Agent 출력은 항상 JSON schema를 만족해야 한다. schema validation 실패는 Agent 실패로 본다.

### NFR-005 평가 가능성

모든 출력 필드는 `labels_*.jsonl`과 비교 가능한 구조여야 한다.

### NFR-006 데이터 분리

Agent는 평가 정답 파일을 읽지 않는다. 정답 파일은 평가 harness에서만 사용한다.

### NFR-007 확장성

실손형 의료보험 외 상품으로 확장할 수 있도록 workflow와 tool contract는 상품군 독립적으로 설계한다.

## 17. 인수 기준

AI Agent Template PRD 기준 개발은 다음 조건을 만족하면 완료로 본다.

- 입력 JSON 스키마가 정의되어 있다.
- 출력 JSON 스키마가 정의되어 있다.
- 심사 판단 순서가 정의되어 있다.
- 사용 가능한 tool contract가 정의되어 있다.
- 반드시 `human_review`로 보내야 하는 조건이 정의되어 있다.
- 평가 지표와 MVP 합격 기준이 정의되어 있다.
- Data Generator 산출물과 연결 방식이 명확하다.
- Agent Template과 실제 Agent MVP의 경계가 명확하다.

## 18. 리스크 및 대응

### 리스크 1: Agent가 최종 지급 결정처럼 동작

대응: 역할을 심사자 보조 의견으로 제한하고, 출력 필드를 `recommended_*`로 명명한다.

### 리스크 2: LLM이 지급액을 임의 계산

대응: 지급액은 반드시 `payable_calculator` 결과를 사용하고, 도구 실패 시 `human_review`로 보낸다.

### 리스크 3: 정답 라벨이 Agent에 노출

대응: Agent 입력 파일과 평가 파일을 분리하고, Template에 정답 파일 접근 금지 원칙을 명시한다.

### 리스크 4: 평가가 accuracy에만 치우침

대응: false denial, false payment, human review miss, fraud recall 등 보험 심사 리스크 지표를 별도 관리한다.

### 리스크 5: 실제 데이터 적용 시 개인정보 리스크 발생

대응: 실제 데이터 적용 전 비식별화 또는 가명처리, 접근권한, 보관기간, 감사 로그 기준을 별도 설계한다.

## 19. 개발자 제공 패키지 확장: SDK + Plugin Interface + Starter Kit

AI Agent Template은 문서와 스키마만 제공하는 수준에서 끝나지 않고, 다른 개발자가 실제 Agent MVP를 빠르고 일관되게 만들 수 있도록 다음 3가지 개발자 제공 패키지를 포함하는 방향으로 확장한다.

```text
AI Agent Template
  -> SDK
  -> Plugin Interface
  -> Starter Kit
  -> AI Agent MVP
```

### 19.1 SDK

SDK는 Template 산출물을 코드에서 안전하게 사용할 수 있게 해주는 Python 기반 개발 도구 묶음이다. SDK는 새로운 심사 기준을 임의로 정의하지 않고, `ai_agent_template` 하위의 schema, workflow, prompt, standards, tool contract를 단일 출처로 읽어 사용한다.

SDK의 주요 책임:

- Template root를 로드하고 버전을 확인한다.
- 입력 claim JSON을 `claim_review_input.schema.json`으로 검증한다.
- Agent 출력 JSON을 `claim_review_output.schema.json`으로 검증한다.
- reason code, coverage code, document code, decision code 표준 registry를 조회한다.
- workflow 정의를 로드하고 실행 순서를 제공한다.
- tool plugin을 등록하고 contract와 호환되는지 확인한다.
- model provider를 교체 가능한 인터페이스로 호출한다.
- 평가 데이터셋과 Agent 출력 파일을 비교해 evaluation metric을 계산한다.

SDK가 하지 않아야 하는 일:

- 보험금 최종 지급 결정을 자동 확정하지 않는다.
- Template에 없는 decision code, reason code를 임의 생성하지 않는다.
- 정답 라벨 파일을 Agent runtime에 노출하지 않는다.
- 지급액 계산을 LLM 추론으로 대체하지 않는다.

### 19.2 Plugin Interface

Plugin Interface는 보험사별 규칙, 검색 방식, 계산기, 모델 provider를 교체할 수 있게 하는 표준 연결 계층이다. Template의 tool contract를 구현체와 분리하여, MVP 이후 실제 보험사 환경에 맞는 도구를 단계적으로 교체할 수 있게 한다.

초기 plugin 유형:

- `ToolPlugin`: `policy_search`, `coverage_resolver`, `document_checker`, `exclusion_checker`, `payable_calculator`, `risk_checker`, `fraud_signal_checker`, `decision_validator` 구현체
- `ModelProviderPlugin`: 범용 LLM, 보험 특화 모델, 온프레미스 모델 adapter
- `DataAdapterPlugin`: Data Generator 산출물 또는 실제 보험사 청구 데이터 변환 adapter
- `PolicyKnowledgePlugin`: 약관 문서, 룰 테이블, 검색 인덱스 연결 adapter
- `EvaluationPlugin`: 보험사별 평가 지표 또는 리포트 확장 adapter

모든 plugin은 다음 조건을 만족해야 한다.

- 이름, 버전, 소유자, 지원 contract version을 선언한다.
- 입력과 출력이 지정된 JSON schema를 통과해야 한다.
- 실패 시 표준 error shape를 반환해야 한다.
- 처리 시간, 상태, error code가 audit log에 남을 수 있어야 한다.
- `human_review` 강제 조건을 우회할 수 없다.
- 정답 라벨 파일에 접근할 수 없다.

### 19.3 Starter Kit

Starter Kit은 AI Agent Template 기반 MVP를 시작하기 위한 실행 가능한 FastAPI 예제 프로젝트다. 개발자는 Starter Kit을 복사하거나 참조하여 `/mvp` 하위에 실제 MVP를 만들 수 있다.

Starter Kit의 목적:

- Template 기반 Agent API를 빠르게 실행한다.
- Customer Claim Screen과 Reviewer Assistant Screen의 기본 화면 흐름을 제공한다.
- SDK validator, workflow runner, plugin registry를 실제로 연결하는 예제를 제공한다.
- Data Generator 산출물을 입력으로 사용해 end-to-end smoke test를 수행한다.
- SQLite 기반 local runtime 저장 구조를 예시로 제공한다.
- 기본 synthetic plugin으로 모델 API 없이도 로컬 검증이 가능하게 한다.

Starter Kit이 포함해야 할 기본 기능:

- `POST /claims`: 청구 입력 접수 및 schema validation
- `POST /reviews`: Agent 보조 심사 의견 생성
- `GET /reviews/{claim_id}`: 심사 결과 조회
- `POST /evaluations/runs`: evaluation dataset 기반 평가 실행
- Customer Claim Screen prototype
- Reviewer Assistant Screen prototype
- plugin 등록 예제
- model provider 교체 예제
- SQLite schema 적용 예제
- schema validation 및 workflow smoke test

### 19.4 개발자 경험 요구사항

다른 개발자가 Template 기반 Agent를 만들 때 다음 흐름을 따를 수 있어야 한다.

1. `ai_agent_template`을 기준으로 SDK를 설치한다.
2. Starter Kit을 실행한다.
3. Data Generator에서 생성한 sample claim을 입력한다.
4. 기본 synthetic plugin으로 Agent 출력을 생성한다.
5. 출력 schema와 workflow validation을 통과하는지 확인한다.
6. 보험사별 plugin을 하나씩 교체한다.
7. 동일 evaluation harness로 성능과 안전 기준을 비교한다.
8. 기준을 통과하면 `/mvp` 구현으로 확장한다.

### 19.5 추가 인수 기준

SDK + Plugin Interface + Starter Kit 확장 개발은 다음 조건을 만족하면 완료로 본다.

- SDK가 Template root를 로드하고 schema, standards, workflow, prompt 경로를 해석할 수 있다.
- SDK가 입력과 출력 JSON validation을 수행할 수 있다.
- Plugin Interface가 tool plugin의 공통 protocol과 error shape를 정의한다.
- 최소 8개 tool contract에 대한 plugin conformance test가 있다.
- Starter Kit이 FastAPI로 실행 가능하다.
- Starter Kit이 Data Generator 산출물 중 claim 1건 이상을 입력받아 schema-valid Agent 출력을 생성할 수 있다.
- Starter Kit이 Customer Claim Screen과 Reviewer Assistant Screen의 기본 화면 흐름을 제공한다.
- SDK, plugin, Starter Kit이 모두 정답 라벨 파일을 Agent runtime에 노출하지 않는다.
- Starter Kit의 DB 접근은 repository 경계로 분리되어 향후 PostgreSQL 구현체로 교체 가능하다.
- SQLite 초기화는 migration 이력을 기록하며, `schema.sql`은 전체 schema snapshot으로 유지한다.

## 20. RAG-ready 요구사항

AI Agent Template은 초기에는 synthetic 약관과 구조화 상품 데이터를 사용하지만, MVP 이후 실제 보험사 약관과 심사지침을 적용할 수 있도록 RAG-ready 구조를 포함한다.

RAG-ready는 실제 vector DB나 embedding pipeline을 지금 구축한다는 의미가 아니다. 의미는 다음과 같다.

- 약관 chunk, retrieval request, retrieval result의 표준 schema를 제공한다.
- `policy_search` tool이 단순 markdown 검색뿐 아니라 retrieval adapter 결과를 받을 수 있게 한다.
- `PolicyKnowledgePlugin` interface를 제공해 keyword, vector, hybrid retriever를 교체할 수 있게 한다.
- Agent output의 `policy_basis`가 `clause_id`, `citation_id`, `retrieval_score`, `retrieval_method`를 optional metadata로 담을 수 있게 한다.
- 검색 결과가 없거나 근거가 불명확하면 `human_review`로 보내는 안전 원칙을 유지한다.

RAG 적용 대상은 우선 약관과 심사지침이다.

```text
policy_documents.md / products.json
-> policy chunks
-> KeywordPolicyRetriever
-> PolicyKnowledgePlugin
-> policy_search
-> policy_basis citation
```

청구 데이터 retrieval은 별도로 다룬다. 과거 유사 청구, 병원/진료/서류 패턴, fraud behavior 분석은 개인정보와 label leakage 위험이 있으므로 MVP 이후 feature store, 권한, 비식별화 기준을 포함해 설계한다.

RAG-ready 상세 기준은 다음 문서를 따른다.

```text
ai_agent_template/docs/RAG_READY.md
```

## 21. Insured Profile and Privacy-Minimized Review Input

The Agent Template assumes the claim is evaluated for a single insured person per request. This does not mean the Agent receives direct personal identity. The standard identity boundary is tokenized:

- `insured_profile.insured_id` identifies the same insured person within the review context.
- `claim.provider_id` identifies the medical provider or pharmacy as a token.
- `claim.receipt_hash` and `claim_history.prior_receipt_hashes` support duplicate receipt matching.
- `claim_history.same_insured_provider_claims_30d` supports repeated same-insured/same-provider behavior review.
- `claim_history.same_provider_claims_30d` supports provider-level aggregate pattern review.

The Agent must not require name, resident registration number, phone number, address, bank account, or raw hospital identity to generate an assistant recommendation.

Age-based review uses `insured_profile.age_at_service`. Age is a review condition, not an automatic denial condition. The default synthetic rule sends age edge cases to `human_review` when `age_at_service < 15` or `age_at_service >= 80`.

Fraud signal handling must be conservative:

- Fraud signals only recommend `human_review`.
- The Agent must not make a final fraud finding.
- Fraud reasoning must be auditable through reason codes such as `DUPLICATE_RECEIPT_SUSPECTED`, `SAME_INSURED_PROVIDER_REPEAT_SUSPECTED`, and `PROVIDER_PATTERN_ANOMALY_SUSPECTED`.
- Direct PII must remain outside the Agent input and should be handled by an upstream ingestion, consent, and identity verification layer.

## 22. Template Parity Requirements for MVP Reuse

The AI Agent Template must include reusable capabilities that are needed by the MVP, not only static schema and workflow definitions.

### 22.1 Operational API Requirements

Template-based applications should expose or be able to implement the following API surface:

- submit and retrieve claims
- list submitted claims
- run and rerun reviews
- retrieve reviewer queue
- save and list reviewer actions
- retrieve claim audit logs
- run evaluations
- retrieve active model/config metadata

The canonical review response field is `output`. Implementations may also return `agent_output` for backward compatibility.

### 22.2 Reviewer Experience Requirements

The reviewer screen should support:

- selecting from submitted claims as well as direct claim id entry
- clearing stale recommendation/evidence panels when a different claim is loaded
- showing a loading state while review workflow execution is in progress
- displaying deterministic confidence separately from LLM explanation confidence
- displaying evidence clarity, judgment difficulty, and uncertainty explanation
- saving reviewer actions and showing action/audit history

### 22.3 Confidence Requirements

The numeric `confidence` is a deterministic tool/rule workflow confidence. The LLM must not replace it with self-reported confidence.

The LLM may assist:

- `review_summary`
- `reviewer_notes`
- `confidence_assessment.evidence_clarity`
- `confidence_assessment.judgment_difficulty`
- `confidence_assessment.uncertainty_level`
- `confidence_assessment.uncertainty_explanation`
- `confidence_assessment.assessment_basis`

The Template must provide `explanation_confidence` so downstream apps can judge whether the LLM-written explanation remains faithful to tool outputs, policy basis, and calculation values.

### 22.4 Persistence Requirements

The Starter Kit persistence boundary must be repository-based and support:

- claim input storage
- agent output storage
- tool call logs
- retrieval logs
- reviewer action history
- audit logs
- evaluation run records

SQLite remains the local default. The repository boundary must allow future PostgreSQL implementation without changing service or API handlers.

## 23. Specialist Agent Architecture Direction

This section defines the next product direction for the AI Agent Template. It is documentation-only until the corresponding schemas, tool contracts, plugins, workflow, and tests are implemented.

The AI Agent Template is the main reusable deliverable. MVP implementations must consume this Template rather than defining incompatible agent behavior inside `/mvp`.

### 23.1 Orchestrator Agent Role

The current claim-review Agent should evolve into an Orchestrator Agent. The Orchestrator coordinates specialist agents and produces a reviewer-facing assistant recommendation. It must not act as the sole source of truth for coverage, fraud, medical causality, calculation, or final payment decision.

The Orchestrator is responsible for:

- validating input and output schemas
- selecting workflow branches
- invoking specialist tool/agent plugins
- merging specialist reports
- detecting conflicts among reports
- preserving citations and calculation trace
- routing uncertain or high-risk claims to `human_review`
- generating a concise reviewer-facing recommendation summary

### 23.2 Policy and Coverage Analysis Agent

`policy_search` and `coverage_resolver` should be extendable into a Policy and Coverage Analysis Agent.

Target responsibilities:

- search large policy corpora, riders, exclusions, non-coverage clauses, special terms, deductible clauses, and burden-of-proof clauses through RAG
- map claim facts, KCD/EDI codes, accident type, care setting, and benefit category to policy clauses
- return legal or contractual basis with citations
- distinguish coverage, exclusion, deductible, limit, and unclear-policy findings
- recommend `human_review` when citation quality is weak or clauses conflict

The Agent must not fabricate clauses. Low-retrieval confidence, missing citation, or citation mismatch must trigger reviewer attention rather than automatic pay or denial.

### 23.3 Fraud Risk Agent

`fraud_signal_checker` should remain the fraud boundary and evolve into a Fraud Risk Agent.

Target responsibilities:

- detect duplicate receipt and duplicate document signals
- analyze raw evidence from document hashes, fingerprints, claim history, and provider aggregates
- integrate with Fraud_Check v1/v2 through the existing plugin contract
- return fraud signal, risk score, reason codes, and evidence summary
- route `fraud_suspected=true` to `human_review`

Fraud risk output must never be used as an automatic denial. It is a reviewer-routing and investigation signal.

### 23.4 Medical Review and Causality Agent

The Template should add a Medical Review and Causality Agent.

Target responsibilities:

- normalize diagnosis and procedure codes using KCD/EDI mapping tools
- compare diagnosis, treatment, care setting, age, sex, document evidence, and prior-history indicators
- estimate diagnosis-treatment compatibility
- identify possible pre-existing condition review needs
- identify possible excessive-treatment review needs
- recommend additional documents or human medical review when evidence is insufficient

This Agent is distinct from Fraud Risk. Fraud focuses on suspicious behavior or document abuse. Medical Review focuses on medical relevance, causality, necessity, and evidence sufficiency.

### 23.5 KCD/EDI Code Mapping Agent

The Template should support a KCD/EDI Code Mapping Agent or tool layer.

Target responsibilities:

- map submitted diagnosis text and diagnosis codes to normalized KCD codes
- map treatment/procedure names and billing codes to normalized EDI codes
- return candidate mappings with confidence and provenance
- detect ambiguous or invalid codes
- provide normalized codes to policy, medical review, and calculation agents

Ambiguous mapping must not be silently resolved when it affects payment, exclusion, or human-review routing.

### 23.6 Document Understanding Agent

The Template should define a Document Understanding Agent contract for PDF/image medical documents.

Target responsibilities:

- classify document type
- extract structured fields from diagnosis certificates, receipts, detailed medical bills, prescriptions, test results, surgery/procedure notes, and physician notes
- preserve extraction confidence and field-level provenance
- flag when VLM or OCR review is required
- provide structured document evidence to Policy, Medical Review, Fraud Risk, and Orchestrator steps

The Template should support both text/OCR pipelines and VLM providers. The Orchestrator should consume structured extraction results rather than raw document bytes whenever possible.

### 23.7 Model Provider Note

The configured `general_llm` model may be suitable for orchestration, policy explanation, report synthesis, and reasoning over structured evidence. It must not be assumed to be sufficient for VLM document understanding unless the serving endpoint explicitly supports image or PDF inputs.

When VLM document understanding is required, the Template should allow a separate model provider such as `document_vlm` to be configured independently from `general_llm`.

### 23.8 Stage A Scope

Stage A implements the reusable foundation without changing the existing claim-review workflow:

- Agent Report standard
- optional output `specialist_reports`
- specialist contracts for Policy/Coverage Analysis, Document Understanding, KCD/EDI Code Mapping, and Medical Review/Causality
- synthetic KCD/EDI baseline registry files
- SQLite registry tables and seed/query boundary
- separate `document_vlm` provider configuration
- optional runtime `medical_evidence` input contract for candidate KCD/EDI mapping confidence, prior medical evidence, and insurer-style medical routing rules
- seedable medical routing rule registry for replacing synthetic rules with insurer-approved rules

Stage A does not yet make specialist agents mandatory workflow steps. The Orchestrator remains compatible with the existing deterministic workflow until the next implementation phase adds specialist plugins and workflow branching.

Real KCD/EDI imports are not included in this repository. Production onboarding must verify official distribution and license terms before loading real code tables.

### 23.9 Runtime Medical Evidence Contract

The Template accepts `medical_evidence` as an optional input object. It is designed to provide non-label evidence to specialist agents without exposing evaluation answers.

Allowed runtime evidence:

- KCD/EDI candidate mappings with confidence and provenance
- ambiguous mapping indicators and reason text
- prior diagnoses, surgeries, tests, and treatment-continuity facts
- pre-existing-condition indicators
- insurer-approved or synthetic-insurer medical routing rules

Disallowed runtime data:

- `expected_*` labels
- hidden medical scenario names
- claim-review labels
- fraud labels
- final adjudication answers

Medical specialist reports may use this evidence to recommend `continue_claim_review`, `request_documents`, or `human_review` inside `specialist_reports`. This does not by itself replace the deterministic claim-review decision unless the insurer explicitly approves a workflow rule that promotes medical routing into final workflow routing.

Synthetic routing rules are carried through `insurer_medical_routing_rules.json` and SQLite `medical_routing_rules`. Production implementations must replace these rows with insurer-approved rules and preserve version, owner, approval status, and effective dates.

### 23.10 Official Registry Import Requirement

The Template must support an approved-file import path for official KCD, official or insurer-authorized EDI/procedure codes, and insurer-approved medical routing rules.

Requirements:

- import from local insurer-approved CSV/JSON files rather than scraping public sites at runtime
- preserve source file, source URL, version, effective dates, and license note
- mark imported official rows as `synthetic=false`
- reject malformed insurer routing rules before SQLite seed
- keep raw official source files outside the repository unless redistribution is explicitly permitted
- expose the same import boundary to Starter Kit and MVP

## 24. Customer PDF Upload Requirement

- An accepted claim can receive one or more PDF attachments through a claim-scoped API.
- Uploads validate claim existence, registered document type, MIME, size, PDF structure, SHA-256, and page count.
- Generated synthetic documents and customer-uploaded runtime documents use separate storage roots.
- SQLite stores metadata and safe relative paths, not PDF bytes or client-provided paths.
- Uploaded receipts are available through the existing internal Document API for Fraud_Check v2 raw-evidence analysis.
- Customer-role authorization permits upload without granting arbitrary claim-read access.
