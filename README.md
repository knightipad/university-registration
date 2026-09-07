# ระบบลงทะเบียนเรียนมหาวิทยาลัย (Django)

โปรเจกต์ Django ตามโครงสร้าง ER diagram: **University → Faculty → Department → Curriculum → Subject**
พร้อมฝั่งลงทะเบียน: **Subject → OpenClass (เปิดสอนเทอมไหน) → Section (กลุ่มเรียนย่อย) → Enrollment → Payment**

Implement เงื่อนไขทั้งหมดที่คุยกันไว้:

1. เช็คช่วงเวลาลงทะเบียนของภาคการศึกษา
2. เช็ค prerequisite (ต้องผ่านวิชาก่อนหน้าด้วยเกรดขั้นต่ำที่กำหนด) — เฉพาะลงแบบ credit
3. ห้ามลงทะเบียนวิชาเดียวกันซ้ำในเทอมเดียวกัน และห้ามลงซ้ำวิชาที่เคยผ่านแล้ว (เฉพาะ credit)
4. เช็คเวลาเรียนชนกัน โดยเช็คทุก schedule slot ของทุก section ที่ลงทะเบียนอยู่
5. Lecture + Lab ผูกกันเป็น section เดียว ลงพร้อมกันเสมอ (ไม่มีการลงแยก)
6. ที่นั่งเต็มแล้ว = ปฏิเสธทันที ไม่มีระบบ waitlist
7. จำกัดหน่วยกิตรวมต่อเทอมตามสถานภาพนักศึกษา (ปกติ/รอพินิจ) — audit ไม่นับหน่วยกิต
8. เช็คสถานภาพนักศึกษา (ห้ามลงทะเบียนถ้าถูกพักการเรียน/ตัดสิทธิ์)
9. ล็อก section ตามภาค — **แต่ละภาควิชากำหนด "ภาค" ของตัวเองได้** ผ่านโมเดล `Program` ที่ผูกกับ `Department` และหน้า admin กรองตัวเลือกภาคให้อัตโนมัติตามภาควิชาของวิชา/นักศึกษาที่เลือก (dependent dropdown)
10. **ลงทะเบียนสำเร็จจะสร้างรายการ `Payment` สถานะ "รอชำระ" อัตโนมัติ** (ค่าลงทะเบียน = หน่วยกิต × อัตราต่อหน่วยกิตใน `settings.CREDIT_FEE_RATE`) นักศึกษากดจ่ายได้ที่หน้าตารางเรียนของฉัน — เป็นการจำลองสถานะการจ่ายเงินเท่านั้น **ไม่ได้ต่อ payment gateway จริง**

ทุกเงื่อนไขรวมอยู่ใน `registration/services.py` (ฟังก์ชัน `enroll_student`, `withdraw_enrollment`, `pay_for_enrollment`)
และเช็คเสร็จภายใต้ database transaction + row lock (`select_for_update`) เพื่อกัน race condition
ตอนมีหลายคนลงทะเบียนที่นั่งสุดท้ายพร้อมกัน

## วิธีติดตั้งและรัน

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo       # สร้างข้อมูลตัวอย่าง (มหาวิทยาลัย, คณะ, ภาควิชา, หลักสูตร, วิชา, section, นักศึกษา)
python manage.py createsuperuser # (ทางเลือก) สร้างแอดมินไว้จัดการข้อมูลผ่าน /admin/

python manage.py runserver
```

จากนั้นเข้า:
- `http://127.0.0.1:8000/register/` — หน้าลงทะเบียนเรียน
- `http://127.0.0.1:8000/my-schedule/` — ตารางเรียน + สถานะการชำระเงิน + ถอนวิชา
- `http://127.0.0.1:8000/admin/` — จัดการข้อมูลทั้งหมด (ต้องมี superuser)

### บัญชีทดสอบจาก `seed_demo`
| username | password | หมายเหตุ |
|---|---|---|
| 6410000001 | demo1234 | ภาคปกติ, ผ่านวิชา 01204111 มาแล้ว (มี Payment สถานะจ่ายแล้ว) |
| 6410000002 | demo1234 | ภาคพิเศษ, สถานะรอพินิจ, ยังไม่ผ่าน prerequisite |

## โครงสร้างไฟล์สำคัญ

- `registration/models.py` — University, Faculty, Department, Curriculum, CurriculumSubject, Program (ภาคของแต่ละภาควิชา), Student, Subject, Prerequisite, Semester, OpenClass, Section, ScheduleSlot, Enrollment, Payment
- `registration/services.py` — จุดรวม logic การเช็คเงื่อนไขทั้งหมด (ห้ามเช็คใน view ตรงๆ)
- `registration/views.py` — หน้าลงทะเบียน + ตารางเรียน + ชำระเงิน
- `registration/admin.py` — จัดการข้อมูลผ่าน Django admin พร้อม dependent dropdown (เลือก Curriculum/OpenClass แล้ว Program กรองอัตโนมัติ)
- `registration/static/registration/admin_program_filter.js` — JS เบื้องหลัง dependent dropdown ของ Program
- `registration/management/commands/seed_demo.py` — สร้างข้อมูลตัวอย่าง

## ปรับ constants ได้ที่ `university_registration/settings.py`
- `MAX_CREDITS_NORMAL`, `MAX_CREDITS_PROBATION` — โควตาหน่วยกิตต่อเทอม
- `MIN_PASSING_GRADE` — เกรดขั้นต่ำที่ถือว่า "ผ่าน" วิชา
- `CREDIT_FEE_RATE` — ค่าลงทะเบียนต่อหน่วยกิต (บาท)

## สิ่งที่ยังไม่ได้ทำ (ตัดสโคปไว้ตามที่คุยกัน)
- ไม่มีระบบ waitlist (ตามที่ตกลง — เต็มแล้วปฏิเสธเลย)
- Payment เป็นการจำลองสถานะเท่านั้น ไม่ได้ต่อ payment gateway จริง (พร้อมพัก/บัตรเครดิต/โอนเงินเป็นแค่ตัวเลือกบันทึกวิธีจ่าย ไม่มีการเรียก API จริง)
- ไม่มี retake/GPA recalculation logic แบบละเอียด (เกรดล่าสุด vs ดีที่สุด)

