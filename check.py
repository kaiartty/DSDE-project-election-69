import json
import os
import glob

def check_multiple_files(directory_path):
    search_pattern = os.path.join(directory_path, '*.json')
    json_files = glob.glob(search_pattern)
    
    if not json_files:
        print(f"❌ ไม่พบไฟล์ JSON ในโฟลเดอร์: {directory_path}")
        print("กรุณาตรวจสอบชื่อโฟลเดอร์และ Path ให้ถูกต้อง")
        return

    print(f"🔍 พบไฟล์ JSON ทั้งหมด {len(json_files)} ไฟล์ กำลังเริ่มตรวจสอบ...\n")
    
    total_files = len(json_files)
    total_units = 0
    passed_units = 0
    issues_found = []
    for file_path in json_files:
        file_name = os.path.basename(file_path) 
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            for tambon_name, units in data.items():
                for unit_name, unit_data in units.items():
                    total_units += 1
                    
                    status = unit_data.get("status", "")
                    ballot_summary = unit_data.get("ballot_summary", {})
                    sub_check = ballot_summary.get("sub_check", "")
                    
                    status_ok = isinstance(status, str) and status.startswith("✅")
                    sub_check_ok = isinstance(sub_check, str) and sub_check.startswith("✅")
                    
                    if status_ok and sub_check_ok:
                        passed_units += 1
                    else:
                        issues_found.append({
                            "ไฟล์": file_name,
                            "ตำบล": tambon_name,
                            "หน่วย": unit_name,
                            "status": status,
                            "sub_check": sub_check,
                            "status_ok": status_ok,
                            "sub_check_ok": sub_check_ok
                        })
                        
        except json.JSONDecodeError as e:
            print(f"❌ ไฟล์ {file_name} มีรูปแบบ JSON ไม่ถูกต้อง: {e}")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดกับไฟล์ {file_name}: {e}")

    print(f"📊 สรุปผลการตรวจสอบรวมทั้งหมด ({total_files} ไฟล์):")
    print(f"   จำนวนหน่วยทั้งหมด: {total_units} หน่วย")
    print(f"   ผ่านสมบูรณ์ (✅ ทั้งคู่): {passed_units} หน่วย")
    print(f"   ไม่ผ่าน/ต้องแก้ไข: {total_units - passed_units} หน่วย")
    print("-" * 60)

    if len(issues_found) == 0 and total_units > 0:
        print("🎉 สำเร็จ! ทุกหน่วยในทุกไฟล์มีสถานะและ sub_check เป็น ✅ เรียบร้อยแล้ว")
    elif total_units == 0:
        print("⚠️ ไม่พบข้อมูลหน่วยใดๆ ในไฟล์ที่ตรวจสอบเลย")
    else:
        print("⚠️ พบหน่วยที่ยังไม่ผ่านเงื่อนไข ดังนี้:")
        current_file = ""
        for issue in issues_found:
            if issue['ไฟล์'] != current_file:
                current_file = issue['ไฟล์']
                print(f"\n📂 ไฟล์: {current_file}")
            
            print(f"   📍 {issue['ตำบล']} -> {issue['หน่วย']}")
            
            if not issue['status_ok']:
                print(f"      ❌ status: '{issue['status']}'")
            if not issue['sub_check_ok']:
                display_sub = issue['sub_check'] if issue['sub_check'] else "ไม่มีข้อมูล (Missing Key)"
                print(f"      ❌ sub_check: '{display_sub}'")

folder_path = 'data/final'

check_multiple_files(folder_path)