# Product Requirement Document: Insurance Claims Review AI Agent MVP

## 1. 목적

`mvp`는 `data_generator`와 `ai_agent_template`을 기반으로 실제 실행 가능한 보험 청구 자동 심사 보조 Agent 애플리케이션을 구현하는 단계다.

이 MVP는 보험금 지급을 자동 확정하는 시스템이 아니다. MVP의 역할은 고객이 제출한 보험 청구 정보를 입력받고, AI Agent가 약관/담보/서류/면책/위험 신호/지급예상금액을 검토한 뒤 보험 심사자에게 보조 의견을 제공하는 것이다. 최종 지급 결정은 반드시 사람 심사자 또는 기존 심사 시스템이 수행한다.

개발 순서는 다음 구조를 따른다.

```text
Data Generator
-> AI Agent Template
-> AI Agent MVP
```

## 2. 배경

보험 청구 자동 심사는 고객 권익, 지급 정확성, 설명 가능성, 감사 가능성이 모두 중요한 업무다. 따라서 MVP는 처음부터 실제 보험사 데이터와 운영 시스템에 직접 연결하지 않고, 다음 기반 위에서 안전하게 검증한다.

- `data_generator`에서 생성한 synthetic claim 데이터
- `ai_agent_template`의 입력/출력 JSON schema
- `ai_agent_template`의 workflow와 tool contract
- synthetic tool plugin
- SQLite 기반 local runtime 저장소
- evaluation runner
- FastAPI 기반 API와 화면 prototype

MVP의 핵심 가치는 자동 지급이 아니라, 심사자의 판단을 빠르고 일관되게 돕는 것이다.

## 3. 범위

### 3.1 포함 범위

- 고객 청구 입력 API
- 고객 청구 입력 화면 prototype
- 보험 심사자 assistant 화면 prototype
- Agent review API
- Agent workflow 실행
- `ai_agent_template` SDK 연동
- synthetic plugin 기반 담보/서류/면책/계산/위험 판단
- `policy_documents.md`와 구조화 상품 데이터 기반 약관 근거 제공
- Template의 RAG-ready `KeywordPolicyRetriever` 기반 약관 citation 제공
- SQLite 저장소 사용
- repository abstraction 사용
- evaluation API
- generated eval dataset 기반 성능 평가
- Agent output JSON schema validation
- human review 강제 조건 적용
- reviewer-facing summary와 policy basis 제공

### 3.2 제외 범위

- 실제 보험금 지급 자동 확정
- 실제 보험사 기간계 시스템 연동
- 실제 고객 개인정보 처리
- 실제 보험사 약관 원문 PDF 자동 파싱
- 운영 인증/인가 체계
- PostgreSQL 전환
- Docker 필수화
- 대규모 RAG/vector DB 구축
- 실시간 fraud detection 모델 운영
- 운영 모니터링/알림 체계

위 제외 범위는 MVP 이후 단계에서 별도 요구사항으로 정의한다.

## 4. 사용자

### 4.1 고객 또는 청구 신청자

고객은 보험 청구에 필요한 정보를 입력하고 제출한다. MVP 단계에서는 실제 고객 서비스를 제공하지 않고, synthetic claim 또는 JSON payload를 기반으로 고객 입력 화면 흐름을 검증한다.

고객 화면에서는 다음 정보를 다룬다.

- 계약 정보
- 상품 정보
- 진료/처방/입원 정보
- 청구금액
- 제출서류
- 청구 이력 요약

고객 화면에는 Agent의 fraud signal, 내부 reason code, 정답 라벨, 위험 점수를 노출하지 않는다.

### 4.2 보험 심사자

보험 심사자는 Agent가 생성한 심사 보조 의견을 확인한다.

심사자 화면에서는 다음 정보를 확인한다.

- 청구 기본 정보
- 담보 매칭 결과
- 권고 결정
- 지급예상금액
- 계산 근거
- 누락서류
- 면책/부지급 검토 사유
- 사람 심사 필요 사유
- 약관 근거
- confidence
- reviewer note

심사자는 Agent 의견을 승인, 수정, 보류, 추가서류 요청, 사람 심사 지정할 수 있어야 한다.

### 4.3 AI Agent 개발자

