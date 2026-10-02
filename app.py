"""Mini app ออกแบบ/ตรวจสอบโครงสร้าง คสล. ตาม ACI 318M-19

รัน: streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="RC Design ACI 318M-19", page_icon="🏗️", layout="wide")
pg = st.navigation([
    st.Page("views/beam.py", title="คาน (Beam)", icon="📏", default=True),
    st.Page("views/column.py", title="เสา (Column)", icon="🏛️"),
])
pg.run()
