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
from appium.webdriver.extensions.android.nativekey import AndroidKey
from selenium.webdriver.common.actions.interaction import POINTER_TOUCH
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed # 병렬 실행을 위한 라이브러리

import getpass
import time
import traceback
import os
import sys

import gspread
from google.oauth2.service_account import Credentials
import requests

# --- Google Generative AI 라이브러리 추가 ---
import google.generativeai as genai

# --- Pillow 라이브러리 import ---
try:
    from PIL import Image
    PIL_AVAILABLE = True # 라이브러리가 있으면 플래그를 True로 설정
except ImportError:
    PIL_AVAILABLE = False # 라이브러리가 없으면 False로 설정
    print("⚠️ 'Pillow' 라이브러리가 설치되지 않았습니다. (pip install pillow)")
    print("   테스트 완료 후 PC에 결과 이미지를 띄우는 기능을 건너뜁니다.")

# -----------------------------------------------------------------------------
# 디바이스 설정 목록 및 공통 변수
# -----------------------------------------------------------------------------

# 테스트할 디바이스 목록 (포트와 deviceName은 반드시 고유해야 합니다!)
DEVICE_CONFIGS = [
    {
        "platformName": "Android",
        "appium:platformVersion": "15.0",
        "appium:deviceName": "R3CR10ZHBZP", # 첫 번째 기기 UDID
        "port": 4723, # 이 기기가 연결될 Appium 서버 포트
        "appium:appPackage": "net.daum.android.daum",
        "appium:appActivity": "net.daum.android.daum.DaumActivity",
        "label": "갤럭시S21울트라(15)" # 로그 구분을 위한 레이블
    },
    {
        "platformName": "Android",
        "appium:platformVersion": "13.0",
        "appium:deviceName": "R3CN30B7EPJ", # 두 번째 기기 UDID
        "port": 4725, # 이 기기가 연결될 Appium 서버 포트
        "appium:appPackage": "net.daum.android.daum",
        "appium:appActivity": "net.daum.android.daum.DaumActivity",
        "label": "갤럭시S20(13)" # 로그 구분을 위한 레이블
    }
]

# 공통 타임아웃 설정
initial_app_load_timeout = 20
element_interaction_timeout = 15
long_interaction_timeout = 30

# 로그 및 결과 파일 설정
LOG_ARTIFACTS_DIR = "test_issue"
if not os.path.exists(LOG_ARTIFACTS_DIR):
    os.makedirs(LOG_ARTIFACTS_DIR)
    print(f"'{LOG_ARTIFACTS_DIR}' 디렉토리를 생성했습니다.")

SPREADSHEET_NAME = "Appium Auto test Report"
APP_NAME = "Daum"
TESTER_NAME = getpass.getuser()
SCRIPT_NAME = os.path.basename(__file__)

# -----------------------------------------------------------------------------
# 헬퍼 함수 (모든 헬퍼 함수는 driver 객체를 인자로 받거나, test_results 리스트를 인자로 받도록 수정되어야 합니다.)
# -----------------------------------------------------------------------------

def get_device_model_name(driver):
    # ... (기존 코드와 동일)
    try:
        command = "getprop ro.product.model"
        model_name = driver.execute_script('mobile: shell', {'command': command})
        cleaned_model_name = model_name.strip()
        print(f"✅ 디바이스 모델명 확인 성공: {cleaned_model_name}")
        return cleaned_model_name
    except Exception as e:
        print(f"❌ adb shell 명령어로 모델명 가져오기 실패: {e}")
        return "N/A"

def get_app_version(driver, package_name):
    # ... (기존 코드와 동일)
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
    """
    [SDK 사용 버전] google-generative-ai 라이브러리를 사용하여 Gemini에게 분석 요청
    """
    # ⚠️ 여기에 본인의 API 키를 입력하세요.
    API_KEY = "AIzaSyB6GbtgJPG8APdyTQqey7R8lAVbWn4JQCs" 
    
    if not API_KEY or "YOUR_API_KEY" in API_KEY:
        print("⚠️ Gemini API 키가 설정되지 않았습니다.")
        return "API Key 누락"

    # 1. 라이브러리 설정
    genai.configure(api_key=API_KEY)

    try:
        # 2. 이미지 로드 (Pillow 사용)
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

        print("🤖 Gemini에게 분석 요청 중... (SDK 방식)")
        
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