개발자는 `ai_agent_template`의 SDK, plugin interface, Starter Kit을 활용하여 MVP를 개발한다. MVP 개발자는 Template의 schema와 tool contract를 임의 변경하지 않고, 필요한 차이는 plugin 또는 config로 반영한다.

## 5. 제품 원칙

MVP는 다음 원칙을 반드시 따른다.

1. Agent는 심사자 보조 의견만 제공한다.
2. 최종 지급 결정은 자동 확정하지 않는다.
3. 입력은 `claim_review_input.schema.json`을 만족해야 한다.
4. 출력은 `claim_review_output.schema.json`을 만족해야 한다.
5. 지급액 계산은 LLM이 아니라 `payable_calculator` tool 결과를 사용한다.
6. `human_review` 강제 조건은 우회할 수 없다.
7. 정답 라벨 파일은 Agent runtime에서 접근하지 않는다.
8. 모든 권고에는 `policy_basis`와 `reason_codes`를 포함한다.
9. 약관 판단은 구조화된 Policy Knowledge를 우선 사용한다.
10. LLM은 판단 확정이 아니라 설명 생성과 요약 보조에 제한적으로 사용한다.
11. MVP는 대규모 vector DB를 구축하지 않지만, Template의 RAG-ready retrieval schema와 citation metadata를 보존한다.

## 6. 약관 및 Policy Knowledge

MVP의 보상 심사 기준이 되는 약관은 원문 문서와 구조화 규칙으로 분리한다.

```text
약관 원문
-> 조항 단위 정리
-> 구조화 Policy Knowledge
-> tool plugin 참조
-> Agent output policy_basis
```

### 6.1 사람이 읽는 약관 문서

초기 MVP에서는 다음 문서를 사용한다.

```text
data_generator/generated/policy_documents.md
```

역할:

- 심사자와 LLM이 근거를 확인할 수 있는 설명용 문서
- `policy_basis.source`에 표시되는 근거 문서
- `policy_search` plugin의 검색 대상

### 6.2 기계가 읽는 구조화 약관

초기 MVP에서는 다음 파일을 구조화 Policy Knowledge의 source of truth로 사용한다.

```text
data_generator/generated/products.json
```

구조화 항목:

- product_id
- product_version
- effective_date
- coverage_code
- coverage_name
- care_setting
- benefit_category
- limit_per_claim
- annual_limit
- deductible type
- deductible rate
- fixed deductible amount
- required_documents
- exclusion rules
- human_review rules

### 6.3 향후 실제 약관 적용 원칙

실제 보험사 약관을 적용할 때는 원문 PDF, Word, HWP를 Agent에 그대로 넣지 않는다. 먼저 다음 절차를 따른다.

1. 원문 약관 수집
2. 조항 단위 chunking
3. clause_id 부여
4. 담보/면책/한도/서류/계산 규칙 추출
5. 사람 검수
6. policy version 부여
7. Policy Knowledge plugin 연결
8. 동일 evaluation harness로 회귀 검증

모든 약관 판단은 version과 clause_id로 추적 가능해야 한다.

### 6.4 MVP의 RAG-ready 적용 범위

MVP는 실제 vector DB, embedding pipeline, reranker를 구축하지 않는다. 다만 `ai_agent_template`에 포함된 RAG-ready 구조를 사용해 약관 근거를 citation 가능한 형태로 전달한다.

적용 범위:

- `KeywordPolicyRetriever`를 사용한 local keyword retrieval
- `policy_chunk.schema.json`, `retrieval_request.schema.json`, `retrieval_result.schema.json` 준수
- `policy_basis`에 `clause_id`, `citation_id`, `retrieval_score`, `retrieval_method`가 있으면 보존
- retrieval 결과가 없거나 근거가 불명확하면 `human_review`로 fallback

상세 기준은 다음 문서를 따른다.

```text
ai_agent_template/docs/RAG_READY.md
```

## 7. 시스템 구성

MVP는 다음 구조를 권장한다.

```text
mvp/
  app/
    api/
      claims.py
      reviews.py
      evaluations.py
      configs.py
      standards.py
    core/
      settings.py
      review_service.py
      evaluation_service.py
      policy_knowledge_service.py
    db/
      repository.py
      sqlite.py
      migrations.py
    ui/
      customer_claim_screen.html
      reviewer_assistant_screen.html
  config/
    app_config.yaml
    model_config.yaml
    plugins.yaml
  tests/
  docs/
    PRD.md
    TECH_SPEC.md
  README.md
```

