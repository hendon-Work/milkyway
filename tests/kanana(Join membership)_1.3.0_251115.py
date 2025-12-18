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
import base64 # 이미지

import gspread # 구글 스프레드시트 라이브러리
from google.oauth2.service_account import Credentials # 구글 연동 라이브러리
import requests # 알림 전송

try:
    from PIL import Image
    PIL_AVAILABLE = True # 라이브러리가 있으면 플래그를 True로 설정
except ImportError:
    PIL_AVAILABLE = False # 라이브러리가 없으면 False로 설정
    print("⚠️ 'Pillow' 라이브러리가 설치되지 않았습니다. (pip install pillow)")
    print("   테스트 완료 후 PC에 결과 이미지를 띄우는 기능을 건너뜁니다.")

# -----------------------------------------------------------------------------
# Appium 옵션 설정
# -----------------------------------------------------------------------------
options = AppiumOptions()
options.load_capabilities({
    "platformName": "Android",
    "appium:platformVersion": "15.0",
    "appium:deviceName": "R3CR10ZHBZP",
    "appium:appPackage": "com.kakao.kanana",
    "appium:appActivity": "com.kakao.kanana.ui.splash.SplashActivity",
    "appium:automationName": "UiAutomator2",
    "appium:ensureWebviewsHavePages": True,
    "appium:newCommandTimeout": 3600,
    "appium:connectHardwareKeyboard": False,
    "appium:nativeWebScreenshot": True,
    "appium:noReset": False,
    "appium:imageMatchThreshold": 0.8
})

# -----------------------------------------------------------------------------
# 전역 변수 및 타임아웃 설정
# -----------------------------------------------------------------------------
driver = None
initial_app_load_timeout = 20 # 앱 초기 로딩 최대 시간
element_interaction_timeout = 15 # 동작 최대 시간
long_interaction_timeout = 30 # 상호작용 최대 시간

# --- 로그 및 스크린샷 저장을 위한 디렉토리 설정 ---
LOG_ARTIFACTS_DIR = "test_issue"
if not os.path.exists(LOG_ARTIFACTS_DIR):
    os.makedirs(LOG_ARTIFACTS_DIR)
    print(f"'{LOG_ARTIFACTS_DIR}' 디렉토리를 생성했습니다.")

# -----------------------------------------------------------------------------
# 결과 저장을 위한 전역 변수
# -----------------------------------------------------------------------------
SPREADSHEET_NAME = "kanana test report"
APP_NAME = "kanana"
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
    