# --- 실패 시 스크린샷과 로그 저장 (Gemini 연동 추가됨) ---
def log_failure_details(driver, base_filename, exception_obj=None):
    """실패 시점의 스크린샷과 '오류 트레이스백'을 파일로 저장하고 Gemini 분석을 요청합니다."""
    if not driver:
        print("Driver가 없어 스크린샷을 저장할 수 없습니다.")
    
    error_log_content = "N/A"

    try:
        # 1. 오류 트레이스백 가져오기
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

    try:
        # 2. 파일 경로 설정
        screenshot_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}.png")
        log_path = os.path.join(LOG_ARTIFACTS_DIR, f"{base_filename}_log.txt")

        # 3. 스크린샷 저장
        if driver:
            driver.save_screenshot(screenshot_path)
            print(f"📸 스크린샷 저장 완료: {screenshot_path}")
            screenshot_abspath = os.path.abspath(screenshot_path)
        else:
            screenshot_abspath = "Driver 없음"

        # 4. 로그 파일 작성
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"### 테스트 실패 로그 ###\n")
            f.write(f"발생 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"스크린샷: {screenshot_abspath}\n\n")
            f.write("--- 오류 트레이스백 ---\n")
            f.write(error_log_content)
        
        print(f"📄 실패 로그 파일 저장 완료: {log_path}")

        # [수정됨] 5. Gemini 분석 요청 호출
        if driver and os.path.exists(screenshot_path):
            print("\n🤖 Gemini에게 실패 원인 분석을 요청합니다...")
            analysis_result = analyze_failure_with_gemini(screenshot_path, error_log_content)
            
            # 분석 결과를 로그 파일 끝에 추가
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n\n--- Gemini AI 분석 결과 ---\n{analysis_result}")

    except Exception as e:
        print(f"❌ 실패 로그 저장 중 오류 발생: {e}")

def log_test_result(driver, test_results_list, device_label, number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, description, result, exception_obj=None):
    """테스트 결과를 기록하고, 실패 시 스크린샷과 오류 트레이스백을 파일로 저장합니다."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 실패 시 로그 파일 생성
    if result == "FAIL":
        # 파일 이름에 디바이스 레이블 추가하여 고유성 확보
        base_filename = f"FAIL_{device_label}_case_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        log_failure_details(driver, base_filename, exception_obj) 

    # 결과를 전달받은 리스트에 추가
    test_results_list.append({
        "디바이스": device_label, # 디바이스 레이블 추가
        "번호": number, "테스트 분류": category, "1depth": depth1, "2depth": depth2,
        "3depth": depth3, "4depth": depth4, "5depth": depth5, "6depth": depth6,
        "7depth": depth7, "Pre-Condition": Pre, "Expected Result": description,
        "Result": result, "실행 시간": timestamp
    })
    print(f"[{device_label}] LOG: [{result}] {description}")

def perform_swipe_action(driver_instance, start_x, start_y, end_x, end_y, duration_ms=300, touch_name="touch_swipe"):
    # ... (기존 코드와 동일)
    actions = ActionChains(driver_instance)
    finger = PointerInput(interaction.POINTER_TOUCH, touch_name)
    actions.w3c_actions = ActionBuilder(driver_instance, mouse=finger)
    actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.move_to_location(end_x, end_y)
    actions.w3c_actions.pointer_action.release()
    actions.perform()

def wait_for_walkthrough_page(device_label, page_description, expected_element_xpath, current_wait):
    """가이드 워크쓰루 페이지의 특정 요소가 나타날 때까지 대기합니다."""
    print(f"[{device_label}] 가이드 워크쓰루 '{page_description}' 로딩 대기 중...")
    try:
        current_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, expected_element_xpath)))
        print(f"[{device_label}] 가이드 워크쓰루 '{page_description}' 요소 확인 완료.")
        return True
    except TimeoutException:
        print(f"[{device_label}] 경고: '{page_description}'의 특정 요소({expected_element_xpath})를 시간 내에 찾지 못했습니다.")
        return False
    except Exception as e_walkthrough:
        print(f"[{device_label}] '{page_description}' 확인 중 예외 발생: {e_walkthrough}")
        return False
    
def write_results_to_gsheet(results, dev_name, device_model, plat_ver, app_pkg, app_ver, start_ts, end_ts, tester_name, script_name):
    """
    Google Sheets 저장 함수 (최종 수정)
    1. 정렬 수정: '테스트 디바이스'만 왼쪽 정렬, 나머지(시간, 건수 등)는 가운데 정렬
    2. 집계 로직: 총 시나리오 vs 총 수행 건수 분리
    3. 디자인: 헤더 동적 위치 감지, 기존 서식(색상, 테두리) 유지
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

    # 2. 데이터 가공 (Pivot)
    unique_devices = sorted(list(set(r["디바이스"] for r in results)))
    base_headers = ["번호", "테스트 분류", "1depth", "2depth", "3depth", "4depth", "5depth", "6depth", "7depth", "Pre-Condition", "Expected Result"]
    
    grouped_data = {}
    total_checks = 0 
    pass_count = 0
    fail_count = 0

    for row in results:
        case_num = str(row["번호"])
        if case_num not in grouped_data:
            grouped_data[case_num] = {k: row.get(k, "-") for k in base_headers}
            grouped_data[case_num]["results"] = {}
            grouped_data[case_num]["timestamps"] = []

        dev = row["디바이스"]
        res = row["Result"]
        grouped_data[case_num]["results"][dev] = res
        grouped_data[case_num]["timestamps"].append(row["실행 시간"])
        
        # 통계 집계
        total_checks += 1
        if res == "PASS": pass_count += 1
        elif res == "FAIL": fail_count += 1

    unique_scenarios = len(grouped_data)
    success_rate = (pass_count / total_checks * 100) if total_checks > 0 else 0.0
    success_rate_str = f"{success_rate:.2f}%"

    # 최종 데이터 리스트 생성
    final_headers = base_headers + unique_devices + ["실행 시간"]
    rows_to_add = []
    sorted_keys = sorted(grouped_data.keys(), key=lambda x: int(x) if x.isdigit() else 9999)

    for key in sorted_keys:
        data = grouped_data[key]
        row = [data[header] for header in base_headers]
        for dev in unique_devices:
            row.append(data["results"].get(dev, "N/A"))
        last_timestamp = max(data["timestamps"]) if data["timestamps"] else "N/A"
        row.append(last_timestamp)
        rows_to_add.append(row)

    
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
        
        # 시트 생성
        date_format = end_ts.strftime('%Y%m%d_%H%M') if isinstance(end_ts, datetime) else datetime.now().strftime('%Y%m%d_%H%M')
        sheet_name = f"{tester_name}_{end_time_str}"
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(rows_to_add) + 50, cols=len(final_headers) + 5)
        
        # --- 3. 요약 데이터 구성 ---
        summary_rows = [
            ["📋 통합 테스트 결과 리포트", ""],
            ["항목", "내용"],
            ["수행자", tester_name],
            ["앱 정보", f"{APP_NAME} (v{app_ver})"],
            ["테스트 디바이스", f"{len(unique_devices)}대 ({', '.join(unique_devices)})"],
            ["스크립트", script_name],
            ["시작 시간", start_time_str],
            ["종료 시간", end_time_str],
            ["소요 시간", duration_str],
            ["", ""],
            ["📊 결과 요약", ""],
            ["총 시나리오", f"{unique_scenarios} 개 (Case)"],
            ["총 수행 건수", f"{total_checks} 건 (Device x Case)"],
            ["성공 (PASS)", f"{pass_count} 건"],
            ["실패 (FAIL)", f"{fail_count} 건"],
            ["성공률", success_rate_str]
        ]
        
        # 헤더 위치 찾기
        section_header_index = -1
        for idx, row in enumerate(summary_rows):
            if "📊 결과 요약" in row[0]:
                section_header_index = idx
                break
        
        worksheet.update(range_name='A1', values=summary_rows, value_input_option='USER_ENTERED')
        
        # --- 4. 상세 결과 데이터 쓰기 ---
        detail_start_row = len(summary_rows) + 3
        worksheet.update(range_name=f'A{detail_start_row}', values=[final_headers])
        worksheet.update(range_name=f'A{detail_start_row + 1}', values=rows_to_add)

        # 데이터 범위 계산
        header_row_index = detail_start_row - 1
        data_start_index = detail_start_row
        data_end_index = detail_start_row + len(rows_to_add)

        # --- 5. 디자인 서식 적용 ---
        print("디자인 서식을 적용합니다...")
        
        try:
            depth4_idx = final_headers.index("4depth")
            expected_result_idx = final_headers.index("Expected Result")
            result_col_start = len(base_headers)
            result_col_end = result_col_start + len(unique_devices)
        except ValueError:
            depth4_idx, expected_result_idx = 5, 10
            result_col_start, result_col_end = 11, 12

        COLOR_HEADER_BG = {"red": 0.2, "green": 0.2, "blue": 0.2}
        COLOR_SUB_BG = {"red": 0.9, "green": 0.9, "blue": 0.9}
        COLOR_WHITE = {"red": 1, "green": 1, "blue": 1}
        COLOR_HEADER_GRAY = {"red": 0.95, "green": 0.95, "blue": 0.95}

        requests = []

        # 5-1. [기본] 데이터 영역 전체: 위쪽 맞춤 & 줄바꿈
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": 0, "endColumnIndex": len(final_headers) },
                "cell": { "userEnteredFormat": { "verticalAlignment": "TOP", "wrapStrategy": "WRAP" } },
                "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)"
            }
        })

        # 5-2. [헤더] 컬럼 인덱스 행: 가운데 정렬 + 굵게 + 배경색
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": header_row_index, "endRowIndex": header_row_index + 1, "startColumnIndex": 0, "endColumnIndex": len(final_headers) },
                "cell": { "userEnteredFormat": { "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "textFormat": {"bold": True}, "backgroundColor": COLOR_HEADER_GRAY } },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat,backgroundColor)"
            }
        })

        # 5-3. [너비] 조정
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": depth4_idx, "endIndex": depth4_idx + 1 }, "properties": {"pixelSize": 123}, "fields": "pixelSize" } })
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": expected_result_idx, "endIndex": expected_result_idx + 1 }, "properties": {"pixelSize": 482}, "fields": "pixelSize" } })
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1 }, "properties": {"pixelSize": 100}, "fields": "pixelSize" } })
        requests.append({ "updateDimensionProperties": { "range": { "sheetId": worksheet.id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2 }, "properties": {"pixelSize": 200}, "fields": "pixelSize" } })

        # 5-4. [결과 컬럼] 디바이스 결과(PASS/FAIL) 영역: 정중앙 맞춤
        requests.append({
            "repeatCell": {
                "range": { "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": result_col_start, "endColumnIndex": result_col_end },
                "cell": { "userEnteredFormat": { "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE" } },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })

        # 5-5. [색상] 결과 컬럼 조건부 서식
        for result_text, bg_color in [("FAIL", {"red": 0.9, "green": 0.6, "blue": 0.6}), ("PASS", {"red": 0.6, "green": 0.9, "blue": 0.6})]:
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{ "sheetId": worksheet.id, "startRowIndex": data_start_index, "endRowIndex": data_end_index, "startColumnIndex": result_col_start, "endColumnIndex": result_col_end }],
                        "booleanRule": { "condition": { "type": "TEXT_EQ", "values": [{"userEnteredValue": result_text}] }, "format": { "backgroundColor": bg_color } }
                    },
                    "index": 0
                }
            })

        # --- 요약표 디자인 ---
        worksheet.merge_cells('A1:B1')
        if section_header_index != -1:
            worksheet.merge_cells(f'A{section_header_index+1}:B{section_header_index+1}')
        
        summary_len = len(summary_rows)
        
        # 1. 항목명(A열): 회색 배경, 굵게, 가운데 정렬
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": summary_len, "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor": COLOR_SUB_BG, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })
        
        # 2. 값(B열): 기본은 가운데 정렬 (요청사항 반영)
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 1, "endRowIndex": summary_len, "startColumnIndex": 1, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })

        # 3. [수정됨] 특정 값(B열) 왼쪽 정렬 (테스트 디바이스만 왼쪽, 나머지는 다시 가운데로)
        # 기본적으로 B열은 위에서 '가운데 정렬'로 설정했으므로, 왼쪽으로 보낼 것만 지정하면 됩니다.
        left_align_targets = ["테스트 디바이스"] 
        
        for idx, row in enumerate(summary_rows):
            if row[0] in left_align_targets:
                requests.append({
                    "repeatCell": {
                        "range": {"sheetId": worksheet.id, "startRowIndex": idx, "endRowIndex": idx+1, "startColumnIndex": 1, "endColumnIndex": 2},
                        "cell": {"userEnteredFormat": {"horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE"}},
                        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
                    }
                })

        # 4. 타이틀 스타일
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"backgroundColor": COLOR_HEADER_BG, "horizontalAlignment": "CENTER", "textFormat": {"foregroundColor": COLOR_WHITE, "bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"
            }
        })
        if section_header_index != -1:
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": worksheet.id, "startRowIndex": section_header_index, "endRowIndex": section_header_index+1, "startColumnIndex": 0, "endColumnIndex": 2},
                    "cell": {"userEnteredFormat": {"backgroundColor": COLOR_HEADER_BG, "horizontalAlignment": "CENTER", "textFormat": {"foregroundColor": COLOR_WHITE, "bold": True}}},
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"
                }
            })
        
        # 5. 전체 테두리
        requests.append({
            "repeatCell": {
                "range": {"sheetId": worksheet.id, "startRowIndex": 0, "endRowIndex": summary_len, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"borders": {"top": {"style": "SOLID"}, "bottom": {"style": "SOLID"}, "left": {"style": "SOLID"}, "right": {"style": "SOLID"}}}},
                "fields": "userEnteredFormat(borders)"
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

def check_element_visibility(driver_wait, term_text, term_label):
        try:
            xpath = f'//android.widget.TextView[@text="{term_text}"]'
            driver_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, xpath)))
            # 로그에 디바이스 구분이 안될 수 있으나, 기능상 문제는 없습니다.
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