MVP는 `ai_agent_template` 내부 파일을 복사해서 수정하기보다, Template SDK를 참조한다.

```python
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    TemplateBundle,
    ToolRegistry,
    WorkflowRunner,
    EvaluationRunner,
)
```

## 8. 주요 기능 요구사항

### FR-001 청구 접수

MVP는 고객 또는 테스트 데이터로부터 청구 payload를 입력받는다.

API:

```text
POST /claims
GET /claims/{claim_id}
```

요구사항:

- 입력 payload는 Template input schema를 통과해야 한다.
- schema validation 실패 시 저장하지 않고 `VALIDATION_ERROR`를 반환한다.
- claim payload는 SQLite에 저장한다.
- 동일 claim_id 재접수 시 update 또는 reject 정책을 명확히 적용한다.

### FR-002 Agent 심사 보조 의견 생성

MVP는 청구 1건에 대해 Agent review를 실행한다.

API:

```text
POST /reviews
GET /reviews/{claim_id}
POST /reviews/{claim_id}/rerun
POST /reviews/{claim_id}/actions
```

요구사항:

- `WorkflowRunner`를 통해 Template workflow를 실행한다.
- 8개 tool plugin을 사용할 수 있어야 한다.
- output schema validation을 반드시 수행한다.
- tool 실패 시 failure policy에 따라 `human_review`로 fallback한다.
- 낮은 담보 매칭 신뢰도는 `human_review`로 보낸다.
- 약관 retrieval citation metadata가 있으면 `policy_basis`에 보존한다.
- 결과는 SQLite에 저장한다.

### FR-003 지급예상금액 계산

MVP는 지급예상금액을 `payable_calculator` tool 결과로 산정한다.

요구사항:

- LLM이 지급액을 직접 계산하지 않는다.
- `recommended_payable_amount`는 `calculation.payable_amount`와 같아야 한다.
- 한도 적용 여부와 자기부담금을 calculation에 남긴다.

### FR-004 서류 확인

MVP는 담보별 필수서류 누락 여부를 확인한다.

요구사항:

- `document_checker` plugin을 사용한다.
- 필수서류가 누락되면 `request_documents`를 권고한다.
- `request_documents` 출력에는 `missing_documents`가 비어 있으면 안 된다.

### FR-005 면책 및 부지급 검토

MVP는 명확한 면책 조건을 확인한다.

요구사항:

- `exclusion_checker` plugin을 사용한다.
- 미용 목적, 기왕증, 고의 사고, 비의료기관, 비보장 치료 등은 부지급 검토 권고로 분류한다.
- 단, fraud 또는 mandatory human review 신호가 더 높은 우선순위인 경우 `human_review`를 우선한다.

### FR-006 Human Review 강제 조건

다음 조건은 반드시 `human_review`로 보낸다.

- 중복 영수증 의심
- 허위 또는 위조 서류 의심
- fraud signal 존재
- 통원 고액 청구
- 입원 고액 청구
- 동일 진단 반복 청구
- 도수치료 반복 청구
- 사고일과 최초 진료일 간격 과다
- 서류와 청구 내용 불일치
- 담보 매칭 confidence 기준 미달
- 필수 tool 실패

출력 조건:

```json
{
  "recommended_decision": "human_review",
  "requires_human_review": true
}
```

### FR-007 고객 화면

MVP는 고객 청구 입력 화면 prototype을 제공한다.

화면 요구사항:

- 계약 정보 입력
- 진료/처방/입원 정보 입력
- 청구금액 입력
- 제출서류 입력
- JSON payload preview
- 청구 제출

고객 화면에는 내부 위험 신호와 정답 라벨을 노출하지 않는다.

### FR-008 심사자 Assistant 화면

MVP는 심사자용 assistant 화면 prototype을 제공한다.

화면 요구사항:

- 권고 결정 표시
- 지급예상금액 표시
- 담보 매칭 결과 표시
- 계산 상세 표시
- 누락서류 표시
- 면책/위험 reason code 표시
- 약관 근거 표시
- confidence 표시
- reviewer action 버튼 제공

