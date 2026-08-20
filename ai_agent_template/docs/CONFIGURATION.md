# Configuration Guide

Version: 1.0.0

이 문서는 `ai_agent_template`과 Starter Kit에서 사용하는 설정 파일의 역할, key 의미, 교체 방법, 보안 원칙을 정의한다.

## 1. 설정 원칙

설정은 코드에 하드코딩하지 않고 config 파일 또는 runtime 환경변수로 주입한다.

핵심 원칙:

- Template 산출물은 기본 기준을 제공한다.
- Starter Kit은 Template 기준을 참조하되, 실행용 config를 별도로 가진다.
- 실제 보험사 적용 시 model provider, tool plugin, DB 경로, Policy Knowledge 경로는 config로 교체한다.
- 실제 API key, token, credential은 repo에 commit하지 않는다.
- `labels_*.jsonl` 경로는 Agent runtime config에 넣지 않는다. labels 파일은 evaluation runner에서만 사용한다.

## 2. 설정 파일 목록

### 2.1 Template 기본 설정

```text
ai_agent_template/config/app_config.yaml
ai_agent_template/config/model_config.yaml
```

Template 기본 설정은 Agent Template이 요구하는 기준값과 기본 model provider 정보를 정의한다. MVP나 Starter Kit은 이 값을 그대로 복사하지 않고, 필요하면 별도 runtime config에서 override한다.

### 2.2 Starter Kit 실행 설정

```text
ai_agent_template/developer_kit/starter_kit/config/app_config.yaml
ai_agent_template/developer_kit/starter_kit/config/model_config.yaml
ai_agent_template/developer_kit/starter_kit/config/plugins.yaml
```

Starter Kit 설정은 FastAPI 예제 앱을 실제로 실행하기 위한 값이다.

### 2.3 향후 MVP 설정

MVP는 다음 구조를 권장한다.

```text
mvp/config/app_config.yaml
mvp/config/model_config.yaml
mvp/config/plugins.yaml
```

MVP config는 Starter Kit config를 출발점으로 삼되, MVP runtime 경로와 보험사별 plugin/provider 값을 별도로 가진다.

## 3. `app_config.yaml`

### 3.1 Template app config

파일:

```text
ai_agent_template/config/app_config.yaml
```

현재 구조:

```yaml
version: 1.0.0
api_framework: FastAPI
openapi_version: 3.1.0
json_schema_draft: "2020-12"
runtime:
  sqlite_path: ai_agent_template/runtime/agent_template.sqlite3
  docker_enabled: false
defaults:
  strict_schema: true
  coverage_confidence_threshold: 0.75
  force_human_review_on_tool_failure: true
  output_language: ko
```

key 설명:

| Key | 설명 |
|---|---|
| `version` | config schema version |
| `api_framework` | API framework 기준. 현재 `FastAPI` |
| `openapi_version` | OpenAPI 문서 기준 version |
| `json_schema_draft` | JSON Schema draft version. 현재 Draft 2020-12 |
| `runtime.sqlite_path` | Template local runtime SQLite 경로 |
| `runtime.docker_enabled` | 현재 Docker 사용 여부. 현재 `false` |
| `defaults.strict_schema` | 입력/출력 schema validation 강제 여부 |
| `defaults.coverage_confidence_threshold` | 담보 매칭 confidence 기준. 미만이면 `human_review` |
| `defaults.force_human_review_on_tool_failure` | tool 실패 시 `human_review` fallback 여부 |
| `defaults.output_language` | reviewer-facing output 기본 언어 |

### 3.2 Starter Kit app config

파일:

```text
ai_agent_template/developer_kit/starter_kit/config/app_config.yaml
```

현재 구조:

```yaml
app_name: claim-review-starter-kit
api_framework: FastAPI
sqlite_path: runtime/starter_kit.sqlite3
template_root: ../../../
```

key 설명:

| Key | 설명 |
|---|---|
| `app_name` | Starter Kit application name |
| `api_framework` | 실행 framework |
| `sqlite_path` | Starter Kit SQLite DB 경로 |
| `template_root` | 참조할 `ai_agent_template` root 상대경로 |

현재 Starter Kit 코드에서는 환경변수를 통해 runtime 경로를 override할 수 있다. YAML parser 기반 app config 전체 로딩은 MVP 단계에서 확장한다.

## 4. `model_config.yaml`

### 4.1 Template model config

파일:

```text
ai_agent_template/config/model_config.yaml
```

현재 기본 provider:

```yaml
active_provider: general_llm
providers:
  general_llm:
    provider_type: openai_compatible
    base_url: https://m2.geniemars.kt.co.kr:10601/v1
    api_key: dummy
    model_id: gemma-4-26B-4aB-it
    temperature: 0
    response_format: json_schema
    timeout_ms: 30000
```

provider key 설명:

| Key | 설명 |
|---|---|
| `active_provider` | 현재 사용할 provider 이름 |
| `provider_type` | provider 구현 방식. 예: `openai_compatible`, `local_mock`, `insurance_domain_model` |
| `base_url` | hosted model API base URL |
| `api_key` | API key. 실제 값은 repo에 저장하지 않는다 |
| `model_id` | 호출할 model identifier |
| `temperature` | 생성 다양성. 심사 업무는 기본 `0` 권장 |
| `response_format` | 출력 형식. 기본 `json_schema` |
| `timeout_ms` | model call timeout |

### 4.2 Starter Kit model config

파일:

```text
ai_agent_template/developer_kit/starter_kit/config/model_config.yaml
```

현재 기본값:

```yaml
active_provider: mock
providers:
  mock:
    provider_type: mock
    model_id: mock-reviewer
    deterministic: true
```

Starter Kit은 기본적으로 `mock` provider를 사용한다. 이 provider는 외부 모델 API 없이 workflow와 schema validation을 검증하기 위한 것이다.

`general_llm`으로 바꾸려면:

```yaml
active_provider: general_llm
providers:
  general_llm:
    provider_type: hosted_llm
    base_url: https://m2.geniemars.kt.co.kr:10601/v1
    api_key: ${MODEL_API_KEY}
    model_id: gemma-4-26B-4aB-it
    temperature: 0
    response_format: json_schema
```

주의:

- 현재 Template의 `HostedLLMProvider`는 provider 설정 로딩 경계만 제공한다.
- 실제 network invocation은 MVP 단계에서 별도 구현해야 한다.
- 실제 API key는 환경변수 또는 secret manager로 주입해야 한다.

## 5. `plugins.yaml`

파일:

```text
ai_agent_template/developer_kit/starter_kit/config/plugins.yaml
```

역할:

- tool contract별 구현 plugin class를 지정한다.
- synthetic plugin을 보험사별 plugin으로 교체할 수 있게 한다.
- `PluginLoader`가 `module`과 `class`를 import해 `ToolRegistry`에 등록한다.

현재 구조:

```yaml
plugins:
  policy_search:
    module: ai_agent_template.developer_kit.plugins.synthetic.policy_search_plugin
    class: SyntheticPolicySearchPlugin
  coverage_resolver:
    module: ai_agent_template.developer_kit.plugins.synthetic.coverage_resolver_plugin
    class: SyntheticCoverageResolverPlugin
```

tool별 필수 항목:

| Key | 설명 |
|---|---|
| `module` | Python import path |
| `class` | plugin class name |

등록되어야 하는 기본 tool:

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

보험사별 plugin 교체 예:

```yaml
plugins:
  payable_calculator:
    module: mvp.plugins.insurer_a.payable_calculator
    class: InsurerAPayableCalculatorPlugin
```

교체 plugin은 반드시 다음 조건을 만족해야 한다.

