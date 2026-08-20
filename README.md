# Automated Claims Processing

보험 청구 자동 심사 AI Agent를 개발하기 위한 실험/검증용 프로젝트입니다. 실제 보험금 지급을 자동 확정하는 시스템이 아니라, 심사자가 검토할 수 있는 보조 의견과 지급/부지급/추가서류/사람 심사 권고를 생성하는 AI Agent 개발 기반을 만드는 것이 목적입니다.

현재 개발 흐름은 다음 순서를 기준으로 합니다.

```text
Data Generator -> AI Agent Template -> AI Agent MVP
```

## 프로젝트 취지

보험 청구 자동 심사는 고객 권익, 보험금 지급 정확성, 설명 가능성, 규제/감사 리스크가 모두 중요한 고위험 업무입니다. 따라서 초기 단계부터 실제 고객 데이터에 의존하기보다, 가상의 실손형 의료보험 상품과 가상의 청구 데이터를 생성하고, 정답 라벨이 있는 평가셋으로 Agent의 판단 품질을 반복 검증할 수 있어야 합니다.

이 프로젝트는 다음을 목표로 합니다.

- 실제 데이터 없이도 보험 청구 자동 심사 Agent 개발을 시작한다.
- 가상의 상품, 약관, 청구, 정답 라벨을 생성한다.
- Agent 입력/출력 JSON schema와 판단 workflow를 표준화한다.
- 지급액 계산, 서류 확인, 면책 판단, 사람 심사 조건을 도구화한다.
- Agent가 정답 라벨을 보지 못하게 분리하고, 별도 evaluation harness에서만 평가한다.
- 향후 실제 보험사 데이터와 보험 특화 모델로 교체할 수 있는 구조를 준비한다.

## 세부 항목 설명

### 1. Data Generator

위치:

```text
data_generator/
```

Data Generator는 가상의 실손형 의료보험 상품과 청구 데이터를 생성하는 독립 모듈입니다.

주요 역할:

- 가상 보험 상품 정의
- 가상 약관 문서 생성
- 가상 청구 데이터 생성
- 정답 라벨 생성
- 개발용/dev 평가용/eval 데이터 분리
- 생성 데이터 validation

주요 산출물:

```text
data_generator/generated/claims_dev.jsonl
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_dev.jsonl
data_generator/generated/labels_eval.jsonl
data_generator/generated/products.json
data_generator/generated/products/product_catalog.json
data_generator/generated/products/{product_id}.json
data_generator/generated/policies.jsonl
data_generator/generated/policy_documents.md
```

주의할 점:

- `claims_*.jsonl`은 Agent 입력입니다.
- `labels_*.jsonl`은 평가용 정답입니다.
- Agent runtime은 `labels_*.jsonl`을 읽으면 안 됩니다.
- Data Generator는 독립적으로 동작하되, 출력 schema는 AI Agent Template 입력 schema와 호환되어야 합니다.
- `products.json`은 기존 단일 active product 호환 파일이고, `products/product_catalog.json`은 다중 상품 인덱스입니다.
- 고객 화면은 Product ID를 직접 입력하거나 카탈로그에서 선택할 수 있으며, 선택된 Product Name과 해당 상품의 Policy 후보를 표시합니다.
- 제출 시 `policy_id`가 선택한 `product_id`에 실제로 연결되어 있는지 Template SDK의 `ProductCatalogRegistry`가 검증합니다.

기본 테스트:

```powershell
python -m unittest discover -s data_generator\tests
```

### 2. AI Agent Template

위치:

```text
ai_agent_template/
```

AI Agent Template은 실제 Agent MVP를 만들기 전, Agent가 따라야 할 계약과 표준을 정의하는 기준 패키지입니다.

주요 역할:

- 입력 JSON schema 정의
- 출력 JSON schema 정의
- 심사 판단 workflow 정의
- tool contract 정의
- reason/decision/coverage/document code 표준화
- prompt template 정의
- human review 강제 조건 정의
- 평가 기준 정의
- Developer Kit 제공

핵심 디렉토리:

```text
ai_agent_template/schemas/
ai_agent_template/workflows/
ai_agent_template/tools/contracts/
ai_agent_template/standards/
ai_agent_template/prompts/
ai_agent_template/eval/
ai_agent_template/docs/
ai_agent_template/developer_kit/
```

Developer Kit 구성:

```text
ai_agent_template/developer_kit/sdk/
ai_agent_template/developer_kit/plugin_interface/
ai_agent_template/developer_kit/plugins/synthetic/
ai_agent_template/developer_kit/starter_kit/
```

주요 기능:

- Template 로더
- schema validator
- standards registry
- workflow loader/runner
- tool registry
- evaluation runner
- plugin conformance test
- synthetic tool plugin 8종
- FastAPI Starter Kit
- SQLite 기반 local runtime 예제

기본 테스트:

```powershell
python -m unittest discover -s ai_agent_template
```

### 3. MVP

예정 위치:

```text
mvp/
```

MVP는 AI Agent Template을 기반으로 실제 실행 가능한 청구 자동 심사 보조 Agent를 구현하는 단계입니다. 현재 프로젝트에서는 MVP를 아직 루트 하위에 별도로 만들지 않았고, `/ai_agent_template/developer_kit/starter_kit`이 MVP 개발의 출발점 역할을 합니다.

MVP에서 구현할 내용:

- 실제 Agent API
- 고객 청구 화면
- 보험 심사자 assistant 화면
- 실제 또는 synthetic plugin 연결
- 모델 provider 연결
- RAG/약관 검색 연결
- 심사 결과 저장
- 평가 리포트 생성
- 운영/감사 로그 기반 확장

MVP 개발 시 지켜야 할 원칙:

- Template의 입력/출력 schema를 유지한다.
- 지급액 계산은 LLM이 아니라 calculator tool 결과를 사용한다.
- `human_review` 강제 조건을 우회하지 않는다.
- 정답 라벨은 Agent runtime에서 접근하지 않는다.
- 모델 교체 후에도 동일 evaluation dataset으로 회귀 검증한다.

## Developer Guide

이 섹션은 AI Agent Template을 기반으로 AI Agent를 개발하는 절차를 설명합니다.

### 1. 전체 구조 이해

Agent 개발자는 먼저 다음 문서를 읽는 것을 권장합니다.

```text
ai_agent_template/docs/PRD.md
ai_agent_template/docs/TECH_SPEC.md
ai_agent_template/docs/CONFIGURATION.md
ai_agent_template/docs/EVALUATION.md
ai_agent_template/docs/API_SPEC_DRAFT.md
```

특히 확인해야 할 기준:

- Agent는 심사자 보조 의견을 생성한다.
- 최종 지급 결정은 사람이 수행한다.
- 출력은 항상 `claim_review_output.schema.json`을 만족해야 한다.
- 권고 결정은 `pay`, `partial_pay`, `request_documents`, `deny`, `human_review` 중 하나여야 한다.
- 고위험 조건은 반드시 `human_review`로 보낸다.

### 2. SDK 사용

SDK는 Template 산출물을 코드에서 안전하게 사용할 수 있게 해줍니다.

주요 진입점:

```python
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    TemplateBundle,
    SchemaValidator,
    ToolRegistry,
    WorkflowRunner,
    EvaluationRunner,
)
```

기본 사용 예:

```python
from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    TemplateBundle,
    ToolRegistry,
    WorkflowRunner,
)

template = TemplateBundle.load("ai_agent_template")

registry = ToolRegistry(template)
for plugin in default_synthetic_plugins():
    registry.register(plugin)
registry.validate_registered_plugins()

runner = WorkflowRunner(template, tool_registry=registry)
agent_output = runner.run(claim_payload)
```

### 3. Plugin 개발

실제 보험사 규칙이나 시스템을 연결할 때는 Template 자체를 수정하기보다 plugin을 교체합니다.

Plugin 유형:

- `ToolPlugin`: 약관 검색, 담보 매칭, 서류 확인, 면책 판단, 지급액 계산 등
- `ModelProviderPlugin`: 범용 LLM, 보험 특화 모델, 온프레미스 모델 연결
- `DataAdapterPlugin`: 실제 보험사 청구 데이터를 Template 입력 schema로 변환

