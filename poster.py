import streamlit as st
import google.generativeai as genai
import requests
from openai import OpenAI
from rembg import remove
from PIL import Image
import io
import json
import base64
import re

# -----------------------------
# 1. 기본 설정 및 스타일링
# -----------------------------
st.set_page_config(page_title="Hybrid Game Toolkit", page_icon="⚔️", layout="wide")

st.markdown("""
<style>
    .game-card {
        background-color: #2b313e;
        border: 2px solid #4a4e69;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        color: white;
        margin-bottom: 20px;
    }
    .card-title {
        font-size: 1.5em;
        font-weight: bold;
        color: #ffd700;
        border-bottom: 1px solid #555;
        padding-bottom: 10px;
        margin-bottom: 10px;
    }
    .stat-box {
        background-color: #1e212b;
        padding: 5px 10px;
        border-radius: 5px;
        margin: 2px;
        display: inline-block;
        font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------
# 2. 유틸리티 함수 (공통)
# -----------------------------
def clean_json_text(text):
    """JSON 청소 함수"""
    try:
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()
        return json.loads(text)
    except:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except:
            return None


def remove_background_advanced(image):
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()
    output_data = remove(
        img_bytes,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10
    )
    return Image.open(io.BytesIO(output_data)).convert("RGBA")


def resize_image(image, size=512):
    return image.resize((size, size), Image.LANCZOS)


# -----------------------------
# 3. OpenAI 로직 (DALL-E & GPT)
# -----------------------------
def run_openai_text(api_key, prompt):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a game data generator. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"OpenAI 텍스트 오류: {e}")
        return {}


def run_dalle_image(api_key, prompt):
    try:
        client = OpenAI(api_key=api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
            response_format="b64_json"
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        return Image.open(io.BytesIO(image_data))
    except Exception as e:
        st.error(f"DALL-E 생성 오류: {e}")
        return None


# -----------------------------
# 4. Google 로직 (Gemini & Imagen) - 수정됨
# -----------------------------
def run_gemini_text(api_key, prompt):
    """
    여러 모델을 순차적으로 시도하여 404 오류를 방지하는 로직
    """
    genai.configure(api_key=api_key)

    # 시도할 모델 리스트 (우선순위 순)
    # 2.0이 안 되면 1.5로 자동 전환됩니다.
    candidate_models = [
        "gemini-2.0-flash",  # 최신 정식
        "gemini-2.0-flash-exp",  # 최신 실험
        "gemini-1.5-flash",  # 안정화 버전 (가장 확실함)
        "gemini-1.5-pro"  # 고성능 버전
    ]

    last_error = ""

    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            result = clean_json_text(response.text)
            if result:
                return result  # 성공하면 즉시 반환
        except Exception as e:
            # 실패하면 에러 저장하고 다음 모델로 넘어감
            last_error = str(e)
            continue

    st.error(f"모든 Gemini 모델 실패: {last_error}")
    return {}


def run_imagen_image(api_key, prompt):
    """
    Imagen 4.0 시도 후 실패 시 3.0으로 자동 전환
    """
    # 시도할 모델 리스트
    image_models = [
        "imagen-4.0-generate-001",
        "imagen-3.0-generate-001",
        "imagen-4.0-fast-generate-001"
    ]

    headers = {'Content-Type': 'application/json'}

    for model_name in image_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "outputFormat": "image/png"}
        }

        try:
            response = requests.post(url, headers=headers, json=payload)

            # 404나 에러가 나면 다음 모델 시도
            if response.status_code != 200:
                continue

            predictions = response.json().get('predictions', [])
            if not predictions: continue

            # 이미지 디코딩
            if 'bytesBase64Encoded' in predictions[0]:
                b64 = predictions[0]['bytesBase64Encoded']
            elif 'image' in predictions[0]:
                b64 = predictions[0]['image']['bytesBase64Encoded']
            else:
                continue

            return Image.open(io.BytesIO(base64.b64decode(b64)))

        except:
            continue

    st.error("이미지 생성 실패 (모든 모델 시도함)")
    return None


# -----------------------------
# 5. 사이드바 (설정 및 암호)
# -----------------------------
with st.sidebar:
    st.title("⚙️ 설정")

    ai_provider = st.radio(
        "사용할 AI 모델",
        ["Google (Gemini)", "OpenAI (DALL-E 3)"],
        captions=["유료/빠름 (암호 필요)", "유료/안정적"]
    )

    is_authorized = False

    if ai_provider == "OpenAI (DALL-E 3)":
        openai_key = st.secrets.get("OPENAI_API_KEY")
        if openai_key:
            st.success("✅ OpenAI 연결됨")
            is_authorized = True
        else:
            st.error("secrets.toml에 OPENAI_API_KEY가 없습니다.")
    else:
        st.markdown("---")
        st.warning("🔒 보안 모드")
        input_password = st.text_input("접근 암호 입력", type="password")

        real_password = st.secrets.get("GEMINI_PASSWORD")
        gemini_key = st.secrets.get("GEMINI_API_KEY")

        if not real_password:
            st.error("secrets.toml에 GEMINI_PASSWORD가 없습니다.")
        elif input_password == real_password:
            if gemini_key:
                st.success("🔓 Gemini 활성화됨")
                is_authorized = True
            else:
                st.error("API 키가 없습니다.")
        elif input_password:
            st.error("🚫 암호 불일치")

    st.markdown("---")
    style_preset = st.selectbox("화풍", ["Fantasy", "Pixel Art", "Anime", "Cyberpunk"])
    resize_option = st.checkbox("512x512 리사이즈", value=True)

# -----------------------------
# 6. 메인 로직
# -----------------------------
st.title(f"🎮 AI 게임 툴킷 ({'OpenAI' if 'OpenAI' in ai_provider else 'Google'})")

if not is_authorized:
    st.info("👈 사이드바에서 인증을 완료해주세요.")
    st.stop()

tab1, tab2 = st.tabs(["🗣️ NPC 생성", "⚔️ 아이템 생성"])

# ================= NPC 생성 =================
with tab1:
    npc_theme = st.text_input("NPC 테마", value="숲속의 엘프 궁수")

    if st.button("🎲 NPC 생성", use_container_width=True):
        with st.spinner(f"텍스트 데이터 생성 중..."):
            prompt = f"""
            Create a unique game NPC based on: '{npc_theme}'.
            Return JSON object with keys: name, role, rarity, stats(STR,DEX,INT,LUK), skill(name,description), backstory, visual_prompt.
            Translate contents to Korean. Output JSON only.
            """

            if "OpenAI" in ai_provider:
                data = run_openai_text(openai_key, prompt)
            else:
                data = run_gemini_text(gemini_key, prompt)

        if data and 'name' in data:
            with st.spinner(f"이미지 생성 중... ({style_preset})"):
                v_prompt = f"{style_preset} style. {data.get('visual_prompt')}. White background, character portrait."

                if "OpenAI" in ai_provider:
                    raw_img = run_dalle_image(openai_key, v_prompt)
                else:
                    raw_img = run_imagen_image(gemini_key, v_prompt)

                if raw_img:
                    final_img = remove_background_advanced(raw_img)
                    if resize_option: final_img = resize_image(final_img)

                    c1, c2 = st.columns([1, 1.5])
                    with c1:
                        st.image(final_img, caption=data['name'])
                    with c2:
                        stats_html = "".join([f"<span class='stat-box'><b>{k}</b>: {v}</span>" for k, v in
                                              data.get('stats', {}).items()])
                        st.markdown(f"""
                        <div class="game-card">
                            <div class="card-title">{data['name']} <small>({data['role']})</small></div>
                            <p><b>등급:</b> {data['rarity']}</p>
                            <div style="margin:10px 0;">{stats_html}</div>
                            <hr style="border-color:#555;">
                            <p><b>✨ 스킬: {data['skill']['name']}</b><br>{data['skill']['description']}</p>
                            <p><i>"{data['backstory']}"</i></p>
                        </div>""", unsafe_allow_html=True)
                else:
                    st.error("이미지 생성 실패")

# ================= 아이템 생성 =================
with tab2:
    item_input = st.text_input("아이템 이름", value="화염의 검")

    if st.button("⚔️ 아이템 생성"):
        with st.spinner("데이터 생성 중..."):
            prompt = f"Create game item: '{item_input}'. Return JSON: name, type, rank, effect, description. Korean text. JSON only."

            if "OpenAI" in ai_provider:
                data = run_openai_text(openai_key, prompt)
            else:
                data = run_gemini_text(gemini_key, prompt)

        if data:
            with st.spinner("아이콘 생성 중..."):
                v_prompt = f"{style_preset} style. Game icon of {item_input}. centered, isolated on white background."

                if "OpenAI" in ai_provider:
                    raw_img = run_dalle_image(openai_key, v_prompt)
                else:
                    raw_img = run_imagen_image(gemini_key, v_prompt)

                if raw_img:
                    final_img = remove_background_advanced(raw_img)
                    if resize_option: final_img = resize_image(final_img)

                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.image(final_img)
                    with c2:
                        st.markdown(f"""
                        <div class="game-card">
                            <div class="card-title">{data.get('name')}</div>
                            <p><b>타입:</b> {data.get('type')} | <b>등급:</b> {data.get('rank')}</p>
                            <p><b>효과:</b> {data.get('effect')}</p>
                            <p style="color:#bbb;">{data.get('description')}</p>
                        </div>""", unsafe_allow_html=True)