심사자 action은 API를 통해 저장되어야 하며, Agent output과 별도의 심사자 판단 이력으로 관리한다.

### FR-009 평가 실행

MVP는 synthetic eval dataset을 기반으로 Agent 성능을 평가한다.

API:

```text
POST /evaluations/runs
GET /evaluations/runs/{run_id}
```

요구사항:

- Agent output과 label file을 분리한다.
- evaluation runner만 `labels_*.jsonl`을 읽는다.
- claim_id 기준으로 output과 label을 매칭한다.
- 평가 결과를 SQLite에 저장한다.

### FR-010 Config 기반 교체

MVP는 plugin과 model provider를 config로 교체할 수 있어야 한다.

Config:

```text
mvp/config/plugins.yaml
mvp/config/model_config.yaml
```

Config key, 환경변수 override, secret 관리, plugin/model 교체 방식은 다음 Template 문서를 따른다.

```text
ai_agent_template/docs/CONFIGURATION.md
```

요구사항:

- synthetic plugin을 기본값으로 사용한다.
- 보험사별 plugin으로 교체 가능해야 한다.
- mock model provider를 기본값으로 사용한다.
- 향후 hosted LLM 또는 보험 특화 모델 provider로 교체 가능해야 한다.

### FR-011 RAG-ready Policy Retrieval

MVP는 Template의 RAG-ready policy retrieval 경로를 연결한다.

요구사항:

- 기본값은 `KeywordPolicyRetriever`를 사용한다.
- retrieval 설정은 config와 환경변수로 조정 가능해야 한다.
- 실제 vector DB는 MVP 범위에 포함하지 않는다.
- `PolicyKnowledgePluginConformance`를 통과하는 외부 retriever로 교체 가능해야 한다.
- 검색 결과의 `citation_id`, `clause_id`, `retrieval_score`, `retrieval_method`는 심사자 화면에서 확인 가능해야 한다.
- retrieval 실패 또는 citation 불명확 시 `human_review`로 보낸다.

## 9. API 요구사항

MVP의 최소 API는 다음과 같다.

```text
GET  /health

POST /claims
GET  /claims/{claim_id}

POST /reviews
GET  /reviews/{claim_id}
POST /reviews/{claim_id}/rerun
POST /reviews/{claim_id}/actions

POST /evaluations/runs
GET  /evaluations/runs/{run_id}

GET  /configs/model
PUT  /configs/model

GET  /standards/decision-codes
GET  /standards/reason-codes
GET  /standards/coverage-codes
GET  /standards/document-codes
```

API 응답은 JSON만 사용한다.

## 10. 데이터 저장 요구사항

초기 MVP는 SQLite를 사용한다.

권장 DB 파일:

```text
mvp/runtime/mvp.sqlite3
```

MVP는 repository abstraction을 사용한다.

```text
ReviewService
  -> ClaimReviewRepository
      -> SQLiteRepository
      -> PostgreSQLRepository later
```

저장 대상:

- claim review input
- agent output
- tool call log
- reviewer action
- evaluation run
- config version
- migration version
- retrieval metadata

Migration 원칙:

- `schema_migrations` 테이블을 사용한다.
- `migrations/*.sql`을 순차 적용한다.
- `schema.sql`은 전체 schema snapshot으로 유지한다.
- 향후 PostgreSQL 전환 시 repository 구현체만 교체한다.

## 11. 입력/출력 계약

MVP는 `ai_agent_template`의 schema를 그대로 사용한다.

입력:

```text
ai_agent_template/schemas/claim_review_input.schema.json
```

출력:

```text
ai_agent_template/schemas/claim_review_output.schema.json
```

MVP는 schema를 복사해서 수정하지 않는다. 변경이 필요하면 Template schema version을 먼저 변경하고, MVP는 해당 version을 명시적으로 사용한다.

## 12. 평가 지표

MVP의 기본 평가 지표는 다음과 같다.

- `schema_validity`
- `decision_accuracy`
- `coverage_accuracy`
- `payable_amount_exact_match`
- `payable_amount_mae`
- `missing_document_exact_match`
- `reason_code_overlap`
- `human_review_recall`
- `fraud_suspected_recall`
- `false_denial_rate`
- `false_payment_rate`
- `human_review_miss_rate`