# --- 실패 시 스크린샷과 페이지 소스를 파일로 저장 ---
def log_failure_details(driver, base_filename, exception_obj=None):
    """실패 시점의 스크린샷과 '오류 트레이스백'을 파일로 저장합니다."""
    if not driver:
        print("Driver가 없어 스크린샷을 저장할 수 없습니다.")
    
    error_log_content = "N/A"

    try:
        # --- 1. 오류 트레이스백 가져오기 ---
        if exception_obj:
            error_log_content = "".join(traceback.format_exception(
                type(exception_obj), 
                exception_obj, 
                exception_obj.__traceback__
            ))
            print("💻 오류 트레이스백 정보 수집 완료.")
        else:
            error_log_content = "오류 객체(exception_obj)가 전달되지 않았습니다.\n(log_test_result 호출 시 exception_obj=e 인자가 누락되었을 수 있습니다.)"
            print("⚠️ exception_obj가 없어 트레이스백을 저장할 수 없습니다.")

    except Exception as e_trace:
        print(f"❌ 트레이스백 수집 중 오류 발생: {e_trace}")
        error_log_content = f"--- 오류 ---\n트레이스백 수집에 실패했습니다: {e_trace}"

    try:
        # 2. 파일 경로 설정
        screenshot_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}.png")
        log_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}_log.txt")

        # 3. 스크린샷 저장 (Driver가 있을 경우)
        if driver:
            driver.save_screenshot(screenshot_path)
            print(f"📸 스크린샷 저장 완료: {screenshot_path}")
            screenshot_abspath = os.path.abspath(screenshot_path)
        else:
            screenshot_abspath = "Driver 없음 (저장 실패)"

        # 4. 로그 파일에 정보 작성 (오류 트레이스백)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"### 테스트 실패 로그 (오류 트레이스백) ###\n\n")
            f.write(f"발생 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"스크린샷 파일: {screenshot_abspath}\n\n")
            f.write("--- 오류 트레이스백 ---\n")
            f.write(error_log_content)
        
        print(f"📄 실패 로그 파일 (오류 트레이스백) 저장 완료: {log_path}")

    except Exception as e:
        print(f"❌ 실패 로그 저장 중 예기치 않은 오류 발생: {e}")

def log_test_result(driver, number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, description, result, exception_obj=None):
    """테스트 결과를 기록하고, 실패 시 스크린샷과 오류 트레이스백을 파일로 저장합니다."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 실패 시 로그 파일 생성
    if result == "FAIL":
        base_filename = f"FAIL_case_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # exception_obj를 log_failure_details로 전달
        log_failure_details(driver, base_filename, exception_obj) 

    test_results.append({
        "번호": number, "테스트 분류": category, "1depth": depth1, "2depth": depth2,
        "3depth": depth3, "4depth": depth4, "5depth": depth5, "6depth": depth6,
        "7depth": depth7, "Pre-Condition": Pre, "Expected Result": description,
        "Result": result, "실행 시간": timestamp
    })
    print(f"LOG: [{result}] {description}")

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

def write_results_to_gsheet(results, dev_name, device_model, plat_ver, app_pkg, app_ver, start_ts, end_ts, tester_name, script_name):
    """기록된 모든 테스트 결과를 Google Sheets 파일로 저장합니다."""
    if not results:
        print("기록된 테스트 결과가 없어 Google Sheets에 저장하지 않습니다.")
        return

    print("\n--- Google Sheets에 결과 저장 시작 ---")
    
    duration_str = "N/A"
    if isinstance(start_ts, datetime) and isinstance(end_ts, datetime):
        duration = end_ts - start_ts
        duration_str = str(timedelta(seconds=round(duration.total_seconds())))

    start_time_str = start_ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(start_ts, datetime) else "N/A"
    end_time_str = end_ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(end_ts, datetime) else "N/A"

    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file('daumapp-d19cf041d47c.json', scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # 시트 이름에 모델명과 시리얼 번호를 모두 사용하여 고유성을 높입니다.
        sheet_name = f"검색_{tester_name}({device_model}){end_time_str}"
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(results) + 20, cols=20)
        
        # --- 1. 헤더 정보 먼저 쓰기 ---
        summary_header = [
            ["테스트 환경 요약"],
            ["수행자", tester_name],
            ["앱 정보", f"{APP_NAME} (v{app_ver})"],
            ["디바이스", f"{device_model} ({dev_name})"],
            ["Android 버전", plat_ver],
            ["수행 스크립트", script_name],
            ["수행 시작 시간", start_time_str],
            ["수행 종료 시간", end_time_str],
            ["총 소요 시간", duration_str],
            []
        ]
        worksheet.append_rows(summary_header, value_input_option='USER_ENTERED')
        headers = list(results[0].keys())
        worksheet.append_row(headers)
        worksheet.freeze(rows=10)

        # --- 2. 데이터를 쓰기 전, 빈 셀의 서식을 먼저 설정 ---
        print("데이터를 쓰기 전, 셀 서식을 미리 설정합니다...")
        try:
            requests_body = {"requests": []}
            
            data_start_row_index = 10
            data_range = {
                "sheetId": worksheet.id, "startRowIndex": data_start_row_index,
                "endRowIndex": data_start_row_index + len(results), "startColumnIndex": 0, "endColumnIndex": len(headers)
            }

            # 배경색을 제거하고, 최종 서식(정렬, 줄바꿈)만 남깁니다.
            formatting_request = {
                "repeatCell": {
                    "range": data_range,
                    "cell": { "userEnteredFormat": { "verticalAlignment": "TOP", "wrapStrategy": "WRAP" } },
                    "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)"
                }
            }
            requests_body["requests"].append(formatting_request)
            
            # 컬럼 너비 조정 요청 추가
            category_col_index = headers.index("테스트 분류")
            depth4_col_index = headers.index("4depth")
            expected_result_col_index = headers.index("Expected Result")
            result_col_index = headers.index("Result")
            requests_body["requests"].extend([
                { "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": category_col_index, "endIndex": category_col_index + 1 }, "properties": { "pixelSize": 138 }, "fields": "pixelSize" } },
                { "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": depth4_col_index, "endIndex": depth4_col_index + 1 }, "properties": { "pixelSize": 123 }, "fields": "pixelSize" } },
                { "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": expected_result_col_index, "endIndex": expected_result_col_index + 1 }, "properties": { "pixelSize": 482 }, "fields": "pixelSize" } },
                { "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": result_col_index, "endIndex": result_col_index + 1 }, "properties": { "pixelSize": 56 }, "fields": "pixelSize" } }
            ])

            # 'Result' 열에 대한 조건부 서식 추가 (값이 "FAIL"일 때 빨간색 배경)
            conditional_format_rule_fail = {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": worksheet.id,
                                "startRowIndex": data_start_row_index,
                                "endRowIndex": data_start_row_index + len(results),
                                "startColumnIndex": result_col_index,
                                "endColumnIndex": result_col_index + 1
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ", # 텍스트가 정확히 일치할 때
                                "values": [{"userEnteredValue": "FAIL"}]
                            },
                            "format": {
                                "backgroundColor": { 
                                    "red": 0.9,   # 연한 빨간색 (R: 229, G: 153, B: 153)
                                    "green": 0.6, 
                                    "blue": 0.6 
                                } 
                            }
                        }
                    },
                    "index": 0 # 첫 번째 규칙
                }
            }
            requests_body["requests"].append(conditional_format_rule_fail)
            
            # 'Result' 열에 대한 조건부 서식 추가 (값이 "PASS"일 때 녹색 배경)
            conditional_format_rule_pass = {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": worksheet.id,
                                "startRowIndex": data_start_row_index,
                                "endRowIndex": data_start_row_index + len(results),
                                "startColumnIndex": result_col_index,
                                "endColumnIndex": result_col_index + 1
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ", # 텍스트가 정확히 일치할 때
                                "values": [{"userEnteredValue": "PASS"}]
                            },
                            "format": {
                                "backgroundColor": { 
                                    "red": 0.6,   # 연한 녹색 (R: 153, G: 229, B: 153)
                                    "green": 0.9, 
                                    "blue": 0.6
                                } 
                            }
                        }
                    },
                    "index": 1 # 두 번째 규칙
                }
            }
            requests_body["requests"].append(conditional_format_rule_pass)
            
            if requests_body["requests"]:
                 spreadsheet.batch_update(body=requests_body)
                 print("✅ 셀 서식 사전 설정 완료.")

        except Exception as e_format:
            print(f"❌ 셀 서식 설정 중 오류 발생: {e_format}")
            traceback.print_exc()

        # --- 3. 서식이 설정된 셀에 데이터 채워넣기 ---
        print("미리 서식이 설정된 셀에 데이터를 기록합니다...")
        rows_to_add = [list(row.values()) for row in results]
        worksheet.update(range_name=f'A{data_start_row_index + 1}', values=rows_to_add, value_input_option='RAW')

        print(f"✅ 테스트 결과가 '{SPREADSHEET_NAME}' 문서의 '{sheet_name}' 시트에 성공적으로 저장되었습니다.")
        print(f"   문서 링크: {spreadsheet.url}")

    except Exception as e:
        print(f"❌ Google Sheets 저장 중 예기치 않은 오류 발생: {e}")
        traceback.print_exc()

# 이미지를 Base64로 인코딩하는 헬퍼 함수
def get_image_b64(path):
    """이미지 파일 경로를 받아 Base64로 인코딩된 문자열을 반환합니다."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')
        
try:
    print("Appium 서버에 연결 중...")
    driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
    print("Appium 세션이 성공적으로 시작되었습니다.")

    # 테스트 시작 시간 기록 ---
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
    initial_element_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View'
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

    # -----------------------------------------------------------------------------
    # 카나나 APP 자동화 시나리오
    # -----------------------------------------------------------------------------

    print("----- 카나나 APP 자동화 시나리오 시작합니다. -----\n")

    case_num_counter = 1

    # --- case 1 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "카나나 앱 진입", "로그인/인트로", "-", "-", "-", "-", "-", "1. 최초 진입\n2.가입, 로그인", "카나나 앱 진입시 첫 페이지가 아래와 같이 노출되는가?\n====================\n- kanana\n- 우리를 잘 이해하는\n-최초의 그룹 AI\n - 앙몬드/카나/스카피 인사하며 움직이는 이미지 노출 (Figma : 가입 - 인트로01)\n - [카카오 로그인]\n - [카카오계정 직접 입력]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '''//android.widget.TextView[@text="우리를 잘 이해하는
최초의 그룹 AI"]''')))
        print("'우리를 잘 이해하는 최초의 그룹 AI' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카카오 로그인"]')))
        print("[카카오 로그인] 버튼 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카카오계정 직접 입력"]')))
        print("[카카오계정 직접 입력] 버튼 확인✅")
        print("1. 카나나 앱 진입시 첫 페이지가 아래와 같이 노출되는가? 'PASS'\n")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 2 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "카나나 앱 진입", "[카카오 로그인]\n(카카오톡 설치)", "카나나 앱 미가입자","-", "-", "-", "-", "1. 카카오톡 설치 상태 ", "카카오계정 로그인 페이지에서 미가입 카계정으로 메이트 서비스에 로그인 완료시 서비스 가입 동의창이 아래와 같이 노출 되는가?\n====================\n- 카나나 아이콘  카나나\n- kakao Corp.\n- [ⓥ 전체 동의하기]\n- 전체동의는 선택목적에 대한 동의를 포함하고 있으며, 선택목적에 대한 동의를 거부해도 서비스 이용이 가능합니다.\n- 동의 항목\n- v [필수] 카나나 서비스 이용 약관 [보기]\n- v [필수] 개인정보 수집 및 이용 동의문 [보기]\n- v [선택] 인공지능 모델 품질 향상을 위한 데이터 활용 동의 [보기]\n- v [선택] 광고 정보 수신 동의 [보기]\n- v [선택] 위치정보 수집 및 이용 동의 [보기]\n- v [선택] 카나나의 광고와 마케팅 메시지를 카카오톡으로 받습니다. (*톡유저 ID O 경우 노출)\n- [동의하고 계속하기]\n- [취소]\n*위치정보 수집 및 이용 동의 [보기] : 카계정 내 위치정보 미동의자의 경우, 가입 동의창에 선택항목항목으로 표시"
    try:
        kakao_login_button_xpath = '//android.widget.TextView[@text="카카오 로그인"]'
        button_kakao_login = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, kakao_login_button_xpath)))
        button_kakao_login.click()
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # [전체 동의하기]
    actions = ActionChains(driver)
    actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "all Consent"))
    actions.w3c_actions.pointer_action.move_to_location(159, 939)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.pause(0.1)
    actions.w3c_actions.pointer_action.release()
    actions.perform()

    # [동의하고 계속하기]
    actions = ActionChains(driver)
    actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "kanana Consent"))
    actions.w3c_actions.pointer_action.move_to_location(732, 2239)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.pause(0.1)
    actions.w3c_actions.pointer_action.release()
    actions.perform()    

    time.sleep(1)

    # --- case 3 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "내 프로필 설정", "-", "-","-", "-", "-", "-", "-", "내 프로필 설정 진입시 화면이 아래와 같이 구성되어 있는가?\n====================\n- [<]\n- 페이지 인디케이터\n- 프로필을 설정해주세요.\n- 프로필 사진 영역\n- 유저 닉네임 영역\n- 생년 월일 영역\n- [다음]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]')))
        print("[<] 버튼 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="프로필을 설정해주세요."]')))
        print("'프로필을 설정해주세요.'문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.ScrollView/android.widget.ImageView[3]')))
        print("프로필 사진 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.EditText[@text="B우즈8"]')))
        print("유저 닉네임 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="생년월일"]')))
        print("생년 월일 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="다음"]')))
        print("[다음] 버튼 확인✅")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 4 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "내 프로필 설정", "프로필 사진 설정 버튼", "[앨범에서 선택]","-", "-", "-", "-", "기획서> 2 > B >\na.내프로필", "사진 선택시 사진 편집기 화면으로 이동 되며, 선택 이미지로 설정 가능한가?"
    try:
         # --- 1. 액션 단계: 프로필 사진 변경 ---
        print("프로필 사진 변경을 시작합니다...")
        Profile_photo_button_xpath = '//android.widget.ScrollView/android.widget.ImageView[3]'
        button_Profile_photo = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Profile_photo_button_xpath)))
        button_Profile_photo.click()

        Profile_album_button_xpath = '//android.widget.TextView[@resource-id="android:id/text1" and @text="앨범에서 선택"]'
        button_Profile_album = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Profile_album_button_xpath)))
        button_Profile_album.click()

        Profile_choice_button_xpath = '//android.view.View[@content-desc="2025. 9. 2. 오후 4:55에 촬영한 사진"]'
        button_Profile_choice = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Profile_choice_button_xpath)))
        button_Profile_choice.click()
        
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]')))
        print("사진 편집 화면으로 이동했습니다.")
        
        Profile_completion_button_xpath = '//android.widget.TextView[@text="완료"]'
        button_Profile_completion = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Profile_completion_button_xpath)))
        button_Profile_completion.click()
        print("✅ 사진 변경 완료. 이제 검증을 시작합니다.")

        time.sleep(3)

        # --- 3. 검증 단계: 변경된 이미지 확인 ---
        try:
            # 중요: 변경된 프로필 사진 요소를 '다시' 찾습니다.
            print("검증을 위해 변경된 프로필 사진 영역을 다시 찾는 중...")
            verify_area_xpath = '//android.widget.ScrollView/android.widget.ImageView[3]'
            post_area = driver.find_element(by=AppiumBy.XPATH, value=verify_area_xpath)
            print("✅ 검증 영역을 찾았습니다.")

            # 해당 영역의 최신 위치와 크기를 가져옵니다.
            location = post_area.location
            size = post_area.size

            # 이미지 탐색 영역을 설정합니다.
            rect_settings = {"imageElementRect": {"left": location['x'], "top": location['y'], "width": size['width'], "height": size['height']}}
            driver.update_settings(rect_settings)
            print(f"탐색 영역을 x:{location['x']}, y:{location['y']}로 제한합니다.")

            # 지정된 영역 안에서 새 이미지를 찾습니다.
            expected_image_path = 'join membership_case4.jpg'
            image_b64 = get_image_b64(expected_image_path)
            print(f"'{expected_image_path}' 이미지를 찾는 중...")
            
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((AppiumBy.IMAGE, image_b64)))
            
            print("✅ 지정된 영역 내에서 변경된 이미지를 성공적으로 찾았습니다.")
            log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")

        finally:
            # 중요: 이미지 탐색 성공/실패 여부와 관계없이 항상 탐색 영역을 초기화합니다.
            driver.update_settings({"imageElementRect": dict()})
            print("이미지 탐색 영역 제한을 해제했습니다.")

    except Exception as e:
        print(f"❌ 테스트 케이스 실행 중 오류 발생: {e}")
        # 오류 발생 시에도 탐색 영역을 초기화해주는 것이 안전합니다.
        try:
            driver.update_settings({"imageElementRect": dict()})
        except Exception as e_finally:
            print(f"오류 복구 중 추가 오류 발생: {e_finally}")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 5 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "내 프로필 설정", "유저 닉네임 영역", "-","-", "-", "-", "-", "-", "유저 닉네임 영역이 아래와 같이 구성 되어 있으며,\n닉네임(한글)을 최소 1자, 최대 20자까지 입력 가능하며 글자수 카운트 되는가?\n====================\n- 닉네임 입력필드 (PH : 닉네임)\n- *프로필ㆍ대화방에 보일 닉네임이에요.    n/20"
    try:
        target_xpath = '//android.widget.EditText[@text="B우즈8"]'
        try:
            print(f"'{target_xpath}' 요소를 찾는 중...")
            
            # WebDriverWait를 사용해 요소가 클릭 가능할 때까지 기다립니다. (안정성 향상)
            edit_text_element = wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, target_xpath))
            )
            
            print("요소를 찾았습니다. 클릭을 시도합니다.")
            # 요소를 클릭하여 입력 필드를 활성화(포커스)합니다.
            edit_text_element.click()
            
            print("입력 필드의 텍스트를 삭제합니다.")
            # .clear() 메소드를 호출하여 텍스트를 모두 지웁니다.
            edit_text_element.clear()
            
            print("✅ 텍스트 삭제 완료!")

        except Exception as e:
            print(f"❌ 오류가 발생했습니다: {e}")
        
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="닉네임"]')))
        print("닉네임 입력필드 (Ph : 닉네임) 확인✅")

        nikname_input_field_xpath = '//android.widget.EditText' 
        nikname_text_to_input = "B우즈8"
        try:
            target_input_field = long_wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, nikname_input_field_xpath))
            )
            target_input_field.click()
            target_input_field.send_keys(nikname_text_to_input)
        except Exception as e_input:
            print(f"닉네임 입력 필드에 텍스트 입력 중 오류 발생: {e_input}")

        try:
            if driver.is_keyboard_shown():
                driver.hide_keyboard()
            else:
                print("키보드가 이미 닫혀 있습니다.")
        except Exception as e:
            print(f"❌ 키보드를 닫는 중 오류 발생: {e}")
        
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="* 프로필·대화방에 보일 닉네임이에요."]')))
        print("'* 프로필·대화방에 보일 닉네임이에요.' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="4/20"]')))
        print("'4/20' 글자 체크 확인✅")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 6 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "내 프로필 설정", "생년 월일 영역", "-","-", "-", "-", "-", "-", "생년월일 영역이 아래와 같이 구성 되어 있으며,\n생년월일을 최대 8자까지 숫자 입력 가능하며 글자수 카운트 되는가?\n====================\n- 생년월일 입력필드 (PH : 생년월일)\n- 생일을 알려주세요.    n/8"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="생년월일"]')))
        print("'생년월일 입력필드 (PH : 생년월일)' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="생일을 알려주세요."]')))
        print("'생일을 알려주세요.' 문구 확인✅")
        try:
            xpath_expression = "//android.widget.ScrollView/android.widget.EditText[2]"
            input_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xpath_expression))
            )
            input_field.send_keys("20010101")
            print("'생년월일' 입력 확인✅")
        except Exception as e:
            print(f"오류가 발생했습니다: {e}")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="8/8"]')))
        print("'8/8' 글자 체크 확인✅")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 7 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "내 프로필 설정", "[다음]", "-","-", "-", "-", "-", "1. 필수 정보 모두 입력\n2. 허용 문자열 입력(한글, 영어, 숫자, 이모지, 기호, 공백)", "[다음] 버튼 선택 시 카나나 ID 만들기 화면으로 이동 되는가?"
    try:
        Profile_next_button_xpath = '//android.widget.TextView[@text="다음"]'
        button_Profile_next = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Profile_next_button_xpath)))
        button_Profile_next.click()

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카나나 ID를 입력해주세요."]')))
        print("'카나나 ID 만들기 화면' 이동 확인✅")
        
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 8 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "카나나 ID 설정", "-", "-","-", "-", "-", "-", "-", "카나나 ID 설정 진입시 화면이 아래와 같이 구성되어 있는가?\n====================\n- [<]\n- 페이지 인디케이터\n- 카나나 ID를 입력해주세요.\n- 카나나 ID 영역\n- [다음]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]')))
        print("[<] 버튼 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카나나 ID를 입력해주세요."]')))
        print("'카나나 ID를 입력해주세요.' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.EditText')))
        print("카나나 ID 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button')))
        print("[다음] 버튼 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 9 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "카나나 ID 설정", "카나나 ID 닉네임 영역", "-","-", "-", "-", "-", "-", "- 유저 닉네임 영역이 아래와 같이 구성 되어 있는가?\n- 최대 20자까지 입력 가능하며 글자수 카운트 되는가\n====================\n- 카나나 ID 입력필드 (PH : 카나나 ID)\n- *ID로 사람들이 나를 찾을 수 있어요.   n/20"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카나나 ID"]')))
        print("카나나 ID 입력필드 (PH : 카나나 ID) 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="* ID로 사람들이 나를 찾을 수 있어요."]')))
        print("'*ID로 사람들이 나를 찾을 수 있어요.' 문구 확인✅")
        try:
            xpath_knanaid = "//android.widget.EditText"
            input_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xpath_knanaid))
            )
            ######################################
            input_field.send_keys("kanana_auto30")
            ######################################
            print("'카나나 ID' 입력 확인✅")
        except Exception as e:
            print(f"오류가 발생했습니다: {e}")

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="13/20"]')))
        print("'13/20' 글자 체크 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 10 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "카나나 ID 설정", "[다음]", "-","-", "-", "-", "-", "1. 입력 필드별 유효성 검증 성공\n2. 허용 문자열 입력(한글, 영어, 숫자, 마침표, 밑줄)", "[다음] 버튼 선택 시 당신의 메이트 설정 화면으로 이동 되는가?"
    try:
        kananaid_next_button_xpath = '//android.widget.Button'
        button_kananaid_next = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, kananaid_next_button_xpath)))
        button_kananaid_next.click()

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카나나에 오신걸 환영해요!"]')))
        print("메이트 설정 화면 이동 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 11 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "당신의 메트", "-", "-","-", "-", "-", "-", "-", "당신의 메이트 설정 진입시 화면이 아래와 같이 구성되어 있는가?\n====================\n- 카나나에 오신걸 환영해요!\n- 앞으로 함께할 메이트의 모습과 이름을 골라주세요.\n- 말풍선 : [닉네임]님, 안녕하세요. 늘 곁에서 도움이 될 당신만의 메이트예요.\n- 메이트 캐릭터 선택 영역\n- Ⓒ 카나나즈\n- 메이트 닉네임 영역\n- [다음]"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="카나나에 오신걸 환영해요!"]')))
        print("'카나나에 오신걸 환영해요!' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '''//android.widget.TextView[@text="앞으로 함께할 메이트의 모습과
이름을 골라주세요."]''')))
        print("'앞으로 함께할 메이트의 모습과 이름을 골라주세요.' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="늘 곁에서 도움이 될 당신만의 메이트예요."]')))
        print("'늘 곁에서 도움이 될 당신만의 메이트예요.' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.ScrollView/android.view.View/f1.r[1]/android.widget.ImageView')))
        print("메이트 캐릭터 선택 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="ⓒ 카나나즈"]')))
        print("'ⓒ 카나나즈' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.EditText[@text="나나"]')))
        print("메이트 닉네임 영역 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button')))
        print("[다음] 버튼 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 12 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "당신의 메트", "메이트 닉네임 영역", "-","-", "-", "-", "-", "-", "메이트 닉네임 영역이 아래와 같이 구성되어 있는가?\n닉네임(한글)을 최소 1자, 최대 10자까지 입력 가능하며 글자수 카운트 되는가?\n====================\n- 입력필드(디폴트 :나나)\n- 입력필드(디폴트 :나나)"
    try:
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.EditText[@text="나나"]')))
        print("입력필드(디폴트 :나나) 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="* 내 메이트 이름이예요."]')))
        print("'* 내 메이트 이름이예요.' 문구 확인✅")
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="2/10"]')))
        print("'2/10' 글자 체크 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # --- case 13 ---
    category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "회원가입", "당신의 메트", "[다음]", "-","-", "-", "-", "-", "1. 입력 필드별 유효성 검증 X", "[다음] 버튼 선택 시 세이프티 고지 화면으로 이동 되는가?"
    try:
        matesetting_next_button_xpath = '//android.widget.Button'
        button_matesetting_next = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, matesetting_next_button_xpath)))
        button_matesetting_next.click()

        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="당신의 소중한 데이터는 안전하게 보호됩니다."]')))
        print("세이프티 고지 화면 이동 확인✅")
            
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
    except Exception as e:
        log_test_result(driver, str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
    case_num_counter += 1

    # 카나나 시작하기 버튼 클릭
    kanana_start_button_xpath = '//android.widget.Button'
    button_kanana_start = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, kanana_start_button_xpath)))
    button_kanana_start.click()

    # 앱 권한 확인 버튼 클릭
    Allow_permission_button_xpath = '//android.widget.Button'
    button_Allow_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Allow_permission_button_xpath)))
    button_Allow_permission.click()

    # 위치 정보 엑세스 앱 사용 중에만 허용 버큰 클릭
    Allow_permission_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_foreground_only_button"]'
    button_Allow_permission = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, Allow_permission_button_xpath)))
    button_Allow_permission.click()

    # 앱 알림 허용 버튼 클릭
    permission_allow_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]'
    button_permission_allow = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_allow_button_xpath)))
    button_permission_allow.click()

    print("\n모든 테스트 시나리오 실행 완료.")

except Exception as e:
    print(f"\n### 스크립트 실행 중 예기치 않은 오류 발생 ###\n오류 메시지: {e}")
    
    # --- 치명적 오류 발생 시 로그 저장 ---
    base_filename = f"FATAL_ERROR_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_failure_details(driver, base_filename, exception_obj=e)
    
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

    # --- 4. PC에 결과 이미지 띄우기 ---
    print("\n--- PC에 테스트 결과 이미지 띄우기 시도 ---")
    if PIL_AVAILABLE:
        PASS_IMAGE_PATH = "/Users/jayden.coys/Autotest/Completed.png" # 예: 성공 이미지 파일 경로
        FAIL_IMAGE_PATH = "/Users/jayden.coys/Autotest/Fail.png" # 예: 실패 이미지 파일 경로
        
        image_path_to_show = None

        # (알림 로직에서 이미 계산했지만, 명확성을 위해 다시 확인)
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
                # 이미지 파일 열기
                img = Image.open(image_path_to_show)
                # 이미지 뷰어(기본 프로그램)로 이미지 띄우기
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