- `ToolPlugin` protocol을 만족한다.
- `name`이 tool contract의 `tool_name`과 일치한다.
- `contract_version`이 Template contract version과 호환된다.
- 입력/출력 payload가 tool contract schema를 통과한다.
- 실패 시 표준 error envelope를 반환한다.
- `human_review` 강제 조건을 우회하지 않는다.
- `labels_*.jsonl`에 접근하지 않는다.

## 6. 환경변수 Override

Starter Kit은 다음 환경변수를 지원한다.

| 환경변수 | 설명 | 기본값 |
|---|---|---|
| `CLAIM_AGENT_TEMPLATE_ROOT` | 참조할 `ai_agent_template` root | Starter Kit 기준 상위 template 경로 |
| `CLAIM_AGENT_SQLITE_PATH` | SQLite DB 파일 경로 | `starter_kit/runtime/starter_kit.sqlite3` |
| `CLAIM_AGENT_REPORTS_DIR` | evaluation report 저장 경로 | `starter_kit/runtime/eval_runs` |
| `CLAIM_AGENT_PLUGIN_CONFIG` | plugin config 파일 경로 | `starter_kit/config/plugins.yaml` |
| `CLAIM_AGENT_MODEL_CONFIG` | model config 파일 경로 | `starter_kit/config/model_config.yaml` |
| `CLAIM_AGENT_RETRIEVAL_ENABLED` | policy retrieval 사용 여부 | `true` |
| `CLAIM_AGENT_RETRIEVAL_MODE` | policy retrieval mode override | `keyword` |
| `CLAIM_AGENT_RETRIEVAL_TOP_K` | policy retrieval top-k override | `3` |
| `FRAUD_CHECK_URL` | remote Fraud_Check base URL | `http://127.0.0.1:8010` |
| `FRAUD_CHECK_API_KEY` | optional Fraud_Check bearer token | none |

예:

```powershell
$env:CLAIM_AGENT_SQLITE_PATH="C:\tmp\claim-agent\starter.sqlite3"
$env:CLAIM_AGENT_PLUGIN_CONFIG="C:\Users\PC\AA\Automated_Claims_Processing\ai_agent_template\developer_kit\starter_kit\config\plugins.remote.yaml"
$env:CLAIM_AGENT_MODEL_CONFIG="C:\Users\PC\AA\Automated_Claims_Processing\mvp\config\model_config.yaml"
$env:FRAUD_CHECK_URL="http://127.0.0.1:8010"
$env:FRAUD_CHECK_API_KEY="optional-token"
```

Fraud_Check가 완료되기 전 기본 local/demo 실행은 `plugins.yaml`의 synthetic fraud checker를 사용한다. 원격 Fraud_Check fail-closed 경로를 검증할 때만 `plugins.remote.yaml`을 `CLAIM_AGENT_PLUGIN_CONFIG` 또는 `CLAIM_MVP_PLUGIN_CONFIG`로 지정한다.

우선순위:

```text
explicit Settings object
-> environment variables
-> Starter Kit default config paths
```

## 7. 보안 및 Secret 관리

금지:

- 실제 API key를 repo에 commit
- 실제 고객 개인정보를 config에 저장
- DB credential을 평문 config로 commit
- labels 파일 경로를 Agent runtime config에 등록

권장:

- local 개발은 `.env` 또는 shell 환경변수 사용
- 운영은 secret manager 사용
- config 파일에는 secret placeholder만 저장
- config version과 checksum을 audit log에 기록

예:

```yaml
api_key: ${MODEL_API_KEY}
```

## 8. 설정 변경 후 검증

plugin 또는 model config를 변경하면 다음 테스트를 실행한다.

```powershell
python -m unittest discover -s ai_agent_template\developer_kit\sdk\tests
python -m unittest discover -s ai_agent_template\developer_kit\plugin_interface\tests
python -m unittest discover -s ai_agent_template\developer_kit\starter_kit\tests
python -m unittest discover -s integration_tests
```

모델 provider를 바꾼 경우 동일 evaluation dataset으로 회귀 검증한다.

```text
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_eval.jsonl
```

검증 기준:

