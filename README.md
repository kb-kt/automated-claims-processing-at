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
data_generator/generated/policy_documents.md
```

주의할 점:

- `claims_*.jsonl`은 Agent 입력입니다.
- `labels_*.jsonl`은 평가용 정답입니다.
- Agent runtime은 `labels_*.jsonl`을 읽으면 안 됩니다.
- Data Generator는 독립적으로 동작하되, 출력 schema는 AI Agent Template 입력 schema와 호환되어야 합니다.

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
- `/mvp` 실제 구현은 다음 단계
