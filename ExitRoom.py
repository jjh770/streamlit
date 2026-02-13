import streamlit as st
from openai import OpenAI
from streamlit_image_coordinates import streamlit_image_coordinates
import requests
from PIL import Image, ImageDraw
from io import BytesIO
import random
import math

# ---------------------------
# 기본 설정
# ---------------------------
st.set_page_config(page_title="✨ 방탈출", layout="wide")

# 🎨 감성 UI 스타일
st.markdown("""
<style>
.stApp {
    background: linear-gradient(180deg, #e6f2ff 0%, #ffffff 100%);
        color: #1a2b4c !important;
}

/* 전체 텍스트 색 */
html, body, [class*="css"]  {
    color: #1a2b4c !important;
}

/* 제목 */
h1, h2, h3 {
    color: #2a4d9b !important;
}

/* 버튼 */
.stButton>button {
    background-color: #4da6ff;
    color: white !important;
    border-radius: 14px;
    border: none;
    padding: 10px 20px;
    font-weight: 600;
}

.stButton>button:hover {
    background-color: #1f7ae0;
}

/* Info / Success / Error 박스 */
.stAlert {
    color: #1a2b4c !important;
}
</style>
""", unsafe_allow_html=True)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------------------------
# 세션 초기화
# ---------------------------
def init_session():
    defaults = {
        "room_image": None,
        "room_description": "",
        "game_stage": "START",
        "secret_points": [],
        "found_points": [],
        "click_count": 0,
        "level": 1,
        "score": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ---------------------------
# 방 생성
# ---------------------------
def generate_room():

    themes = [
        "abandoned classroom at sunset",
        "mysterious school library",
        "rooftop overlooking academy city",
        "underground research lab",
        "old music room",
        "student council office",
        "school infirmary at night"
    ]

    theme = random.choice(themes)

    prompt = f"""
    High quality anime-style background illustration inspired by modern Japanese mobile RPG games.

    First-person perspective escape room scene.
    Location: {theme}

    Clean anime line art.
    Soft cel shading.
    Bright pastel colors.
    Soft bloom lighting.
    Subtle floating light particles.
    Highly detailed environment.
    Many small objects scattered naturally.
    No characters.
    """

    with st.spinner("🎨 방 생성 중..."):
        image_response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024"
        )

        image_url = image_response.data[0].url
        img_response = requests.get(image_url)
        img = Image.open(BytesIO(img_response.content))

        st.session_state.room_image = img

        # 🧠 한글 설명 생성
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "밝고 청량한 애니메이션 감성으로 방을 한국어 한 문장으로 묘사하세요."
                },
                {
                    "role": "user",
                    "content": f"{theme} 공간을 묘사하세요."
                }
            ]
        )

        st.session_state.room_description = chat.choices[0].message.content

        # 🎯 아이템 배치 (800 기준)
        item_count = 2 + st.session_state.level
        points = []
        for _ in range(item_count):
            x = random.randint(80, 950)
            y = random.randint(80, 950)
            points.append((x, y))

        st.session_state.secret_points = points
        st.session_state.found_points = []
        st.session_state.click_count = 0
        st.session_state.game_stage = "PLAYING"

# ---------------------------
# 클릭 판정
# ---------------------------
def check_click(x, y):

    if st.session_state.game_stage != "PLAYING":
        return

    st.session_state.click_count += 1

    if st.session_state.click_count > 20:
        st.session_state.game_stage = "GAME_OVER"
        return

    HIT_RADIUS = 50
    NEAR_RADIUS = 150

    closest = None
    closest_dist = 9999

    for p in st.session_state.secret_points:
        if p in st.session_state.found_points:
            continue
        dist = math.dist((x, y), p)
        if dist < closest_dist:
            closest = p
            closest_dist = dist

    if closest:
        if closest_dist < HIT_RADIUS:
            st.session_state.found_points.append(closest)
            st.session_state.score += 100
            st.toast("✨ 단서 발견!", icon="✨")
            st.rerun()
        elif closest_dist < NEAR_RADIUS:
            st.toast("🔥 가까워요!", icon="🔥")
        else:
            st.toast("❄️ 아무것도 없습니다.", icon="❄️")

    if len(st.session_state.found_points) == len(st.session_state.secret_points):
        st.session_state.game_stage = "ESCAPED"
        st.session_state.score += 300
        st.session_state.level += 1

# ---------------------------
# UI 시작
# ---------------------------
st.title("✨ 방탈출")
st.caption("학원 도시에서 숨겨진 단서를 찾아보세요.")

if st.session_state.room_image is None:
    if st.button("🎮 게임 시작"):
        generate_room()
        st.rerun()

else:
    st.info(st.session_state.room_description)

    col1, col2 = st.columns([2, 1])

    with col1:
        img_copy = st.session_state.room_image.copy()
        draw = ImageDraw.Draw(img_copy)

        for p in st.session_state.found_points:
            draw.ellipse(
                (p[0]-15, p[1]-15, p[0]+15, p[1]+15),
                outline="green",
                width=4
            )

        value = streamlit_image_coordinates(img_copy, key="canvas")

        if value:
            real_x = value["x"] * (img_copy.width / value["width"])
            real_y = value["y"] * (img_copy.height / value["height"])
            check_click(real_x, real_y)

    with col2:
        st.markdown("### 📊 상태창")
        st.markdown(f"""
        **레벨**: {st.session_state.level}  
        **점수**: {st.session_state.score}  
        **남은 기회**: {20 - st.session_state.click_count}  
        **남은 단서**: {len(st.session_state.secret_points) - len(st.session_state.found_points)}
        """)

        if st.session_state.game_stage == "ESCAPED":
            st.success("🚪 방 탈출 성공!")
            if st.button("다음 레벨"):
                generate_room()
                st.rerun()

        if st.session_state.game_stage == "GAME_OVER":
            st.error("💀 게임 오버")
            if st.button("처음부터"):
                st.session_state.level = 1
                st.session_state.score = 0
                generate_room()
                st.rerun()
