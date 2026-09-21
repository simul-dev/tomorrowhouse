"""Real Chromium acceptance workflow against the built local application."""
from pathlib import Path
import argparse
import json
import re
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    screenshots = ROOT / "artifacts" / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / "artifacts" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    steps, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.url, wait_until="networkidle")
        expect(page.get_by_role("heading", name="수도권 물류 네트워크", exact=False)).to_be_visible()
        expect(page.locator(".facility-row")).to_have_count(10)
        expect(page.locator(".kpi-card")).to_have_count(15)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        steps.append("initial 66-region dataset, 10 candidates, 15 KPI cards and desktop layout")

        def run():
            with page.expect_response(lambda r:r.url.endswith("/api/solve") and r.request.method=="POST", timeout=60000) as response:
                page.get_by_role("button", name="최적화 실행", exact=True).click()
            r = response.value
            assert r.status == 200, r.text()
            result = r.json()
            expect(page.get_by_role("button", name="최적화 실행", exact=True)).to_be_enabled(timeout=10000)
            return result, r.request.post_data_json

        page.get_by_label("시나리오 이름", exact=True).fill("브라우저 검증 Base")
        base, _ = run()
        assert base["status"] == "optimal" and base["validation"]["passed"]
        assert abs(base["objective"]-541155890.8803548)<1
        expect(page.locator(".dc-marker.opened")).to_have_count(4)
        page.get_by_role("tab",name="DC별 처리량",exact=True).click()
        assert page.locator("#detail-table-panel tbody tr td:last-child").all_text_contents() == ["비활성"]*10
        page.get_by_role("tab",name="수요지역 배정",exact=True).click()
        page.screenshot(path=str(screenshots/"desktop.png"), full_page=True)
        steps.append("real Base solve, independently audited objective and four opened map markers")

        with page.expect_download() as pending:
            page.get_by_role("button", name="결과 Excel 다운로드", exact=False).click()
        pending.value.save_as(str(runtime/"browser-result.xlsx"))
        assert (runtime/"browser-result.xlsx").stat().st_size>1000
        with page.expect_download() as pending:
            page.get_by_label("현재 JSON 백업", exact=True).click()
        pending.value.save_as(str(runtime/"browser-scenario.json"))
        steps.append("real validated Excel result and JSON backup downloads")

        # Name is set before solving so the stored result exactly matches input.
        page.get_by_role("button", name="저장", exact=True).click()
        page.get_by_label("현재 시나리오 복제", exact=True).click()
        page.get_by_role("button", name="비교 · 보관함", exact=True).click()
        expect(page.locator(".saved-card")).to_have_count(2)
        for checkbox in page.locator(".saved-card input[type=checkbox]").all():
            checkbox.check()
        expect(page.locator(".comparison table thead th")).to_have_count(3)
        page.get_by_label("시나리오 보관함 닫기").click()
        page.reload(wait_until="networkidle")
        page.get_by_role("button", name="비교 · 보관함", exact=True).click()
        expect(page.locator(".saved-card")).to_have_count(2)
        with page.expect_response(lambda r:r.url.endswith("/api/validate")):
            page.get_by_role("button", name="불러오기", exact=True).first.click()
        expect(page.locator(".dc-marker.opened")).to_have_count(4)
        steps.append("scenario save, duplicate, side-by-side comparison, reload persistence and restore")

        page.get_by_role("button", name="구리시 DC 선택", exact=True).click()
        latitude = page.get_by_label("DC 위도", exact=True)
        old = float(latitude.input_value())
        latitude.fill(str(old+0.03))
        expect(page.locator(".dc-marker.opened")).to_have_count(0)
        moved, request = run()
        assert moved["validation"]["passed"]
        assert next(f for f in request["facilities"] if f["name"]=="구리시 DC")["lat"] == old+0.03
        assert abs(moved["objective"]-base["objective"])>1
        steps.append("coordinate editing invalidates stale output and recalculates the actual solve")

        page.get_by_role("button", name="지도에서 DC 추가", exact=True).click()
        area = page.locator(".network-map")
        area.scroll_into_view_if_needed()
        area.click(position={"x":120,"y":200})
        expect(page.locator(".facility-row")).to_have_count(11)
        expect(page.get_by_label("DC 이름",exact=True)).to_have_value("신규 DC 11")
        page.wait_for_timeout(600)  # Let Leaflet finish the intentional pan-to-new-candidate animation.
        marker = page.locator(".leaflet-marker-icon:has(.dc-marker.selected)")
        box = marker.bounding_box()
        before = latitude.input_value()
        x, y = box["x"]+box["width"]/2, box["y"]+box["height"]/2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x+40, y+35,steps=12)
        page.mouse.up()
        expect(latitude).not_to_have_value(before)
        page.get_by_label("선택 DC 삭제",exact=True).click()
        expect(page.locator(".facility-row")).to_have_count(10)
        page.get_by_label("지도 레이어 설정",exact=True).click()
        page.get_by_label("프리미엄 수요",exact=True).uncheck()
        page.get_by_label("프리미엄 수요",exact=True).check()
        steps.append("map click adds a DC, actual marker drag updates coordinates, delete and layer controls")

        page.get_by_label("04 정식화 전체 수리모형 열기", exact=True).click()
        expect(page.get_by_role("heading", name="MILP 정식화", exact=True)).to_be_visible()
        expect(page.locator(".workflow-track")).to_have_count(0)
        assert page.locator(".constraint-list>li").count() == 8
        assert "Σ_t w_t" in page.locator(".formula-block").first.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Formulation overflow"
        page.get_by_role("button", name="해법 워크플로우로", exact=True).click()
        expect(page.locator(".workflow-track>li")).to_have_count(7)
        steps.append("formulation view opens the full MILP from the workflow and returns without layout overflow")

        page.get_by_role("tab", name="정책", exact=True).click()
        page.get_by_label("프리미엄 배송거리 활성화",exact=True).uncheck()
        relaxed, _ = run()
        assert relaxed["validation"]["passed"]
        assert all(c["type"]!="premium_distance" for c in relaxed["applied_constraints"])
        page.get_by_label("프리미엄 배송거리 기본값 복원",exact=True).click()
        expect(page.get_by_label("프리미엄 배송거리 활성화",exact=True)).to_be_checked()
        # A policy the twelve templates cannot state: cap the premium shortfall
        # only. The cap is derived from the unconstrained optimum of this exact
        # scenario, so the rule is guaranteed to bind rather than sit slack.
        shortfall = lambda r: sum(a["unmet"]["premium"] for a in r["periods"][0]["assignments"])
        cap = shortfall(moved) - 10
        assert cap > 0, "Baseline has too little premium shortfall to bind against."
        page.get_by_label("제약 템플릿", exact=True).select_option("custom")
        page.get_by_role("button", name="제약 추가", exact=True).click()
        rule = page.locator(".constraint-card").last
        rule.get_by_label("항 1 지표", exact=True).select_option("unmet")
        rule.get_by_label("항 1 상품", exact=True).select_option("premium")
        rule.get_by_label("우변 값", exact=True).fill(str(cap))
        expect(rule.locator(".rule-formula code")).to_have_text(f"미충족 물량(프리미엄) ≤ {cap}")
        custom, custom_request = run()
        assert custom["validation"]["passed"], custom
        applied = [c for c in custom["applied_constraints"] if c["type"] == "custom"]
        assert len(applied) == 1 and applied[0]["terms"][0]["product"] == "premium", applied
        assert shortfall(custom) <= cap < shortfall(moved), (shortfall(custom), cap, shortfall(moved))
        assert not any("축약" in note for note in custom["diagnostics"]), custom["diagnostics"]
        rule.get_by_label("사용자 정의 제약식 삭제", exact=True).click()
        steps.append("custom linear rule built in the UI binds the premium shortfall and passes the independent audit")

        for value in ("force_open", "forbid_open"):
            page.get_by_label("제약 템플릿",exact=True).select_option(value)
            page.get_by_role("button",name="제약 추가",exact=True).click()
        infeasible, _ = run()
        assert infeasible["status"]=="infeasible"
        expect(page.locator(".result-failure")).to_be_visible()
        steps.append("constraint deactivate/reset and deliberate conflicting policies show infeasible correctly")

        # Upload replaces only the in-memory scenario; the source file is unchanged.
        page.get_by_role("button", name="Excel 업로드",exact=True).click()
        with page.expect_response(lambda r:r.url.endswith("/api/upload")) as upload:
            page.get_by_label("Excel 수요 파일",exact=True).set_input_files(str(ROOT/"GLR_CASE_내일의집_수요정보.xlsx"))
        assert upload.value.status==200
        page.get_by_role("tab",name="거점",exact=True).click()
        expect(page.locator(".facility-row")).to_have_count(10)
        page.get_by_label("JSON 시나리오 파일",exact=True).set_input_files(str(runtime/"browser-scenario.json"))
        expect(page.get_by_label("시나리오 이름",exact=True)).to_have_value("브라우저 검증 Base")
        expect(page.locator(".dc-marker.opened")).to_have_count(0)
        page.get_by_role("tab", name="설정",exact=True).click()
        page.get_by_role("button",name="기간 추가",exact=True).click()
        page.get_by_role("button",name="기간 추가",exact=True).click()
        page.get_by_label("기간 2 삭제",exact=True).click()
        page.get_by_role("button",name="기간 추가",exact=True).click()
        assert page.get_by_label("기간 2 이름",exact=True).input_value() != page.get_by_label("기간 3 이름",exact=True).input_value()
        periods_result, _ = run()
        assert periods_result["validation"]["passed"]
        steps.append("period add/delete/add keeps unique names and produces a valid multi-period solve")
        page.get_by_role("button", name="3년 성장 설정",exact=True).click()
        multi, _ = run()
        assert len(multi["periods"])==3 and multi["validation"]["passed"]
        page.get_by_label("결과 조회 기간",exact=True).select_option("2")
        steps.append("Excel upload, schema-validated JSON import and shared-opening three-year UI solve")

        page.set_viewport_size({"width":390,"height":844})
        page.get_by_role("heading",level=1).scroll_into_view_if_needed()
        page.wait_for_timeout(350)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile document overflow"
        expect(page.get_by_role("button",name="최적화 실행",exact=True)).to_be_visible()
        page.screenshot(path=str(screenshots/"mobile.png"),full_page=True)
        steps.append("390px mobile layout without document overflow")
        assert not errors, errors
        browser.close()
    report = {"passed":True,"steps":steps,"page_errors":errors,"browser":"Chromium / Playwright 1.60.0"}
    (ROOT/"artifacts"/"browser-validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