초기 MVP 합격 기준:

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

Synthetic dataset 기준으로는 더 높은 성능을 기대할 수 있으나, 실제 데이터 적용 시 기준은 별도 리스크 검토 후 조정한다.

## 13. 비기능 요구사항

### NFR-001 안전성

MVP는 최종 지급 결정처럼 보이는 표현을 사용하지 않는다. 모든 문구는 권고 또는 보조 의견으로 표현한다.

### NFR-002 설명 가능성

모든 Agent output은 다음을 포함해야 한다.

- `policy_basis`
- `reason_codes`
- `calculation`
- `review_summary`
- `reviewer_notes`

### NFR-003 감사 가능성

MVP는 다음 이력을 저장해야 한다.

- 입력 payload
- Agent output
- tool call log
- model provider 정보
- schema/workflow/prompt version
- reviewer action

### NFR-004 교체 가능성

MVP는 다음 요소를 교체 가능하게 설계한다.

- model provider
- tool plugin
- Policy Knowledge source
- policy retriever
- repository implementation
- evaluation dataset

### NFR-005 개인정보 보호

MVP 단계에서는 실제 개인정보를 사용하지 않는다. 실제 데이터 적용 전 다음을 별도 설계한다.

- 비식별화
- 가명처리
- 접근권한
- 보관기간
- 감사 로그
- field-level masking

## 14. MVP 완료 기준

MVP는 다음 조건을 만족하면 완료로 본다.

- `/mvp` 하위에 독립 실행 가능한 FastAPI 앱이 있다.
- 고객 청구 입력 화면이 있다.
- 심사자 assistant 화면이 있다.
- `POST /claims`로 청구를 접수할 수 있다.
- `POST /reviews`로 Agent review를 실행할 수 있다.
- Agent output이 Template output schema를 통과한다.
- 8개 tool plugin이 workflow에서 호출된다.
- RAG-ready keyword retrieval 경로가 연결되고 `policy_basis` citation metadata가 보존된다.
- 지급액은 `payable_calculator` 결과를 사용한다.
- mandatory human review 조건이 적용된다.
- 결과가 SQLite에 저장된다.
- evaluation run을 실행할 수 있다.
- `data_generator/generated/claims_eval.jsonl` 기준 평가가 가능하다.
- Agent runtime은 `labels_*.jsonl`을 읽지 않는다.
- 전체 테스트가 통과한다.

## 15. 리스크 및 대응

### 리스크 1: Agent가 최종 지급 결정처럼 보임

대응: 출력 필드와 화면 문구를 모두 `recommended_*`, `권고`, `보조 의견` 중심으로 설계한다.

### 리스크 2: LLM이 계산을 임의로 수행

대응: 지급액 계산은 반드시 `payable_calculator` tool 결과만 사용한다.

### 리스크 3: 약관 근거가 불명확함

대응: 모든 결과에 `policy_basis`를 포함하고, 구조화 Policy Knowledge와 원문 clause를 연결한다.

### 리스크 4: 정답 라벨이 runtime에 노출됨

대응: labels 파일은 evaluation service에서만 읽고, review service와 workflow에서는 접근하지 않는다.

### 리스크 5: synthetic dataset에 과적합됨

대응: synthetic eval 통과 후 실제 데이터 적용 전 별도 holdout dataset, edge case dataset, 심사자 검수 dataset을 구성한다.

### 리스크 6: 실제 DB 전환 시 코드 변경 범위가 커짐

대응: MVP 초기부터 repository abstraction과 migration runner를 사용한다.

### 리스크 7: 약관 retrieval 결과를 과신함

대응: RAG 결과는 지급액 계산이나 최종 결정의 source of truth로 사용하지 않고, citation 가능한 약관 근거 보조로만 사용한다. 검색 결과가 없거나 confidence가 낮으면 `human_review`로 보낸다.

## 16. 향후 확장

MVP 이후 확장 후보:

- 실제 보험사 약관 구조화 pipeline
- PolicyKnowledgePlugin 구현
- 실제 보험사 claim data adapter
- 보험 특화 LLM provider
- vector DB와 hybrid RAG 기반 약관 검색
- PostgreSQL repository
- Docker 기반 실행 환경
- 운영 인증/인가
- reviewer feedback 기반 평가셋 보강
- human-in-the-loop 개선 workflow
## 17. Demo Scenario Builder Separation

This section supersedes the previous demo preset placement if there is a conflict.

MVP demo and real customer input must be visually and technically separated.

Customer input:

- Route: `/ui/customer`
- Purpose: direct claim input and submit flow
- Must not show expected decision, fraud scenario labels, demo verification checklist, or internal scenario shortcuts
- Must submit only `claim_review_input` compatible payload

Demo scenario builder:

- Route: `/ui/demo`
- API: `GET /demo/scenarios`, `GET /demo/scenarios/{scenario_id}`
- Config: `/mvp/config/demo_scenarios.json`
- Purpose: internal synthetic scenario testing, mutation, direct JSON editing, expected-vs-actual comparison
- May show expected recommendation and verification points as demo metadata
- Must not send expected recommendation, labels, or verification metadata as claim payload

Required demo capabilities:

- Load scenario preset from config
- Allow manual form edits
- Allow direct JSON edits
- Provide mutation buttons for common edge cases
- Submit claim through `/claims`
- Run review through `/reviews`
- Compare original expected recommendation with actual Agent output

The demo scenario layer must remain separable from customer claim intake, so future deployments can disable or remove `/ui/demo` and `/demo/*` without changing the customer claim or reviewer assistant workflows.

Fraud_Check v2 verification is presented as a separate preset group on `/ui/demo`. These presets use fixed generated claim IDs to retain links to seeded history and document evidence. They must cover clean, duplicate, altered duplicate, document mismatch, behavioral threshold, provider-volume threshold, and document-processing failure cases. Runtime payloads must not contain expected Fraud results or evaluation labels; expectation metadata is returned and rendered outside the claim object.

## 18. MVP Demo Scenario Presets

MVP는 시연과 내부 검증을 위해 고객 청구 화면에 demo scenario preset을 제공한다.
이 기능은 실제 고객 서비스 기능이 아니라, synthetic claim 기반으로 Agent workflow의 대표 판단 경로를 빠르게 확인하기 위한 MVP 보조 기능이다.

지원 preset은 다음 6개다.

| Scenario | Expected Agent Recommendation | Verification Focus |
| --- | --- | --- |
| Normal Pay | `pay` | 보장 대상, 서류 완비, 공제 적용 후 지급 권고 |
| Partial Pay | `partial_pay` | 보장 대상이나 1회 한도 적용으로 일부 지급 권고 |
| Request Documents | `request_documents` | 필수 서류 누락으로 추가 서류 요청 |
| Deny | `deny` | 계약 상태 또는 보장 기간 조건 불충족 |
| Human Review | `human_review` | 반복 청구, 고액 청구 등 심사자 확인 필요 |
| Fraud Signal | `human_review` | 중복 영수증 등 이상 신호로 human review 필요 |

요구사항:

- 고객 청구 화면에서 preset button을 클릭하면 입력 form이 해당 synthetic claim으로 채워진다.
- preset은 `claim_review_input` JSON Schema와 호환되어야 한다.
- preset의 expected result와 verification focus는 화면에서 확인 가능해야 한다.
- expected result는 payload로 전송하지 않는다.
- 평가용 label file은 기존과 동일하게 evaluation service에서만 접근한다.
- 실제 심사 결과와 근거는 `/reviews` 실행 후 심사자 assistant 화면에서 확인한다.
- backend workflow, schema, repository, evaluation logic은 이 기능 추가로 변경하지 않는다.

## 19. Insured Profile and Privacy-Minimized MVP Intake

This section supersedes older claim-intake descriptions where they conflict.

MVP claim intake and demo scenarios must submit `insured_profile` with each claim. The MVP assumes one insured person per claim review request, represented by token fields rather than direct personal identity.

Required MVP input fields:

- `insured_profile.insured_id`
- `insured_profile.age_at_service`
- `insured_profile.age_band`
- `insured_profile.sex`
- `insured_profile.policyholder_relation`
- `claim.provider_id`
- `claim.receipt_hash`
- `claim_history.same_insured_provider_claims_30d`
- `claim_history.same_provider_claims_30d`
- `claim_history.prior_receipt_hashes`

