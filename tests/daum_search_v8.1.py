from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from appium.webdriver.extensions.android.nativekey import AndroidKey # 안드로이드 기기 물리버튼 사용 라이브러리
from selenium.webdriver.common.actions.interaction import POINTER_TOUCH
from datetime import datetime, timedelta  # 날짜 및 시간 라이브러리

import getpass
import time # 시간 기능 라이브러리
import traceback # 오류 로깅 라이브러리
import os # 운영체제 라이브러리

import gspread # 구글 스프레드시트 라이브러리
from google.oauth2.service_account import Credentials # 구글 연동 라이브러리
import requests # 알림 전송

# --- Google Generative AI 라이브러리 추가 ---
import google.generativeai as genai

# --- Pillow 라이브러리 ---
try:
    from PIL import Image
    PIL_AVAILABLE = True # 라이브러리가 있으면 플래그를 True로 설정
except ImportError:
    PIL_AVAILABLE = False # 라이브러리가 없으면 False로 설정
    print("⚠️ 'Pillow' 라이브러리가 설치되지 않았습니다.")
    print("   테스트 완료 후 PC에 결과 이미지를 띄우는 기능을 건너뜁니다.")

# -----------------------------------------------------------------------------
# Appium 옵션 설정
# -----------------------------------------------------------------------------
options = AppiumOptions()
options.load_capabilities({
    "platformName": "Android",
    "appium:platformVersion": "15.0",
    "appium:deviceName": "R3CR10ZHBZP",
    "appium:appPackage": "net.daum.android.daum",
    "appium:appActivity": "net.daum.android.daum.DaumActivity",
    "appium:automationName": "UiAutomator2",
    "appium:ensureWebviewsHavePages": True,
    "appium:newCommandTimeout": 3600,
    "appium:connectHardwareKeyboard": False,
    "appium:nativeWebScreenshot": True,
    "appium:noReset": False,
})

# -----------------------------------------------------------------------------
# 전역 변수 및 타임아웃 설정
# -----------------------------------------------------------------------------
driver = None
initial_app_load_timeout = 20 # 앱 초기 로딩 최대 시간
element_interaction_timeout = 15 # 동작 최대 시간
long_interaction_timeout = 30 # 상호작용 최대 시간

# --- 로그 및 스크린샷 저장을 위한 디렉토리 설정 ---
LOG_ARTIFACTS_DIR = "/Users/jayden.coys/Autotest/fail_log" 

if not os.path.exists(LOG_ARTIFACTS_DIR):
    os.makedirs(LOG_ARTIFACTS_DIR)
    print(f"'{LOG_ARTIFACTS_DIR}' 디렉토리를 생성했습니다.")

# -----------------------------------------------------------------------------
# 결과 저장을 위한 전역 변수
# -----------------------------------------------------------------------------
SPREADSHEET_NAME = "DaumApp_Result" # 구글 스프레드시트 파일명
APP_NAME = "Daum" # 앱 이름
TESTER_NAME = getpass.getuser() # PC 계정명
SCRIPT_NAME = os.path.basename(__file__) # 자동화 파일명
test_results = []
device_name = "N/A" # 디바이스 모델명
platform_version = "N/A" # 안드로이드 버전
app_package_name = "N/A" # 앱 패키지 명
app_version = "N/A" # 앱 버전
run_start_time = None  # 테스트 시작 시간
run_end_time = None    # 테스트 종료 시간

# 테스트 디바이스 조회
def get_device_model_name(driver):
    try:
        command = "getprop ro.product.model"
        model_name = driver.execute_script('mobile: shell', {'command': command})
        
        cleaned_model_name = model_name.strip()
        
        print(f"✅ 디바이스 모델명 확인 성공: {cleaned_model_name}")
        return cleaned_model_name

    except Exception as e:
        print(f"❌ adb shell 명령어로 모델명 가져오기 실패: {e}")
        return "N/A"

# 앱 버전 조회
def get_app_version(driver, package_name):
    try:
        print(f"'{package_name}'의 앱 정보 조회를 시도합니다 (adb shell 방식)...")
        
        command = f"dumpsys package {package_name}"
        result = driver.execute_script('mobile: shell', {'command': command})
        
        for line in result.splitlines():
            if "versionName=" in line:
                version = line.split("versionName=")[1].strip()
                print(f"✅ 앱 버전 확인 성공: v{version}")
                return version
        
        print("⚠️ dumpsys 결과에서 'versionName'을 찾지 못했습니다.")
        return "Not Found"

    except Exception as e:
        print(f"❌ adb shell 명령어로 앱 버전 가져오기 실패: {e}")
        print("   가장 가능성이 높은 원인은 Appium 서버 실행 시 '--allow-insecure=adb_shell' 옵션이 빠진 경우입니다.")
        return "N/A"
    
# --- Gemini 분석 함수 ---
def analyze_failure_with_gemini(screenshot_path, error_message):

    API_KEY = "AIzaSyB6GbtgJPG8APdyTQqey7R8lAVbWn4JQCs" 
    
    if not API_KEY or "YOUR_API_KEY" in API_KEY:
        print("⚠️ Gemini API 키가 설정되지 않았습니다.")
        return "API Key 누락"

    # 1. 라이브러리 설정
    genai.configure(api_key=API_KEY)

    try:
        # 2. 이미지 로드
        if not PIL_AVAILABLE:
            return "Pillow 라이브러리 없음 (이미지 처리 불가)"
            
        image = Image.open(screenshot_path)

        # 3. 모델 설정
        model = genai.GenerativeModel('gemini-2.0-flash')

        # 4. 프롬프트 구성
        prompt_text = f"""
        당신은 전문 QA 엔지니어입니다. 
        다음 에러 로그와 스크린샷을 보고 한국어로 답변해 주세요.
        
        1. [원인]: 왜 실패했는지 한 문장으로 설명하세요.
        2. [해결]: 어떻게 고쳐야 하는지 한 문장으로 제안하세요.
        
        [에러 로그]
        {error_message}
        """

        print("🤖 Gemini에게 분석 요청 중...")
        
        # 5. 콘텐츠 생성 요청 (이미지와 텍스트를 리스트로 전달)
        response = model.generate_content([prompt_text, image])
        
        # 6. 결과 반환
        if response.text:
            print(f"✅ Gemini 분석 완료:\n{response.text}")
            return response.text.strip()
        else:
            return "AI 응답 내용 없음"

    except Exception as e:
        print(f"❌ Gemini 분석 중 오류 발생: {e}")
        return f"분석 실패: {str(e)}"

