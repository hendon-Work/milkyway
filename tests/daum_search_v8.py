from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By  # AppiumBy 대신 사용
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

from datetime import datetime, timedelta
import getpass
import time
import traceback
import os
import requests  # 알림 전송

# --- 구글 시트 및 AI 라이브러리 ---
import json
import gspread
# [수정] 구글 시트 인증을 위한 라이브러리 추가
from oauth2client.service_account import ServiceAccountCredentials 
import google.generativeai as genai

# --- Pillow 라이브러리 ---
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ 'Pillow' 라이브러리가 없습니다.")

# -----------------------------------------------------------------------------
# [핵심 변경] Selenium Chrome 옵션 설정 (헤드리스 모바일 모드)
# -----------------------------------------------------------------------------
options = Options()
# 1. GitHub Actions에서 실행하기 위한 필수 옵션 (헤드리스)
options.add_argument("--headless=new") 
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=412,915") # 갤럭시 S20 크기

# 2. 모바일 기기인 척 속이기 (User-Agent & Viewport)
mobile_emulation = {
    "deviceName": "Samsung Galaxy S20 Ultra" 
}
options.add_experimental_option("mobileEmulation", mobile_emulation)

# -----------------------------------------------------------------------------
# 전역 변수 및 설정
# -----------------------------------------------------------------------------
driver = None
element_interaction_timeout = 10
long_interaction_timeout = 20

# 로그 폴더 설정
LOG_ARTIFACTS_DIR = os.path.join(os.getcwd(), "logs")
if not os.path.exists(LOG_ARTIFACTS_DIR):
    os.makedirs(LOG_ARTIFACTS_DIR)

# 결과 저장 변수
SPREADSHEET_NAME = "WebAuto"
APP_NAME = "Daum Mobile Web" # 앱 대신 모바일 웹으로 변경
TESTER_NAME = "GitHub_Action_Bot" # 자동화 봇
SCRIPT_NAME = os.path.basename(__file__)
test_results = []
device_name = "GitHub Runner (Linux)"
device_model = "Headless Chrome"
app_version = "Web Version"
platform_version = "Linux"

run_start_time = None
run_end_time = None

# -----------------------------------------------------------------------------
# 함수 정의
# -----------------------------------------------------------------------------

# Gemini 분석 함수
def analyze_failure_with_gemini(screenshot_path, error_message):
    API_KEY = "AIzaSyB6GbtgJPG8APdyTQqey7R8lAVbWn4JQCs" # [주의] 실제 키 보안 유의
    if not API_KEY or "YOUR_API_KEY" in API_KEY:
        return "API Key 누락"
    return "Gemini 분석 건너뜀 (Secrets 설정 필요)"

def log_test_result(driver, number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, description, result, exception_obj=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_results.append({
        "번호": number, "테스트 분류": category, "1depth": depth1, "2depth": depth2,
        "3depth": depth3, "4depth": depth4, "5depth": depth5, "6depth": depth6,
        "7depth": depth7, "Pre-Condition": Pre, "Expected Result": description,
        "Result": result, "실행 시간": timestamp
    })
    print(f"LOG: [{result}] {description}")

    if result == "FAIL":
        print(f"\n--- ❌ 테스트 실패 (Case #{number}) ---")
        base_filename = f"FAIL_case_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 스크린샷 저장
        if driver:
            screenshot_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}.png")
            driver.save_screenshot(screenshot_path)
            print(f"📸 스크린샷 저장: {screenshot_path}")
        print("--- 실패 처리 종료 ---")

def write_results_to_gsheet(results, dev_name, device_model, plat_ver, app_pkg, app_ver, start_ts, end_ts, tester_name, script_name):
    print("\n--- Google Sheets에 결과 저장 시작 ---")
    
    # 1. GitHub Actions에서 만든 키 파일 이름
    json_file_name = 'google_key.json' 

    if not os.path.exists(json_file_name):
        print(f"❌ 오류: 인증 파일({json_file_name})이 없습니다. GitHub Secrets 설정을 확인하세요.")
        return

    try:
        # 2. 구글 시트 인증 및 연결
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_file_name, scope)
        client = gspread.authorize(creds)
        
        # 3. 시트 열기
        spreadsheet = client.open(SPREADSHEET_NAME) 
        
        # 4. 새 워크시트 생성 (이름: 날짜_시간)
        sheet_name = datetime.now().strftime('%Y%m%d_%H%M%S')
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(results)+5, cols=10)
        
        # 5. 헤더 추가
        headers = ["번호", "카테고리", "기대결과", "실행결과", "실행시간", "비고"]
        worksheet.append_row(headers)
        
        # 6. 데이터 한 줄씩 추가
        for res in results:
            row = [
                res.get("번호", ""),
                res.get("테스트 분류", ""),
                res.get("Expected Result", ""),
                res.get("Result", ""),
                res.get("실행 시간", ""),
                "자동화 테스트"
            ]
            worksheet.append_row(row)
            
        print(f"✅ 구글 시트 저장 완료! (시트명: {sheet_name})")

    except Exception as e:
        print(f"❌ 구글 시트 저장 중 에러 발생: {e}")