MVP fraud signal demo must show behavior-based review without raw PII:

- duplicate receipt via receipt hash
- same insured and same provider repetition via aggregate counter
- provider-level anomaly via aggregate counter

The reviewer assistant may display `insured_id`, age, and sex because they are review-useful and privacy-minimized. It must not display or require raw name, resident registration number, phone, address, or account information.

## 20. LLM Provider and Tool-First Agent Behavior

The MVP uses the same AI Agent Template pattern as the template runtime:

- deterministic tools/rules decide coverage, documents, exclusions, calculation, fraud signal, and human-review routing
- the configured LLM generates reviewer-facing narrative fields only
- schema validation and decision validation remain mandatory
- the LLM must not override `recommended_decision`, `recommended_payable_amount`, `reason_codes`, `calculation`, or `policy_basis`

Current MVP model configuration:

```yaml
active_provider: general_llm
providers:
  general_llm:
    provider_type: openai_compatible
    base_url: https://m2.geniemars.kt.co.kr:10601/v1
    api_key: dummy
    model_id: gemma-4-26B-4aB-it
```

## 21. Fraud_Check Remote Review Requirement

MVP fraud review must be performed through the AI Agent Template `fraud_signal_checker` tool contract. Until Fraud_Check is complete, the default MVP `plugins.yaml` uses the synthetic fraud checker for local demos.

Remote Fraud_Check integration is enabled by selecting:

```yaml
# mvp/config/plugins.remote.yaml
fraud_signal_checker:
  module: mvp.app.plugins.remote_fraud_signal_checker
  class: RemoteFraudSignalCheckerPlugin
```

Required environment:

```powershell
$env:CLAIM_MVP_PLUGIN_CONFIG = "C:\Users\PC\AA\Automated_Claims_Processing\mvp\config\plugins.remote.yaml"
$env:FRAUD_CHECK_URL = "http://127.0.0.1:8010"
$env:FRAUD_CHECK_API_KEY = "optional-token"
```

Business rules:

- Fraud_Check is an assistant signal provider, not a final fraud adjudicator.
- `fraud_suspected=true` must always route the claim to `human_review`.
- Fraud_Check unavailability, timeout, HTTP error, invalid JSON, or invalid response contract must fail closed to `human_review`.
- The system must not automatically deny a claim because of fraud signal.
- The system must not automatically pay a claim when Fraud_Check is unavailable.
- Default local/demo execution must not require Fraud_Check to be running.
- Raw claim payloads and direct personal identifiers must not be written to general application logs.

## 22. Specialist Agent UX and MVP Scope Direction

This section is a planned MVP direction and does not require immediate implementation. The AI Agent Template remains the source of truth. MVP changes must follow Template schema, workflow, and plugin contracts.

### 22.1 MVP Role

The MVP should demonstrate how a Template-based Orchestrator Agent can consume specialist agent reports and present them to an insurance reviewer. MVP must not define incompatible specialist-agent behavior independently from `/ai_agent_template`.

### 22.2 Planned Specialist Report Areas

The reviewer assistant screen should be extendable to display:

- Assistant Recommendation
- Policy and Coverage Analysis
- Medical Review and Causality
- Fraud Risk
- Document Understanding
- Calculation and Deductible Trace
- Evidence and Tool Trace

These areas may be implemented as tabs, collapsible panels, or compact worklist sections. The customer claim-intake screen should remain minimally changed.

### 22.3 Policy and Coverage UX

MVP should show policy analysis in reviewer-facing language:

- matched policy clauses
- rider/special-term findings
- exclusions or non-coverage clauses
- deductible and limit basis
- citation status
- conflicts or unclear clauses

Low citation quality must be displayed as a reviewer warning, not as a hidden failure.

### 22.4 Medical Review UX

MVP should show medical review as an assistant report, not as a final medical adjudication.

Reviewer-visible fields may include:

- normalized KCD code and mapping confidence
- normalized EDI code and mapping confidence
- diagnosis-treatment relationship
- medical necessity summary
- pre-existing condition review signal
- excessive-treatment review signal
- requested additional documents
- reason for human medical review