# -----------------------------------------------------------------------------
# 테스트 시퀀스 함수 (각 스레드에서 실행됨)
# -----------------------------------------------------------------------------

def run_daum_search_test(device_config):
    """
    하나의 디바이스 설정에 대한 전체 테스트 시퀀스를 실행하고 결과를 반환합니다.
    """
    
    # -----------------------------------------------------------------------------
    # 로컬 변수 및 설정 (전역 변수 대체)
    # -----------------------------------------------------------------------------
    driver = None
    test_results_list = [] # 이 스레드의 결과를 담을 로컬 리스트
    run_start_time = datetime.now()
    
    # 디바이스별 설정 추출
    device_label = device_config["label"]
    APPIUM_SERVER_URL = f"http://127.0.0.1:{device_config['port']}"
    
    options = AppiumOptions()
    options.load_capabilities({
        **{k: v for k, v in device_config.items() if k not in ['port', 'label']},
        "appium:automationName": "UiAutomator2",
        "appium:ensureWebviewsHavePages": True,
        "appium:newCommandTimeout": 3600,
        "appium:connectHardwareKeyboard": False,
        "appium:nativeWebScreenshot": True,
        "appium:noReset": False,
    })

    # 드라이버 환경 변수 초기화
    device_name = device_config["appium:deviceName"]
    platform_version = device_config["appium:platformVersion"]
    app_package_name = device_config["appium:appPackage"]
    device_model = "N/A"
    app_version = "N/A"
    
    case_num_counter = 1 # 테스트 케이스 번호 카운터

    # 헬퍼 함수 내에서 사용되는 상수 (함수 외부에서 정의되었지만, 이 함수 내에서도 필요)
    INPUT_FIELD_XPATH = '//android.widget.EditText'
    SEARCH_BUTTON_XPATH = '//android.widget.Button[@content-desc="검색"]'
    HOME_BUTTON_XPATH = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
    SIDE_MENU_BUTTON_XPATH = '//android.widget.Button[@content-desc="사이드 메뉴"]'
    MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH = '//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout/androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.view.View[1]/android.view.View/android.widget.Button[3]'

    # 로컬 헬퍼 함수 정의 (클로저를 통해 driver, wait, long_wait, test_results_list에 접근)
    
    def local_log(number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, desc, result, exception_obj=None):
        log_test_result(driver, test_results_list, device_label, number, category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, Pre, desc, result, exception_obj)
        
    def local_navigate_to_search_entry(long_wait, wait):
        print(f"[{device_label}] --- 공통 작업: 검색 엔트리 페이지로 이동 시작 ---")
        # 1. 홈으로 이동 버튼 클릭
        home_button_xpath = '//android.widget.ImageButton[@content-desc="홈으로 이동"]'
        home_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, home_button_xpath)))
        home_button.click()
        # 2. 홈 화면 로딩 확인
        side_menu_xpath = '//android.widget.Button[@content-desc="사이드 메뉴"]'
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, side_menu_xpath)))
        print(f"[{device_label}] 홈 화면으로 성공적으로 이동했습니다.")
        # 3. 메인 검색창 클릭하여 검색 엔트리 페이지로 진입
        search_entry_button_xpath = MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH
        search_entry_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, search_entry_button_xpath)))
        search_entry_button.click()
        print(f"[{device_label}] --- 공통 작업: 검색 엔트리 페이지로 이동 완료 ---\n")

    def local_perform_search_cycle(driver, short_wait, long_w, search_term, term_label_text):
        print(f"[{device_label}] {term_label_text} 검색어 진행: '{search_term}'")
        # (기존 perform_search_cycle 로직을 복사하여 넣으세요. 단, print 문에 device_label 추가)
        
        try:
            search_input_element = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, INPUT_FIELD_XPATH))
            )
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_term)
            print(f"[{device_label}] '{search_term}' 입력 완료.")

        except TimeoutException:
            print(f"[{device_label}] 오류: 메인 검색 입력 필드(XPath: {INPUT_FIELD_XPATH})를 시간 내에 찾거나 클릭할 수 없습니다.")
            raise 
        
        try:
            target_button_mainsearch_execute = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, SEARCH_BUTTON_XPATH))
            )
            target_button_mainsearch_execute.click()
            print(f"[{device_label}] 검색 버튼 클릭 완료.")
        except TimeoutException:
            print(f"[{device_label}] 오류: 검색 실행 버튼(XPath: {SEARCH_BUTTON_XPATH})을 시간 내에 클릭할 수 없습니다.")
            raise

        try:
            target_button_maintap_home_code = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, HOME_BUTTON_XPATH))
            )
            target_button_maintap_home_code.click()
            print(f"[{device_label}] 홈 버튼 클릭 완료.")

            short_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, SIDE_MENU_BUTTON_XPATH)))
            print(f"[{device_label}] 홈 화면으로 이동 확인.")
        except TimeoutException:
            print(f"[{device_label}] 오류: 홈으로 이동 버튼(XPath: {HOME_BUTTON_XPATH})을 클릭하거나 홈 화면 확인 중 시간 초과.")
            raise

        try:
            target_button_main_search_entry = long_w.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH))
            )
            target_button_main_search_entry.click()
            print(f"[{device_label}] 검색 엔트리 재진입")
        except TimeoutException:
            print(f"[{device_label}] 오류: 메인 페이지 검색 진입 버튼(XPath: {MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH})을 시간 내에 클릭할 수 없습니다.")
            raise

        print(f"[{device_label}] {term_label_text} 검색어 '{search_term}' 작업 완료 ✅\n")

    def local_scroll_down_on_search_screen(driver_instance):
        """검색 화면에서 아래로 스크롤합니다."""
        print(f"[{device_label}] 검색화면 스크롤 시작 📜")
        # (기존 scroll_down_on_search_screen 로직 복사)
        try:
            actions_search_lp = ActionChains(driver_instance)
            actions_search_lp.w3c_actions = ActionBuilder(driver_instance, mouse=PointerInput(POINTER_TOUCH, "search_touch_lp"))
            actions_search_lp.w3c_actions.pointer_action.move_to_location(483, 1638) # 시작 좌표
            actions_search_lp.w3c_actions.pointer_action.pointer_down()
            actions_search_lp.w3c_actions.pointer_action.move_to_location(479, 623)  # 종료 좌표
            actions_search_lp.w3c_actions.pointer_action.release()
            actions_search_lp.perform()
            print(f"[{device_label}] 스크롤 완료 👍")
        except Exception as e:
            print(f"[{device_label}] 스크롤 중 오류 발생: {e}")

    try:
        print(f"[{device_label}] Appium 서버 {APPIUM_SERVER_URL}에 연결 중...")
        driver = webdriver.Remote(APPIUM_SERVER_URL, options=options)
        print(f"[{device_label}] Appium 세션이 성공적으로 시작되었습니다.")

        # 환경 정보 조회
        device_model = get_device_model_name(driver)
        app_version = get_app_version(driver, app_package_name)

        # WebDriverWait 객체 초기화
        wait = WebDriverWait(driver, element_interaction_timeout)
        long_wait = WebDriverWait(driver, long_interaction_timeout)

        # --- 1. 앱 로딩 및 초기 화면 요소 확인 중 ---
        print(f"[{device_label}] \n--- 앱 로딩 및 초기 화면 요소 확인 중 ---")
        initial_element_xpath = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View'
        try:
            WebDriverWait(driver, initial_app_load_timeout).until(
                EC.presence_of_element_located((AppiumBy.XPATH, initial_element_xpath))
            )
            print(f"[{device_label}] 앱 초기 화면 요소가 확인되었습니다.")
        except TimeoutException:
            print(f"[{device_label}] 경고: 지정된 초기 화면 요소를 {initial_app_load_timeout}초 내에 찾지 못했습니다.")
            time.sleep(5)

        # --- 2. 가이드 워크쓰루 ---
        print(f"[{device_label}] \n--- 가이드 워크쓰루 진행 ---")
        walkthrough_pages = [
            {"swipe_coords": (958, 1065, 213, 1069), "wait_element_xpath": '//android.widget.TextView[@text="홈 탭"]', "description": "홈 탭 안내"},
            {"swipe_coords": (958, 1126, 213, 1139), "wait_element_xpath": '//android.widget.TextView[@text="콘텐츠 탭"]', "description": "콘텐츠 탭 안내"},
            {"swipe_coords": (946, 1171, 262, 1151), "wait_element_xpath": '//android.widget.TextView[@text="커뮤니티 탭"]', "description": "커뮤니티 탭 안내"},
            {"swipe_coords": (975, 1040, 188, 1032), "wait_element_xpath": '//android.widget.TextView[@text="쇼핑 탭"]', "description": "쇼핑 탭 안내"},
            {"swipe_coords": (958, 1126, 213, 1139), "wait_element_xpath": '//android.widget.TextView[@text="루프 탭"]', "description": "루프 탭 안내"},
        ]
        for i, page_info in enumerate(walkthrough_pages):
            print(f"[{device_label}] 가이드 워크쓰루 스와이프 {i+1} ({page_info['description']}) 시작 중...")
            perform_swipe_action(driver, *page_info["swipe_coords"])
            if not wait_for_walkthrough_page(device_label, page_info["description"], page_info["wait_element_xpath"], wait):
                print(f"[{device_label}] 경고: {page_info['description']} 확인 실패. 다음 단계로 진행합니다.")
            print(f"[{device_label}] {page_info['description']}으로 이동 완료.")

        print(f"[{device_label}] 마지막 스와이프 (접근 권한 안내) 시작 중...")
        perform_swipe_action(driver, 958, 1126, 213, 1139, touch_name="touch_gw_final")
        if not wait_for_walkthrough_page(device_label, "접근 권한 안내", '//android.widget.TextView[@text="접근 권한 안내"]', wait):
            print(f"[{device_label}] 오류: 접근 권한 안내 페이지로 이동 실패!")
            # 오류 발생 시 해당 기기 테스트를 여기서 FAIL 처리하고 계속 진행
            local_log(str(case_num_counter) + "-0", "초기 설정", "워크쓰루", "-", "-", "-", "-", "-", "접근 권한 안내 페이지 로드 실패", "PASS", "FAIL", Exception("접근 권한 안내 페이지 로드 실패"))
            # 치명적 오류로 간주하고 다음 단계로 이동

        # --- 3. '다음 시작하기' 버튼 클릭 ---
        print(f"[{device_label}] \n--- '다음 시작하기' 버튼 클릭 시도 ---")
        daum_start_button_xpath = '//android.widget.Button'
        try:
            daum_start_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, daum_start_button_xpath)))
            daum_start_button.click()
            print(f"[{device_label}] '다음 시작하기' 버튼 클릭 성공.")
        except TimeoutException:
                print(f"[{device_label}] 오류: '다음 시작하기' 버튼을 시간 내에 찾거나 클릭할 수 없습니다.")
                raise # 테스트 실패 처리

        # --- 4. 코치 마크 해제 ---
        print(f"[{device_label}] \n--- 코치 마크 해제 시도 ---")
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
            print(f"[{device_label}] 코치 마크 해제 (좌표 기반 탭) 완료.")
        except Exception as e_coach_mark:
            print(f"[{device_label}] 코치 마크 해제 중 오류 발생 (무시하고 진행): {e_coach_mark}")
        time.sleep(1)

        # --- 5. 알림 권한 '허용' 버튼 클릭 ---
        print(f"[{device_label}] \n--- 알림 권한 '허용' 버튼 클릭 시도 ---")
        permission_allow_button_xpath = '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]'
        try:
            permission_allow_button = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, permission_allow_button_xpath)))
            permission_allow_button.click()
            print(f"[{device_label}] '허용' 버튼 클릭 성공 (알림 권한).\n")
        except TimeoutException:
            print(f"[{device_label}] 경고: 알림 권한 '허용' 버튼을 시간 내에 찾지 못했습니다. 계속합니다.")

        # -----------------------------------------------------------------------------
        # 다음APP 자동화 시나리오 (기존 로직 복사 및 local_log 적용)
        # -----------------------------------------------------------------------------

        print(f"[{device_label}] ----- 다음APP(Search) 자동화 시나리오 시작합니다. -----\n")

        # --- case 1 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "-", "-", "-", "-", "-", "-", "-", "-", "검색창 탭 시 엔트리 페이지가 정상적으로 노출되는가?\n====================\n- [ < '검색어 또는 URL 입력'  '돋보기' ]\n- 최근검색어 리스트\n-- [최근 검색어 끄기/켜기] [전체삭제] [닫기]\n - 투데이 버블 beta (I)\n[새로고침] [키워드버블1]  [키워드버블2]\n [키워드버블3] [키워드버블4]\n[키워드버블5]"
        try:
            main_search_button_xpath = MAIN_PAGE_SEARCH_ENTRY_BUTTON_XPATH
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, main_search_button_xpath))).click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="검색어 또는 URL 입력"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.Button[@content-desc="최근 검색어 끄기"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="투데이 버블"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1

        # --- case 2 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "-", "-", "-", "-", "-", "-", "-", "입력필드 선택시 키패드가 활성화되어 입력가능한가?\n====================\n- [ < '검색어 또는 URL 입력'  '돋보기' ]\nPlace holder: '검색어 또는 URL 입력' [돋보기]"
        try:
            if driver.is_keyboard_shown():
                print(f"[{device_label}] 키패드가 정상적으로 활성화되었습니다. ✅")
            else:
                print(f"[{device_label}] 경고: 키패드가 활성화되지 않았습니다. ❌")
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
            
        # --- case 3 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "텍스트/숫자", "-", "-", "-", "-", "-", "텍스트 입력시 해당 텍스트와 일치하는 서제스트가 노출되는가?\n====================\n*일치하는 서제스트가 없는경우 미노출\n*키워드 하이라이트 (일치하는 항목 볼드)"
        try:
            input_field_xpath = INPUT_FIELD_XPATH
            search_text_to_input = "은하철도 999"
            search_input_element = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath)))
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_text_to_input)
            time.sleep(1)
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999 메텔"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999 철이"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # --- case 4 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "텍스트/숫자", "돋보기] 키패드 [검색]", "-", "-", "-", "-", "해당 검색결과가 노출되는 인앱브라우저가 오픈되는가?"
        try:
            button_xpath_mainsearch_inputOk = SEARCH_BUTTON_XPATH
            target_button_mainsearch_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_mainsearch_inputOk)))
            target_button_mainsearch_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.search.daum.net, 주소입력창, 버튼"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)
        
        # --- case 5 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "URL", "-", "-", "-", "-", "-", "http://, https://를 포함한 URL 입력시 해당 텍스트와 일치하는 서제스트가 노출되는가?\n====================\n*일치하는 서제스트가 없는경우 미노출\n*키워드 하이라이트 (일치하는 항목 볼드)"
        try:
            input_field_xpath = INPUT_FIELD_XPATH
            search_text_to_input = "http://www.naver.com"
            search_input_element = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath)))
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_text_to_input)
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.view.View[@content-desc="바로가기, 버튼, http://www.naver.com"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # --- case 6 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "URL", "[돋보기] 키패드 [검색]", "-", "-", "-", "-", "해당 검색결과가 노출되는 인앱브라우저가 오픈되는가?"
        try:
            button_xpath_mainsearch_inputOk = SEARCH_BUTTON_XPATH
            target_button_mainsearch_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_mainsearch_inputOk)))
            target_button_mainsearch_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.naver.com, 주소입력창, 버튼"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)
        
        # --- case 7 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "텍스트", "리스트 선택", "-", "-", "-", "리스트 선택 시 해당 검색결과로 이동되는가?"
        try:
            input_field_xpath = INPUT_FIELD_XPATH
            search_text_to_input = "손흥민"
            search_input_element = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath)))
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_text_to_input)
            time.sleep(1)
            button_xpath_Surgest_inputOk = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View/android.widget.Button'
            target_button_Surgest_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest_inputOk)))
            target_button_Surgest_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="손흥민 - Daum 검색"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)
        
        # --- case 8 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "URL", "리스트 선택", "-", "-", "-", "리스트 선택 시 해당 검색결과로 이동되는가?"
        try:
            input_field_xpath = INPUT_FIELD_XPATH
            search_text_to_input = "www.naver.com"
            search_input_element = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath)))
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_text_to_input)
            button_xpath_Surgest2_inputOk = '//android.view.View[@content-desc="바로가기, 버튼, http://www.naver.com"]'
            target_button_Surgest2_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest2_inputOk)))
            target_button_Surgest2_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.naver.com, 주소입력창, 버튼"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)

        # --- case 9 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "입력필드", "검색어 입력", "서제스트", "비주얼 서제스트", "방송, 드라마", "-", "-", "-", "방송, 드라마 타이틀을 검색한경우, 원형 썸네일이 포함된 서제스트가\n노출되고, 선택시 해당 검색결과로 이동되는가?"
        try:
            input_field_xpath = INPUT_FIELD_XPATH
            search_text_to_input = "무한도전"
            search_input_element = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, input_field_xpath)))
            search_input_element.click()
            search_input_element.clear()
            search_input_element.send_keys(search_text_to_input)
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View/android.view.View')))
            button_xpath_Surgest3_inputOk = '//android.widget.TextView[@text="무한도전"]'
            target_button_Surgest3_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Surgest3_inputOk)))
            target_button_Surgest3_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="무한도전 - Daum 검색"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)

        # --- case 10 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "-", "-", "-", "-", "-", "-", "최근 검색어 내역이 있는 경우 리스트가 정상적으로 노출되는가?\n====================\n- 최근검색어 리스트\n최근 검색어 목록 / 해당 검색어로 검색한 날짜 / [x]\n- 최근검색 기능 툴\n[최근검색어 끄기/켜기]               [닫기]\n- 투데이 버블 Beta                          [i]\n[새로고침] [키워드버블1]  [키워드버블2]\n[키워드버블3] [키워드버블4]\n[키워드버블5]"
        try:
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="무한도전"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="손흥민"]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="은하철도 999"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
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
            for search_term, term_label in search_tasks:
                time.sleep(1)
                local_perform_search_cycle(driver, wait, long_wait, search_term, term_label)

            if driver.is_keyboard_shown(): driver.hide_keyboard()
            
            # 검색 이력 확인 및 스크롤
            # (check_element_visibility, check_element_invisibility는 외부 정의 함수를 그대로 사용)
            local_scroll_down_on_search_screen(driver)
            check_element_invisibility(wait, "은하철도 999", "1번째") # 삭제되었는지 확인

            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        time.sleep(1)

        # --- case 12 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "히스토리 스토리", "리스트 선택", "-", "-", "-", "-", "리스트 선택시 해당 검색결과로 이동되는가?"
        try:
            button_xpath_Search_historyOk = '//android.widget.TextView[@text="손흥민"]'
            target_button_Searchhis_execute = long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Search_historyOk)))
            target_button_Searchhis_execute.click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.webkit.WebView[@text="손흥민 - Daum 검색"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인 홈 이동 후 검색 엔트리 진입
        local_navigate_to_search_entry(long_wait, wait)
        time.sleep(1)
        
        # --- case 13 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "키패드 상위 툴바", "[최근 검색어 끄기]", "-", "-", "-", "-", "키패드 상위에 존재하는 [최근 검색어 끄기] 버튼 선택시 설정확인 얼럿이\n 노출되고, [확인]시 적용되는가?\n====================\n'최근 검색어 끄기'\n'최근검색어 사용을 중지 하시겠습니까?'\n[취소] [확인]"
        try:
            button_xpath_Recent_searches_off = '//android.widget.Button[@content-desc="최근 검색어 끄기"]'
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_off))).click()
            time.sleep(1)
            button_xpath_Recent_searches_offOK = '//android.widget.Button[@resource-id="android:id/button1"]'
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_offOK))).click()
            time.sleep(1)
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="최근 검색어 기능이 꺼져 있습니다."]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 최근 검색어 켜기 (다음 케이스를 위해)
        button_xpath_Recent_searches_on = '//android.widget.Button[@content-desc="최근 검색어 켜기"]'
        long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_searches_on))).click()
        time.sleep(1)

        # --- case 14 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "최근 검색어\n히스토리", "최근 검색어 있음", "히스토리 리스트", "리스트 삭제", "전체 삭제", "-", "-", "-", "전체 삭제시 영역 내 안내문구가 노출되는가?\n'최근 검색어가 없습니다.'"
        try:
            button_xpath_Recent_delete_all = '//android.widget.Button[@content-desc="전체삭제"]'
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_delete_all))).click()
            button_xpath_Recent_delete_allOk = '//android.widget.Button[@resource-id="android:id/button1"]'
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_Recent_delete_allOk))).click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="최근 검색어가 없습니다."]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # --- case 15 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "-", "-", "-", "-", "-", "-", "-", "투데이 버블 영역이 아래와 같이 노출되는가?\n====================\n- 투데이 버블 beta (I)\n[키워드버블1] [키워드버블2]\n[키워드버블3] [키워드버블4]\n[키워드버블5]"
        try:
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="투데이 버블"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e)
        case_num_counter += 1
        
        # --- case 16 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "키워드 리스트", "-", "-", "-", "-", "-", "-", "새로고침 버튼과 랜덤한 5개의 키워드 리스트가 정상적으로 노출되는가?\n====================\n가로사이즈에 맞춰 최대 3줄 노출\n2x3 또는 3x2"
        try:
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[3]/android.view.View/android.widget.Button')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[4]')))
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[8]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # --- case 17 ---
        category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc = "엔트리 페이지", "투데이 버블", "키워드 리스트", "키워드 상세", "키워드 상세", "-", "-", "-", "-", "해당 키워드 검색결과 페이지로 이동되는가?"
        try:
            button_xpath_bublle_click = '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View[1]/android.view.View[4]'
            long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_bublle_click))).click()
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.LinearLayout[@content-desc="m.search.daum.net, 주소입력창, 버튼"]')))
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "PASS")
        except Exception as e:
            local_log(str(case_num_counter), category, depth1, depth2, depth3, depth4, depth5, depth6, depth7, pre, desc, "FAIL", exception_obj=e) 
        case_num_counter += 1
        
        # 메인으로 이동
        button_xpath_maintap_home_code = HOME_BUTTON_XPATH
        long_wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, button_xpath_maintap_home_code))).click()
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, SIDE_MENU_BUTTON_XPATH)))

        print(f"[{device_label}] \n모든 테스트 시나리오 실행 완료.")

    except Exception as e:
        print(f"[{device_label}] \n### 스크립트 실행 중 치명적인 오류 발생 ###\n오류 메시지: {e}")
        # 치명적 오류 발생 시 로그 저장
        base_filename = f"FATAL_ERROR_{device_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        log_failure_details(driver, base_filename, exception_obj=e)
        traceback.print_exc(file=sys.stdout) # 콘솔에도 출력
        # test_results_list가 비어있다면 오류 케이스를 하나 추가
        if not test_results_list:
             test_results_list.append({
                "디바이스": device_label, "번호": "FATAL", "테스트 분류": "시스템", "1depth": "초기화", "2depth": "-",
                "3depth": "-", "4depth": "-", "5depth": "-", "6depth": "-",
                "7depth": "-", "Pre-Condition": "Appium 연결 및 초기 설정", "Expected Result": "스크립트 정상 실행",
                "Result": "FAIL", "실행 시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    finally:
        run_end_time = datetime.now()
        if driver:
            print(f"[{device_label}] Appium 세션을 종료합니다.")
            driver.quit()
        
        # 최종 결과 딕셔너리 반환
        return {
            "test_results": test_results_list,
            "device_name": device_name,
            "device_model": device_model,
            "platform_version": platform_version,
            "app_package_name": app_package_name,
            "app_version": app_version,
            "run_start_time": run_start_time,
            "run_end_time": run_end_time
        }

# -----------------------------------------------------------------------------
# 메인 실행 함수
# -----------------------------------------------------------------------------

def main_parallel_run():
    all_test_results_data = [] # 모든 스레드의 결과를 담을 컨테이너
    
    MAX_WORKERS = len(DEVICE_CONFIGS) 
    
    print(f"\n=======================================================")
    print(f"🖥️  {MAX_WORKERS}개 디바이스에서 병렬 테스트 시작...")
    print(f"=======================================================")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 각 디바이스 설정에 대해 run_daum_search_test 함수를 비동기적으로 실행합니다.
        future_to_device = {executor.submit(run_daum_search_test, config): config for config in DEVICE_CONFIGS}
        
        for future in as_completed(future_to_device):
            device_config = future_to_device[future]
            device_id = device_config["appium:deviceName"]
            
            try:
                # 결과(딕셔너리)를 받습니다.
                result_data = future.result()
                all_test_results_data.append(result_data)
                print(f"✅ [{device_id}] 테스트 완료, 결과 수집 성공.")
                
            except Exception as e:
                print(f"❌ [{device_id}] 테스트 실행 중 스레드 레벨에서 치명적인 예외 발생: {e}")
                
    
    # --- 최종 결과 취합 및 리포팅 ---
    
    final_test_results = []
    
    # 시작/종료 시간 취합
    if all_test_results_data:
        # 모든 기기의 결과 리스트를 하나로 합치기
        for result_data in all_test_results_data:
            final_test_results.extend(result_data["test_results"])
        
        # 전체 테스트 시작 시간은 가장 빠른 시작 시간
        global_run_start_time = min(r["run_start_time"] for r in all_test_results_data if r.get("run_start_time"))
        # 전체 테스트 종료 시간은 가장 늦은 종료 시간
        global_run_end_time = max(r["run_end_time"] for r in all_test_results_data if r.get("run_end_time"))
    else:
        global_run_start_time = datetime.now()
        global_run_end_time = datetime.now()
        
    print(f"\n=======================================================")
    print(f"🎉 모든 병렬 테스트 실행 완료. 최종 결과 리포팅 시작...")
    print(f"총 케이스 수: {len(final_test_results)}")
    print(f"=======================================================")

    # Google Sheets 저장
    if final_test_results:
        # NOTE: write_results_to_gsheet은 하나의 환경 정보만 받으므로, 첫 번째 기기의 정보를 대표로 사용합니다.
        first_result = all_test_results_data[0] if all_test_results_data else {"device_name": "N/A", "device_model": "Parallel Run", "platform_version": "N/A", "app_package_name": "N/A", "app_version": "N/A"}
        write_results_to_gsheet(
            final_test_results, first_result["device_name"], first_result["device_model"], 
            first_result["platform_version"], first_result["app_package_name"], first_result["app_version"], 
            global_run_start_time, global_run_end_time, TESTER_NAME, SCRIPT_NAME
        )
    
    # --- 휴대폰 알림 전송 로직 ---
    print("\n--- 휴대폰으로 테스트 완료 알림 전송 시도 ---")
    try:
        # 테스트 결과 요약 (전체 결과 기반)
        total_cases = len(final_test_results)
        fail_cases = sum(1 for r in final_test_results if r.get("Result") == "FAIL")
        pass_cases = total_cases - fail_cases
        
        if fail_cases > 0:
            notification_title = f"❌ Appium 병렬 테스트 실패 (실패: {fail_cases}건)"
            notification_priority = "high"
        elif total_cases > 0:
            notification_title = f"✅ Appium 병렬 테스트 성공 (성공: {pass_cases}건)"
            notification_priority = "default"
        else:
            notification_title = "⚠️ Appium 테스트 결과 없음"
            notification_priority = "low"

        duration = global_run_end_time - global_run_start_time
        duration_str = str(timedelta(seconds=round(duration.total_seconds())))

        message_body = (
            f"앱: {APP_NAME} (총 {MAX_WORKERS}대)\n"
            f"결과: 성공 {pass_cases} / 실패 {fail_cases}\n"
            f"총 소요시간: {duration_str}\n"
            f"수행자: {TESTER_NAME}"
        )
        
        requests.post(
            "https://ntfy.sh/daumapp_autotest",
            data=message_body.encode(encoding='utf-8'),
            headers={
                "Title": notification_title.encode('utf-8'),
                "Priority": notification_priority,
                "Tags": "tada,white_check_mark" if fail_cases == 0 else "rotating_light,x"
            }
        )
        print(f"✅ ntfy.sh 알림 전송 완료")

    except Exception as e_notify:
        print(f"❌ ntfy.sh 알림 전송 중 오류 발생: {e_notify}")

    print("\n스크립트 실행 종료.")


if __name__ == '__main__':
    main_parallel_run()