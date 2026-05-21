import streamlit as st
import json
import os
import requests
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import gspread

# 1. 환경 설정 및 데이터 파일 정의
HISTORY_FILE = "summary_history.json"
API_KEY_FILE = ".env"

def load_api_key():
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        return line.strip().split("=", 1)[1]
        except:
            return ""
    return ""

def save_api_key(api_key):
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={api_key}\n")

# --- Google Sheets 연결 함수 ---
def get_gspread_client():
    try:
        # Streamlit Cloud 배포 시 st.secrets 사용
        if "gcp_service_account" in st.secrets:
            return gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
        # 로컬 테스트 시 구글 인증 파일 사용
        elif os.path.exists("google_credentials.json"):
            return gspread.service_account(filename="google_credentials.json")
    except Exception:
        pass
    return None

def get_worksheet():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet_url = ""
        # Streamlit secrets에 스프레드시트 주소 저장
        if "GOOGLE_SHEET_URL" in st.secrets:
            sheet_url = st.secrets["GOOGLE_SHEET_URL"]
        
        if not sheet_url:
            return None
            
        doc = client.open_by_url(sheet_url)
        worksheet = doc.sheet1
        
        # 시트가 완전히 비어있다면 헤더(첫 줄) 생성
        if not worksheet.get_all_values():
            worksheet.append_row(["video_id", "title", "category", "summary", "url", "date"])
        return worksheet
    except Exception as e:
        # st.sidebar.error(f"구글 시트 연결 오류: {e}")
        return None
# -------------------------------

def load_history():
    ws = get_worksheet()
    if ws:
        try:
            return ws.get_all_records()
        except Exception:
            pass
            
    # 로컬 JSON Fallback (구글 시트 연동 전이거나 실패했을 때)
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_to_history(video_id, title, category, summary, url):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    ws = get_worksheet()
    if ws:
        try:
            records = ws.get_all_records()
            if not any(str(item.get('video_id', '')) == str(video_id) for item in records):
                ws.append_row([video_id, title, category, summary, url, date_str])
            return # 시트 저장 성공시 함수 종료
        except Exception:
            pass
            
    # 로컬 JSON Fallback
    history = load_history()
    if not any(item['video_id'] == video_id for item in history):
        new_record = {
            "video_id": video_id,
            "title": title,
            "category": category,
            "summary": summary,
            "url": url,
            "date": date_str
        }
        history.append(new_record)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

def update_category(video_id, new_category):
    ws = get_worksheet()
    if ws:
        try:
            records = ws.get_all_records()
            for idx, item in enumerate(records):
                if str(item.get('video_id', '')) == str(video_id):
                    # get_all_records()는 첫 줄(헤더)을 건너뛰므로 첫 데이터는 row=2가 됨. idx가 0부터 시작하므로 +2
                    row_index = idx + 2 
                    # 카테고리는 3번째 열(C열)
                    ws.update_cell(row_index, 3, new_category) 
                    break
            return
        except Exception:
            pass
            
    # 로컬 JSON Fallback
    history = load_history()
    for item in history:
        if item['video_id'] == video_id:
            item['category'] = new_category
            break
            
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def get_youtube_title(url):
    try:
        response = requests.get(f"https://noembed.com/embed?url={url}")
        return response.json().get("title", "제목 없음 유튜브 영상")
    except:
        return "유튜브 영상"

# 2. Streamlit UI 설정
st.set_page_config(page_title="유튜브 요약기", layout="wide")

st.title("📺 유튜브 영상 카테고리별 요약 시스템")
st.caption("Gemini AI를 활용하여 유튜브 자막을 추출하고 핵심 내용을 정리합니다.")

if 'api_key' not in st.session_state:
    st.session_state['api_key'] = load_api_key()
if 'view_record' not in st.session_state:
    st.session_state['view_record'] = None
if 'current_tab_state' not in st.session_state:
    st.session_state['current_tab_state'] = "🔗 유튜브 링크"

# 3. 사이드바 구현
st.sidebar.title("📁 요약 기록")

history_data = load_history()