- output schema validity = 100%
- mandatory human review 조건 유지
- payable calculation이 tool result와 일치
- false denial / false payment 증가 여부 확인

## 9. 실제 보험사 적용 시 설정 흐름

실제 보험사 적용 시 config 변경 순서:

1. `DataAdapterPlugin` 구현
2. 보험사별 `plugins.yaml` 작성
3. `PolicyKnowledgePlugin` 또는 `policy_search` plugin 교체
4. `payable_calculator` plugin을 보험사 산식으로 교체
5. `model_config.yaml`에서 보험 특화 model provider 등록
6. synthetic eval과 실제 검증셋을 분리해 회귀 평가
7. 심사자 UAT 후 MVP config로 승격

## 10. RAG-ready 설정

Starter Kit의 기본 app config는 RAG-ready 경로를 검증하기 위한 retrieval 설정을 포함한다.

```yaml
retrieval:
  enabled: true
  mode: keyword
  top_k: 3
```

초기 구현은 vector DB를 사용하지 않는다. `KeywordPolicyRetriever`가 `policy_documents.md`와 `products.json`을 읽어 retrieval contract를 검증한다.

향후 실제 RAG로 전환할 때는 config에 다음 항목을 추가할 수 있다.

## Public API Authentication

Local/demo authentication is disabled by default. Operational API-key RBAC is enabled only with environment variables; secrets are never stored in YAML.

Starter Kit:

```powershell
$env:CLAIM_AGENT_AUTH_ENABLED = "true"
$env:CLAIM_AGENT_CUSTOMER_API_KEY = "<runtime-secret>"
$env:CLAIM_AGENT_REVIEWER_API_KEY = "<runtime-secret>"
$env:CLAIM_AGENT_ADMIN_API_KEY = "<runtime-secret>"
```

MVP uses `CLAIM_MVP_AUTH_ENABLED`, `CLAIM_MVP_CUSTOMER_API_KEY`, `CLAIM_MVP_REVIEWER_API_KEY`, and `CLAIM_MVP_ADMIN_API_KEY`. Customer keys can submit claims and attach PDFs, reviewer keys can access claim/review work surfaces, and admin keys can run evaluations and demo administration. Internal Fraud APIs keep the separate `CLAIMS_INTERNAL_API_KEY` contract.

## Customer Document Storage

Customer-uploaded PDFs are separated from Data Generator output. Configure writable runtime storage with:

```powershell
$env:CLAIM_AGENT_DOCUMENT_STORAGE_DIR = "C:\runtime\claim-agent\documents"
$env:CLAIM_MVP_DOCUMENT_STORAGE_DIR = "C:\runtime\claim-mvp\documents"
$env:CLAIMS_INTERNAL_MAX_DOCUMENT_BYTES = "10000000"
```

Defaults are the respective Starter Kit or MVP `runtime/documents` directories. SQLite stores only metadata and a generated relative path; PDF bytes are never stored in the database. The generated synthetic document root remains read-only from the upload flow.

```yaml
retrieval:
  enabled: true
  mode: hybrid
  top_k: 5
  vector_store:
    provider: pgvector
    collection: policy_chunks
  reranker:
    enabled: true
    model_id: insurer-reranker
```

운영 secret 또는 DB credential은 config 파일에 평문 저장하지 않고 환경변수나 secret manager로 주입한다.

RAG-ready 상세 기준:

```text
ai_agent_template/docs/RAG_READY.md
```

권장 MVP config 위치:

```text
mvp/config/app_config.yaml
mvp/config/model_config.yaml
mvp/config/plugins.yaml
```

## 11. 문서 참조

관련 문서:

```text
ai_agent_template/docs/PRD.md
ai_agent_template/docs/TECH_SPEC.md
ai_agent_template/docs/API_SPEC_DRAFT.md
ai_agent_template/docs/OPERATIONS_TEMPLATE.md
ai_agent_template/docs/EVALUATION.md
ai_agent_template/docs/RAG_READY.md
mvp/docs/PRD.md
```
