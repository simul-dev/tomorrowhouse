from io import BytesIO
import json
import hashlib
from pathlib import Path
import pytest
from openpyxl import Workbook
from backend.data import read_excel, default_scenario, DataError
from backend.schemas import Scenario


def workbook(rows):
    w = Workbook()
    for row in rows:
        w.active.append(row)
    b = BytesIO()
    w.save(b)
    return b.getvalue()


HEADER = ["지역", "위도", "경도", "대형", "소형", "프리미엄"]
ROW = ["C_K수원시", 37.26, 127.02, 1, 10, 5]


def test_original_source_exact_totals_and_hash():
    scenario, audit = default_scenario()
    expected = json.loads(Path("docs/source-audit.json").read_text(encoding="utf-8"))
    assert audit["sha256"] == expected["files"]["GLR_CASE_내일의집_수요정보.xlsx"]
    assert audit["demand"] == expected["demand"]
    assert audit["customers"] == 66
    assert audit["total_cbm"] == 7107
    assert len(scenario.facilities) == 10
    assert default_scenario()[0] == scenario
    allowed = {(c.lat,c.lon) for c in scenario.customers if c.id.startswith("C_K")}
    assert all((f.lat,f.lon) in allowed for f in scenario.facilities)
    for filename, digest in expected["files"].items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("rows", [
    [ROW, ROW], [["C_KA", 37, 127, -1, 2, 3]],
    [["C_KA", 37, 127, 1.2, 2, 3]], [["C_KA", 100, 127, 1, 2, 3]],
    [["C_KA", 37, 127, None, 2, 3]], [["C_KA", 37, 127, "=1+1", 2, 3]],
])
def test_bad_excel_is_rejected(rows):
    with pytest.raises(DataError):
        read_excel(workbook([HEADER, *rows]))


def test_explicit_mapping_and_optional_population():
    customers, audit = read_excel(workbook([["custom", *HEADER[1:]], ROW]), mapping={"id":"custom"})
    assert customers[0].population == 0
    assert audit["total_units"] == 16


def test_json_rejects_invalid_reference_and_unknown_fields():
    scenario, _ = default_scenario()
    raw = scenario.model_dump()
    raw["constraints"].append({"id":"bad", "type":"force_open", "facility_id":"absent"})
    with pytest.raises(ValueError):
        Scenario.model_validate(raw)
    raw = scenario.model_dump()
    raw["vehicles"][0]["capacity_cbm"] = 0.5
    with pytest.raises(ValueError):
        Scenario.model_validate(raw)


def test_distance_known_equatorial_arc_and_symmetry():
    from backend.distance import haversine_km
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.1950802335)
    assert haversine_km(37, 127, 37, 127) == 0
    assert haversine_km(37, 127, 38, 128) == pytest.approx(haversine_km(38, 128, 37, 127))