if history_data:
    categories = sorted(list(set([item.get('category', '미분류') for item in history_data])))
    
    for category in categories:
        with st.sidebar.expander(f"📁 {category}", expanded=False):
            category_records = [item for item in history_data if item.get('category', '미분류') == category]
            for idx, record in enumerate(category_records):
                # 버튼 클릭 시 즉시 본문에 불러오기 (이후 자동 리런)
                if st.button(f"📄 {record['title']}", key=f"hist_{record['video_id']}_{idx}", use_container_width=True):
                    st.session_state['view_record'] = record
                    st.session_state['current_tab_state'] = "📄 본문 내용"
                    st.rerun()
else:
    st.sidebar.write("아직 저장된 요약 기록이 없습니다.")


# 4. 메인 화면 - 탭 시스템 (라디오 버튼으로 대체하여 프로그래밍 방식의 화면 전환 지원)
tabs = ["🔗 유튜브 링크", "📄 본문 내용", "⚙️ 설정"]

# Determine the initial index for the radio button based on st.session_state['current_tab_state']
try:
    initial_tab_index = tabs.index(st.session_state['current_tab_state'])
except ValueError:
    initial_tab_index = 0 # Default to the first tab if the state is somehow invalid

# Render st.radio without a key, and capture its return value.
# This return value reflects the user's current selection from the radio buttons.
user_selected_tab = st.radio("메뉴", tabs, horizontal=True, label_visibility="collapsed", index=initial_tab_index)


# If the user manually changed the tab via the radio buttons, update st.session_state['current_tab_state']
if user_selected_tab != st.session_state['current_tab_state']:
    st.session_state['current_tab_state'] = user_selected_tab
    st.rerun() # Rerun to ensure the correct tab content is displayed immediately

# Now, use st.session_state['current_tab_state'] to determine which content to display.
if st.session_state['current_tab_state'] == "⚙️ 설정":
    st.subheader("⚙️ API 및 시스템 설정")
    api_key_input = st.text_input("Gemini API Key를 입력하세요:", type="password", value=st.session_state['api_key'])
    if st.button("설정 저장"):
        if api_key_input:
            save_api_key(api_key_input)
            st.session_state['api_key'] = api_key_input
            st.success("🎉 API 키가 성공적으로 저장되었습니다! 이제 '유튜브 링크' 탭을 이용하실 수 있습니다.")
        else:
            st.warning("입력된 내용이 없습니다.")