# --- [웹 전용] 검색 홈으로 이동 함수 ---
def navigate_to_home(driver):
    print("🌐 다음 모바일 웹 홈으로 이동합니다...")
    driver.get("https://m.daum.net")
    time.sleep(2)

# -----------------------------------------------------------------------------
# 메인 실행 로직
# -----------------------------------------------------------------------------
try:
    print("🚀 Chrome Driver(Headless) 시작 중...")
    driver = webdriver.Chrome(options=options)
    
    # 윈도우 크기 강제 설정 (모바일 비율)
    driver.set_window_size(412, 915) 
    
    print("✅ 브라우저 실행 성공!")
    run_start_time = datetime.now()

    wait = WebDriverWait(driver, element_interaction_timeout)
    long_wait = WebDriverWait(driver, long_interaction_timeout)

    # 1. 웹사이트 접속
    navigate_to_home(driver)

    case_num_counter = 1

    # -----------------------------------------------------------------------------
    # 테스트 시나리오
    # -----------------------------------------------------------------------------
    
    # --- Case 1: 홈 화면 확인 ---
    category, desc = "홈 화면", "다음 모바일 웹 홈이 정상적으로 노출되는가?"
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 검색창 확인
        search_input_xpath = '//input[@name="q" or @id="q"]'
        wait.until(EC.visibility_of_element_located((By.XPATH, search_input_xpath)))
        
        log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    # --- Case 2: 검색어 입력 및 결과 확인 ---
    category, desc = "검색 기능", "검색어 입력 후 결과 페이지로 이동하는가?" # [수정] 오타 ccategory -> category
    try:
        search_term = "GitHub Actions Test"
        
        # 1. 검색창 찾기
        search_input = wait.until(EC.element_to_be_clickable((By.XPATH, '//input[@name="q" or @type="search"]')))
        
        # 2. 검색어 입력
        search_input.click()
        search_input.clear()
        search_input.send_keys(search_term)
        print(f"검색어 입력: {search_term}")
        
        # 3. 엔터키 입력
        print("⌨️ 엔터키를 입력하여 검색을 시도합니다...")
        search_input.send_keys(Keys.ENTER)
        
        # 4. URL 변경 대기
        try:
            wait.until(EC.url_contains("search"))
            print(f"✅ 검색 결과 URL 진입 확인: {driver.current_url}")
            log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "PASS")
        except TimeoutException:
            print(f"❌ URL 변경 감지 실패. 현재 URL: {driver.current_url}")
            raise Exception("검색 후 URL이 변경되지 않았습니다.")
            
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    # --- Case 3: 화면 스크롤 ---
    category, desc = "브라우저 동작", "화면 스크롤이 정상적으로 동작하는가?"
    try:
        print("📜 스크롤 다운 시도...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);") # 다시 위로
        print("스크롤 완료")
        log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, "-", "-", "-", "-", "-", "-", "-", "-", desc, "FAIL", exception_obj=e)
    case_num_counter += 1

except Exception as e:
    print(f"\n### 🚨 치명적 오류 발생: {e}")
    traceback.print_exc()

finally:
    run_end_time = datetime.now()
    
    # [수정] 구글 시트 저장 함수 호출 추가
    if test_results:
        write_results_to_gsheet(
            test_results, device_name, device_model, 
            platform_version, "Daum Mobile Web", app_version, 
            run_start_time, run_end_time, TESTER_NAME, SCRIPT_NAME
        )
    
    # 드라이버 종료
    if driver:
        print("\n🛑 브라우저를 종료합니다.")
        driver.quit()

    # 결과 요약 출력
    print("\n" + "="*30)
    print("      테스트 실행 완료      ")
    print("="*30)
    print(f"총 소요 시간: {run_end_time - run_start_time}")