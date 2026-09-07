from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from registration.models import (
    Curriculum,
    CurriculumSubject,
    Department,
    Enrollment,
    EnrollmentType,
    Faculty,
    OpenClass,
    Payment,
    Prerequisite,
    Program,
    ScheduleSlot,
    Section,
    Semester,
    SlotType,
    Student,
    StudentStatus,
    Subject,
    SubjectCategory,
    University,
)


class Command(BaseCommand):
    help = "สร้างข้อมูลตัวอย่างไว้ทดสอบระบบลงทะเบียน (มหาวิทยาลัย, คณะ, ภาควิชา, หลักสูตร, วิชา, กลุ่มเรียน, นักศึกษา, การชำระเงิน)"

    def handle(self, *args, **options):
        now = timezone.now()

        univ, _ = University.objects.get_or_create(code="KU", defaults={"name": "มหาวิทยาลัยเกษตรศาสตร์"})
        faculty, _ = Faculty.objects.get_or_create(university=univ, code="ENG", defaults={"name": "คณะวิศวกรรมศาสตร์"})
        dept, _ = Department.objects.get_or_create(faculty=faculty, code="CPE", defaults={"name": "วิศวกรรมคอมพิวเตอร์"})
        curriculum, _ = Curriculum.objects.get_or_create(
            department=dept, code="CPE-65", defaults={"name": "วศ.บ. วิศวกรรมคอมพิวเตอร์ (หลักสูตรปรับปรุง 2565)"}
        )

        prog_regular, _ = Program.objects.get_or_create(department=dept, name="ภาคปกติ")
        prog_special, _ = Program.objects.get_or_create(department=dept, name="ภาคพิเศษ")

        intro, _ = Subject.objects.get_or_create(
            code="01204111", defaults={"name": "Computer Programming", "credits": 3, "department": dept}
        )
        data_struct, _ = Subject.objects.get_or_create(
            code="01204211", defaults={"name": "Data Structures", "credits": 3, "department": dept}
        )
        Prerequisite.objects.get_or_create(subject=data_struct, required_subject=intro, defaults={"min_grade": "D"})

        CurriculumSubject.objects.get_or_create(curriculum=curriculum, subject=intro, defaults={"category": SubjectCategory.CORE})
        CurriculumSubject.objects.get_or_create(curriculum=curriculum, subject=data_struct, defaults={"category": SubjectCategory.CORE})

        semester, _ = Semester.objects.get_or_create(
            year=2569,
            term=1,
            defaults={
                "registration_start": now - timedelta(days=1),
                "registration_end": now + timedelta(days=14),
                "withdrawal_deadline": now + timedelta(days=45),
            },
        )

        open_class = OpenClass.objects.get_or_create(subject=data_struct, semester=semester)[0]

        sec_regular = Section.objects.create(
            open_class=open_class, section_number="001",
            instructor_name="อ.สมชาย", program=prog_regular, max_capacity=2,
        )
        ScheduleSlot.objects.create(section=sec_regular, slot_type=SlotType.LECTURE, day_of_week=0,
                                     start_time="09:00", end_time="11:00", room="9-101")
        ScheduleSlot.objects.create(section=sec_regular, slot_type=SlotType.LAB, day_of_week=2,
                                     start_time="13:00", end_time="16:00", room="Lab-2")

        sec_special = Section.objects.create(
            open_class=open_class, section_number="801",
            instructor_name="อ.สมหญิง", program=prog_special, max_capacity=30,
        )
        ScheduleSlot.objects.create(section=sec_special, slot_type=SlotType.LECTURE, day_of_week=5,
                                     start_time="09:00", end_time="12:00", room="9-201")

        user1, created = User.objects.get_or_create(username="6410000001", defaults={"first_name": "แนน"})
        if created:
            user1.set_password("demo1234")
            user1.save()
        student1, _ = Student.objects.get_or_create(
            user=user1, defaults={
                "student_id": "6410000001", "curriculum": curriculum, "program": prog_regular,
                "year_level": 2, "gpa": 3.2, "status": StudentStatus.ACTIVE,
            }
        )
        # ให้ student1 "ผ่าน" 01204111 มาแล้ว เพื่อทดสอบ prerequisite ผ่าน
        past_semester, _ = Semester.objects.get_or_create(
            year=2568, term=2,
            defaults={
                "registration_start": now - timedelta(days=200),
                "registration_end": now - timedelta(days=190),
                "withdrawal_deadline": now - timedelta(days=180),
            },
        )
        past_open_class = OpenClass.objects.get_or_create(subject=intro, semester=past_semester)[0]
        past_section = Section.objects.create(
            open_class=past_open_class, section_number="001",
            instructor_name="อ.เก่า", program=None, max_capacity=50,
        )
        past_enrollment, _ = Enrollment.objects.get_or_create(
            student=student1, section=past_section,
            defaults={"enrollment_type": EnrollmentType.CREDIT, "status": Enrollment.Status.COMPLETED, "grade": "B"},
        )
        Payment.objects.get_or_create(
            enrollment=past_enrollment,
            defaults={"amount": past_enrollment.fee_amount, "status": Payment.Status.PAID, "paid_at": now - timedelta(days=185)},
        )

        user2, created = User.objects.get_or_create(username="6410000002", defaults={"first_name": "บีม"})
        if created:
            user2.set_password("demo1234")
            user2.save()
        Student.objects.get_or_create(
            user=user2, defaults={
                "student_id": "6410000002", "curriculum": curriculum, "program": prog_special,
                "year_level": 2, "gpa": 2.4, "status": StudentStatus.PROBATION,
            }
        )

        self.stdout.write(self.style.SUCCESS(
            "สร้างข้อมูลตัวอย่างสำเร็จ: user 6410000001 / 6410000002 (password: demo1234)"
        ))