# --- 실패 시 스크린샷과 로그 저장
def log_test_result(driver, number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, description, result, exception_obj=None):
    """
    테스트 결과를 리스트에 저장하고, FAIL인 경우 자동으로 스크린샷, 로그 파일 생성 및 Gemini 분석을 수행합니다.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 결과 리스트에 데이터 추가
    test_results.append({
        "번호": number, "테스트 분류": category, "1depth": depth1, "2depth": depth2,
        "3depth": depth3, "4depth": depth4, "5depth": depth5, "6depth": depth6,
        "7depth": depth7, "Pre-Condition": Pre, "Expected Result": description,
        "Result": result, "실행 시간": timestamp
    })
    
    print(f"LOG: [{result}] {description}")

    # 2. 결과가 'FAIL'인 경우 상세 로그 저장 및 AI 분석 로직 실행
    if result == "FAIL":
        print(f"\n--- ❌ 테스트 실패 처리 시작 (Case #{number}) ---")
        base_filename = f"FAIL_case_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # (1) 오류 트레이스백 추출
        error_log_content = "N/A"
        try:
            if exception_obj:
                error_log_content = "".join(traceback.format_exception(
                    type(exception_obj), 
                    exception_obj, 
                    exception_obj.__traceback__
                ))
                print("💻 오류 트레이스백 정보 수집 완료.")
            else:
                error_log_content = "오류 객체가 전달되지 않았습니다."
        except Exception as e_trace:
            print(f"❌ 트레이스백 수집 중 오류 발생: {e_trace}")
            error_log_content = f"트레이스백 수집 실패: {e_trace}"

        # (2) 스크린샷 저장 및 로그 파일 생성
        try:
            screenshot_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}.png")
            log_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}_log.txt")
            screenshot_abspath = "Driver 없음"

            # 스크린샷 저장
            if driver:
                driver.save_screenshot(screenshot_path)
                print(f"📸 스크린샷 저장 완료: {screenshot_path}")
                screenshot_abspath = os.path.abspath(screenshot_path)
            else:
                print("⚠️ Driver가 없어 스크린샷을 저장할 수 없습니다.")

            # 로그 파일 작성
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"### 테스트 실패 로그 ###\n")
                f.write(f"케이스 번호: {number}\n")
                f.write(f"테스트 분류: {category}\n")
                f.write(f"기대 결과: {description}\n")
                f.write(f"발생 시간: {timestamp}\n")
                f.write(f"스크린샷: {screenshot_abspath}\n\n")
                f.write("--- 오류 트레이스백 ---\n")
                f.write(error_log_content)
            
            print(f"📄 실패 로그 파일 1차 저장 완료: {log_path}")

            # (3) Gemini 분석 요청
            if driver and os.path.exists(screenshot_path):
                print("\n🤖 Gemini에게 실패 원인 분석을 요청합니다...")
                analysis_result = analyze_failure_with_gemini(screenshot_path, error_log_content)
                
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n\n--- Gemini AI 분석 결과 ---\n{analysis_result}")
                print("✅ Gemini 분석 결과 로그 파일에 추가 완료.")

        except Exception as e:
            print(f"❌ 실패 로그 저장 및 분석 중 오류 발생: {e}")
        
        print("--- 테스트 실패 처리 종료 ---\n")

def perform_swipe_action(driver_instance, start_x, start_y, end_x, end_y, duration_ms=300, touch_name="touch_swipe"):
    """지정된 좌표로 스와이프 동작을 수행합니다."""
    actions = ActionChains(driver_instance)
    finger = PointerInput(interaction.POINTER_TOUCH, touch_name)
    actions.w3c_actions = ActionBuilder(driver_instance, mouse=finger)
    actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.move_to_location(end_x, end_y)
    actions.w3c_actions.pointer_action.release()
    actions.perform()

def wait_for_walkthrough_page(page_description, expected_element_xpath, current_wait):
    """가이드 워크쓰루 페이지의 특정 요소가 나타날 때까지 대기합니다."""
    print(f"가이드 워크쓰루 '{page_description}' 로딩 대기 중...")
    try:
        current_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, expected_element_xpath)))
        print(f"가이드 워크쓰루 '{page_description}' 요소 확인 완료.")
        return True
    except TimeoutException:
        print(f"경고: '{page_description}'의 특정 요소({expected_element_xpath})를 시간 내에 찾지 못했습니다.")
        return False
    except Exception as e_walkthrough:
        print(f"'{page_description}' 확인 중 예외 발생: {e_walkthrough}")
        return False
    
def perform_search_cycle(driver, short_wait, long_w, search_term, term_label_text):
        print(f"{term_label_text} 검색어 진행: '{search_term}'")

        try:
            search_input_element = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, INPUT_FIELD_XPATH))
            )
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_term)
            print(f"'{search_term}' 입력 완료.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {INPUT_FIELD_XPATH})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise 
        
        try:
            target_button_mainsearch_execute = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, SEARCH_BUTTON_XPATH))
            )
            target_button_mainsearch_execute.click()
            print("검색 버튼 클릭 완료.")
        except TimeoutException:
            print(f"오류: 검색 실행 버튼(XPath: {SEARCH_BUTTON_XPATH})을 시간 내에 클릭할 수 없습니다.")
            raise

        try:
            target_button_maintap_home_code = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, HOME_BUTTON_XPATH))
            )
            target_button_maintap_home_code.click()
            print("홈 버튼 클릭 완료.")

            short_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, SIDE_MENU_BUTTON_XPATH)))
            print("홈 화면으로 이동 확인.")
        except TimeoutException:
            print(f"오류: 홈으로 이동 버튼(XPath: {HOME_BUTTON_XPATH})을 클릭하거나 홈 화면 확인 중 시간 초과.")
            raise

        try:
            target_button_main_search_entry = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH))
            )
            target_button_main_search_entry.click()
            print("검색 엔트리 재진입")
        except TimeoutException:
            print(f"오류: 메인 페이지 검색 진입 버튼(XPath: {MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH})을 시간 내에 클릭할 수 없습니다.")
            raise

        print(f"{term_label_text} 검색어 '{search_term}' 작업 완료 ✅\n")

def check_element_visibility(driver_wait, term_text, term_label):
        try:
            xpath = f'//android.widget.TextView[@text="{term_text}"]'
            driver_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, xpath)))
            print(f"✅ {term_label} 검색어 '{term_text}' 확인 완료")
            return True
        except Exception as e:
            print(f"⚠️ {term_label} 검색어 '{term_text}' 확인 중 오류: {e}")
            return False

def check_element_invisibility(driver_wait, term_text, term_label):
        try:
            xpath = f'//android.widget.TextView[@text="{term_text}"]'
            driver_wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, xpath)))
            print(f"✅ {term_label} 검색어 '{term_text}' 미노출 확인 완료")
            return True
        except Exception as e:
            print(f"⚠️ {term_label} 검색어 '{term_text}' 미노출 확인 중 오류: {e}")
            return False

def scroll_down_on_search_screen(driver_instance):
        """검색 화면에서 아래로 스크롤합니다."""
        print("검색화면 스크롤 시작 📜")
        try:
            actions_search_lp = ActionChains(driver_instance)
            actions_search_lp.w3c_actions = ActionBuilder(driver_instance, mouse=PointerInput(POINTER_TOUCH, "search_touch_lp"))
            actions_search_lp.w3c_actions.pointer_action.move_to_location(483, 1638) # 시작 좌표
            actions_search_lp.w3c_actions.pointer_action.pointer_down()
            actions_search_lp.w3c_actions.pointer_action.move_to_location(479, 623)  # 종료 좌표
            actions_search_lp.w3c_actions.pointer_action.release()
            actions_search_lp.perform()
            print("스크롤 완료 👍")
        except Exception as e:
            print(f"스크롤 중 오류 발생: {e}")

def write_results_to_gsheet(results, dev_name, device_model, plat_ver, app_pkg, app_ver, start_ts, end_ts, tester_name, script_name):
    """
    Google Sheets 저장 함수 (1depth 너비 수정)
    - 이슈 해결: C열(1depth)이 여백용 20px로 설정되어 텍스트가 깨지는 문제 해결 -> 120px로 확장
    - 레이아웃: 좌측 환경정보 / 우측 결과요약 (C열은 간격 역할 겸 1depth 데이터 표시)
    """
    if not results:
        print("기록된 테스트 결과가 없어 Google Sheets에 저장하지 않습니다.")
        return

    print("\n--- Google Sheets에 결과 저장 시작 ---")
    
    # 1. 시간 및 통계 계산
    duration_str = "N/A"
    if isinstance(start_ts, datetime) and isinstance(end_ts, datetime):
        duration = end_ts - start_ts
        duration_str = str(timedelta(seconds=round(duration.total_seconds())))

    start_time_str = start_ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(start_ts, datetime) else "N/A"
    end_time_str = end_ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(end_ts, datetime) else "N/A"

    total_count = len(results)
    pass_count = sum(1 for r in results if r.get("Result") == "PASS")
    fail_count = sum(1 for r in results if r.get("Result") == "FAIL")
    success_rate = (pass_count / total_count * 100) if total_count > 0 else 0.0
    success_rate_str = f"{success_rate:.2f}%"

    try:
        # 인증 및 시트 열기
        json_file_path = "/Users/jayden.coys/Autotest/config/daumapp-d19cf041d47c.json"

        if not os.path.exists(json_file_path):
            print(f"❌ 오류: 인증 파일을 찾을 수 없습니다. 경로를 확인하세요: {json_file_path}")
            return

        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(json_file_path, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # 시트 이름 설정
        date_format = end_ts.strftime('%Y%m%d_%H%M') if isinstance(end_ts, datetime) else datetime.now().strftime('%Y%m%d_%H%M')
        sheet_name = f"{tester_name}({device_model}){end_time_str}"
        
        # 시트 생성
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(results) + 50, cols=20)
        
        # --- 2. 상단 데이터 구성 ---
        # 좌측 표 (A~B열)
        env_rows = [
            ["📋 테스트 환경 정보", ""],
            ["항목", "내용"],
            ["수행자", tester_name],
            ["앱 정보", f"{APP_NAME} (v{app_ver})"],
            ["테스트 디바이스", f"{device_model} ({dev_name})"],
            ["OS 버전", f"Android {plat_ver}"],
            ["스크립트", script_name],
            ["시작 시간", start_time_str],
            ["종료 시간", end_time_str],
            ["소요 시간", duration_str]
        ]

        # 우측 표 (D~E열)
        stats_rows = [
            ["📊 결과 요약", ""],
            ["항목", "결과"],
            ["총 수행 건수", f"{total_count} 건"],
            ["성공 (PASS)", f"{pass_count} 건"],
            ["실패 (FAIL)", f"{fail_count} 건"],
            ["성공률", success_rate_str]
        ]
        
        worksheet.update(range_name='A1', values=env_rows, value_input_option='USER_ENTERED')
        worksheet.update(range_name='D1', values=stats_rows, value_input_option='USER_ENTERED')
        
        # --- 3. 상세 결과 데이터 쓰기 ---
        detail_start_row = len(env_rows) + 3
        headers = list(results[0].keys())
        
        worksheet.update(range_name=f'A{detail_start_row}', values=[headers])
        rows_to_add = [list(row.values()) for row in results]
        worksheet.update(range_name=f'A{detail_start_row + 1}', values=rows_to_add)

        # 데이터 범위 인덱스 계산
        header_row_index = detail_start_row - 1
        data_start_index = detail_start_row 
        data_end_index = detail_start_row + len(results)

        # --- 4. 서식 디자인 적용 ---
        print("서식(대시보드 레이아웃, 정렬, 색상)을 적용합니다...")

        try:
            expected_result_col_idx = headers.index("Expected Result")
            result_col_idx = headers.index("Result")
            depth4_col_idx = headers.index("4depth")
        except ValueError:
            expected_result_col_idx = 10
            result_col_idx = 11
            depth4_col_idx = 5

        COLOR_HEADER_BG = {"red": 0.2, "green": 0.2, "blue": 0.2}
        COLOR_SUB_BG = {"red": 0.9, "green": 0.9, "blue": 0.9}
        COLOR_WHITE = {"red": 1, "green": 1, "blue": 1}
        COLOR_HEADER_GRAY = {"red": 0.85, "green": 0.85, "blue": 0.85} 

        requests = []

        # 4-1. [기본] 데이터 영역 전체: 위쪽 맞춤 & 줄바꿈
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": 0, "endColumnIndex": len(headers) },
                "cell": { "userEnteredFormat": { "verticalAlignment": "TOP", "wrapStrategy": "WRAP" } },
                "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)"
            }
        })

        # 4-2. [헤더] 컬럼 인덱스: 가운데 정렬 + 굵게 + 회색 배경
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": header_row_index, "endRowIndex": header_row_index + 1, "startColumnIndex": 0, "endColumnIndex": len(headers) },
                "cell": { "userEnteredFormat": { "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "backgroundColor": COLOR_HEADER_GRAY, "textFormat": {"bold": True} } },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,backgroundColor,textFormat)"
            }
        })

        # 4-3. [너비] 주요 컬럼 너비 조정
        # Expected Result (482px)
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": expected_result_col_idx, "endIndex": expected_result_col_idx + 1 }, "properties": {"pixelSize": 482}, "fields": "pixelSize" } })
        # 4depth (123px)
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": depth4_col_idx, "endIndex": depth4_col_idx + 1 }, "properties": {"pixelSize": 123}, "fields": "pixelSize" } })
        
        # [수정됨] C열 (1depth) 너비 확장 (기존 20px -> 120px)
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3 }, "properties": {"pixelSize": 120}, "fields": "pixelSize" } })
        
        # A, B, D, E열 (요약표 및 데이터 컬럼) 보기 좋게 조정
        # A, D열 (항목명, 2depth)
        for col_idx in [0, 3]: 
            requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": col_idx, "endIndex": col_idx + 1 }, "properties": {"pixelSize": 130}, "fields": "pixelSize" } })
        # B, E열 (값, 3depth)
        for col_idx in [1, 4]: 
            requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": col_idx, "endIndex": col_idx + 1 }, "properties": {"pixelSize": 200}, "fields": "pixelSize" } })

        # 4-4. [Result 컬럼] 정중앙 맞춤
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": result_col_idx, "endColumnIndex": result_col_idx + 1 },
                "cell": { "userEnteredFormat": { "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE" } },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })

        # 4-5. [색상] Result 조건부 서식
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{ "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": result_col_idx, "endColumnIndex": result_col_idx + 1 }],
                    "booleanRule": { "condition": { "type": "TEXT_EQ", "values": [{"userEnteredValue": "FAIL"}] }, "format": { "backgroundColor": { "red": 0.9, "green": 0.6, "blue": 0.6 } } }
                }, "index": 0
            }
        })
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{ "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": result_col_idx, "endColumnIndex": result_col_idx + 1 }],
                    "booleanRule": { "condition": { "type": "TEXT_EQ", "values": [{"userEnteredValue": "PASS"}] }, "format": { "backgroundColor": { "red": 0.6, "green": 0.9, "blue": 0.6 } } }
                }, "index": 1
            }
        })

        # --- 상단 표 디자인 (좌측 Env, 우측 Stats) ---
        worksheet.merge_cells('A1:B1') # 환경정보 타이틀
        worksheet.merge_cells('D1:E1') # 결과요약 타이틀

        env_len = len(env_rows)
        stats_len = len(stats_rows)

        # 좌측 표 (A~B) 전체 테두리
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": env_len, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"borders": {"top": {"style": "SOLID"}, "bottom": {"style": "SOLID"}, "left": {"style": "SOLID"}, "right": {"style": "SOLID"}}}},
                "fields": "userEnteredFormat(borders)"
            }
        })
        # 우측 표 (D~E) 전체 테두리
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": stats_len, "startColumnIndex": 3, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {"borders": {"top": {"style": "SOLID"}, "bottom": {"style": "SOLID"}, "left": {"style": "SOLID"}, "right": {"style": "SOLID"}}}},
                "fields": "userEnteredFormat(borders)"
            }
        })

        # 타이틀 스타일
        for col_start in [0, 3]: 
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": col_start, "endColumnIndex": col_start + 2},
                    "cell": {"userEnteredFormat": {"backgroundColor": COLOR_HEADER_BG, "horizontalAlignment": "CENTER", "textFormat": {"foregroundColor": COLOR_WHITE, "bold": True, "fontSize": 12}}},
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"
                }
            })

        # 항목명 스타일 (A열, D열)
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": env_len, "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor": COLOR_SUB_BG, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": stats_len, "startColumnIndex": 3, "endColumnIndex": 4},
                "cell": {"userEnteredFormat": {"backgroundColor": COLOR_SUB_BG, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # 값 스타일 (왼쪽 정렬) - B열, E열
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": env_len, "startColumnIndex": 1, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": stats_len, "startColumnIndex": 4, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })

        spreadsheet.batch_update(body={"requests": requests})
        print("✅ 서식 및 정렬 적용 완료.")
        
        worksheet.freeze(rows=detail_start_row)
        print(f"✅ 리포트 저장 완료: {spreadsheet.url}")
        print(f"   (시트명: {sheet_name})")

    except Exception as e:
        print(f"❌ Google Sheets 저장 중 오류 발생: {e}")
        traceback.print_exc()

# 현재 위치가 어디든, 홈 화면을 거쳐 검색 엔트리 페이지로 이동하는 공통 함수        
def navigate_to_search_entry(long_wait, wait):
    print("\n--- 공통 작업: 검색 엔트리 페이지로 이동 시작 ---")
    try:
        # 1. 홈으로 이동 버튼 클릭
        home_button_xpath = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
        home_button = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, home_button_xpath))
        )
        home_button.click()
        
        # 2. 홈 화면 로딩 확인
        side_menu_xpath = '//android.widget.Button[@content-desc="사이드 메뉴"]'
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, side_menu_xpath)))
        print("홈 화면으로 성공적으로 이동했습니다.")

        # 3. 메인 검색창 클릭하여 검색 엔트리 페이지로 진입
        search_entry_button_xpath = '//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout/androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.view.View[1]/android.view.View/android.widget.Button[3]'
        search_entry_button = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, search_entry_button_xpath))
        )
        search_entry_button.click()
        print("--- 공통 작업: 검색 엔트리 페이지로 이동 완료 ---\n")

    except Exception as e:
        print(f"❌ 검색 엔트리 페이지로 이동 중 오류 발생: {e}")
        raise

# 현재 위치가 어디든, 홈 화면으로 이동하는 공통 함수
def navigate_to_home(long_wait, wait):
    print("\n--- 공통 작업: 검색 엔트리 페이지로 이동 시작 ---")
    try:
        # 1. 홈으로 이동 버튼 클릭
        home_button_xpath = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
        home_button = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, home_button_xpath))
        )
        home_button.click()
        
        # 2. 홈 화면 로딩 확인
        side_menu_xpath = '//android.widget.Button[@content-desc="사이드 메뉴"]'
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, side_menu_xpath)))
        print("홈 화면으로 성공적으로 이동했습니다.")

    except Exception as e:
        print(f"❌ 검색 엔트리 페이지로 이동 중 오류 발생: {e}")
        raise

try:
    print("Appium 서버에 연결 중...")
    driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
    print("Appium 세션이 성공적으로 시작되었습니다.")

    # 테스트 시작 시간 기록
    run_start_time = datetime.now()

    print("--- 테스트 환경 정보 가져오기 ---")
    caps = options.capabilities
    device_name = caps.get("appium:deviceName", "Unknown Device")
    platform_version = caps.get("appium:platformVersion", "Unknown Version")
    app_package_name = caps.get("appium:appPackage", "Unknown App")
    device_model = get_device_model_name(driver)
    app_version = get_app_version(driver, app_package_name)

    # WebDriverWait 객체 초기화
    wait = WebDriverWait(driver, element_interaction_timeout)
    long_wait = WebDriverWait(driver, long_interaction_timeout)

    # --- 1. 앱 로딩 대기 ---
    print("\n--- 앱 로딩 및 초기 화면 요소 확인 중 ---")
    initial_element_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View'
    try:
        WebDriverWait(driver, initial_app_load_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath))
        )
        print("앱 초기 화면 요소가 확인되었습니다.")
    except TimeoutException:
        print(f"경고: 지정된 초기 화면 요소를 {initial_app_load_timeout}초 내에 찾지 못했습니다.")
        try:
            driver.save_screenshot("app_load_failure.png")
            print(f"페이지 소스 (앱 로드 실패 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        print("대체 대기 시간(5초) 적용 후 계속 진행 시도...")
        time.sleep(5)

    # --- 2. 가이드 워크쓰루 ---
    print("\n--- 가이드 워크쓰루 진행 ---")
    walkthrough_pages = [
        {"swipe_coords": (958, 1065, 213, 1069), "wait_element_xpath": '//android.widget.TextView[@text="홈 탭"]', "description": "홈 탭 안내"},
        {"swipe_coords": (958, 1126, 213, 1139), "wait_element_xpath": '//android.widget.TextView[@text="콘텐츠 탭"]', "description": "콘텐츠 탭 안내"},
        {"swipe_coords": (946, 1171, 262, 1151), "wait_element_xpath": '//android.widget.TextView[@text="커뮤니티 탭"]', "description": "커뮤니티 탭 안내"},
        {"swipe_coords": (975, 1040, 188, 1032), "wait_element_xpath": '//android.widget.TextView[@text="쇼핑 탭"]', "description": "쇼핑 탭 안내"},
        {"swipe_coords": (958, 1126, 213, 1139), "wait_element_xpath": '//android.widget.TextView[@text="루프 탭"]', "description": "루프 탭 안내"},
    ]
    for i, page_info in enumerate(walkthrough_pages):
        print(f"가이드 워크쓰루 스와이프 {i+1} ({page_info['description']}) 시작 중...")
        perform_swipe_action(driver, *page_info["swipe_coords"]) # touch_name 기본값 사용
        if not wait_for_walkthrough_page(page_info["description"], page_info["wait_element_xpath"], wait):
            print(f"경고: {page_info['description']} 확인 실패. 다음 단계로 진행합니다.")
        print(f"{page_info['description']}으로 이동 완료.")

    print("마지막 스와이프 (접근 권한 안내) 시작 중...")
    perform_swipe_action(driver, 958, 1126, 213, 1139, touch_name="touch_gw_final")
    if not wait_for_walkthrough_page("접근 권한 안내", '//android.widget.TextView[@text="접근 권한 안내"]', wait):
        print("오류: 접근 권한 안내 페이지로 이동 실패!")
        raise Exception("접근 권한 안내 페이지 로드 실패") # 필요시 테스트 실패 처리
    print("접근 권한 워크쓰루 이동 완료.")

    # --- 3. '다음 시작하기' 버튼 클릭 ---
    print("\n--- '다음 시작하기' 버튼 클릭 시도 ---")
    daum_start_button_xpath = '//android.widget.Button'
    try:
        daum_start_button = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, daum_start_button_xpath))
        )
        daum_start_button.click()
        print("'다음 시작하기' 버튼 클릭 성공.")
    except TimeoutException:
            print(f"오류: 대체 XPath로도 '다음 시작하기' 버튼을 시간 내에 찾거나 클릭할 수 없습니다.")
            raise # 테스트 실패 처리

    # --- 4. 코치 마크 해제 ---
    print("\n--- 코치 마크 해제 시도 ---")

    try:
        coach_mark_tap_coords = (561, 1290)
        actions_coach = ActionChains(driver)
        coach_finger = PointerInput(interaction.POINTER_TOUCH, "touch_coach_dismiss")
        actions_coach.w3c_actions = ActionBuilder(driver, mouse=coach_finger)
        actions_coach.w3c_actions.pointer_action.move_to_location(coach_mark_tap_coords[0], coach_mark_tap_coords[1])
        actions_coach.w3c_actions.pointer_action.pointer_down()
        actions_coach.w3c_actions.pointer_action.pause(duration=0.1)
        actions_coach.w3c_actions.pointer_action.release()
        actions_coach.perform()
        print("코치 마크 해제 (좌표 기반 탭) 완료.")
    except Exception as e_coach_mark:
        print(f"코치 마크 해제 중 오류 발생 (요소를 찾지 못했거나 다른 문제): {e_coach_mark}")
    time.sleep(1)

    # --- 5. 알림 권한 '허용' 버튼 클릭 ---
    print("\n--- 알림 권한 '허용' 버튼 클릭 시도 ---")
    permission_allow_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]'
    try:
        permission_allow_button = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, permission_allow_button_xpath))
        )
        permission_allow_button.click()
        print("'허용' 버튼 클릭 성공 (알림 권한).\n")
    except TimeoutException:
        print(f"경고: 알림 권한 '허용' 버튼({permission_allow_button_xpath})을 시간 내에 찾거나 클릭할 수 없습니다.")
        print("알림 권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

    # -----------------------------------------------------------------------------
    # 다음APP 자동화 시나리오
    # -----------------------------------------------------------------------------

    print("----- 다음APP(Search) 자동화 시나리오 시작합니다. -----\n")

    case_num_counter = 1

    # --- case 1 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "-", "-", "-", "-", "-", "-", "-", "-", "검색창 탭 시 엔트리 페이지가 정상적으로 노출되는가?\n====================\n- [ < '검색어 또는 URL 입력'  '돋보기' ]\n- 최근검색어 리스트\n-- [최근 검색어 끄기/켜기] [전체삭제] [닫기]\n - 투데이 버블 beta (I)\n[새로고침] [키워드버블1]  [키워드버블2]\n [키워드버블3] [키워드버블4]\n[키워드버블5]"
    try:
        main_search_button_xpath = '//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout/androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.view.View[1]/android.view.View/android.widget.Button[3]'
        long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, main_search_button_xpath))).click()
        
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="검색어 또는 URL 입력"]')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button[@content-desc="최근 검색어 끄기"]')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="투데이 버블"]')))
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 2 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "-", "-", "-", "-", "-", "-", "-", "입력필드 선택시 키패드가 활성화되어 입력가능한가?\n====================\n- [ < '검색어 또는 URL 입력'  '돋보기' ]\nPlace holder: '검색어 또는 URL 입력' [돋보기]"
    try:
        try:
            if driver.is_keyboard_shown():
                print("키패드가 정상적으로 활성화되었습니다. ✅")
            else:
                print("경고: 키패드가 활성화되지 않았습니다. ❌")
        except Exception as e:
            print(f"키패드 상태 확인 중 오류 발생: {e}")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
       log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
        
    # --- case 3 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "텍스트/숫자", "-", "-", "-", "-", "-", "텍스트 입력시 해당 텍스트와 일치하는 서제스트가 노출되는가?\n====================\n*일치하는 서제스트가 없는경우 미노출\n*키워드 하이라이트 (일치하는 항목 볼드)"
    try:
        try:
            pass
        except TimeoutException:
            print("경고: 검색 입력창으로 전환 확인 중 시간 초과")
        input_field_xpath = '//android.widget.EditText'

        search_text_to_input = "은하철도 999"

        try:
            search_input_element = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath))
            )
            print("메인 검색 입력 필드를 찾았으며 클릭 및 입력 가능합니다.")

            search_input_element.click()
            search_input_element.clear()
            print(f"메인 검색 입력 필드에 '{search_text_to_input}' 텍스트 입력을 시도합니다.")
            search_input_element.send_keys(search_text_to_input)
            print(f"'{search_text_to_input}' 텍스트를 성공적으로 입력했습니다.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {input_field_xpath})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise
        except Exception as e_input:
            print(f"메인 검색 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

            raise
        
        time.sleep(1)

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999"]')))
        print("첫번째 서제스트 확인'은하철도 999")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999 메텔"]')))
        print("두번째 서제스트 확인'은하철도 999 메텔")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999 철이"]')))
        print("세번째 서제스트 확인'은하철도 999 메텔")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # --- case 4 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "텍스트/숫자", "돋보기] 키패드 [검색]", "-", "-", "-", "-", "해당 검색결과가 노출되는 인앱브라우저가 오픈되는가?"
    try:
        button_xpath_mainsearch_inputOk = '//android.widget.Button[@content-desc="검색"]'
        target_button_mainsearch_execute = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_mainsearch_inputOk))
        )
        target_button_mainsearch_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.search.daum.net, 주소입력창, 버튼"]')))
        print("검색 결과 페이지 노출 확인")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)

    # --- case 5 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "URL", "-", "-", "-", "-", "-", "http://, https://를 포함한 URL 입력시 해당 텍스트와 일치하는 서제스트가 노출되는가?\n====================\n*일치하는 서제스트가 없는경우 미노출\n*키워드 하이라이트 (일치하는 항목 볼드)"
    try:
        try:
            pass
        except TimeoutException:
            print("경고: 검색 입력창으로 전환 확인 중 시간 초과")
        input_field_xpath = '//android.widget.EditText'

        search_text_to_input = "http://www.naver.com"

        try:
            search_input_element = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath))
            )
            print("메인 검색 입력 필드를 찾았으며 클릭 및 입력 가능합니다.")

            search_input_element.click()
            search_input_element.clear()
            print(f"메인 검색 입력 필드에 '{search_text_to_input}' 텍스트 입력을 시도합니다.")
            search_input_element.send_keys(search_text_to_input)
            print(f"'{search_text_to_input}' 텍스트를 성공적으로 입력했습니다.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {input_field_xpath})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise
        except Exception as e_input:
            print(f"메인 검색 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

            raise

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.view.View[@content-desc="바로가기, 버튼, http://www.naver.com"]')))
        print("서제스트 확인")
        print("서제스트 노출 확인")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 6 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "URL", "[돋보기] 키패드 [검색]", "-", "-", "-", "-", "해당 검색결과가 노출되는 인앱브라우저가 오픈되는가?"
    try:
        button_xpath_mainsearch_inputOk = '//android.widget.Button[@content-desc="검색"]'
        target_button_mainsearch_execute = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_mainsearch_inputOk))
        )
        target_button_mainsearch_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.naver.com, 주소입력창, 버튼"]')))
        print("검색 결과 페이지 노출 확인")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)

    # --- case 7 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "텍스트", "리스트 선택", "-", "-", "-", "리스트 선택 시 해당 검색결과(손흥민)로 이동되는가?"
    try:
        try:
            pass
        except TimeoutException:
            print("경고: 검색 입력창으로 전환 확인 중 시간 초과")
        input_field_xpath = '//android.widget.EditText'

        search_text_to_input = "손흥민"

        try:
            search_input_element = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath))
            )
            print("메인 검색 입력 필드를 찾았으며 클릭 및 입력 가능합니다.")

            search_input_element.click()
            search_input_element.clear()
            print(f"메인 검색 입력 필드에 '{search_text_to_input}' 텍스트 입력을 시도합니다.")
            search_input_element.send_keys(search_text_to_input)
            print(f"'{search_text_to_input}' 텍스트를 성공적으로 입력했습니다.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {input_field_xpath})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise
        except Exception as e_input:
            print(f"메인 검색 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

            raise

        time.sleep(1)
        print("검색 버튼 클릭 합니다.")
        button_xpath_Surgest_inputOk = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View/android.widget.Button'
        target_button_Surgest_execute = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest_inputOk))
        )
        target_button_Surgest_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="손흥민 - Daum 검색"]')))
        print("검색 결과 페이지 노출 확인")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)

    # --- case 8 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "URL", "리스트 선택", "-", "-", "-", "리스트 선택 시 해당 검색결과로 이동되는가?"
    try:
        try:
            pass
        except TimeoutException:
            print("경고: 검색 입력창으로 전환 확인 중 시간 초과")
        input_field_xpath = '//android.widget.EditText'

        search_text_to_input = "www.naver.com"

        try:
            search_input_element = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath))
            )
            print("메인 검색 입력 필드를 찾았으며 클릭 및 입력 가능합니다.")

            search_input_element.click()
            search_input_element.clear()
            print(f"메인 검색 입력 필드에 '{search_text_to_input}' 텍스트 입력을 시도합니다.")
            search_input_element.send_keys(search_text_to_input)
            print(f"'{search_text_to_input}' 텍스트를 성공적으로 입력했습니다.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {input_field_xpath})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise
        except Exception as e_input:
            print(f"메인 검색 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

            raise

        button_xpath_Surgest2_inputOk = '//android.view.View[@content-desc="바로가기, 버튼, http://www.naver.com"]'
        target_button_Surgest2_execute = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest2_inputOk))
        )
        target_button_Surgest2_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.naver.com, 주소입력창, 버튼"]')))
        print("검색 결과 페이지 노출 확인")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)

    # --- case 9 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "비주얼 서제스트", "방송, 드라마", "-", "-", "-", "방송, 드라마 타이틀을 검색한경우, 원형 썸네일이 포함된 서제스트가\n노출되고, 선택시 해당 검색결과로 이동되는가?"
    try:
        try:
            pass
        except TimeoutException:
            print("경고: 검색 입력창으로 전환 확인 중 시간 초과")
        input_field_xpath = '//android.widget.EditText'

        search_text_to_input = "무한도전"

        try:
            search_input_element = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath))
            )
            print("메인 검색 입력 필드를 찾았으며 클릭 및 입력 가능합니다.")

            search_input_element.click()
            search_input_element.clear()
            print(f"메인 검색 입력 필드에 '{search_text_to_input}' 텍스트 입력을 시도합니다.")
            search_input_element.send_keys(search_text_to_input)
            print(f"'{search_text_to_input}' 텍스트를 성공적으로 입력했습니다.")

        except TimeoutException:
            print(f"오류: 메인 검색 입력 필드(XPath: {input_field_xpath})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise
        except Exception as e_input:
            print(f"메인 검색 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

            raise

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View/android.view.View')))
        print("원형 썸네일 확인")

        button_xpath_Surgest3_inputOk = '//android.widget.TextView[@text="무한도전"]'
        target_button_Surgest3_execute = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest3_inputOk))
        )
        target_button_Surgest3_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="무한도전 - Daum 검색"]')))
        print("검색 결과 페이지 노출 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)

    # --- case 10 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "-", "-", "-", "-", "-", "-", "최근 검색어 내역이 있는 경우 리스트가 정상적으로 노출되는가?\n====================\n- 최근검색어 리스트\n최근 검색어 목록 / 해당 검색어로 검색한 날짜 / [x]\n- 최근검색 기능 툴\n[최근검색어 끄기/켜기]               [닫기]\n- 투데이 버블 Beta                          [i]\n[새로고침] [키워드버블1]  [키워드버블2]\n[키워드버블3] [키워드버블4]\n[키워드버블5]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="무한도전"]')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="손흥민"]')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999"]')))
        print("최근 검색어 모두 확인" )

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    INPUT_FIELD_XPATH = '//android.widget.EditText'
    SEARCH_BUTTON_XPATH = '//android.widget.Button[@content-desc="검색"]'
    HOME_BUTTON_XPATH = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
    SIDE_MENU_BUTTON_XPATH = '//android.widget.Button[@content-desc="사이드 메뉴"]'
    MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH = '//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout/androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.view.View[1]/android.view.View/android.widget.Button[3]'
    
    # --- case 11 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "히스토리 리스트", "정렬", "20개 초과", "-", "-", "-", "20개 이상 검색한 경우 최근 검색어가 노출되고 가장 과거에 저장되었던\n검색어는 자동 삭제되는가?"
    try:
        search_tasks = [
            ("토트넘", "4번째"), ("한화이글스", "5번째"), ("대전하나시티즌", "6번째"),
            ("구글", "7번째"), ("윈터", "8번째"), ("성심당", "9번째"),
            ("카카오", "10번째"), ("원피스", "11번째"), ("삼성전자", "12번째"),
            ("로스트아크", "13번째"), ("춘식이", "14번째"), ("갤럭시", "15번째"),
            ("키보드", "16번째"), ("카나나", "17번째"), ("버즈", "18번째"),
            ("페이커", "19번째"), ("치지직", "20번째"), ("하츄핑", "21번째")
        ]

        for search_term, term_label in search_tasks: # 검색 전 1초 대기
            time.sleep(1)

            perform_search_cycle(driver, wait, long_wait, search_term, term_label)

        print("모든 검색어 쌓기 작업 완료!")
        time.sleep(1)

        print("검색어 확인...")

        try:
            if driver.is_keyboard_shown():
                driver.hide_keyboard()
                print("키패드를 닫았습니다. ⌨️⬇️")
            else:
                print("키패드가 이미 닫혀 있습니다. ✅")
        except Exception as e:
            print(f"키패드 상태 확인/닫기 중 오류 발생 (무시하고 진행): {e}")


        print("검색 이력 확인 (스크롤 전)")
        search_terms_before_scroll = [
            ("하츄핑", "21번째"), ("치지직", "20번째"), ("페이커", "19번째"),
            ("버즈", "18번째"), ("카나나", "17번째"), ("키보드", "16번째"),
            ("갤럭시", "15번째"),
            ("춘식이", "14번째"), ("로스트아크", "13번째"), ("삼성전자", "12번째"),
            ("원피스", "11번째"), ("카카오", "10번째"), ("성심당", "9번째")
        ]

        for term, label in search_terms_before_scroll:
            check_element_visibility(wait, term, label)

        scroll_down_on_search_screen(driver)

        print("검색 이력 확인 (스크롤 후)")
        search_terms_after_scroll = [
            ("윈터", "8번째"), ("구글", "7번째"), ("대전하나시티즌", "6번째"),
            ("한화이글스", "5번째"), ("토트넘", "4번째"), ("무한도전", "3번째"),
            ("손흥민", "2번째")
        ]
        for term, label in search_terms_after_scroll:
            check_element_visibility(wait, term, label)
        print("첫 번째 검색어 미노출 확인")
        check_element_invisibility(wait, "은하철도 999", "1번째")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    time.sleep(1)

    # --- case 12 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "히스토리 스토리", "리스트 선택", "-", "-", "-", "-", "리스트 선택시 해당 검색결과로 이동되는가?"
    try:
        button_xpath_Search_historyOk = '//android.widget.TextView[@text="손흥민"]'
        target_button_Searchhis_execute = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Search_historyOk))
            )
        target_button_Searchhis_execute.click()
        print("검색 결과 화면으로 이동합니다.")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="손흥민 - Daum 검색"]')))
        print("검색 결과 페이지 노출 확인") 
        check_element_invisibility(wait, "은하철도 999", "1번째")

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인 홈 이동 후 검색 엔트리 진입
    navigate_to_search_entry(long_wait, wait)
    time.sleep(1)
    
    # --- case 13 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "키패드 상위 툴바", "[최근 검색어 끄기]", "-", "-", "-", "-", "키패드 상위에 존재하는 [최근 검색어 끄기] 버튼 선택시 설정확인 얼럿이\n 노출되고, [확인]시 적용되는가?\n====================\n'최근 검색어 끄기'\n'최근검색어 사용을 중지 하시겠습니까?'\n[취소] [확인]"
    try:
        button_xpath_Recent_searches_off = '//android.widget.Button[@content-desc="최근 검색어 끄기"]'
        target_button_Recent_searches_off = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_off))
        )
        target_button_Recent_searches_off.click()
        print("[최근 검색어 끄기] 버튼 선택 완료" )
        time.sleep(1)

        button_xpath_Recent_searches_offOK = '//android.widget.Button[@resource-id="android:id/button1"]'
        target_button_Recent_searches_offOK = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_offOK))
        )
        target_button_Recent_searches_offOK.click()
        print("최근 검색어 끄기 얼럿 내 [확인]버튼 선택 완료" )
        time.sleep(1)

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="최근 검색어 기능이 꺼져 있습니다."]')))
        print('"최근 검색어 기능이 꺼져 있습니다."문구 확인')

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 최근 검색어 켜기
    button_xpath_Recent_searches_on = '//android.widget.Button[@content-desc="최근 검색어 켜기"]'
    target_button_Recent_searches_on = long_wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_on))
    )
    target_button_Recent_searches_on.click()
    print("[최근 검색어 켜기] 완료" )
    time.sleep(1)

    # --- case 14 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "히스토리 리스트", "리스트 삭제", "전체 삭제", "-", "-", "-", "전체 삭제시 영역 내 안내문구가 노출되는가?\n'최근 검색어가 없습니다.'"
    try:
        button_xpath_Recent_delete_all = '//android.widget.Button[@content-desc="전체삭제"]'
        target_button_Recent_delete_all = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_delete_all))
        )
        target_button_Recent_delete_all.click()
        print("[전체삭제] 버튼 선택" )

        button_xpath_Recent_delete_allOk = '//android.widget.Button[@resource-id="android:id/button1"]'
        target_button_Recent_delete_allOk = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_delete_allOk))
        )
        target_button_Recent_delete_allOk.click()
        print("검색어 기록 삭제 얼럿 내 [확인]버튼 선택" )

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="최근 검색어가 없습니다."]')))
        print('"최근 검색어 기능이 꺼져 있습니다." 안내문구 확인')

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # --- case 15 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "-", "-", "-", "-", "-", "-", "-", "투데이 버블 영역이 아래와 같이 노출되는가?\n====================\n- 투데이 버블 beta (I)\n[키워드버블1] [키워드버블2]\n[키워드버블3] [키워드버블4]\n[키워드버블5]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="투데이 버블"]')))
        print("투데이 버블 영역 노출 확인" )

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 16 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "키워드 리스트", "-", "-", "-", "-", "-", "-", "새로고침 버튼과 랜덤한 5개의 키워드 리스트가 정상적으로 노출되는가?\n====================\n가로사이즈에 맞춰 최대 3줄 노출\n2x3 또는 3x2"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[3]/android.view.View/android.widget.Button')))
        print("새로보기 버튼 확인" )
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[4]')))
        print("첫번째 버블 확인" )
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[5]')))
        print("두번째 버블 확인" )
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[6]')))
        print("세번째 버블 확인" )
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[7]')))
        print("네번째 버블 확인" )
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[8]')))
        print("다섯번째 버블 확인" )

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # --- case 17 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "키워드 리스트", "키워드 상세", "키워드 상세", "-", "-", "-", "-", "해당 키워드 검색결과 페이지로 이동되는가?"
    try:
        button_xpath_bublle_click = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[4]'
        target_button_bublle_click = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_bublle_click))
        )
        target_button_bublle_click.click()

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.search.daum.net, 주소입력창, 버튼"]')))

        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1
    
    # 메인으로 이동
    button_xpath_maintap_home_code = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
    target_button_maintap_home_code = long_wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_maintap_home_code))
    )
    target_button_maintap_home_code.click()
    print("메인 탭 홈버튼을 클릭하여 메인 홈으로 이동")
    wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button[@content-desc="사이드 메뉴"]')))
    print("메인 홈 이동 완료")

    # --- case 18 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "-", "-", "-", "-", "-", "-", "-", "특수검색", "검색창 우측 특수검색 아이콘 선택 시 특수검색 바텀시트가 오픈되는가?\n====================\nDefault 꽃 검색"
    try:
        print("'특수검색' 버튼 클릭")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()
        print("'특수검색' 버튼 클릭 성공.")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="무엇을 찾아드릴까요?"]')))
        print("'특수검색 바텀시트 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 19 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "바텀시트\n(Short press)", "구성", "-", "-", "-", "-", "-", "특수검색", "특수검색 바텀시트가 아래와 같이 구성되어있는가?\n====================\n무엇을 찾아드릴까요?\n[음성 검색] / [음악 검색]\n[꽃 검색] / [코드 검색]\n[히스토리]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="무엇을 찾아드릴까요?"]')))
        print("무엇을 찾아드릴까요? 타이틀 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.widget.Button')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="음성 검색"]')))
        print("[음성 검색] 버튼 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.widget.Button')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="음악 검색"]')))
        print("[음악 검색] 버튼 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[3]/android.widget.Button')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="꽃 검색"]')))
        print("[꽃 검색] 버튼 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.widget.Button')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="코드 검색"]')))
        print("[코드 검색] 버튼 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[5]/android.widget.Button')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="히스토리"]')))
        print("[히스토리] 버튼 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # --- 테스트 20 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "최근 특수검색\n(Long press)", "꽃\n(Default)", "권한 미허용", "-", "-", "-", "-", "-", "버튼 롱프레스시 OS 권한 요청 얼럿이 노출되어, 승인 시 코드 검색이 실행되는가?"
    try:
        print("꽃 버튼 롱프레스")
        button_xpath_special_search_lp = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button_lp = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_special_search_lp))
        )
        actions = ActionChains(driver)
        actions.click_and_hold(special_search_button_lp).pause(1).release().perform()
        print("꽃 버튼 롱프레스 성공")

        # 카메라/위치 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="꽃 검색"]')))
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.ImageView[@resource-id="net.daum.android.daum:id/flower_path"]')))
        print("꽃 검색 카메라 프리뷰 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # --- case 21 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "최근 특수검색\n(Long press)", "음성", "권한 미허용", "-", "-", "-", "-", "-", "버튼 롱프레스시 OS 권한 요청 얼럿이 노출되어, 승인 시 음성 검색이 실행되는가?"
    try:
        print("특수검색 '음성'으로 변경")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()

        voice_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.widget.Button'
        target_button_voice_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, voice_compose_button_xpath)))
        target_button_voice_compose.click()

        # 오디오 권한
        permission_deny_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_deny_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_deny_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_deny_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        print("특수검색 '음성'으로 변경 완료")

        print("음성 버튼 롱프레스")

        button_xpath_special_search_lp = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button_lp = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_special_search_lp))
        )
        actions = ActionChains(driver)
        actions.click_and_hold(special_search_button).pause(1).release().perform()
        print("음성 버튼 롱프레스 성공")

        # 오디오 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@content-desc="음성검색, 제목"]')))
        print("음성 검색 카메라 프리뷰 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # 마이크 권한 초기화

    print("마이크 권한 초기화 진행")

    try:
        print("설정 앱을 실행합니다...")
        driver.activate_app('com.android.settings')
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='연결' or @text='소리 및 진동']"))
        )
        print("설정 앱 실행 확인.")
        time.sleep(1)

        applications_menu_text = "애플리케이션"
        print(f"'{applications_menu_text}' 메뉴를 찾는 중...")

        try:
            applications_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{applications_menu_text}").instance(0))')
            applications_menu_element.click()
            print(f"'{applications_menu_text}' 메뉴 클릭 성공.")
        except NoSuchElementException:
            print(f"'{applications_menu_text}' 메뉴를 찾지 못했습니다. 스크린샷을 확인하고 XPath 또는 텍스트를 조정해주세요.")
            driver.save_screenshot("error_finding_applications_menu.png")
            raise

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@content-desc='검색'] | //*[@text='앱 검색'] | //*[contains(@resource-id, 'search_src_text')] | //androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout[1]"))
        )
        print("애플리케이션 목록 화면으로 이동 확인.")
        time.sleep(2)

        target_app_names = ["다음"]
        daum_app_element = None

        for app_name_to_find in target_app_names:
            print(f"'{app_name_to_find}' 앱을 찾는 중...")
            try:
                scroll_command = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{app_name_to_find}").instance(0))'
                daum_app_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, scroll_command)

                if daum_app_element:
                    print(f"'{app_name_to_find}' 앱을 찾았습니다.")
                    daum_app_element.click()
                    print(f"'{app_name_to_find}' 앱 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{app_name_to_find}' 이름으로 앱을 찾지 못했습니다. 다음 이름으로 시도합니다.")
        
        if not daum_app_element:
            print(f"앱 목록에서 '{target_app_names}' 앱을 찾지 못했습니다.")
            raise NoSuchElementException(f"앱 목록에서 ({target_app_names}) 앱을 찾을 수 없습니다.")

        print(f"'{target_app_names[0]}' 앱 정보 화면으로 성공적으로 이동했습니다.")
        time.sleep(1)

    except NoSuchElementException as e_no_element:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)

    try:
        permissions_menu_text_candidates = ["권한"]
        permissions_menu_element = None

        for text_candidate in permissions_menu_text_candidates:
            try:
                print(f"'{text_candidate}' 메뉴를 찾는 중...")
                permissions_menu_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                permissions_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, permissions_menu_query)
                if permissions_menu_element:
                    permissions_menu_element.click()
                    print(f"'{text_candidate}' 메뉴 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 메뉴를 찾지 못했습니다.")
        
        if not permissions_menu_element:
            raise NoSuchElementException(f"권한 메뉴({permissions_menu_text_candidates})를 찾을 수 없습니다.")

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[contains(@text, '허용됨') or contains(@text, '허용되지 않음') or @text='마이크' or @text='Microphone']"))
        )
        print("권한 목록 화면으로 이동 확인.")
        time.sleep(1)

        microphone_permission_text_candidates = ["마이크"]
        microphone_permission_element = None

        for text_candidate in microphone_permission_text_candidates:
            try:
                print(f"'{text_candidate}' 권한을 찾는 중...")
                microphone_permission_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                microphone_permission_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, microphone_permission_query)
                if microphone_permission_element:
                    microphone_permission_element.click()
                    print(f"'{text_candidate}' 권한 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 권한을 찾지 못했습니다.")

        if not microphone_permission_element:
            raise NoSuchElementException(f"마이크 권한({microphone_permission_text_candidates})을 찾을 수 없습니다.")
            
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")) 
        )
        print("마이크 권한 상세 설정 화면으로 이동 확인.")
        time.sleep(1)

        deny_option_selected = False
        deny_option_xpaths = [
            "//android.widget.RadioButton[@text='허용 안함']",
            '//android.widget.RadioButton[@resource-id="com.android.permissioncontroller:id/deny_radio_button"]',
        ]
        deny_option_element = None
        for xpath_candidate in deny_option_xpaths:
            try:
                print("'허용 안함' 옵션 찾는 중...")
                deny_option_element = driver.find_element(AppiumBy.XPATH, xpath_candidate)
                if deny_option_element.is_displayed():
                    if deny_option_element.get_attribute("checked") == "true":
                        print("'허용 안함'이 이미 선택되어 있습니다.")
                    else:
                        deny_option_element.click()
                        print("'허용 안함' 옵션 선택 성공.")
                    deny_option_selected = True
                    break 
            except NoSuchElementException:
                print(f"XPath '{xpath_candidate}'로 '허용 안함' 옵션을 찾지 못했습니다.") 
        time.sleep(1)
        print("'마이크'권한 초기화 완료")

        daum_app_package = "net.daum.android.daum"
        print("'다음' 앱으로 다시 전환합니다...")
        driver.activate_app(daum_app_package)
        print("'다음' 앱으로 전환 시도 완료.")
        time.sleep(1)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)

    print("다음 앱 재실행")
    daum_app_package = "net.daum.android.daum"

    try:
        print("백그라운드 앱 모두 삭제 시도...")
        try:
            driver.press_keycode(AndroidKey.APP_SWITCH)
            time.sleep(2)

            close_all_button_selectors = [
                {"by": AppiumBy.XPATH, "value": "//*[@text='모두 닫기']"},
                {"by": AppiumBy.XPATH, "value": "//*[contains(@content-desc, '모두 닫기') or contains(@content-desc, 'Close all')]"},
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/clear_all_button"},
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/close_all_button"},
            ]   
            closed_all_apps_successfully = False
            for selector_info in close_all_button_selectors:
                try:
                    close_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((selector_info["by"], selector_info["value"]))
                    )
                    close_all_button.click()
                    closed_all_apps_successfully = True
                    time.sleep(2) 
                    break 
                    print(f"'모두 닫기' 버튼 ({selector_info['value']})을 시간 내에 찾거나 클릭할 수 없습니다.")
                except NoSuchElementException:
                     print(f"'모두 닫기' 버튼 ({selector_info['value']})을 찾을 수 없습니다.")
        except Exception as e_clear_apps:
            print(f"백그라운드 앱 삭제 과정 중 예외 발생: {e_clear_apps}")
            traceback.print_exc()
            print("경고: 백그라운드 앱 삭제에 실패했을 수 있습니다. 다음 단계(앱 재실행)는 계속 시도합니다.")
        print("'다음' 앱을 재실행합니다...")
        try:
            driver.activate_app(daum_app_package)
            time.sleep(1)
            print("다음 앱 재실행 완료")
        except Exception as e_restart_after_clear:
            error_message = f"오류: 다음 앱 재실행 중 문제 발생: {e_restart_after_clear}"
            print(error_message)
            traceback.print_exc()
    except Exception as e_main_block:
        print(f"백그라운드 앱 삭제 및 다음 앱 재실행 과정에서 오류 발생: {e_main_block}")
        traceback.print_exc()

    print("특수검색 '뮤직'으로 변경")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()

    music_compose1_button_xpath = '//android.widget.TextView[@text="음악 검색"]'
    target_button_music_compose1 = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, music_compose1_button_xpath)))
    target_button_music_compose1.click()

    driver.back()
    time.sleep(1)

    print("특수검색 '뮤직'으로 변경 완료")

    # --- case 22 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "최근 특수검색\n(Long press)", "음악", "권한 미허용", "-", "-", "-", "-", "-", "버튼 롱프레스시 OS 권한 요청 얼럿이 노출되어, 승인 시 음악 검색이 실행되는가?"
    try:
        print("뮤직 버튼 롱프레스")
        button_xpath_special_search_lp = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button_lp = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_special_search_lp))
        )
        actions = ActionChains(driver)
        actions.click_and_hold(special_search_button_lp).pause(1).release().perform()
        print("뮤직 버튼 롱프레스 성공")

        # 오디오 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@content-desc="음악검색, 제목"]')))
        print("뮤직 검색 프리뷰 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # 카메라 권환 초기화

    print("권환 초기화")

    try:
        print("설정 앱을 실행합니다...")
        driver.activate_app('com.android.settings')
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='연결' or @text='소리 및 진동']"))
        )
        print("설정 앱 실행 및 초기 화면 로드 확인.")
        time.sleep(1)

        applications_menu_text = "애플리케이션"
        print(f"'{applications_menu_text}' 메뉴를 스크롤하여 찾는 중...")

         # 화면 크기를 가져와 스크롤 좌표를 설정합니다.
        window_size = driver.get_window_size()
        start_x = window_size['width'] // 2
        start_y = int(window_size['height'] * 0.8)
        end_y = int(window_size['height'] * 0.2)

        found_app_menu = False
        # 최대 10번까지 스크롤하며 요소를 찾습니다.

        for _ in range(10):
            try:
                # XPath를 사용해 현재 화면에서 '애플리케이션' 요소를 찾습니다.
                applications_menu_element = driver.find_element(AppiumBy.XPATH, f"//*[@text='{applications_menu_text}']")
                print(f"'{applications_menu_text}' 메뉴를 찾았습니다.")
                applications_menu_element.click()
                print(f"'{applications_menu_text}' 메뉴 클릭 성공.")
                found_app_menu = True
                break  # 요소를 찾았으므로 반복을 중단합니다.
            except NoSuchElementException:
                # 요소를 찾지 못하면 화면을 아래에서 위로 스크롤합니다.
                print("메뉴를 찾지 못해 아래로 스크롤합니다.")
                driver.swipe(start_x, start_y, start_x, end_y, 400)
                time.sleep(1) # 스크롤 후 잠시 대기

        # 스크롤을 모두 시도한 후에도 요소를 찾지 못하면 오류를 발생시킵니다.
        if not found_app_menu:
            print(f"'{applications_menu_text}' 메뉴를 스크롤하여 찾지 못했습니다.")
            driver.save_screenshot("error_finding_applications_menu.png")
            raise NoSuchElementException(f"Could not find element with text: {applications_menu_text}")

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@content-desc='검색'] | //*[@text='앱 검색'] | //*[contains(@resource-id, 'search_src_text')] | //androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout[1]"))
        )
        print("애플리케이션 목록 화면으로 이동 확인.")
        time.sleep(2)

        target_app_names = ["다음"]
        daum_app_element = None

        for app_name_to_find in target_app_names:
            print(f"'{app_name_to_find}' 앱을 찾는 중...")
            try:
                scroll_command = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{app_name_to_find}").instance(0))'
                daum_app_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, scroll_command)

                if daum_app_element:
                    print(f"'{app_name_to_find}' 앱을 찾았습니다.")
                    daum_app_element.click()
                    print(f"'{app_name_to_find}' 앱 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{app_name_to_find}' 이름으로 앱을 찾지 못했습니다. 다음 이름으로 시도합니다.")

        
        if not daum_app_element:
            print(f"앱 목록에서 '{target_app_names}' 앱을 찾지 못했습니다.")
            driver.save_screenshot("error_finding_daum_app.png")
            raise NoSuchElementException(f"앱 목록에서 다음 앱({target_app_names})을 찾을 수 없습니다.")
        time.sleep(1)

    except TimeoutException as e_timeout:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_timeout_error.png")
            print(f"현재 페이지 소스 (설정 이동 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_no_element_error.png")
            print(f"현재 페이지 소스 (설정 이동 요소 없음 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except Exception as e_general:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 알 수 없는 오류 발생: {e_general}"
        print(error_message)
        traceback.print_exc()
        try:
            driver.save_screenshot("settings_navigation_general_error.png")
            print(f"현재 페이지 소스 (설정 이동 일반 오류 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    try:
        permissions_menu_text_candidates = ["권한"]
        permissions_menu_element = None

        for text_candidate in permissions_menu_text_candidates:
            try:
                permissions_menu_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                permissions_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, permissions_menu_query)
                if permissions_menu_element:
                    permissions_menu_element.click()
                    print(f"'{text_candidate}' 메뉴 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 메뉴를 찾지 못했습니다.")
        
        if not permissions_menu_element:
            raise NoSuchElementException(f"권한 메뉴({permissions_menu_text_candidates})를 찾을 수 없습니다.")

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[contains(@text, '허용됨') or contains(@text, '허용되지 않음') or @text='마이크' or @text='Microphone']"))
        )
        print("권한 목록 화면으로 이동 확인.")
        time.sleep(1)

        camera_permission_text_candidates = ["카메라"]
        camera_permission_element = None

        for text_candidate in camera_permission_text_candidates:
            try:
                camera_permission_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                camera_permission_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, camera_permission_query)
                if camera_permission_element:
                    camera_permission_element.click()
                    print(f"'{text_candidate}' 권한 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 권한을 찾지 못했습니다.")

        if not microphone_permission_element:
            raise NoSuchElementException(f"마이크 권한({camera_permission_text_candidates})을 찾을 수 없습니다.")
            
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")) 
        )
        print("카메라 권한 상세 설정 화면으로 이동 확인.")
        time.sleep(1)
        
        deny_option_selected = False
        deny_option_xpaths = [
            "//android.widget.RadioButton[@text='허용 안함']",
            "//android.widget.RadioButton[@text='Deny']",
            "//android.widget.RadioButton[@text='거부']",
            "//*[(@text='허용 안함' or @text='Deny' or @text='거부') and @class='android.widget.TextView']/../android.widget.RadioButton", 
            "//android.widget.LinearLayout[descendant::android.widget.TextView[@text='허용 안함' or @text='Deny' or @text='거부']]//android.widget.RadioButton" 
        ]
        deny_option_element = None
        for xpath_candidate in deny_option_xpaths:
            try:
                deny_option_element = driver.find_element(AppiumBy.XPATH, xpath_candidate)
                if deny_option_element.is_displayed():

                    if deny_option_element.get_attribute("checked") == "true":
                        print("'허용 안함'이 이미 선택되어 있습니다.")
                    else:
                        deny_option_element.click()
                        print("'허용 안함' 옵션 선택 성공.")
                    deny_option_selected = True
                    break 
            except NoSuchElementException:
                print(f"XPath '{xpath_candidate}'로 '허용 안함' 옵션을 찾지 못했습니다.")
            except Exception as e_find_deny:
                print(f"XPath '{xpath_candidate}'로 요소 찾는 중 오류: {e_find_deny}")
        if not deny_option_selected and not (deny_option_element and deny_option_element.get_attribute("checked") == "true"):
            print("라디오 버튼 직접 선택 실패. '허용 안함' 텍스트 클릭 시도...")
            try:
                deny_text_element = driver.find_element(AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")
                deny_text_element.click()
                print("'허용 안함' 텍스트 클릭 성공.")
                deny_option_selected = True
            except NoSuchElementException:
                print("'허용 안함' 텍스트도 찾거나 클릭할 수 없습니다.")
                raise NoSuchElementException("마이크 권한 '허용 안함' 옵션을 선택할 수 없습니다.")
        
        time.sleep(1)

        additional_confirm_texts = ["무시하고 허용 안함", "Deny anyway", "거부 확인"]
        for confirm_text in additional_confirm_texts:
            try:
                additional_confirm_button = driver.find_element(AppiumBy.XPATH, f"//*[@text='{confirm_text}']")
                if additional_confirm_button.is_displayed():
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 중...")
                    additional_confirm_button.click()
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 성공.")
                    time.sleep(1) 
                    break 
            except NoSuchElementException:
                pass

        daum_app_package = "net.daum.android.daum"
        print("'다음' 앱으로 다시 전환합니다...")
        driver.activate_app(daum_app_package)

        print("'다음' 앱으로 전환 시도 완료.")
        try:
            WebDriverWait(driver, long_interaction_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath))
            )
            print("다음 앱 전환 성공.")
        except TimeoutException:
            print("다음 앱 초기 화면 요소를 시간 내에 찾지 못했습니다. 앱 전환 상태를 확인해주세요.")
        time.sleep(3)
    except TimeoutException as e_timeout:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("permission_setting_timeout_error.png")
            print(f"현재 페이지 소스 (권한 설정 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug: print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        raise Exception(error_message)

    daum_app_package = "net.daum.android.daum"
    try:
        print("백그라운드 앱 모두 삭제 시도...")
        try:
            driver.press_keycode(AndroidKey.APP_SWITCH)
            time.sleep(2)

            close_all_button_selectors = [
                {"by": AppiumBy.XPATH, "value": "//*[@text='모두 닫기']"},
                {"by": AppiumBy.XPATH, "value": "//*[contains(@content-desc, '모두 닫기') or contains(@content-desc, 'Close all')]"},
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/clear_all_button"}, # 비교적 최신 One UI
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/close_all_button"}, # 이전 One UI
            ]
            
            closed_all_apps_successfully = False
            for selector_info in close_all_button_selectors:
                try:
                    close_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((selector_info["by"], selector_info["value"]))
                    )
                    close_all_button.click()
                    closed_all_apps_successfully = True
                    print("백그라운드 앱 '모두 닫기' 성공.")
                    time.sleep(2) 
                    break 
                    print(f"'모두 닫기' 버튼 ({selector_info['value']})을 시간 내에 찾거나 클릭할 수 없습니다.")
                except NoSuchElementException:
                     print(f"'모두 닫기' 버튼 ({selector_info['value']})을 찾을 수 없습니다.")

        except Exception as e_clear_apps:
            print(f"백그라운드 앱 삭제 과정 중 예외 발생: {e_clear_apps}")
            traceback.print_exc()
            print("경고: 백그라운드 앱 삭제에 실패했을 수 있습니다. 다음 단계(앱 재실행)는 계속 시도합니다.")
            try:
                driver.press_keycode(AndroidKey.HOME)
                time.sleep(1)
            except Exception as e_gohome:
                print(f"홈으로 이동 중 오류: {e_gohome}")
        print("'다음' 앱을 재실행합니다...")
        try:
            driver.activate_app(daum_app_package)
            print("앱 재실행 후 초기 화면 요소가 나타날 때까지 대기 중...")
            WebDriverWait(driver, initial_app_load_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath)) 
            )
            print("다음 앱이 성공적으로 재실행되었고 초기 화면 요소가 확인되었습니다.")
        except TimeoutException as e_timeout_restart_after_clear:
            error_message = f"오류: 백그라운드 정리 후 다음 앱 재실행 중 타임아웃: {e_timeout_restart_after_clear}"
            print(error_message)
    except Exception as e_main_block:
        print(f"백그라운드 앱 삭제 및 다음 앱 재실행 과정에서 예기치 않은 오류 발생: {e_main_block}")
        traceback.print_exc()
        
    print("특수검색 '코드'로 변경")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()

    code_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.widget.Button'
    target_button_code_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, code_compose_button_xpath)))
    target_button_code_compose.click()

    driver.back()
    time.sleep(1)

    print("특수검색 '코드'로 변경 완료")

    # --- case 23 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수 검색", "최근 특수검색\n(Long press)", "코드", "권한 미허용", "-", "-", "-", "-", "-", "버튼 롱프레스시 OS 권한 요청 얼럿이 노출되어, 승인 시 코드 검색이 실행되는가?"
    try:
        print("코드 버튼 롱프레스")
        button_xpath_special_search_lp = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button_lp = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_special_search_lp))
        )
        actions = ActionChains(driver)
        actions.click_and_hold(special_search_button_lp).pause(1).release().perform()
        print("코드 버튼 롱프레스 성공")

        # 카메라/위치 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="QR코드/바코드 검색"]')))
        print("코드 검색 프리뷰 확인")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # 카메라 권환 초기화

    print("카메라 권환 초기화")

    try:
        print("설정 앱을 실행합니다...")
        driver.activate_app('com.android.settings')
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='연결' or @text='소리 및 진동']"))
        )
        print("설정 앱 실행 및 초기 화면 로드 확인.")
        time.sleep(1)

        applications_menu_text = "애플리케이션"
        print(f"'{applications_menu_text}' 메뉴를 찾는 중...")

        try:
            applications_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{applications_menu_text}").instance(0))')
            applications_menu_element.click()
            print(f"'{applications_menu_text}' 메뉴 클릭 성공.")
        except NoSuchElementException:
            print(f"'{applications_menu_text}' 메뉴를 찾지 못했습니다. 스크린샷을 확인하고 XPath 또는 텍스트를 조정해주세요.")
            driver.save_screenshot("error_finding_applications_menu.png")
            raise

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@content-desc='검색'] | //*[@text='앱 검색'] | //*[contains(@resource-id, 'search_src_text')] | //androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout[1]"))
        )
        print("애플리케이션 목록 화면으로 이동 확인.")
        time.sleep(2)

        target_app_names = ["다음"]
        daum_app_element = None

        for app_name_to_find in target_app_names:
            print(f"'{app_name_to_find}' 앱을 찾는 중...")
            try:
                scroll_command = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{app_name_to_find}").instance(0))'
                daum_app_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, scroll_command)

                if daum_app_element:
                    print(f"'{app_name_to_find}' 앱을 찾았습니다.")
                    daum_app_element.click()
                    print(f"'{app_name_to_find}' 앱 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{app_name_to_find}' 이름으로 앱을 찾지 못했습니다. 다음 이름으로 시도합니다.")

        
        if not daum_app_element:
            print(f"앱 목록에서 '{target_app_names}' 앱을 찾지 못했습니다.")
            driver.save_screenshot("error_finding_daum_app.png")
            raise NoSuchElementException(f"앱 목록에서 다음 앱({target_app_names})을 찾을 수 없습니다.")
        time.sleep(1)

    except TimeoutException as e_timeout:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_timeout_error.png")
            print(f"현재 페이지 소스 (설정 이동 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_no_element_error.png")
            print(f"현재 페이지 소스 (설정 이동 요소 없음 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except Exception as e_general:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 알 수 없는 오류 발생: {e_general}"
        print(error_message)
        traceback.print_exc()
        try:
            driver.save_screenshot("settings_navigation_general_error.png")
            print(f"현재 페이지 소스 (설정 이동 일반 오류 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    try:
        permissions_menu_text_candidates = ["권한"]
        permissions_menu_element = None

        for text_candidate in permissions_menu_text_candidates:
            try:
                permissions_menu_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                permissions_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, permissions_menu_query)
                if permissions_menu_element:
                    permissions_menu_element.click()
                    print(f"'{text_candidate}' 메뉴 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 메뉴를 찾지 못했습니다.")
        
        if not permissions_menu_element:
            raise NoSuchElementException(f"권한 메뉴({permissions_menu_text_candidates})를 찾을 수 없습니다.")

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[contains(@text, '허용됨') or contains(@text, '허용되지 않음') or @text='마이크' or @text='Microphone']"))
        )
        print("권한 목록 화면으로 이동 확인.")
        time.sleep(1)

        camera_permission_text_candidates = ["카메라"]
        camera_permission_element = None

        for text_candidate in camera_permission_text_candidates:
            try:
                camera_permission_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                camera_permission_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, camera_permission_query)
                if camera_permission_element:
                    camera_permission_element.click()
                    print(f"'{text_candidate}' 권한 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 권한을 찾지 못했습니다.")

        if not microphone_permission_element:
            raise NoSuchElementException(f"마이크 권한({camera_permission_text_candidates})을 찾을 수 없습니다.")
            
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")) 
        )
        print("카메라 권한 상세 설정 화면으로 이동 확인.")
        time.sleep(1)
        
        deny_option_selected = False
        deny_option_xpaths = [
            "//android.widget.RadioButton[@text='허용 안함']",
            "//android.widget.RadioButton[@text='Deny']",
            "//android.widget.RadioButton[@text='거부']",
            "//*[(@text='허용 안함' or @text='Deny' or @text='거부') and @class='android.widget.TextView']/../android.widget.RadioButton", 
            "//android.widget.LinearLayout[descendant::android.widget.TextView[@text='허용 안함' or @text='Deny' or @text='거부']]//android.widget.RadioButton" 
        ]
        deny_option_element = None
        for xpath_candidate in deny_option_xpaths:
            try:
                deny_option_element = driver.find_element(AppiumBy.XPATH, xpath_candidate)
                if deny_option_element.is_displayed():

                    if deny_option_element.get_attribute("checked") == "true":
                        print("'허용 안함'이 이미 선택되어 있습니다.")
                    else:
                        deny_option_element.click()
                        print("'허용 안함' 옵션 선택 성공.")
                    deny_option_selected = True
                    break 
            except NoSuchElementException:
                print(f"XPath '{xpath_candidate}'로 '허용 안함' 옵션을 찾지 못했습니다.")
            except Exception as e_find_deny:
                print(f"XPath '{xpath_candidate}'로 요소 찾는 중 오류: {e_find_deny}")
        if not deny_option_selected and not (deny_option_element and deny_option_element.get_attribute("checked") == "true"):
            print("라디오 버튼 직접 선택 실패. '허용 안함' 텍스트 클릭 시도...")
            try:
                deny_text_element = driver.find_element(AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")
                deny_text_element.click()
                print("'허용 안함' 텍스트 클릭 성공.")
                deny_option_selected = True
            except NoSuchElementException:
                print("'허용 안함' 텍스트도 찾거나 클릭할 수 없습니다.")
                raise NoSuchElementException("마이크 권한 '허용 안함' 옵션을 선택할 수 없습니다.")
        
        time.sleep(1)

        additional_confirm_texts = ["무시하고 허용 안함", "Deny anyway", "거부 확인"]
        for confirm_text in additional_confirm_texts:
            try:
                additional_confirm_button = driver.find_element(AppiumBy.XPATH, f"//*[@text='{confirm_text}']")
                if additional_confirm_button.is_displayed():
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 중...")
                    additional_confirm_button.click()
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 성공.")
                    time.sleep(1) 
                    break 
            except NoSuchElementException:
                pass

        daum_app_package = "net.daum.android.daum"
        print("'다음' 앱으로 다시 전환합니다...")
        driver.activate_app(daum_app_package)

        print("'다음' 앱으로 전환 시도 완료.")
        try:
            WebDriverWait(driver, long_interaction_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath))
            )
            print("다음 앱 전환 성공.")
        except TimeoutException:
            print("다음 앱 초기 화면 요소를 시간 내에 찾지 못했습니다. 앱 전환 상태를 확인해주세요.")
        time.sleep(3)
    except TimeoutException as e_timeout:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("permission_setting_timeout_error.png")
            print(f"현재 페이지 소스 (권한 설정 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug: print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        raise Exception(error_message)

    daum_app_package = "net.daum.android.daum"
    try:
        print("백그라운드 앱 모두 삭제 시도...")
        try:
            driver.press_keycode(AndroidKey.APP_SWITCH)
            time.sleep(2)

            close_all_button_selectors = [
                {"by": AppiumBy.XPATH, "value": "//*[@text='모두 닫기']"},
                {"by": AppiumBy.XPATH, "value": "//*[contains(@content-desc, '모두 닫기') or contains(@content-desc, 'Close all')]"},
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/clear_all_button"}, # 비교적 최신 One UI
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/close_all_button"}, # 이전 One UI
            ]
            
            closed_all_apps_successfully = False
            for selector_info in close_all_button_selectors:
                try:
                    close_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((selector_info["by"], selector_info["value"]))
                    )
                    close_all_button.click()
                    closed_all_apps_successfully = True
                    print("백그라운드 앱 '모두 닫기' 성공.")
                    time.sleep(2) 
                    break 
                    print(f"'모두 닫기' 버튼 ({selector_info['value']})을 시간 내에 찾거나 클릭할 수 없습니다.")
                except NoSuchElementException:
                     print(f"'모두 닫기' 버튼 ({selector_info['value']})을 찾을 수 없습니다.")

        except Exception as e_clear_apps:
            print(f"백그라운드 앱 삭제 과정 중 예외 발생: {e_clear_apps}")
            traceback.print_exc()
            print("경고: 백그라운드 앱 삭제에 실패했을 수 있습니다. 다음 단계(앱 재실행)는 계속 시도합니다.")
            try:
                driver.press_keycode(AndroidKey.HOME)
                time.sleep(1)
            except Exception as e_gohome:
                print(f"홈으로 이동 중 오류: {e_gohome}")
        print("'다음' 앱을 재실행합니다...")
        try:
            driver.activate_app(daum_app_package)
            print("앱 재실행 후 초기 화면 요소가 나타날 때까지 대기 중...")
            WebDriverWait(driver, initial_app_load_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath)) 
            )
            print("다음 앱이 성공적으로 재실행되었고 초기 화면 요소가 확인되었습니다.")
        except TimeoutException as e_timeout_restart_after_clear:
            error_message = f"오류: 백그라운드 정리 후 다음 앱 재실행 중 타임아웃: {e_timeout_restart_after_clear}"
            print(error_message)
    except Exception as e_main_block:
        print(f"백그라운드 앱 삭제 및 다음 앱 재실행 과정에서 예기치 않은 오류 발생: {e_main_block}")
        traceback.print_exc()

    print("카메라 권한 초기화 완료")

    # --- case 24 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[꽃]검색", "접근 권한 얼럿", "-", "-", "-", "-", "-", "-", "-", "꽃 검색 진입시 카메라 필수권한 획득을 위한 얼럿이 노출되는가"
    try:
        print("특수검색 클릭")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()
        print("특수검색 클릭 완료")

        print("특수검색 바텀시트 [꽃 검색] 선택")
        flower_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[3]/android.widget.Button'
        target_button_flower_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, flower_compose_button_xpath)))
        target_button_flower_compose.click()
        print("특수검색 바텀시트 [꽃 검색] 선택 완료")
        
        def check_element_visibility(wait_object, description, xpath):
            print(f"{description} 확인 중...")
            try:
                element = wait_object.until(EC.visibility_of_element_located((AppiumBy.XPATH, xpath)))
                print(f"{description} 확인 완료 ✅")
                return element
            except Exception as e:
                print(f"{description} 확인 실패 ❌: {e}")
                raise # 원래의 예외를 다시 발생시켜 테스트가 실패하도록 함

        # --- 카메라/위치 권한 확인 시작 ---
        print("\n# 카메라 필수권한 얼럿 확인")

        # 1. 얼럿 문구 확인
        permission_message_xpath = '//android.widget.TextView[@resource-id="com.android.permissioncontroller:id/permission_message" and @text="다음에서 사진을 촬영하고 동영상을 녹화하도록 허용하시겠습니까?"]'
        check_element_visibility(wait, "얼럿 문구", permission_message_xpath)

        # 2. "앱 사용 중에만 허용" 버튼 확인
        allow_foreground_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_foreground_only_button" and @text="앱 사용 중에만 허용"]'
        check_element_visibility(wait, "[앱 사용 중에만 허용] 버튼", allow_foreground_button_xpath)

        # 3. "이번만 허용" 버튼 확인
        allow_one_time_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button" and @text="이번만 허용"]'
        check_element_visibility(wait, "[이번만 허용] 버튼", allow_one_time_button_xpath)

        # 4. "허용 안함" 버튼 확인
        deny_button_xpath_by_text = '//android.widget.Button[@text="허용 안함"]'
        check_element_visibility(wait, "[허용 안함] 버튼", deny_button_xpath_by_text)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 25 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[꽃]검색", "접근 권한 얼럿", "[허용]", "-", "-", "-", "-", "-", "-", "권한 획득시 카메라 프리뷰로 전환되는가?"
    try:
        # 카메라/위치 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        # 2. 타이틀 '꽃 검색' 확인
        title_xpath = '//android.widget.TextView[@text="꽃 검색"]'
        check_element_visibility(wait, "타이틀 '꽃 검색'", title_xpath)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 26 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[꽃]검색", "꽃 검색\n프리뷰", "-", "-", "-", "-", "-", "-", "-", "꽃 검색 카메라 프리뷰가 정상적으로 노출되는가?\n====================\n[<] / [X]\n⎧ 꽃의 정면을 크게 촬영해 주세요. ⎫\n   (꽃 테두리)   \n⎩                                                ⎭\n[갤러리]       [촬영 버튼]        [플래시]"
    try:
        # 1. 뒤로가기 버튼 확인
        back_button_xpath = '//android.widget.ImageButton[@content-desc="뒤로 이동"]'
        check_element_visibility(wait, "[뒤로가기] 버튼", back_button_xpath)

        # 2. 타이틀 '꽃 검색' 확인
        title_xpath = '//android.widget.TextView[@text="꽃 검색"]'
        check_element_visibility(wait, "타이틀 '꽃 검색'", title_xpath)

        # 3. 갤러리 버튼 확인
        gallery_button_xpath = '//android.widget.ImageButton[@content-desc="앨범에서 검색"]'
        check_element_visibility(wait, "[갤러리] 버튼", gallery_button_xpath)

        # 4. 촬영 버튼 확인
        capture_button_xpath = '//android.widget.ImageButton[@content-desc="촬영"]'
        check_element_visibility(wait, "[촬영] 버튼", capture_button_xpath)

        # 5. 플래시 버튼 확인 (CheckBox)
        flash_button_xpath = '//android.widget.CheckBox[@content-desc="플래시"]'
        check_element_visibility(wait, "[플래시] 버튼", flash_button_xpath)

        # 6. 줌 기본 버튼 확인
        zoom_default_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/zoom_default_button"]'
        check_element_visibility(wait, "[줌 기본] 버튼", zoom_default_button_xpath)

        # 7. 줌인 버튼 확인
        zoom_in_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/zoom_in_button"]'
        check_element_visibility(wait, "[줌인] 버튼", zoom_in_button_xpath)

        # 8. 안내 문구 확인
        guide_text_xpath = '//android.widget.TextView[@text="꽃의 정면을 크게 촬영해 주세요"]'
        check_element_visibility(wait, "'꽃의 정면을 크게 촬영해 주세요' 문구", guide_text_xpath)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 27 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[꽃]검색", "꽃 검색\n프리뷰", "[갤러리]", "-", "-", "-", "-", "-", "-", "추가 권한 요청없이 이미지 피커가 오픈되는가?"
    try:
        gallery_button_element = check_element_visibility(wait, "[갤러리] 버튼", gallery_button_xpath)
        if gallery_button_element:
            print(f"[갤러리] 버튼 클릭 시도 중...")
            gallery_button_element.click()
            print(f"[갤러리] 버튼 클릭 완료 ✅")
        else:
            print(f"[갤러리] 버튼을 찾지 못해 클릭할 수 없습니다.")

        # 1. "사진" 확인
        photo_view_xpath = '//android.widget.TextView[@text="사진"]'
        check_element_visibility(wait, "'사진'", photo_view_xpath)

        # 2. "앨범" 확인
        album_view_xpath = '//android.widget.TextView[@text="컬렉션"]'
        check_element_visibility(wait, "'컬랙션'", album_view_xpath)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 28 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[꽃]검색", "꽃 검색\n프리뷰", "[갤러리]", "사진 선택", "유효 이미지", "-", "-", "-", "-", "사진 선택 및 사진 크롭 시 해당 결과 페이지로 즉시 랜딩되는가?"
    try:
        # 찾으려는 사진의 content-desc 값
        target_photo_desc = "2025. 9. 1. 오후 5:27에 촬영한 사진"
        
        print("갤러리 바텀시트 로딩 대기 중...")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="사진"]')))
        print("갤러리 바텀시트 확인 완료.")

        print(f"사진('{target_photo_desc}')을 찾기 위해 좌표 기반 스와이프를 시작합니다...")

        # --- [변경] 좌표 기반 스와이프 로직 ---
        found_element = None
        max_swipes = 10 # 최대 스와이프 횟수
        
        # 화면 크기 가져오기
        size = driver.get_window_size()
        start_x = size['width'] // 2
        start_y = int(size['height'] * 0.8) # 화면 하단 80% 지점
        end_y = int(size['height'] * 0.3)   # 화면 상단 30% 지점 (위로 끌어올림)

        for i in range(max_swipes):
            try:
                # 1. 현재 화면에서 요소 찾기 시도
                element = driver.find_element(AppiumBy.XPATH, f'//android.view.View[@content-desc="{target_photo_desc}"]')
                if element.is_displayed():
                    found_element = element
                    break # 찾았으면 루프 탈출
            except NoSuchElementException:
                pass # 못 찾았으면 스와이프 진행

            # 2. 못 찾았으면 스와이프 수행 (W3C Action)
            print(f"[{i+1}/{max_swipes}] 사진을 찾는 중... 스크롤 합니다.")
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.pause(0.1) # 터치 인식 대기
            actions.w3c_actions.pointer_action.move_to_location(start_x, end_y)
            actions.w3c_actions.pointer_action.release()
            actions.perform()
            
            time.sleep(1) # 스크롤 애니메이션 대기

        if found_element:
            found_element.click()
            print(f"사진 선택 완료 ({target_photo_desc}) ✅")
        else:
            print(f"오류: {max_swipes}회 스크롤 했으나 '{target_photo_desc}' 사진을 찾을 수 없습니다. ❌")
            raise NoSuchElementException(f"사진을 찾을 수 없음: {target_photo_desc}")
        # ------------------------------------

        # 갤러리 '완료' 버튼 클릭
        flower_Completion_button_xpath = '//android.widget.TextView[@resource-id="com.sec.android.gallery3d:id/navigation_bar_item_small_label_view" and @text="완료"]'
        print("'완료' 버튼 클릭 시도...")
        try:
            element_to_click = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, flower_Completion_button_xpath)))       
            element_to_click.click()
            print("완료 버튼 선택 완료 ✅")
        except Exception as e:
            print(f"완료 버튼 클릭 실패 ❌: {e}")
            raise
        
        time.sleep(3)
        
        try:
            # content-desc 속성에 '오스테오스퍼멈' 이라는 텍스트가 포함된 요소를 찾습니다.
            result_element = wait.until(EC.presence_of_element_located(
                (AppiumBy.XPATH, "//*[contains(@content-desc, '오스테오스퍼멈')]")
            ))
            
            # 해당 요소의 content-desc 내용을 가져와서 출력합니다.
            result_text = result_element.get_attribute('content-desc')
            
            print("\n🎉 최종 테스트 성공! 🎉")
            print(f"찾은 요소의 설명: '{result_text}'")

        except Exception as e:
            print(f"\n--- 💥 최종 테스트 실패! 💥 ---")
            print(f"오류: {e}")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL")
    case_num_counter += 1

    driver.back()
    time.sleep(1)

    # 카메라 권환 초기화

    print("카메라 권환 초기화")

    try:
        print("설정 앱을 실행합니다...")
        driver.activate_app('com.android.settings')
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='연결' or @text='소리 및 진동']"))
        )
        print("설정 앱 실행 및 초기 화면 로드 확인.")
        time.sleep(1)

        applications_menu_text = "애플리케이션"
        print(f"'{applications_menu_text}' 메뉴를 찾는 중...")

        try:
            applications_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{applications_menu_text}").instance(0))')
            applications_menu_element.click()
            print(f"'{applications_menu_text}' 메뉴 클릭 성공.")
        except NoSuchElementException:
            print(f"'{applications_menu_text}' 메뉴를 찾지 못했습니다. 스크린샷을 확인하고 XPath 또는 텍스트를 조정해주세요.")
            driver.save_screenshot("error_finding_applications_menu.png")
            raise

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@content-desc='검색'] | //*[@text='앱 검색'] | //*[contains(@resource-id, 'search_src_text')] | //androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout[1]"))
        )
        print("애플리케이션 목록 화면으로 이동 확인.")
        time.sleep(2)

        target_app_names = ["다음"]
        daum_app_element = None

        for app_name_to_find in target_app_names:
            print(f"'{app_name_to_find}' 앱을 찾는 중...")
            try:
                scroll_command = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{app_name_to_find}").instance(0))'
                daum_app_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, scroll_command)

                if daum_app_element:
                    print(f"'{app_name_to_find}' 앱을 찾았습니다.")
                    daum_app_element.click()
                    print(f"'{app_name_to_find}' 앱 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{app_name_to_find}' 이름으로 앱을 찾지 못했습니다. 다음 이름으로 시도합니다.")
  
        if not daum_app_element:
            print(f"앱 목록에서 '{target_app_names}' 앱을 찾지 못했습니다.")
            driver.save_screenshot("error_finding_daum_app.png")
            raise NoSuchElementException(f"앱 목록에서 다음 앱({target_app_names})을 찾을 수 없습니다.")
        time.sleep(1)

    except TimeoutException as e_timeout:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_timeout_error.png")
            print(f"현재 페이지 소스 (설정 이동 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        try:
            driver.save_screenshot("settings_navigation_no_element_error.png")
            print(f"현재 페이지 소스 (설정 이동 요소 없음 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except Exception as e_general:
        error_message = f"오류: 설정에서 다음 앱 화면으로 이동 중 알 수 없는 오류 발생: {e_general}"
        print(error_message)
        traceback.print_exc()
        try:
            driver.save_screenshot("settings_navigation_general_error.png")
            print(f"현재 페이지 소스 (설정 이동 일반 오류 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug:
            print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    try:
        permissions_menu_text_candidates = ["권한"]
        permissions_menu_element = None

        for text_candidate in permissions_menu_text_candidates:
            try:
                permissions_menu_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                permissions_menu_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, permissions_menu_query)
                if permissions_menu_element:
                    permissions_menu_element.click()
                    print(f"'{text_candidate}' 메뉴 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 메뉴를 찾지 못했습니다.")
        
        if not permissions_menu_element:
            raise NoSuchElementException(f"권한 메뉴({permissions_menu_text_candidates})를 찾을 수 없습니다.")

        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[contains(@text, '허용됨') or contains(@text, '허용되지 않음') or @text='마이크' or @text='Microphone']"))
        )
        print("권한 목록 화면으로 이동 확인.")
        time.sleep(1)

        camera_permission_text_candidates = ["카메라"]
        camera_permission_element = None

        for text_candidate in camera_permission_text_candidates:
            try:
                camera_permission_query = f'new UiScrollable(new UiSelector().scrollable(true).instance(0)).scrollIntoView(new UiSelector().text("{text_candidate}").instance(0))'
                camera_permission_element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, camera_permission_query)
                if camera_permission_element:
                    camera_permission_element.click()
                    print(f"'{text_candidate}' 권한 클릭 성공.")
                    break
            except NoSuchElementException:
                print(f"'{text_candidate}' 권한을 찾지 못했습니다.")

        if not camera_permission_element:
            raise NoSuchElementException(f"마이크 권한({camera_permission_text_candidates})을 찾을 수 없습니다.")
            
        WebDriverWait(driver, long_interaction_timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")) 
        )
        print("카메라 권한 상세 설정 화면으로 이동 확인.")
        time.sleep(1)
        
        deny_option_selected = False
        deny_option_xpaths = [
            "//android.widget.RadioButton[@text='허용 안함']",
            "//android.widget.RadioButton[@text='Deny']",
            "//android.widget.RadioButton[@text='거부']",
            "//*[(@text='허용 안함' or @text='Deny' or @text='거부') and @class='android.widget.TextView']/../android.widget.RadioButton", 
            "//android.widget.LinearLayout[descendant::android.widget.TextView[@text='허용 안함' or @text='Deny' or @text='거부']]//android.widget.RadioButton" 
        ]
        deny_option_element = None
        for xpath_candidate in deny_option_xpaths:
            try:
                deny_option_element = driver.find_element(AppiumBy.XPATH, xpath_candidate)
                if deny_option_element.is_displayed():

                    if deny_option_element.get_attribute("checked") == "true":
                        print("'허용 안함'이 이미 선택되어 있습니다.")
                    else:
                        deny_option_element.click()
                        print("'허용 안함' 옵션 선택 성공.")
                    deny_option_selected = True
                    break 
            except NoSuchElementException:
                print(f"XPath '{xpath_candidate}'로 '허용 안함' 옵션을 찾지 못했습니다.")
            except Exception as e_find_deny:
                print(f"XPath '{xpath_candidate}'로 요소 찾는 중 오류: {e_find_deny}")
        if not deny_option_selected and not (deny_option_element and deny_option_element.get_attribute("checked") == "true"):
            print("라디오 버튼 직접 선택 실패. '허용 안함' 텍스트 클릭 시도...")
            try:
                deny_text_element = driver.find_element(AppiumBy.XPATH, "//*[@text='허용 안함' or @text='Deny' or @text='거부']")
                deny_text_element.click()
                print("'허용 안함' 텍스트 클릭 성공.")
                deny_option_selected = True
            except NoSuchElementException:
                print("'허용 안함' 텍스트도 찾거나 클릭할 수 없습니다.")
                raise NoSuchElementException("마이크 권한 '허용 안함' 옵션을 선택할 수 없습니다.")
        
        time.sleep(1)

        additional_confirm_texts = ["무시하고 허용 안함", "Deny anyway", "거부 확인"]
        for confirm_text in additional_confirm_texts:
            try:
                additional_confirm_button = driver.find_element(AppiumBy.XPATH, f"//*[@text='{confirm_text}']")
                if additional_confirm_button.is_displayed():
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 중...")
                    additional_confirm_button.click()
                    print(f"추가 확인 버튼 '{confirm_text}' 클릭 성공.")
                    time.sleep(1) 
                    break 
            except NoSuchElementException:
                pass

        daum_app_package = "net.daum.android.daum"
        print("'다음' 앱으로 다시 전환합니다...")
        driver.activate_app(daum_app_package)

        print("'다음' 앱으로 전환 시도 완료.")
        try:
            WebDriverWait(driver, long_interaction_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath))
            )
            print("다음 앱 전환 성공.")
        except TimeoutException:
            print("다음 앱 초기 화면 요소를 시간 내에 찾지 못했습니다. 앱 전환 상태를 확인해주세요.")
        time.sleep(3)
    except TimeoutException as e_timeout:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 타임아웃 발생: {e_timeout}"
        print(error_message)
        try:
            driver.save_screenshot("permission_setting_timeout_error.png")
            print(f"현재 페이지 소스 (권한 설정 타임아웃 시):\n{driver.page_source[:2000]}")
        except Exception as e_debug: print(f"디버깅 정보 저장 중 오류: {e_debug}")
        raise Exception(error_message)
    except NoSuchElementException as e_no_element:
        error_message = f"오류: 다음 앱 마이크 권한 설정 중 요소를 찾을 수 없음: {e_no_element}"
        print(error_message)
        raise Exception(error_message)

    daum_app_package = "net.daum.android.daum"
    try:
        print("백그라운드 앱 모두 삭제 시도...")
        try:
            driver.press_keycode(AndroidKey.APP_SWITCH)
            time.sleep(2)

            close_all_button_selectors = [
                {"by": AppiumBy.XPATH, "value": "//*[@text='모두 닫기']"},
                {"by": AppiumBy.XPATH, "value": "//*[contains(@content-desc, '모두 닫기') or contains(@content-desc, 'Close all')]"},
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/clear_all_button"}, # 비교적 최신 One UI
                {"by": AppiumBy.ID, "value": "com.android.systemui:id/close_all_button"}, # 이전 One UI
            ]
            
            closed_all_apps_successfully = False
            for selector_info in close_all_button_selectors:
                try:
                    close_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((selector_info["by"], selector_info["value"]))
                    )
                    close_all_button.click()
                    closed_all_apps_successfully = True
                    print("백그라운드 앱 '모두 닫기' 성공.")
                    time.sleep(2) 
                    break 
                    print(f"'모두 닫기' 버튼 ({selector_info['value']})을 시간 내에 찾거나 클릭할 수 없습니다.")
                except NoSuchElementException:
                     print(f"'모두 닫기' 버튼 ({selector_info['value']})을 찾을 수 없습니다.")

        except Exception as e_clear_apps:
            print(f"백그라운드 앱 삭제 과정 중 예외 발생: {e_clear_apps}")
            traceback.print_exc()
            print("경고: 백그라운드 앱 삭제에 실패했을 수 있습니다. 다음 단계(앱 재실행)는 계속 시도합니다.")
            try:
                driver.press_keycode(AndroidKey.HOME)
                time.sleep(1)
            except Exception as e_gohome:
                print(f"홈으로 이동 중 오류: {e_gohome}")
        print("'다음' 앱을 재실행합니다...")
        try:
            driver.activate_app(daum_app_package)
            print("앱 재실행 후 초기 화면 요소가 나타날 때까지 대기 중...")
            WebDriverWait(driver, initial_app_load_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath)) 
            )
            print("다음 앱이 성공적으로 재실행되었고 초기 화면 요소가 확인되었습니다.")
        except TimeoutException as e_timeout_restart_after_clear:
            error_message = f"오류: 백그라운드 정리 후 다음 앱 재실행 중 타임아웃: {e_timeout_restart_after_clear}"
            print(error_message)
    except Exception as e_main_block:
        print(f"백그라운드 앱 삭제 및 다음 앱 재실행 과정에서 예기치 않은 오류 발생: {e_main_block}")
        traceback.print_exc()

    print("카메라 권한 초기화 완료")

    # --- case 29 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "접근 권한 얼럿", "-", "-", "-", "-", "-", "-", "-", "코드 검색 진입시 카메라 필수권한 획득을 위한 얼럿이 노출되는가?"
    try:
        print("특수검색 클릭")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()
        print("특수검색 클릭 완료")

        print("특수검색 바텀시트 [코드 검색] 선택")
        flower_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.widget.Button'
        target_button_flower_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, flower_compose_button_xpath)))
        target_button_flower_compose.click()
        print("특수검색 바텀시트 [코드 검색] 선택 완료")
        
        def check_element_visibility(wait_object, description, xpath):
            print(f"{description} 확인 중...")
            try:
                element = wait_object.until(EC.visibility_of_element_located((AppiumBy.XPATH, xpath)))
                print(f"{description} 확인 완료 ✅")
                return element
            except Exception as e:
                print(f"{description} 확인 실패 ❌: {e}")
                raise # 원래의 예외를 다시 발생시켜 테스트가 실패하도록 함

        # --- 카메라/위치 권한 확인 시작 ---
        print("\n# 카메라 필수권한 얼럿 확인")

        # 1. 얼럿 문구 확인
        permission_message_xpath = '//android.widget.TextView[@resource-id="com.android.permissioncontroller:id/permission_message" and @text="다음에서 사진을 촬영하고 동영상을 녹화하도록 허용하시겠습니까?"]'
        check_element_visibility(wait, "얼럿 문구", permission_message_xpath)

        # 2. "앱 사용 중에만 허용" 버튼 확인
        allow_foreground_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_foreground_only_button" and @text="앱 사용 중에만 허용"]'
        check_element_visibility(wait, "[앱 사용 중에만 허용] 버튼", allow_foreground_button_xpath)

        # 3. "이번만 허용" 버튼 확인
        allow_one_time_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button" and @text="이번만 허용"]'
        check_element_visibility(wait, "[이번만 허용] 버튼", allow_one_time_button_xpath)

        # 4. "허용 안함" 버튼 확인
        deny_button_xpath_by_text = '//android.widget.Button[@text="허용 안함"]'
        check_element_visibility(wait, "[허용 안함] 버튼", deny_button_xpath_by_text)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 30 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "접근 권한 얼럿", "[허용]", "-", "-", "-", "-", "-", "-", "권한을 획득하여 얼럿 종료와 함께 코드 검색이 가능한가?"
    try:
        # 카메라/위치 권한
        permission_once_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]'
        try:
            target_button_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_once_button_xpath)))
            target_button_permission.click()
            print("권한 '이번만 허용' 버튼 클릭 성공.")
        except TimeoutException:
            print(f"경고: 권한 '이번만 허용' 버튼({permission_once_button_xpath})을 시간 내에 찾지 못했습니다.")
            print("권한 창이 나타나지 않았거나 이미 처리된 것으로 간주하고 계속합니다.")

        # 1. 뒤로가기 버튼 확인
        back_button_xpath = '//android.widget.ImageButton[@content-desc="뒤로 이동"]'
        check_element_visibility(wait, "[뒤로가기] 버튼", back_button_xpath)

        # 2. 타이틀 'QR코드/바코드 검색' 확인
        title_xpath = '//android.widget.TextView[@text="QR코드/바코드 검색"]'
        check_element_visibility(wait, "타이틀 '꽃 검색'", title_xpath)

        # 3. 갤러리 버튼 확인
        gallery_button_xpath = '//android.widget.ImageButton[@content-desc="앨범에서 검색"]'
        check_element_visibility(wait, "[갤러리] 버튼", gallery_button_xpath)

        # 4. 바코드 입력 버튼 확인
        barcode_input_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/barcode_input_button"]'
        check_element_visibility(wait, "[바코드 입력] 버튼", barcode_input_button_xpath)

        # 5. 줌 기본 버튼 확인
        zoom_default_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/zoom_default_button"]'
        check_element_visibility(wait, "[줌 기본] 버튼", zoom_default_button_xpath)

        # 7. 줌인 버튼 확인
        zoom_in_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/zoom_in_button"]'
        check_element_visibility(wait, "[줌인] 버튼", zoom_in_button_xpath)

        # 8. 안내 문구 확인
        guide_text_xpath = '//android.widget.TextView[@text="바코드 검색은 도서만 지원합니다."]'
        check_element_visibility(wait, "'바코드 검색은 도서만 지원합니다.", guide_text_xpath)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 31 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[갤러리]", "-", "-", "-", "-", "-", "-", "-", "[갤러리] 선택 시 추가 권한 요청없이 이미지 피커가 오픈되는가?"
    try:
        gallery_button_element = check_element_visibility(wait, "[갤러리] 버튼", gallery_button_xpath)
        if gallery_button_element:
            print(f"[갤러리] 버튼 클릭 시도 중...")
            gallery_button_element.click()
            print(f"[갤러리] 버튼 클릭 완료 ✅")
        else:
            print(f"[갤러리] 버튼을 찾지 못해 클릭할 수 없습니다.")

        # 1. "사진" 확인
        photo_view_xpath = '//android.widget.TextView[@text="사진"]'
        check_element_visibility(wait, "'사진'", photo_view_xpath)

        # 2. "컬렉션" 확인
        album_view_xpath = '//android.widget.TextView[@text="컬렉션"]'
        check_element_visibility(wait, "'컬렉션'", album_view_xpath)
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 32 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[갤러리]", "코드뷰", "QR 기타\n(텍스트)", "노츨 코드뷰\n(코드뷰 UI)", "-", "-", "-", "-", "텍스트 정보가 정상적으로 노출되는가?\n====================\n1줄이상 말줄임 처리"
    try:
        target_qrcode_desc = "2025. 5. 17. 오후 5:33에 촬영한 사진"
        
        print("갤러리 바텀시트 로딩 대기 중...")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="사진"]')))
        
        print(f"QR코드 사진('{target_qrcode_desc}') 찾기 - 좌표 스와이프 시작")

        # --- [변경] 좌표 기반 스와이프 로직 ---
        found_element = None
        max_swipes = 10
        size = driver.get_window_size()
        start_x = size['width'] // 2
        start_y = int(size['height'] * 0.8)
        end_y = int(size['height'] * 0.3)

        for i in range(max_swipes):
            try:
                element = driver.find_element(AppiumBy.XPATH, f'//android.view.View[@content-desc="{target_qrcode_desc}"]')
                if element.is_displayed():
                    found_element = element
                    break
            except NoSuchElementException:
                pass

            print(f"[{i+1}/{max_swipes}] 스크롤 중...")
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.pause(0.1)
            actions.w3c_actions.pointer_action.move_to_location(start_x, end_y)
            actions.w3c_actions.pointer_action.release()
            actions.perform()
            time.sleep(1)

        if found_element:
            found_element.click()
            print(f"QR코드 사진 선택 완료 ({target_qrcode_desc}) ✅")
        else:
            print(f"오류: 사진을 찾을 수 없습니다. ❌")
            raise NoSuchElementException(f"사진을 찾을 수 없음: {target_qrcode_desc}")
        # ------------------------------------

        # 갤러리 '완료' 버튼 클릭
        qrcode_Completion_button_xpath = '//android.widget.TextView[@resource-id="com.sec.android.gallery3d:id/navigation_bar_item_small_label_view" and @text="완료"]'
        print("'완료' 버튼 클릭 시도...")
        try:
            element_to_click = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, qrcode_Completion_button_xpath)))       
            element_to_click.click()
            print("완료 버튼 선택 완료 ✅")
        except Exception as e:
            print(f"완료 버튼 클릭 실패 ❌: {e}")
            raise

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="ENTA1125012300038"]')))
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 33 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[갤러리]", "코드뷰", "QR 기타\n(텍스트)", "노츨 코드뷰\n(코드뷰 UI)", "코드뷰 클릭", "-", "-", "-", "해당 책 검색 결과 페이지로 랜딩되는가?\n====================\n코드 정보\n[QR 코드]\nQR 텍스트"
    try:
        qrcode_result_xpath = '//android.widget.TextView[@text="ENTA1125012300038"]'
        print("코드뷰 버튼 클릭 시도 중...")
        try:
            element_to_click = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, qrcode_result_xpath)))
            element_to_click.click()      
            print("코드뷰 버튼 클릭 완료 ✅")
        except Exception as e:
            print("코드뷰 버튼 클릭 실패 ❌: {e}")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="코드 정보"]')))
        print("타이틀 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="ENTA1125012300038"]')))
        print("QR코드 텍스트 확인 완료 ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    time.sleep(0.5)

    # 메인으로 이동
    navigate_to_home(long_wait, wait)

    print("특수검색 클릭")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()
    print("특수검색 클릭 완료")

    print("특수검색 바텀시트 [코드 검색] 선택")
    code_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.widget.Button'
    target_button_code_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, code_compose_button_xpath)))
    target_button_code_compose.click()
    print("특수검색 바텀시트 [코드 검색] 선택 완료")

    time.sleep(0.5)

    # --- case 34 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[갤러리]", "코드뷰", "도서 바코드", "노츨 코드뷰\n(코드뷰 UI)", "-", "-", "-", "-", "도서 바코드 코드뷰가 정상적으로 노출되는가?\n====================\n- 썸네일\n- 제목\n- 저자\n- 출판\n- 발행"
    try:
        gallery_button_element = check_element_visibility(wait, "[갤러리] 버튼", gallery_button_xpath)
        if gallery_button_element:
            print(f"[갤러리] 버튼 클릭 시도 중...")
            gallery_button_element.click()
            print(f"[갤러리] 버튼 클릭 완료 ✅")
        else:
            print(f"[갤러리] 버튼을 찾지 못해 클릭할 수 없습니다.")

        ############################################
        # 바코드 사진 찾기 (좌표 스와이프)
        ###########################################
        
        target_barcode_desc = "2025. 5. 14. 오후 3:56에 촬영한 사진"
        
        print("갤러리 바텀시트 로딩 대기 중...")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="사진"]')))

        print(f"바코드 사진('{target_barcode_desc}') 찾기 - 좌표 스와이프 시작")

        # --- [변경] 좌표 기반 스와이프 로직 ---
        found_element = None
        max_swipes = 10
        size = driver.get_window_size()
        start_x = size['width'] // 2
        start_y = int(size['height'] * 0.8)
        end_y = int(size['height'] * 0.3)

        for i in range(max_swipes):
            try:
                element = driver.find_element(AppiumBy.XPATH, f'//android.view.View[@content-desc="{target_barcode_desc}"]')
                if element.is_displayed():
                    found_element = element
                    break
            except NoSuchElementException:
                pass

            print(f"[{i+1}/{max_swipes}] 스크롤 중...")
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.pause(0.1)
            actions.w3c_actions.pointer_action.move_to_location(start_x, end_y)
            actions.w3c_actions.pointer_action.release()
            actions.perform()
            time.sleep(1)

        if found_element:
            found_element.click()
            print(f"바코드 사진 선택 완료 ({target_barcode_desc}) ✅")
        else:
            print(f"오류: 사진을 찾을 수 없습니다. ❌")
            raise NoSuchElementException(f"사진을 찾을 수 없음: {target_barcode_desc}")
        # ------------------------------------

        # 갤러리 '완료' 버튼 클릭
        barcode_Completion_button_xpath = '//android.widget.TextView[@resource-id="com.sec.android.gallery3d:id/navigation_bar_item_small_label_view" and @text="완료"]'
        print("'완료' 버튼 클릭 시도...")
        try:
            element_to_click = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, barcode_Completion_button_xpath)))       
            element_to_click.click()
            print("완료 버튼 선택 완료 ✅")
        except Exception as e:
            print(f"완료 버튼 클릭 실패 ❌: {e}")
            raise

        # 결과 확인
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.ImageView[@resource-id="net.daum.android.daum:id/image"]')))
        print("썸네일 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="원피스 50: 여기에 있다"]')))
        print("제목 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="Eiichiro Oda"]')))
        print("저자 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="대원씨아이"]')))
        print("출판 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="net.daum.android.daum:id/date_label"]')))
        print("발행 확인 완료 ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    time.sleep(0.5)

    # --- case 35 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[갤러리]", "코드뷰", "도서 바코드", "노츨 코드뷰\n(코드뷰 UI)", "코드뷰 클릭", "-", "-", "-", "해당 책 검색 결과 페이지로 랜딩되는가?"
    try:
        barcode_result_button_xpath = '//android.view.ViewGroup[@resource-id="net.daum.android.daum:id/search_book_result_view"]'
        target_button_barcode_result_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, barcode_result_button_xpath)))
        target_button_barcode_result_button.click()

        time.sleep(2)

        print("\n# 바코드 검색 결과 화면 확인")

        # 1. 탭 메뉴 확인 (책소개, 리뷰, 판매정보)
        tab_book_intro1_xpath = '//android.widget.TextView[@text="책소개"]'
        tab_review1_xpath = '//android.widget.TextView[@text="리뷰"]'
        tab_sales_info1_xpath = '//android.widget.TextView[@text="판매정보"]'

        check_element_visibility(wait, "탭 '책소개'", tab_book_intro1_xpath)
        check_element_visibility(wait, "탭 '리뷰'", tab_review1_xpath)
        check_element_visibility(wait, "탭 '판매정보'", tab_sales_info1_xpath)
        print("책소개, 리뷰, 판매정보 탭 확인 완료 ✅")

        book_title1_xpath = '//android.view.View[@text="원피스 50: 여기에 있다"]'
        book_author1_xpath = '//android.widget.TextView[@text="저자  오다 에이치로"]'

        check_element_visibility(wait, "책 제목 '원피스 50: 여기에 있다'", book_title1_xpath)
        check_element_visibility(wait, "저자명 '저자 오다 에이치로'", book_author1_xpath)
        print("책 제목, 저자명 확인 완료 ✅")

        # 3. 상세 정보 섹션 타이틀 확인 (소개, 저자, 목차)
        section_intro1_xpath = '//android.widget.TextView[@text="소개"]'
        section_author1_xpath = '//android.widget.TextView[@text="저자"]'
        section_toc1_xpath = '//android.widget.TextView[@text="목차"]' # TOC: Table of Contents

        check_element_visibility(wait, "섹션 '소개'", section_intro1_xpath)
        check_element_visibility(wait, "섹션 '저자'", section_author1_xpath)
        check_element_visibility(wait, "섹션 '목차'", section_toc1_xpath)
        print("소개 / 저자 / 목차 섹션 확인 완료 ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL")
    case_num_counter += 1

    # 메인으로 이동
    navigate_to_home(long_wait, wait)

    print("특수검색 클릭")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()
    print("특수검색 클릭 완료")

    print("특수검색 바텀시트 [코드 검색] 선택")
    code_compose_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.widget.Button'
    target_button_code_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, code_compose_button_xpath)))
    target_button_code_compose.click()
    print("특수검색 바텀시트 [코드 검색] 선택 완료")
    
    # --- case 36 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[바코드 입력]", "-", "-", "-", "-", "-", "-", "-", "버튼 선택 시 아래와 같은 페이지로 이동되는가?\n====================\n[<] 바코드 입력\n바코드 이미지 (숫자텍스트 주황색으로 노출)\n바코드 하단의 숫자를 입력해주세요. \n[입력란]"
    try:
        barcode_input_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/barcode_input_button"]'
        print("[바코드 입력] 버튼 클릭 시도 중...")
        try:
            element_to_click = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, barcode_input_button_xpath)))
            element_to_click.click()      
            print("[바코드 입력] 버튼 클릭 완료 ✅")
        except Exception as e:
            print("[바코드 입력] 버튼 클릭 실패 ❌: {e}")
        
        time.sleep(0.5)
        print("\n# 바코드 입력 페이지 확인")

        # 1. 뒤로가기 버튼 확인
        barcode_back_button_xpath = '//android.widget.ImageButton[@content-desc="뒤로 이동"]'
        check_element_visibility(wait, "[뒤로가기] 버튼", barcode_back_button_xpath)

        # 2. 타이틀 '바코드 입력' 확인
        barcode_title_xpath = '//android.widget.TextView[@text="바코드 입력"]'
        check_element_visibility(wait, "타이틀 '바코드 입력'", barcode_title_xpath)

        # 3. 안내 문구 확인
        barcode_guide_text_xpath = '//android.widget.TextView[@text="바코드 하단의 숫자를 입력해주세요."]'
        check_element_visibility(wait, "안내 문구 '바코드 하단의 숫자를 입력해주세요.'", barcode_guide_text_xpath)

        # 4. 입력 필드 확인
        barcode_input_field_xpath = '//android.widget.EditText[@resource-id="android:id/text2"]'
        check_element_visibility(wait, "입력 필드", barcode_input_field_xpath)

        # 5. [확인] 버튼 확인
        barcode_confirm_button_xpath = '//android.widget.Button[@resource-id="net.daum.android.daum:id/ok_button"]'
        check_element_visibility(wait, "[확인] 버튼", barcode_confirm_button_xpath)
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 37 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[바코드 입력]", "입력필드", "-", "-", "-", "-", "-", "-", "숫자 키패드가 오픈되어 입력이 가능한가?"
    try:
        button_xpath_barcode_inputFilde = '//android.widget.EditText[@resource-id="android:id/text2"]'
        barcode_text_to_input = "9788925285986"
        target_button_barcode_inputFilde = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_barcode_inputFilde))
        )
        print("바코드 입력 필드를 찾았으며 클릭 가능합니다. 클릭을 시도합니다...")
        target_button_barcode_inputFilde.click()
        print("바코드 입력 필드를 성공적으로 클릭했습니다.")
        try:
            print(f"바코드 입력 필드에 '{barcode_text_to_input}' 텍스트 입력을 시도합니다.")
            target_button_barcode_inputFilde.send_keys(barcode_text_to_input)
            print(f"'{barcode_text_to_input}' 텍스트를 성공적으로 입력했습니다.")
        except Exception as e_input:
            print(f"바코드 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 38 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "[코드] 검색", "[바코드 입력]", "입력필드", "[확인]/[완료]", "검색 성공", "-", "-", "-", "-", "도서 바코드 검색 완료된 경우 검색결과가 정상적으로 조회되어 아래와 같이 보여지는가?\n(검색내역 책별로 상이함)\n====================\n- 책 검색 \n-  책소개 / 리뷰/ 판매정보\n- 책 썸네일, 제목, 저자명\n- 소개 / 저자 / 목차 / 출판사서평"
    try:
        button_xpath_barcode_inputOk = '//android.widget.Button[@resource-id="net.daum.android.daum:id/ok_button"]'
        print("바코드 입력 확인")
        target_button_barcode_inputOk = long_wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_barcode_inputOk))
        )
        target_button_barcode_inputOk.click()
        print("[확인] 버튼 클릭 완료.")

        time.sleep(1)

        print(" 바코드 검색 결과 화면 확인 완료")

        try:
            result_element = wait.until(EC.presence_of_element_located(
                (AppiumBy.XPATH, "//*[contains(@text, '원피스 51: 11인의 초신성')]")
            ))

            result_text = result_element.get_attribute('text') # 속성을 text로 가져오기

            print("\n🎉 최종 테스트 성공! 🎉")
            print(f"찾은 요소의 텍스트: '{result_text}'")

        except Exception as e:
            print(f"\n--- 💥 최종 테스트 실패! 💥 ---")
            print(f"오류: {e}")

        print(" 바코드 검색 결과 화면 확인")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL")
    case_num_counter += 1
    
    # 메인으로 이동
    navigate_to_home(long_wait, wait)

    # --- case 39 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "-", "-", "-", "-", "-", "-", "-", "-", "버튼 선택 시 특수검색 히스토리 페이지로 이동되어 노출 탭간 이동이 가능한가?\n====================\n[X] / [<] 히스토리 [삭제]\n[X] / [<] 히스토리 [삭제]"
    try:
        print("특수검색 클릭")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()
        print("특수검색 클릭 완료")

        print("특수검색 바텀시트 [히스토리] 선택")
        history_compose_button_xpath = '//android.widget.TextView[@text="히스토리"]'
        target_button_history_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_compose_button_xpath)))
        target_button_history_compose.click()
        print("특수검색 바텀시트 [히스토리] 선택 완료")

        print("히스토리 페이지 버튼 확인")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.view.View[@content-desc="뒤로 이동"]')))
        print("[뒤로가기] 버튼 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="히스토리"]')))
        print("타이틀 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button[@content-desc="편집"]')))
        print("[편집] 버튼 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="음악"]')))
        print("음악 탭 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="꽃"]')))
        print("꽃 탭 확인 완료 ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="코드"]')))
        print("코드 탭 확인 완료 ✅")

        print("탭 간 이동 확인")
        print("꽃 탭 이동 확인")
        history_flower_button_xpath = '//android.widget.TextView[@text="꽃"]'
        target_button_history_flower = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_flower_button_xpath)))
        target_button_history_flower.click()
        print("꽃 탭 이동 확인 완료  ✅")
        time.sleep(0.5)

        print("코드 탭 이동 확인")
        history_code_button_xpath = '//android.widget.TextView[@text="코드"]'
        target_button_history_code = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_code_button_xpath)))
        target_button_history_code.click()
        print("코드 탭 이동 확인 완료  ✅")
        time.sleep(0.5)

        print("음악 탭 이동 확인")
        history_music_button_xpath = '//android.widget.TextView[@text="음악"]'
        target_button_history_music = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_music_button_xpath)))
        target_button_history_music.click()
        print("음악 탭 이동 확인 완료  ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    time.sleep(0.5)

    # --- case 40 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[꽃]", "히스토리 있음", "리스트", "-", "-", "-", "-", "-", "꽃 검색 히스토리 리스트가 정상적으로 노출되는가?\n====================\n꽃이름, 학명, 뜻, 검색한 날짜"
    try:
        print("꽃 탭 이동 확인")
        history_flower_button_xpath = '//android.widget.TextView[@text="꽃"]'
        target_button_history_flower = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_flower_button_xpath)))
        target_button_history_flower.click()
        print("꽃 탭 이동 확인 완료  ✅")
        time.sleep(0.5)

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="오스테오스퍼멈 Osteospermum spp."]')))    
        print("꽃, 학명 이름 확인 완료  ✅") 
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="영원한 사랑"]')))    
        print("뜻 확인 완료  ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    time.sleep(0.5)

    # --- case 41 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[꽃]", "히스토리 있음", "리스트 선택", "-", "-", "-", "-", "-", "리스트 선택시 해당 꽃 검색 결과로 이동하는가?"
    try:
        history_flower1_button_xpath = '//android.widget.TextView[@text="오스테오스퍼멈 Osteospermum spp."]'
        target_button_history_flower1 = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_flower1_button_xpath)))
        target_button_history_flower1.click()
        print("꽃 탭 이동 확인 완료  ✅")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="오스테오스퍼멈 - Daum 검색"]')))
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL")
    case_num_counter += 1

    time.sleep(0.5)

    # 메인으로 이동
    navigate_to_home(long_wait, wait)

    print("특수검색 클릭")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()
    print("특수검색 클릭 완료")

    print("특수검색 바텀시트 [히스토리] 선택")
    history_compose_button_xpath = '//android.widget.TextView[@text="히스토리"]'
    target_button_history_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_compose_button_xpath)))
    target_button_history_compose.click()
    print("특수검색 바텀시트 [히스토리] 선택 완료")

    print("꽃 탭 이동 확인")
    history_flower_button_xpath = '//android.widget.TextView[@text="꽃"]'
    target_button_history_flower = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_flower_button_xpath)))
    target_button_history_flower.click()
    print("꽃 탭 이동 확인 완료  ✅")
    time.sleep(0.5)

    # --- case 42 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[꽃]", "히스토리 있음", "[삭제]", "[개별 선택]", "[삭제]", "-", "-", "-", "히스토리 목록을 선택한 상태에서 [삭제] 버튼 선택 시, 해당 항목은 리스트에서 제외되는가?"
    try:
        history_edit_button_xpath = '//android.widget.Button[@content-desc="편집"]'
        target_button_history_edit = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_edit_button_xpath)))
        target_button_history_edit.click()
        print("[편집] 버튼 선택")

        history_checkbox_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.view.View/android.view.View/android.widget.CheckBox'
        target_button_history_checkbox = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_checkbox_button_xpath)))
        target_button_history_checkbox.click()
        print("임의의 히스토리 목록 체크")

        history_delete_button_xpath = '//android.widget.Button[@content-desc="삭제"]'
        target_button_history_delete = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_delete_button_xpath)))
        target_button_history_delete.click()
        print("[삭제] 버튼 선택")

        history_deleteok_button_xpath = '//android.widget.Button[@text="확인"]'
        target_button_history_deleteok = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_deleteok_button_xpath)))
        target_button_history_deleteok.click()
        print("[확인] 버튼 선택")
        
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="검색한 히스토리가 없어요"]')))
        print("삭제 확인 완료  ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    time.sleep(0.5)

    # --- case 43 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[코드]", "히스토리 있음", "리스트", "-", "-", "-", "-", "-", "코드 검색 히스토리 리스트가 정상적으로 노출되는가?\n====================\n- QR : URL 주소 노출\n- 바코드 : 도서명 노출"
    try:
        print("코드 탭 이동 확인")
        history_code_button_xpath = '//android.widget.TextView[@text="코드"]'
        target_button_history_code = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_code_button_xpath)))
        target_button_history_code.click()
        print("코드 탭 이동 확인 완료  ✅")
        time.sleep(0.5)

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="원피스 51: 11인의 초신성"]')))
        print("바코드 : 도서명 노출 확인 완료  ✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="ENTA1125012300038"]')))
        print("QR : 텍스 노출 확인 완료  ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1
    
    # --- case 44 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[코드]", "히스토리 있음", "리스트 선택", "-", "-", "-", "-", "-", "리스트 선택시 해당 코드 검색 결과로 이동하는가?"
    try:
        print("바코드 결과 페이지 확인")
        history_barcode_button_xpath = '//android.widget.TextView[@text="원피스 51: 11인의 초신성"]'
        target_button_history_barcode = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_barcode_button_xpath)))
        target_button_history_barcode.click()
        print("바코드 결과 페이지 이동")
        time.sleep(0.5)

        # 바코드 결과 페이지
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="원피스 51: 11인의 초신성 - Daum 검색"]')))
        # check_element_visibility(wait, "탭 '책소개'", tab_book_intro_xpath)
        # check_element_visibility(wait, "탭 '리뷰'", tab_review_xpath)
        # check_element_visibility(wait, "탭 '판매정보'", tab_sales_info_xpath)
        # print("책소개, 리뷰, 판매정보 탭 확인")
        print("바코드 확인 결과 페이지 확인 완료 ✅")

        driver.back()
        time.sleep(1)

        print("특수검색 클릭")
        special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
        special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
        special_search_button.click()
        print("특수검색 클릭 완료")

        print("특수검색 바텀시트 [히스토리] 선택")
        history_compose_button_xpath = '//android.widget.TextView[@text="히스토리"]'
        target_button_history_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_compose_button_xpath)))
        target_button_history_compose.click()
        print("특수검색 바텀시트 [히스토리] 선택 완료")

        print("코드 탭 이동 확인")
        history_code_button_xpath = '//android.widget.TextView[@text="코드"]'
        target_button_history_code = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_code_button_xpath)))
        target_button_history_code.click()
        print("코드 탭 이동 확인 완료  ✅")

        time.sleep(1)

        print("QR코드 결과 페이지 확인")
        history_qrcode_button_xpath = '//android.widget.TextView[@text="ENTA1125012300038"]'
        target_button_history_qrcode = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_qrcode_button_xpath)))
        target_button_history_qrcode.click()

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="ENTA1125012300038"]')))
        print("QR코드 텍스트 확인 완료 ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    driver.back()
    time.sleep(0.5)

    print("특수검색 클릭")
    special_search_button_xpath = '//android.widget.Button[@content-desc="특수검색"]'
    special_search_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, special_search_button_xpath)))
    special_search_button.click()
    print("특수검색 클릭 완료")

    print("특수검색 바텀시트 [히스토리] 선택")
    history_compose_button_xpath = '//android.widget.TextView[@text="히스토리"]'
    target_button_history_compose = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_compose_button_xpath)))
    target_button_history_compose.click()
    print("특수검색 바텀시트 [히스토리] 선택 완료")

    print("코드 탭 이동 확인")
    history_code_button_xpath = '//android.widget.TextView[@text="코드"]'
    target_button_history_code = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_code_button_xpath)))
    target_button_history_code.click()
    print("코드 탭 이동 확인 완료  ✅")

    # --- case 45 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "특수검색 히스토리", "[코드]", "히스토리 있음", "[삭제]", "[개별 선택]", "[삭제]", "-", "-", "-", "임의의 히스토리 목록을 선택한 상태에서 [삭제] 버튼 선택 시, 해당 항목은 리스트에서 제외되는가"
    try:
        history_edit_button_xpath = '//android.widget.Button[@content-desc="편집"]'
        target_button_history_edit = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_edit_button_xpath)))
        target_button_history_edit.click()
        print("[편집] 버튼 선택 완료  ✅")

        history_checkbox_button_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.view.View/android.view.View/android.widget.CheckBox'
        target_button_history_checkbox = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_checkbox_button_xpath)))
        target_button_history_checkbox.click()
        print("임의의 히스토리 목록 체크 확인 완료  ✅")

        history_delete_button_xpath = '//android.widget.Button[@content-desc="삭제"]'
        target_button_history_delete = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_delete_button_xpath)))
        target_button_history_delete.click()
        print("[삭제] 버튼 선택 ✅")

        history_deleteok_button_xpath = '//android.widget.Button[@text="확인"]'
        target_button_history_deleteok = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, history_deleteok_button_xpath)))
        target_button_history_deleteok.click()
        print("[확인] 버튼 선택 ✅")

        wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="원피스 51: 11인의 초신성"]')))
        print("삭제 확인 완료 ✅")
 
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
    case_num_counter += 1

    
    print("\n모든 테스트 시나리오 실행 완료.")

except Exception as e:
    print(f"\n### 스크립트 실행 중 예기치 않은 오류 발생 ###\n오류 메시지: {e}")

    log_test_result(
        driver, 
        number="FATAL", 
        category="System Error", 
        depth1="-", depth2="-", depth3="-", depth4="-", depth5="-", depth6="-", depth7="-", 
        Pre="-", 
        description=f"스크립트 실행 중 치명적 오류 발생: {str(e)}", 
        result="FAIL", 
        exception_obj=e
    )
    
    traceback.print_exc()

finally:
    run_end_time = datetime.now()
    
    # --- 1. 구글 시트 저장 ---
    if test_results:
        write_results_to_gsheet(
            test_results, device_name, device_model, 
            platform_version, app_package_name, app_version, 
            run_start_time, run_end_time, TESTER_NAME, SCRIPT_NAME
        )
        
    # --- 2. 휴대폰 알림 전송 로직 ---
    print("\n--- 휴대폰으로 테스트 완료 알림 전송 시도 ---")
    try:
        # 테스트 결과 요약
        total_cases = len(test_results)
        fail_cases = sum(1 for r in test_results if r.get("Result") == "FAIL")
        pass_cases = total_cases - fail_cases
        
        # 알림 제목 및 내용 설정
        if fail_cases > 0:
            notification_title = f"❌ Appium 테스트 실패 (실패: {fail_cases}건)"
            notification_priority = "high" # 실패 시 높은 우선순위
        elif total_cases > 0:
            notification_title = f"✅ Appium 테스트 성공 (성공: {pass_cases}건)"
            notification_priority = "default" # 성공 시 기본 우선순위
        else:
            notification_title = "⚠️ Appium 테스트 결과 없음"
            notification_priority = "low" # 결과가 없는 경우 낮은 우선순위

        # ntfy.sh로 보낼 메시지 본문
        duration_str = "N/A"
        if isinstance(run_start_time, datetime) and isinstance(run_end_time, datetime):
            duration = run_end_time - run_start_time
            duration_str = str(timedelta(seconds=round(duration.total_seconds())))

        message_body = (
            f"앱: {APP_NAME} (v{app_version})\n"
            f"기기: {device_model} ({device_name})\n"
            f"결과: 성공 {pass_cases} / 실패 {fail_cases}\n"
            f"총 소요시간: {duration_str}\n"
            f"수행자: {TESTER_NAME}"
        )
        
        requests.post(
            "https://ntfy.sh/daumapp_autotest", # ntfy.sh 주소
            data=message_body.encode(encoding='utf-8'),
            headers={
                "Title": notification_title.encode('utf-8'),
                "Priority": notification_priority,
                "Tags": "tada,white_check_mark" if fail_cases == 0 else "rotating_light,x" # 아이콘 태그
            }
        )
        print(f"✅ ntfy.sh 알림 전송 완료")

    except ImportError:
        print("❌ 알림 전송 실패: 'requests' 라이브러리가 설치되지 않았습니다. (pip install requests)")
    except Exception as e_notify:
        print(f"❌ ntfy.sh 알림 전송 중 오류 발생: {e_notify}")

    # --- 3. 드라이버 종료 ---
    if driver:
        print("\n테스트 완료. Appium 세션을 종료합니다.")
        driver.quit()
    else:
        print("\nAppium 드라이버가 시작되지 않았습니다.")

    # --- 4. PC에 결과 이미지 띄우기  ---
    print("\n--- PC에 테스트 결과 이미지 띄우기 시도 ---")
    if PIL_AVAILABLE:
        PASS_IMAGE_PATH = "/Users/jayden.coys/Autotest/Completed.png" # 예: 성공 이미지 파일 경로
        FAIL_IMAGE_PATH = "/Users/jayden.coys/Autotest/Fail.png" # 예: 실패 이미지 파일 경로
        
        image_path_to_show = None

        total_cases_img = len(test_results)
        fail_cases_img = sum(1 for r in test_results if r.get("Result") == "FAIL")

        if fail_cases_img > 0:
            image_path_to_show = FAIL_IMAGE_PATH
            print(f"테스트 실패. {FAIL_IMAGE_PATH} 이미지를 띄웁니다.")
        elif total_cases_img > 0: # 실패 0, 전체 1 이상 = 모두 성공
            image_path_to_show = PASS_IMAGE_PATH
            print(f"테스트 성공! {PASS_IMAGE_PATH} 이미지를 띄웁니다.")
        else:
            print("실행된 테스트 케이스가 없어(total_cases=0) 이미지를 띄우지 않습니다.")

        if image_path_to_show:
            try:
                img = Image.open(image_path_to_show)
                img.show()
                print(f"✅ 결과 이미지를 PC에 성공적으로 띄웠습니다.")
            except FileNotFoundError:
                print(f"❌ 이미지 띄우기 실패: 파일 경로를 찾을 수 없습니다.")
                print(f"   (지정된 경로: {os.path.abspath(image_path_to_show)})")
            except Exception as e_img:
                print(f"❌ PC에 이미지 띄우기 중 오류 발생: {e_img}")
    else:
        print("(앞서 안내한 대로 'Pillow' 라이브러리가 없어 이 단계를 건너뛰었습니다.)")

print("스크립트 실행 종료.")