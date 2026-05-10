import streamlit as st
import json
import os
import subprocess
import time
import shutil

BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
st.set_page_config(page_title="JSON Editor", layout="wide")

st.set_page_config(page_title="JSON Editor", layout="wide")

st.markdown("""
    <style>
    div[data-testid="stNumberInput"] label p {
        white-space: normal !important;
        word-wrap: break-word !important;
        line-height: 1.3 !important;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ Settings")

amphoes = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d)) and d != "final"]

if not amphoes:
    st.error("❌ ไม่พบโฟลเดอร์อำเภอในโฟลเดอร์ `data/`")
    st.stop()

selected_amphoe = st.sidebar.selectbox("📍 เลือกอำเภอ:", sorted(amphoes))

AMPHOE_DIR = os.path.join(DATA_DIR, selected_amphoe)
RAW_DIR = os.path.join(AMPHOE_DIR, "raw")
PROCESS_DIR = os.path.join(AMPHOE_DIR, "process")
PDF_BASE = os.path.join(AMPHOE_DIR, "pdfs")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESS_DIR, exist_ok=True)
os.makedirs(PDF_BASE, exist_ok=True)

# Autocopy Raw to Process (if not exits) 
raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith('.json')]
if not raw_files:
    st.sidebar.error(f"⚠️ ไม่พบไฟล์ JSON ต้นฉบับใน `{RAW_DIR}`")
    st.stop()

for f in raw_files:
    r_path = os.path.join(RAW_DIR, f)
    p_path = os.path.join(PROCESS_DIR, f)
    if not os.path.exists(p_path):
        shutil.copy2(r_path, p_path)

# Selection
process_files = [f for f in os.listdir(PROCESS_DIR) if f.endswith('.json')]
selected_filename = st.sidebar.selectbox("📄 เลือกไฟล์:", sorted(process_files))

st.sidebar.markdown("---")
view_mode = st.sidebar.radio(
    "โหมดการทำงาน:", 
    ["📝 แก้ไขข้อมูล (Process)", "👀 ดูต้นฉบับ (Raw)"]
)

is_raw_mode = "Raw" in view_mode
is_ss_mode = "ss" in selected_filename.lower()

TARGET_PROCESS_PATH = os.path.join(PROCESS_DIR, selected_filename)
TARGET_RAW_PATH = os.path.join(RAW_DIR, selected_filename)

actual_read_path = TARGET_RAW_PATH if is_raw_mode else TARGET_PROCESS_PATH

@st.cache_data(show_spinner=False)
def load_data(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None

data = load_data(actual_read_path)

if data is None:
    st.error(f"❌ ไม่พบข้อมูลในไฟล์: {actual_read_path}")
    st.stop()

# Status file
if is_raw_mode:
    st.warning("👀 **โหมดดูต้นฉบับ (Raw):** คุณกำลังดูข้อมูลไฟล์ดิบ ปุ่มบันทึกจะถูกล็อกการใช้งาน", icon="🔒")
else:
    st.info("📝 **โหมดแก้ไข (Process):** การแก้ไขและการบันทึกทั้งหมดจะถูกบันทึกลงไฟล์ในโฟลเดอร์ Process", icon="💾")

st.title(f"📝 {selected_amphoe} / {selected_filename}")

# Widgets
col1, col2, col3 = st.columns([3, 3, 2])

with col1:
    tambon = st.selectbox("ตำบล:", options=sorted(data.keys()))

with col2:
    unit_options = sorted(data.get(tambon, {}).keys(), 
                          key=lambda x: int(x.replace("หน่วย ", "") or 0))
    unit = st.selectbox("หน่วย:", options=unit_options)

with col3:
    st.write("")
    st.write("")
    if st.button("📄 เปิด PDF", type="secondary"):
        unit_dir = os.path.join(PDF_BASE, tambon, unit)
        if not os.path.exists(unit_dir):
            st.error(f"❌ หาโฟลเดอร์ PDF ไม่พบที่: `{unit_dir}`")
        else:
            try:
                pdfs = [f for f in os.listdir(unit_dir) if f.endswith(".pdf")]
                target_pdfs = []
                for pdf in pdfs:
                    if is_ss_mode and "บช" not in pdf: target_pdfs.append(pdf)
                    elif not is_ss_mode and "บช" in pdf: target_pdfs.append(pdf)
                if not target_pdfs: target_pdfs = pdfs

                if target_pdfs:
                    for pdf in target_pdfs:
                        path = os.path.join(unit_dir, pdf)
                        st.toast(f"📄 กำลังเปิดไฟล์: {pdf}")
                        if os.name == 'nt': os.startfile(path)
                        elif os.uname().sysname == 'Darwin': subprocess.Popen(["open", path])
                        else: subprocess.Popen(["evince", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    st.warning(f"⚠️ ไม่พบไฟล์ PDF ในโฟลเดอร์: {unit_dir}")
            except Exception as e:
                st.error(f"⚠️ เกิดข้อผิดพลาดในการเปิด PDF: {e}")

PARTY_NAMES = [
    "ไทยทรัพย์ทวี", "เพื่อชาติไทย", "ใหม่", "มิติใหม่", "รวมใจไทย",
    "รวมไทยสร้างชาติ", "พลวัต", "ประชาธิปไตยใหม่", "เพื่อไทย", "ทางเลือกใหม่",
    "เศรษฐกิจ", "เสรีรวมไทย", "รวมพลังประชาชน", "ท้องที่ไทย", "อนาคตไทย",
    "พลังเพื่อไทย", "ไทยชนะ", "พลังสังคมใหม่", "สังคมประชาธิปไตยไทย", "ฟิวชัน",
    "ไทรวมพลัง", "ก้าวอิสระ", "ปวงชนไทย", "วิชชั่นใหม่", "เพื่อชีวิตใหม่",
    "คลองไทย", "ประชาธิปัตย์", "ไทยก้าวหน้า", "ไทยภักดี", "แรงงานสร้างชาติ",
    "ประชากรไทย", "ครูไทยเพื่อประชาชน", "ประชาชาติ", "สร้างอนาคตไทย", "รักชาติ",
    "ไทยพร้อม", "ภูมิใจไทย", "พลังธรรมใหม่", "กรีน", "ไทยธรรม",
    "แผ่นดินธรรม", "กล้าธรรม", "พลังประชารัฐ", "โอกาสใหม่", "เป็นธรรม",
    "ประชาชน", "ประชาไทย", "ไทยสร้างไทย", "ไทยก้าวใหม่", "ประชาอาสาชาติ",
    "พร้อม", "เครือข่ายชาวนาแห่งประเทศไทย", "ไทยพิทักษ์ธรรม", "ความหวังใหม่",
    "ไทยรวมไทย", "เพื่อบ้านเมือง", "พลังไทยรักชาติ"
]

# Visualization
d = data.get(tambon, {}).get(unit, {})
votes = d.get("votes") or {}
candidate_info = d.get("candidate_info") or {}
trusted = d.get("trusted_total")

bs = d.get("ballot_summary", {})
sub_check = bs.get("sub_check", "ไม่มีข้อมูล")
alloc_check = bs.get("alloc_check", "ไม่มีข้อมูล")

st.markdown("---")
st.markdown(f"#### 📍 {tambon} / {unit}")

# Manual Confirm / Auto-fill if no table
if len(votes) == 0 and not is_raw_mode:
    st.warning("⚠️ ไม่พบข้อมูลตารางในไฟล์ OCR กรุณาเลือกวิธีจัดการข้อมูลด้านล่าง:")
    
    if not is_ss_mode:
        if st.button("📋 สร้างช่องกรอกคะแนน 57 พรรค (Party List)"):
            d["votes"] = {str(i): 0 for i in range(1, 58)}
            with open(TARGET_PROCESS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            st.cache_data.clear()
            st.rerun()
    else:
        neighbors = [u for u in data.get(tambon, {}).keys() if u != unit and data[tambon][u].get("candidate_info")]
        
        if neighbors:
            target_neighbor = st.selectbox("เลือกหน่วยที่จะคัดลอกรายชื่อผู้สมัคร:", neighbors)
            if st.button(f"🔗 ดึงรายชื่อจาก {target_neighbor}"):
                d["candidate_info"] = data[tambon][target_neighbor].get("candidate_info")
                d["votes"] = {k: 0 for k in d["candidate_info"].keys()}
                with open(TARGET_PROCESS_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                st.cache_data.clear()
                st.rerun()
        else:
            if st.button("🆕 สร้างช่องว่างเบอร์ 1-15"):
                d["votes"] = {str(i): 0 for i in range(1, 16)}
                with open(TARGET_PROCESS_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                st.cache_data.clear()
                st.rerun()

votes = d.get("votes") or {}
candidate_info = d.get("candidate_info") or {}
status_col1, status_col2 = st.columns(2)
with status_col1:
    st.markdown(f"**จำนวนบัตรดี (เป้าหมาย)**: `{trusted}`")
    st.markdown(f"**Status การรวมคะแนน**: `{d.get('status', 'ไม่มีข้อมูล')}`")
with status_col2:
    st.markdown(f"**Sub Check (ดี+เสีย+ไม่เลือก)**: `{sub_check}`")
    st.markdown(f"**Alloc Check (ใช้+เหลือ)**: `{alloc_check}`")

# edit
with st.form("edit_form"):
    st.markdown("##### 🎯 ข้อมูลบัตร (Ballot Summary)")
    
    row1_c1, row1_c2, row1_c3 = st.columns(3)
    with row1_c1:
        edit_alloc = st.number_input("บัตรที่รับมา (Alloc):", value=int(bs.get("ballots_alloc") or 0), min_value=0, step=1, disabled=is_raw_mode)
    with row1_c2:
        edit_used = st.number_input("ใช้ไป (Used):", value=int(bs.get("ballots_used") or 0), min_value=0, step=1, disabled=is_raw_mode)
    with row1_c3:
        edit_remain = st.number_input("เหลือ (Remain):", value=int(bs.get("ballots_remain") or 0), min_value=0, step=1, disabled=is_raw_mode)

    row2_c1, row2_c2, row2_c3 = st.columns(3)
    with row2_c1:
        edit_valid = st.number_input("บัตรดี (Valid):", value=int(bs.get("ballots_valid") or 0), min_value=0, step=1, disabled=is_raw_mode)
    with row2_c2:
        edit_spoiled = st.number_input("บัตรเสีย (Spoiled):", value=int(bs.get("ballots_spoiled") or 0), min_value=0, step=1, disabled=is_raw_mode)
    with row2_c3:
        edit_novote = st.number_input("ไม่เลือกใคร (No Vote):", value=int(bs.get("ballots_no_vote") or 0), min_value=0, step=1, disabled=is_raw_mode)

    txt_note = st.text_input("📝 หมายเหตุเพิ่มเติม:", value=d.get("manual_note", ""), placeholder="เช่น ลายมืออ่านยาก, มีรอยขีดฆ่า", disabled=is_raw_mode)

    st.markdown("---")
    st.markdown("##### 🗳️ คะแนนแต่ละพรรค/ผู้สมัคร (เรียงตามเบอร์)")
    
    vote_cols = st.columns(5)
    vote_inputs = {}
    
    for i, kid in enumerate(sorted(votes.keys(), key=lambda x: int(x))):
        val = votes[kid] if isinstance(votes[kid], int) else 0
        if not is_ss_mode:
            try: disp_name = PARTY_NAMES[int(kid)-1]
            except: disp_name = ""
        else:
            disp_name = candidate_info.get(kid, {}).get("name", "")
            party_name = candidate_info.get(kid, {}).get("party", "")
            if party_name: disp_name += f" ({party_name})"
                
        label = f"เบอร์ {kid}: {disp_name}"
        
        with vote_cols[i % 5]:
            mode_key = "raw" if is_raw_mode else "proc"
            key_vote =f"v_{mode_key}_{selected_amphoe}_{selected_filename}_{tambon}_{unit}_{kid}"
            vote_inputs[kid] = st.number_input(label, value=val, min_value=0, step=1, key=key_vote, disabled=is_raw_mode)
            
    submit_btn = st.form_submit_button("💾 บันทึกและตรวจสอบข้อมูล", type="primary", disabled=is_raw_mode)

# Save & Check
if submit_btn and not is_raw_mode:
    d["votes"] = {kid: val for kid, val in vote_inputs.items()}
    new_sum = sum(d["votes"].values())
    bs.update({
        "ballots_valid": edit_valid, "ballots_spoiled": edit_spoiled, "ballots_no_vote": edit_novote,
        "ballots_used": edit_used, "ballots_alloc": edit_alloc, "ballots_remain": edit_remain
    })
    s_sum = edit_valid + edit_spoiled + edit_novote
    bs["sub_check"] = "✅ ok" if s_sum == edit_used else f"⚠️ {s_sum} != used({edit_used})"
    a_sum = edit_used + edit_remain
    bs["alloc_check"] = "✅ ok" if a_sum == edit_alloc else f"⚠️ {edit_used}+{edit_remain} != alloc({edit_alloc})"
    d["ballot_summary"] = bs
    d["trusted_total"] = edit_valid 
    diff = edit_valid - new_sum
    d["status"] = "✅ exact match (manual edit)" if diff == 0 else f"⚠️ sum={new_sum} trusted={edit_valid} diff={diff}"
    d["final_sum"] = new_sum
    d["manual_note"] = txt_note
    d["manual_edited"] = True
    
    try:
        with open(TARGET_PROCESS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        st.toast("บันทึกข้อมูลเรียบร้อยแล้ว")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")