MVP must consume the AI Agent Template `medical_evidence` input contract when present. The customer screen should not expose or edit this object directly in normal claim intake; demo or generated-data flows may submit it as structured synthetic evidence.

The customer screen should not expose internal KCD/EDI uncertainty, fraud labels, medical labels, or hidden scenario metadata.

### 22.5 Document Understanding UX

MVP should support document-understanding results from OCR, text PDF extraction, or VLM providers when the Template introduces the contract.

Reviewer-visible fields may include:

- document type
- extracted key fields
- extraction confidence
- field mismatch warnings
- table extraction status
- VLM/OCR fallback status

Raw full OCR text, raw document bytes, and direct personal identifiers should not be displayed by default.

### 22.6 Model Provider Expectation

The current MVP `general_llm` provider is used for reasoning over structured evidence and generating reviewer-facing narrative. It must not be assumed to perform VLM document reading unless the serving endpoint has passed a provider conformance test for image/PDF input.

If VLM is required, MVP should configure a separate Template-compatible provider such as `document_vlm` and keep the existing `general_llm` for orchestration and narrative generation.

## 23. Specialist Agent Foundation Alignment

The MVP now mirrors the AI Agent Template foundation for future specialist-agent development.

Implemented MVP foundations:

- KCD medical-code registry persistence through SQLite.
- EDI procedure-code registry persistence through SQLite.
- diagnosis-treatment relationship rule persistence for medical review and causality checks.
- specialist agent report and document extraction result tables for future reviewer-facing panels.
- registry seed command that loads synthetic outputs from `data_generator/generated`.
- model-provider role separation: `general_llm` remains the orchestrator/reasoning provider, while `document_vlm` is configured as a disabled, separately testable document-understanding provider.

The MVP keeps the current claim/review workflow stable. Specialist reports are additive and must not replace the deterministic workflow output fields: `recommended_decision`, `recommended_payable_amount`, `coverage_code`, `calculation`, `policy_basis`, `reason_codes`, and `requires_human_review`.

Medical specialist routing from `medical_evidence.insurer_medical_routing_rules` is reviewer-facing by default. It should not override the final claim-review decision unless a later insurer-approved workflow policy explicitly promotes medical routing to final workflow routing.

MVP must seed and query Template-compatible `medical_routing_rules` so the demo can run with synthetic rules and later switch to insurer-approved rules without changing API handlers or UI contracts.

MVP must provide the same official registry import command as the AI Agent Template Starter Kit. Official KCD/EDI rows and insurer medical routing rules are operational configuration data, not customer claim data and not evaluation labels.

Runtime label isolation remains mandatory. `medical_labels_*`, `code_mapping_labels_*`, `policy_coverage_labels_*`, `fraud_labels_*`, and claim-review `labels_*` are evaluation-only files and must not be loaded into the runtime DB or exposed through runtime APIs.

Official KCD/EDI data is not bundled. Production use must import authorized official files or APIs, store source/version/effective-date/checksum/license metadata, and avoid redistributing restricted code tables unless the insurer has the right to do so.

## 24. Specialist Report Runtime Consumption

The MVP now consumes the AI Agent Template's `specialist_reports` output during review execution.

Reviewer-facing reports currently include:

- Policy and Coverage Analysis
- Document Understanding
- Medical Review and Causality
- Fraud Risk Analysis

The default MVP report source is a synthetic insurer-style plugin pack. It demonstrates how insurer-specific specialist plugins can be swapped through configuration without changing claim intake, deterministic payment calculation, or reviewer authority.

The customer claim screen does not expose internal agent reports. It provides a separate post-submission PDF attachment area, while reviewer users inspect specialist reports in the Reviewer Assistant `Agent Reports` section after running review.

This is still an assistant-support feature. Specialist reports must not become final payment decisions without reviewer action or insurer-approved downstream workflow.

## Customer PDF Upload Requirement

- The customer claim screen supports attaching a typed PDF after `POST /claims` succeeds.
- MVP reuses the AI Agent Template upload service, repository contract, integrity checks, and internal Document API behavior.
- Uploaded document types and the actual medical-receipt SHA-256 are synchronized into the persisted claim before review.
- Invalid MIME, oversized, empty, malformed, unknown-claim, and unsupported document-type uploads return structured errors.
