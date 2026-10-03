"""ลิงก์ข้ามหน้าที่ไม่ล่มเมื่อรันหน้าเดี่ยว (เช่น AppTest หรือ streamlit run views/xxx.py)"""
import streamlit as st


def page_link(page, label, icon=None):
    try:
        st.page_link(page, label=label, icon=icon)
    except Exception:   # noqa: BLE001 — StreamlitPageNotFoundError เมื่อไม่ได้เปิดผ่าน app.py
        st.caption(f"{icon or ''} {label} (เปิดผ่าน app.py)")