Tool plugin은 다음 조건을 만족해야 합니다.

- `name`
- `version`
- `contract_name`
- `contract_version`
- `owner`
- `timeout_ms`
- `failure_policy`
- `run(payload, context)`

Plugin 검증:

```powershell
python -m unittest discover -s ai_agent_template\developer_kit\plugin_interface\tests
```

### 4. Synthetic Plugins 사용

기본 synthetic plugin은 Data Generator 산출물과 호환되는 기준 구현체입니다.

제공되는 tool plugin:

```text
policy_search
coverage_resolver
document_checker
exclusion_checker
payable_calculator
risk_checker
fraud_signal_checker
decision_validator
```

위치는 다음과 같습니다.

```text
ai_agent_template/developer_kit/plugins/synthetic/
```

이 plugin들은 MVP 초기 개발과 smoke test에 사용할 수 있습니다. 실제 보험사 적용 시에는 이 plugin들을 보험사별 구현체로 교체합니다.

### 5. Starter Kit 실행

Starter Kit은 FastAPI 기반 예제 앱입니다.

설정 파일의 역할, plugin/model 교체, 환경변수 override는 다음 문서를 기준으로 합니다.

```text
ai_agent_template/docs/CONFIGURATION.md
```

위치:

```text
ai_agent_template/developer_kit/starter_kit/
```

의존성 설치:

```powershell
C:\Python314\python.exe -m pip install -r C:\Users\PC\AA\Automated_Claims_Processing\ai_agent_template\developer_kit\starter_kit\requirements.txt
```

서버 실행:

```powershell
cd C:\Users\PC\AA\Automated_Claims_Processing\ai_agent_template\developer_kit\starter_kit
C:\Python314\python.exe -m uvicorn app.main:app --reload --port 8000
```

또는 프로젝트 루트에서 실행할 수 있습니다.

```powershell
cd C:\Users\PC\AA\Automated_Claims_Processing
C:\Python314\python.exe -m uvicorn ai_agent_template.developer_kit.starter_kit.app.main:app --reload --port 8000
```

접속 URL:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/ui/customer
http://127.0.0.1:8000/ui/reviewer
```

Starter Kit 테스트:

```powershell
python -m unittest discover -s ai_agent_template\developer_kit\starter_kit\tests
```

### 6. 평가 실행

Agent 출력은 정답 라벨과 비교해 평가합니다.

평가 기준 예:

- `schema_validity`
- `decision_accuracy`
- `coverage_accuracy`
- `payable_amount_exact_match`
- `missing_document_exact_match`
- `human_review_recall`
- `fraud_suspected_recall`
- `false_denial_rate`
- `human_review_miss_rate`

중요 원칙:

- Agent는 `claims_*.jsonl`만 입력으로 사용합니다.
- `labels_*.jsonl`은 evaluation runner에서만 사용합니다.
- 평가 결과가 좋아도 실제 지급 결정은 자동 확정하지 않습니다.

### 7. 호환성 테스트

Data Generator 출력과 AI Agent Template 입력 schema의 호환성은 별도 integration test에서 검증합니다.

```powershell
python -m unittest discover -s integration_tests
```

이 테스트는 두 모듈의 독립성을 유지하면서도, 생성 데이터가 Agent Template 입력으로 사용 가능한지 확인합니다.

## 권장 개발 순서

1. Data Generator로 synthetic 데이터 생성
2. integration test로 schema 호환성 확인
3. AI Agent Template의 SDK와 synthetic plugin으로 workflow 검증
4. Starter Kit으로 API/UI smoke test 수행
5. `/mvp` 하위에 실제 MVP 프로젝트 생성
6. synthetic plugin을 보험사별 plugin으로 단계적 교체
7. 동일 evaluation harness로 회귀 검증

## 전체 테스트 명령

```powershell
python -m unittest discover -s data_generator\tests
python -m unittest discover -s ai_agent_template
python -m unittest discover -s integration_tests
```

## 현재 상태

- Data Generator 구현 완료
- AI Agent Template 구현 완료
- SDK 구현 완료
- Plugin Interface 구현 완료
- Synthetic Plugins 8종 구현 완료
- FastAPI Starter Kit 구현 완료
- Data Generator와 AI Agent Template 간 integration test 구현 완료
- `/mvp` FastAPI/API/UI/SQLite 기반 구현 완료
- Fraud_Check v1/v2 연동 경계, fail-closed 정책, 내부 fraud-context/document API 구현 완료
- Specialist Agent report 생성, 저장, API 조회, Reviewer 화면 표시 구현 완료
- Document extraction fallback, `document_vlm` conformance hook, extraction 결과 저장 구현 완료

## 향후 Agentic AI 고도화 방향

Main 산출물은 `/ai_agent_template`이며, `/mvp`는 Template 기반 구현 예시입니다. 따라서 새로운 Agentic AI 기능은 먼저 Template의 schema, workflow, tool contract, plugin interface, evaluation 기준으로 정의하고, MVP는 해당 계약을 적용하는 방식으로 개발합니다.

권장 구조:

```text
Claim Input
-> Orchestrator Agent
   -> Policy and Coverage Analysis Agent
   -> Fraud Risk Agent
   -> Medical Review and Causality Agent
   -> KCD/EDI Code Mapping Agent
   -> Document Understanding Agent
   -> Payable Calculation Agent
   -> Decision Validator
