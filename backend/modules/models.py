from typing import Literal, Any
from pydantic import BaseModel, Field
from modules.auth import StrictModel
class CreateApplication(StrictModel):
    service_code: str = Field(min_length=3, max_length=60)
    option_code: str = Field(min_length=2, max_length=40)
    district: str = Field(min_length=2, max_length=40)
    eligibility_consent: Literal[True]
    payment_consent: Literal[True]
class DemoJourney(StrictModel):
    scenario: Literal['success', 'timeout_after_commit', 'treasury_unavailable'] = 'success'
    service_code: str = Field(default='MH_SKILL_BENEFIT', min_length=3, max_length=60)
    option_code: str | None = Field(default=None, min_length=2, max_length=40)
    review: Literal['manual', 'auto'] = 'auto'
class ReviewDecision(StrictModel):
    decision: Literal['SANCTION', 'REJECT']
    remarks: str = Field(min_length=5, max_length=500)
    version: int = Field(ge=0)
class RetryRequest(StrictModel):
    version: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=300)
class RevokeRequest(StrictModel):
    reason: str = Field(min_length=5, max_length=300)
class ScenarioRequest(StrictModel):
    scenario: Literal['success', 'timeout_after_commit', 'treasury_unavailable']
class DataAccessRequest(StrictModel):
    fields: list[str] = Field(min_length=1, max_length=10)
    purpose: str = Field(min_length=1, max_length=100)
class StageView(BaseModel):
    id: str
    name: str
    system: str
    connector: str
    state: str
    external_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    operation_id: str
    attempts: list[dict[str, Any]] = []
    evidence: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    error: str | None = None
    review: dict[str, Any] | None = None
class ApplicationView(BaseModel):
    id: str
    transaction_id: str
    person_reference: str
    owner_name: str
    service_code: str
    service_name: str = ''
    option_code: str = ''
    option_label: str = ''
    department: str = ''
    unit: str = ''
    district: str
    status: str
    created_at: str
    updated_at: str
    version: int
    stages: list[StageView]
    events: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    consents: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    canonical: dict[str, Any] = {}
    scenario: str | None = None
    review_mode: str | None = None
    next_retry_at: str | None = None
    amount: int
    is_demo: bool
class ApplicationList(BaseModel):
    items: list[ApplicationView]
    total: int
    next_cursor: str | None = None