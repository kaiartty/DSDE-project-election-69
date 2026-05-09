# 🗳️ Election JSON Editor & Impute Tool (Local Multi-District Version)

## 📁 โครงสร้างการจัดเก็บข้อมูล (Project Directory Structure)

เพื่อให้ระบบแสกนหาไฟล์และเปิด PDF ได้ถูกต้อง ต้องจัดเรียงโฟลเดอร์ดังนี้:

```text
D:\EDUCATION\dsde\proj\ 
├── impute.py               # ไฟล์โปรแกรมหลัก (Streamlit)
├── impute.md               # ไฟล์คู่มือการใช้งาน
├── data\                   # Root Folder 
│   ├── <ชื่ออำเภอ>\         # แยกโฟลเดอร์ตามอำเภอ (เช่น เชียงดาว, พร้าว)
│   │   ├── raw\            # 📥 [Read-Only] ไฟล์ JSON ต้นฉบับจากระบบ OCR (ห้ามแก้)
│   │   │   ├── *_ss.json           # ข้อมูล ส.ส. แบบแบ่งเขต
│   │   │   └── *_confidence.json   # ข้อมูล ส.ส. แบบบัญชีรายชื่อ
│   │   ├── process\        # 💾 [Working] ไฟล์ JSON สำหรับแก้ไข (System Auto-copy จาก raw)
│   │   └── pdfs\           # 📄 โฟลเดอร์เก็บไฟล์ PDF ต้นฉบับ
│   │       └── [ชื่อตำบล]\  
│   │           └── [หน่วย X]\ 
│   │               ├── ส.ส.1.pdf    # เอกสาร ส.ส. เขต (ชื่อไฟล์ห้ามมีคำว่า บช)
│   │               └── ส.ส.บช1.pdf  # เอกสาร ส.ส. บัญชีรายชื่อ (ชื่อไฟล์ต้องมีคำว่า บช)