-> Reviewer Assistant Output
```

핵심 원칙:

- 현재 claim-review Agent는 전체 사령관 역할의 Orchestrator Agent로 발전시킨다.
- `policy_search`와 `coverage_resolver`는 대규모 약관/RAG/citation 검증을 포함하는 Policy and Coverage Analysis Agent로 확장한다.
- `fraud_signal_checker`는 Fraud_Check v1/v2 연동을 유지하면서 Fraud Risk Agent 경계로 관리한다.
- 의료 심사와 인과관계 분석은 Fraud Risk와 분리된 Medical Review and Causality Agent로 추가한다.
- KCD/EDI 코드 매핑은 별도 Agent 또는 tool layer로 두고, 모호한 매핑은 `human_review`로 보낸다.
- 문서 판독은 OCR/text extraction과 VLM provider를 분리해서 설계한다.
- `gemma-4-26B-4aB-it`는 구조화된 증거 기반 reasoning과 reviewer-facing narrative에 사용하고, 이미지/PDF 직접 판독은 endpoint가 VLM 입력을 지원한다는 conformance test 통과 후에만 사용한다.
- 현재 Template SDK와 MVP는 `DocumentExtractionService`를 통해 synthetic PDF metadata, text-PDF extraction, scan-style metadata fallback 결과를 Document Understanding Agent report에 연결한다.
- `document_vlm`은 별도 provider로 남겨두며, config에서 활성화되고 conformance test를 통과한 경우에만 OCR/VLM extraction에 사용한다.
- 문서 추출 결과는 `document_extraction_results`에 저장되고, MVP Reviewer 화면의 Agent Reports에서 문서별 field status를 확인할 수 있다.
- Agent별 report는 `specialist_agent_reports`에 별도 저장되며, MVP와 Starter Kit은 `GET /reviews/{claim_id}/specialist-reports`로 조회할 수 있다.
- Policy/Coverage Agent는 synthetic 약관 조항 단위 citation을 생성하고, Evaluation은 citation clause recall과 citation requirement pass rate를 산출한다.
- Medical Review Agent는 synthetic KCD/EDI normalized code, diagnosis-treatment relationship, medical routing, medical reason code를 report에 포함한다.
- Data Generator는 Template-compatible `medical_evidence`를 생성하여 candidate KCD/EDI confidence, 과거 진료/수술/검사 evidence, synthetic insurer medical routing rule을 runtime claim에 제공한다.
- `insurer_medical_routing_rules.json`은 Starter Kit과 MVP SQLite의 `medical_routing_rules` 테이블로 seed 가능하며, 실제 보험사 승인 rule로 교체 가능한 경계다.
- Model-backed specialist agent가 활성화되어도 deterministic structured findings는 보존되고, 모델 생성 finding은 보조 근거로만 추가된다.
- 실제 VLM 검증은 `DOCUMENT_VLM_BASE_URL`, `DOCUMENT_VLM_API_KEY`, `DOCUMENT_VLM_MODEL_ID`, `DOCUMENT_VLM_ENABLED=true` 설정 후 `python -m ai_agent_template.developer_kit.sdk.claim_agent_sdk.document_vlm_conformance --config mvp\config\model_config.yaml --sample-document data_generator\generated\documents\eval\CLM-EVAL-000001\medical_receipt.pdf`로 수행한다.
- Evaluation은 기본 심사 지표 외에 KCD/EDI mapping, 문서추출, 의료 인과관계 routing/reason, policy citation clause/requirement 전용 metric도 산출한다.
- 고객 화면의 UX는 최소 변경하고, 심사자 화면에 전문 Agent report 패널을 추가하는 방향을 우선한다.

현재 synthetic 평가 기준값:

```text
base decision metrics: 1.0
false_payment_rate: 0.0
false_denial_rate: 0.0
document_field_label_accuracy: 0.9917
kcd_mapping_accuracy: 0.92
edi_mapping_accuracy: 0.92
citation_clause_recall: 1.0
ambiguous_code_human_review_recall: 1.0
medical_causality_routing_accuracy: 1.0
medical_reason_code_recall: 1.0
```

현재 medical specialist 지표는 synthetic `medical_evidence` 기준으로 안정화되었습니다. KCD/EDI 후보 매핑은 import된 registry row를 review runtime에서 직접 조회하는 구조로 고도화되었습니다. 다음 고도화는 synthetic ambiguity threshold와 routing policy를 실제 보험사 승인 기준으로 교체하는 방향이 적절합니다.

## Completeness Quality Gates

Contract consistency, fail-closed routing, label isolation, evaluation release thresholds, startup validation, and full regression execution are owned by the AI Agent Template and reused by MVP.

```powershell
python scripts\run_quality_gates.py
```

The command runs Data Generator, AI Agent Template, MVP, and integration tests in order. See `ai_agent_template/docs/COMPLETENESS_GATES.md` for the blocking metrics and failure-criticality policy.

Project implementation status is tracked in `PROJECT_STATUS.md`. The formal API contract is `ai_agent_template/docs/API_SPEC.md`, supported dependencies are defined in `ai_agent_template/developer_kit/starter_kit/requirements.lock`, and operational procedures are in `ai_agent_template/docs/OPERATIONS_RUNBOOK.md`.

### 인증 및 권한 설정

기존 UI와 로컬 데모의 사용 흐름을 유지하기 위해 public API 인증은 기본적으로 비활성화되어 있습니다. 운영 인증 테스트에서는 API key를 소스 코드나 설정 파일에 저장하지 않고 다음 환경변수로만 주입합니다.

AI Agent Template Starter Kit:

```powershell
$env:CLAIM_AGENT_AUTH_ENABLED = "true"
$env:CLAIM_AGENT_CUSTOMER_API_KEY = "<runtime-secret>"
$env:CLAIM_AGENT_REVIEWER_API_KEY = "<runtime-secret>"
$env:CLAIM_AGENT_ADMIN_API_KEY = "<runtime-secret>"
```

MVP:

```powershell
$env:CLAIM_MVP_AUTH_ENABLED = "true"
$env:CLAIM_MVP_CUSTOMER_API_KEY = "<runtime-secret>"
$env:CLAIM_MVP_REVIEWER_API_KEY = "<runtime-secret>"
$env:CLAIM_MVP_ADMIN_API_KEY = "<runtime-secret>"
```

현재 구현은 `customer`, `reviewer`, `admin` 역할을 구분하는 API-key 기반 RBAC 기준선입니다. 실제 보험사 적용 시에는 이를 기업 IdP/OIDC 인증과 조직·직무별 권한 정책으로 교체하고, key 수명 주기 관리와 접근 권한 회수 절차를 운영 체계에 포함해야 합니다. 내부 Fraud API 인증은 별도 서비스 간 계약인 `CLAIMS_INTERNAL_API_KEY`를 사용합니다.

Decision audit records include schema, workflow, prompt, model, plugin, specialist Agent, policy source, and Template bundle fingerprints without storing API keys or direct insured identifiers.

### 고객 PDF 문서 업로드

Claim 접수 후 고객 화면에서 문서 유형과 PDF를 선택해 실제 파일을 연결할 수 있습니다. Starter Kit과 MVP는 동일한 API 계약을 사용합니다.

```text
POST /claims/{claim_id}/documents?document_type=medical_receipt
Content-Type: application/pdf
Body: PDF bytes
```

업로드 파일은 Data Generator 산출물과 분리된 `runtime/documents`에 저장되고, SQLite에는 생성된 상대경로, SHA-256, MIME, 파일 크기, 페이지 수만 기록됩니다. 저장 위치는 `CLAIM_AGENT_DOCUMENT_STORAGE_DIR` 또는 `CLAIM_MVP_DOCUMENT_STORAGE_DIR`로 변경할 수 있습니다. `medical_receipt` 업로드 시 실제 PDF SHA-256이 claim의 `receipt_hash`에 반영되어 Fraud_Check v2 원시증거 분석에 사용됩니다.

공식/보험사 승인 registry import 경계:

```powershell
python -m ai_agent_template.developer_kit.starter_kit.app.db.import_official_medical_registry `
  --kcd-file C:\approved_sources\kcd.csv `
  --edi-file C:\approved_sources\edi.csv `
  --routing-rules-file C:\approved_sources\insurer_medical_routing_rules.json `
  --version official-2026.1 `
  --effective-from 2026-01-01

python -m mvp.app.db.import_official_medical_registry `
  --kcd-file C:\approved_sources\kcd.csv `
  --edi-file C:\approved_sources\edi.csv `
  --routing-rules-file C:\approved_sources\insurer_medical_routing_rules.json `
  --version official-2026.1 `
  --effective-from 2026-01-01
