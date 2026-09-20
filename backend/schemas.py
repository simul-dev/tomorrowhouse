"""Validated public scenario contract. All costs are KRW; volume is CBM."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

PRODUCTS = ("large", "small", "premium")
VOLUMES = {"large": 1.0, "small": 0.2, "premium": 0.2}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Demand(StrictModel):
    large: int = Field(ge=0, le=1000000)
    small: int = Field(ge=0, le=1000000)
    premium: int = Field(ge=0, le=1000000)


class Customer(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    population: int = Field(default=0, ge=0)
    demand: Demand


class Facility(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    fixed_cost: float = Field(default=20000000, ge=0)
    handling_cost: float = Field(default=50, ge=0)
    capacity_cbm: float = Field(default=700, gt=0)
    enabled: bool = True


class Vehicle(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    capacity_cbm: int = Field(ge=1, le=10000)
    fixed_cost: float = Field(ge=0)
    cost_per_km: float = Field(ge=0)
    enabled: bool = True
    max_trips: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def positive_trip_cost(self):
        if self.fixed_cost <= 0:
            raise ValueError("차량 회당 고정비는 0보다 커야 합니다.")
        return self


class Period(StrictModel):
    name: str = Field(default="2027", min_length=1, max_length=60)
    demand_multiplier: float = Field(default=1, ge=0, le=10)
    days: int = Field(default=1, ge=1, le=366)


class Parameters(StrictModel):
    demand_multiplier: float = Field(default=1, ge=0, le=10)
    fixed_cost_weight: float = Field(default=1, ge=0, le=100)
    transport_cost_weight: float = Field(default=1, gt=0, le=100)
    unmet_penalty: float = Field(default=200000, ge=0)
    inbound_cost_per_unit: float = Field(default=2000, ge=0)
    allow_unmet: bool = True
    separate_premium: bool = True
    time_limit: float = Field(default=30, ge=0.1, le=300)
    mip_rel_gap: float = Field(default=0.01, ge=0, le=0.2)
    periods: list[Period] = Field(default_factory=lambda: [Period()], min_length=1, max_length=3)


ConstraintType = Literal[
    "min_dcs", "max_dcs", "capacity", "max_distance", "premium_distance",
    "force_open", "forbid_open", "allow_assignment", "forbid_assignment",
    "max_trips", "min_fulfillment", "budget",
]


class Constraint(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    type: ConstraintType
    enabled: bool = True
    value: float | None = Field(default=None, ge=0)
    facility_id: str | None = None
    customer_id: str | None = None
    vehicle_id: str | None = None

    @model_validator(mode="after")
    def validate_template(self):
        refs = {"force_open": ["facility_id"], "forbid_open": ["facility_id"],
                "allow_assignment": ["facility_id", "customer_id"],
                "forbid_assignment": ["facility_id", "customer_id"]}
        for key in refs.get(self.type, []):
            if not getattr(self, key):
                raise ValueError(f"{self.type}: {key}가 필요합니다.")
        if self.type not in (*refs, "capacity") and self.value is None:
            raise ValueError(f"{self.type}: 값이 필요합니다.")
        if self.type in ("min_dcs", "max_dcs", "max_trips") and self.value is not None and self.value != int(self.value):
            raise ValueError("개수/운행횟수는 정수여야 합니다.")
        if self.type == "min_fulfillment" and self.value > 1:
            raise ValueError("수요 충족률은 0~1입니다.")
        allowed_refs = {
            "capacity": {"facility_id"}, "max_distance": {"customer_id"},
            "premium_distance": {"customer_id"}, "max_trips": {"vehicle_id"},
            **{k: set(v) for k, v in refs.items()},
        }.get(self.type, set())
        for key in ("facility_id", "customer_id", "vehicle_id"):
            if getattr(self, key) is not None and key not in allowed_refs:
                raise ValueError(f"{self.type}: {key}를 지원하지 않습니다.")
        return self


class Scenario(StrictModel):
    name: str = Field(default="Base · 2027", min_length=1, max_length=120)
    customers: list[Customer] = Field(min_length=1, max_length=500)
    facilities: list[Facility] = Field(min_length=1, max_length=50)
    vehicles: list[Vehicle] = Field(min_length=1, max_length=10)
    parameters: Parameters = Field(default_factory=Parameters)
    constraints: list[Constraint] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_ids_and_references(self):
        for name in ("customers", "facilities", "vehicles", "constraints"):
            ids = [x.id for x in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name}: 중복 ID가 있습니다.")
        for c in self.constraints:
            for key, group in (("facility_id", self.facilities), ("customer_id", self.customers), ("vehicle_id", self.vehicles)):
                ref = getattr(c, key)
                if ref is not None and ref not in {x.id for x in group}:
                    raise ValueError(f"{c.id}: 알 수 없는 {key} {ref}")
        if len({p.name for p in self.parameters.periods}) != len(self.parameters.periods):
            raise ValueError("기간 이름은 중복될 수 없습니다.")
        return self
