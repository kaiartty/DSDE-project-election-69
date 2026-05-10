import json
import os
import glob


def check_multiple_files(directory_path):
    json_files = glob.glob(os.path.join(directory_path, "*.json"))

    if not json_files:
        print(f"ไม่พบไฟล์ JSON ในโฟลเดอร์: {directory_path}")
        return

    print(f"พบไฟล์ JSON ทั้งหมด {len(json_files)} ไฟล์ กำลังเริ่มตรวจสอบ...\n")

    total_units  = 0
    passed_units = 0
    issues_found = []

    for file_path in json_files:
        file_name = os.path.basename(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for tambon_name, units in data.items():
                for unit_name, unit_data in units.items():
                    total_units += 1

                    status     = unit_data.get("status", "")
                    bs         = unit_data.get("ballot_summary", {})
                    sub_check  = bs.get("sub_check", "")

                    status_ok    = isinstance(status,    str) and status.startswith("✅")
                    sub_check_ok = isinstance(sub_check, str) and sub_check.startswith("✅")

                    if status_ok and sub_check_ok:
                        passed_units += 1
                    else:
                        issues_found.append({
                            "file":          file_name,
                            "tambon":        tambon_name,
                            "unit":          unit_name,
                            "status":        status,
                            "sub_check":     sub_check,
                            "status_ok":     status_ok,
                            "sub_check_ok":  sub_check_ok,
                        })

        except json.JSONDecodeError as e:
            print(f"ไฟล์ {file_name} มีรูปแบบ JSON ไม่ถูกต้อง: {e}")
        except Exception as e:
            print(f"เกิดข้อผิดพลาดกับไฟล์ {file_name}: {e}")

    # summary
    print(f"สรุปผลการตรวจสอบรวม ({len(json_files)} ไฟล์):")
    print(f"  หน่วยทั้งหมด : {total_units}")
    print(f"  ผ่านสมบูรณ์  : {passed_units}")
    print(f"  ต้องแก้ไข    : {total_units - passed_units}")
    print("-" * 60)

    if total_units == 0:
        print("ไม่พบข้อมูลหน่วยใดๆ ในไฟล์ที่ตรวจสอบ")
        return

    if not issues_found:
        print("สำเร็จ! ทุกหน่วยมีสถานะและ sub_check เป็น ok แล้ว")
        return

    # detail per file
    print("พบหน่วยที่ยังไม่ผ่านเงื่อนไข:")
    current_file = ""
    for issue in issues_found:
        if issue["file"] != current_file:
            current_file = issue["file"]
            print(f"\n{current_file}")

        print(f"  {issue['tambon']} -> {issue['unit']}")
        if not issue["status_ok"]:
            print(f"    status    : '{issue['status']}'")
        if not issue["sub_check_ok"]:
            display_sub = issue["sub_check"] or "missing"
            print(f"    sub_check : '{display_sub}'")


if __name__ == "__main__":
    check_multiple_files("data/final")