```

KCD는 통계청/통계분류포털 또는 국가법령정보센터 고시 경로에서, EDI는 HIRA/공공데이터포털/보험사 승인 파일 경로에서 확인한 뒤 import해야 합니다. 제한된 공식 코드표는 repository에 포함하지 않습니다.

Import 후에는 `RuntimeMedicalRegistryService`가 KCD/EDI 후보, diagnosis-treatment rule, insurer medical routing rule을 조회하여 `medical_evidence`로 병합하고, AI Agent Template `WorkflowRunner`와 MVP review flow가 동일하게 사용합니다.

관련 문서:

```text
data_generator/docs/PRD.md
data_generator/docs/TECH_SPEC.md
ai_agent_template/docs/PRD.md
ai_agent_template/docs/TECH_SPEC.md
mvp/docs/PRD.md
mvp/docs/TECH_SPEC.md
```

## KCD/EDI Registry 운영 원칙

`data_generator`는 synthetic KCD/EDI 기준 데이터를 생성하고, `ai_agent_template`은 이를 SQLite registry로 적재할 수 있습니다.

```powershell
python -m ai_agent_template.developer_kit.starter_kit.app.db.seed_medical_registry --generated-dir data_generator\generated
```

주의:

- 저장소에 포함된 KCD/EDI 데이터는 synthetic 개발/평가용입니다.
- 실제 KCD는 공식 고시 및 통계 분류 배포 경로를 확인한 뒤 적재해야 합니다.
- 실제 EDI/수가/치료재료 코드는 HIRA 등 권한 있는 공식 배포 경로와 라이선스/이용 조건을 확인한 뒤 적재해야 합니다.
- 실제 코드 원본 파일은 Agent prompt/runtime payload에 직접 넣지 않고, version/effective date/source/checksum을 남긴 DB registry로 관리합니다.
- 라이선스상 재배포가 제한된 실제 코드 테이블은 이 repository에 포함하지 않습니다.