elif st.session_state['current_tab_state'] == "🔗 유튜브 링크":
    st.subheader("🆕 새로운 영상 요약하기")

    if not st.session_state.get('api_key', ''):
        st.warning("⚠️ 요약을 시작하려면 먼저 상단의 **'⚙️ 설정' 탭**으로 이동하여 Gemini API Key를 입력하고 [설정 저장]을 눌러주세요.")
    else:
        url = st.text_input("유튜브 영상 링크(URL)를 입력하세요:")
        
        category_list = ["물리학", "AI & 에듀테크", "인문/교양", "뉴스/트렌드", "직접 입력"]
        selected_cat = st.selectbox("영상의 카테고리를 선택하세요:", category_list)
        
        if selected_cat == "직접 입력":
            custom_cat = st.text_input("새로운 카테고리명을 입력하세요:", placeholder="예: 취미, 요리 등")
            final_category = custom_cat if custom_cat else "기타"
        else:
            final_category = selected_cat

        if st.button("🚀 자막 추출 및 AI 요약 시작"):
            if not url:
                st.error("유튜브 링크를 입력해 주세요.")
            else:
                with st.spinner("유튜브 자막을 추출하고 Gemini가 핵심 내용을 정리하는 중입니다..."):
                    try:
                        if "v=" in url:
                            video_id = url.split("v=")[-1].split("&")[0]
                        else:
                            video_id = url.split("/")[-1]
                        
                        video_title = get_youtube_title(url)
                        
                        try:
                            api_instance = YouTubeTranscriptApi()
                            transcript_list = api_instance.list(video_id)
                            srt = transcript_list.find_transcript(['ko', 'en']).fetch()
                        except (AttributeError, Exception):
                            srt = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
                        
                        # 💡 [핵심 수정 부분] 어떤 형태의 데이터가 들어와도 에러 없이 텍스트를 추출하도록 보완
                        text_pieces = []
                        for t in srt:
                            if isinstance(t, dict):
                                text_pieces.append(t.get('text', ''))
                            elif hasattr(t, 'text'):
                                text_pieces.append(t.text)
                            else:
                                try:
                                    text_pieces.append(t['text'])
                                except:
                                    text_pieces.append(str(t))
                                    
                        full_text = " ".join(text_pieces)
                        
                        genai.configure(api_key=st.session_state['api_key'])
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        
                        prompt = f"""
                        당신은 유튜브 영상을 분석하여 핵심 정보를 일목요연하게 정리해주는 전문 요약가입니다.
                        제공된 유튜브 자막 텍스트를 바탕으로 다음 구조에 맞추어 깔끔하게 요약해 주세요.
                        중요: 영상 제목은 출력하지 마세요. 각 섹션의 제목 바로 다음 줄에 내용을 작성하고, 섹션이 끝날 때마다 반드시 줄바꿈(엔터)을 두 번 넣어서 구분되게 해주세요.
                        
                        1. 🌟 한 줄 요약
                        (여기에 한 줄 요약 내용 작성)
                        
                        2. 📌 핵심 키워드
                        (여기에 핵심 키워드 내용 작성)
                        
                        3. 📝 상세 내용 및 구조화
                        (여기에 상세 내용 작성)
                        
                        4. 💡 시사점 및 결론
                        (여기에 시사점 내용 작성)
                        
                        자막 텍스트:
                        {full_text}
                        """
                        
                        response = model.generate_content(prompt)
                        summary_result = response.text
                        
                        save_to_history(video_id, video_title, final_category, summary_result, url)
                        
                        # 방금 생성된 요약을 본문 탭에서 바로 볼 수 있도록 세션 업데이트
                        st.session_state['view_record'] = {
                            "video_id": video_id,
                            "title": video_title,
                            "category": final_category,
                            "summary": summary_result,
                            "url": url,
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state['current_tab_state'] = "📄 본문 내용"
                        
                        st.success("🎉 요약이 완료되었습니다! '📄 본문 내용' 탭에서 결과를 확인하세요.")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ 오류가 발생했습니다: {e}\n(자막이 없는 영상이거나, API 키가 올바르지 않을 수 있습니다.)")

elif st.session_state['current_tab_state'] == "📄 본문 내용":
    if st.session_state.get('view_record'):
        rec = st.session_state['view_record']
        
        # 노란색 메모지 스타일의 커스텀 CSS 주입
        st.markdown("""
        <style>
        /* 메모지 내부 텍스트 기본 설정 */
        .memo-pad {
            background-color: #fff9c4; /* 밝고 따뜻한 노란색 (포스트잇 느낌) */
            color: #212121; /* 가독성 높은 진한 흑회색 */
            padding: 2.5rem 2rem;
            border-radius: 4px;
            box-shadow: 3px 3px 15px rgba(0,0,0,0.1); /* 부드러운 그림자 */
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
            line-height: 1.8;
            font-size: 1.1rem;
            border-top: 15px solid #fbc02d; /* 상단에 진한 노란색 테이프 느낌 포인트 */
            margin-top: 1rem;
            margin-bottom: 2rem;
        }
        
        /* 메모지 내부의 제목 스타일링 */
        .memo-pad h3 {
            color: #d84315; /* 가독성 좋은 짙은 주황/붉은색 계열 */
            margin-top: 2rem;
            margin-bottom: 0.8rem;
            font-size: 1.4rem;
            font-weight: 800;
            border-bottom: 1px dashed #d84315; /* 점선 밑줄 추가 */
            padding-bottom: 0.3rem;
            display: inline-block;
        }
        
        /* 첫 번째 h3는 위쪽 여백 제거 */
        .memo-pad h3:first-child {
            margin-top: 0;
        }
        
        /* 메모지 내부의 볼드체(강조) 스타일링 */
        .memo-pad strong {
            color: #c62828; /* 짙은 빨간색으로 강조 (배경 박스 없음) */
            font-weight: 700;
        }
        
        /* 메모지 내부 리스트 간격 */
        .memo-pad li {
            margin-bottom: 0.5rem;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown(f"# 📄 {rec['title']}")
        
        # 메타 정보는 심플한 텍스트로 유지
        st.markdown(f"**📌 카테고리:** `{rec['category']}` &nbsp;&nbsp;|&nbsp;&nbsp; **📅 일시:** `{rec.get('date', '기록 없음')}` &nbsp;&nbsp;|&nbsp;&nbsp; **🔗 [영상 링크]({rec['url']})**")
        st.markdown("---") 
        
        # 줄바꿈 및 마크다운 처리가 명확하게 적용되도록 텍스트 후처리 (정규식 사용)
        import re
        formatted_summary = rec['summary']
        
        # 1번 섹션(한 줄 요약) 이전에 나오는 모든 내용(영상 제목, 빈 줄 등)을 날려버려서 상단 여백 제거
        # "[영상 제목]" 이나 "## [영상 제목]" 등 어떤 형태가 오든 '🌟 한 줄 요약' 앞까지 전부 삭제 (앞에 '1. ' 이 생략되어 있거나, ** 볼드체 기호가 여러 개 있어도 동작)
        formatted_summary = re.sub(r"^.*?(?:1\.\s*)?🌟\s*\**한\s*줄\s*요약\**\s*[:-]?\s*", "### 1. 🌟 한 줄 요약\n\n", formatted_summary, flags=re.DOTALL)
        
        # 나머지 섹션들도 콜론을 지우고 무조건 다음 줄로 넘김 (볼드체 별표가 여러 개 있어도 처리, 번호가 생략되어 있어도 처리)
        formatted_summary = re.sub(r"(?:2\.\s*)?📌\s*\**핵심\s*키워드\**\s*[:-]?\s*", "\n\n### 2. 📌 핵심 키워드\n\n", formatted_summary)
        formatted_summary = re.sub(r"(?:3\.\s*)?📝\s*\**상세\s*내용\s*및\s*구조화\**\s*[:-]?\s*", "\n\n### 3. 📝 상세 내용 및 구조화\n\n", formatted_summary)
        formatted_summary = re.sub(r"(?:4\.\s*)?💡\s*\**시사점\s*및\s*결론\**\s*[:-]?\s*", "\n\n### 4. 💡 시사점 및 결론\n\n", formatted_summary)
        
        # 앞뒤에 혹시 남아있을 수 있는 불필요한 공백/줄바꿈 최종 정리
        formatted_summary = formatted_summary.strip()
        
        # Streamlit의 markdown 함수 대신 HTML div 태그로 감싸서 확실하게 배경을 적용
        # (markdown 함수로 변환된 HTML을 div 안에 넣습니다)
        import markdown
        html_summary = markdown.markdown(formatted_summary)
        
        st.markdown(f'<div class="memo-pad">{html_summary}</div>', unsafe_allow_html=True)
        
        st.write("") # 여백
        
        # --- 카테고리 변경 UI 시작 ---
        st.markdown("### 🔄 카테고리 변경")
        cat_col1, cat_col2 = st.columns([3, 1])
        with cat_col1:
            category_list = ["물리학", "AI & 에듀테크", "인문/교양", "뉴스/트렌드", "직접 입력"]
            current_cat = rec['category']
            options = category_list.copy()
            if current_cat not in options and current_cat != "직접 입력":
                options.insert(0, current_cat)
                
            new_cat_selection = st.selectbox("새 카테고리 선택:", options, key=f"cat_select_{rec['video_id']}")
            if new_cat_selection == "직접 입력":
                new_cat_input = st.text_input("새로운 카테고리명:", key=f"cat_input_{rec['video_id']}")
                new_category = new_cat_input if new_cat_input else "기타"
            else:
                new_category = new_cat_selection
                
        with cat_col2:
            st.write("") # 수직 중앙 정렬용 여백
            st.write("")
            if st.button("변경 적용", use_container_width=True, key=f"cat_btn_{rec['video_id']}"):
                if new_category != current_cat:
                    update_category(rec['video_id'], new_category)
                    st.session_state['view_record']['category'] = new_category
                    st.success(f"카테고리가 '{new_category}'(으)로 변경되었습니다.")
                    st.rerun()
        # --- 카테고리 변경 UI 끝 ---
        
        st.write("") # 여백
        st.markdown("---")
        
        st.download_button(
            label="💾 텍스트 파일로 다운로드",
            data=rec['summary'],
            file_name=f"{rec['title']}_요약.txt",
            mime="text/plain",
            use_container_width=True
        )
    else:
        st.info("👈 왼쪽 사이드바에서 요약 기록을 선택하거나, '🔗 유튜브 링크' 탭에서 새로운 영상을 요약해 보세요.")