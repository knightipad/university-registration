"""
services.py — รวม logic การเช็คเงื่อนไขทั้งหมดตอนลงทะเบียน/ถอนวิชา
ไม่ควรเช็คเงื่อนไขพวกนี้ใน view โดยตรง ให้เรียกผ่านฟังก์ชันในไฟล์นี้เท่านั้น
เพื่อให้จุดเช็คกฎรวมอยู่ที่เดียว และห่อด้วย transaction กัน race condition
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Enrollment,
    EnrollmentType,
    Payment,
    Section,
    Student,
    StudentStatus,
    grade_meets_minimum,
)
from django.conf import settings


def _check_registration_period(section: Section):
    """เงื่อนไข #1"""
    now = timezone.now()
    sem = section.semester
    if not (sem.registration_start <= now <= sem.registration_end):
        raise ValidationError("ช่วงเวลาลงทะเบียนของภาคการศึกษานี้ปิดแล้ว หรือยังไม่เปิด")


def _check_student_status(student: Student):
    """เงื่อนไข #8"""
    if student.status == StudentStatus.SUSPENDED:
        raise ValidationError("นักศึกษาอยู่ในสถานะพักการเรียน/ถูกตัดสิทธิ์ ไม่สามารถลงทะเบียนได้")


def _check_program_lock(student: Student, section: Section):
    """เงื่อนไข #9"""
    if section.program_id is not None and section.program_id != student.program_id:
        raise ValidationError(
            f"กลุ่มเรียนนี้เปิดเฉพาะ '{section.program}' "
            f"นักศึกษาสังกัดภาค '{student.program}' ไม่มีสิทธิ์ลงทะเบียน"
        )


def _check_duplicate_enrollment(student: Student, section: Section):
    """เงื่อนไข #3 (ส่วนที่ 1): ห้ามลงวิชาเดียวกันซ้ำในเทอมเดียวกัน (คนละ section ของวิชาเดียวกันก็ห้าม)"""
    same_subject_active = Enrollment.objects.filter(
        student=student,
        section__open_class__subject=section.subject,
        section__open_class__semester=section.semester,
        status=Enrollment.Status.ENROLLED,
    ).exists()
    if same_subject_active:
        raise ValidationError("นักศึกษาลงทะเบียนวิชานี้ไว้แล้วในภาคการศึกษานี้ (คนละกลุ่มเรียนก็ถือว่าซ้ำ)")


def _check_already_passed(student: Student, section: Section, enrollment_type: str):
    """เงื่อนไข #3 (ส่วนที่ 2): ห้ามลงซ้ำวิชาที่เคยผ่านแล้ว — เฉพาะกรณีลงแบบนับหน่วยกิต (credit)"""
    if enrollment_type != EnrollmentType.CREDIT:
        return  # audit ลงซ้ำวิชาที่เคยผ่านแล้วได้ (ไม่กระทบเกรด/หน่วยกิต)

    passed = Enrollment.objects.filter(
        student=student,
        section__open_class__subject=section.subject,
        status=Enrollment.Status.COMPLETED,
        enrollment_type=EnrollmentType.CREDIT,
    )
    for e in passed:
        if e.grade and grade_meets_minimum(e.grade, settings.MIN_PASSING_GRADE):
            raise ValidationError("นักศึกษาผ่านวิชานี้แล้ว ไม่สามารถลงทะเบียนซ้ำแบบนับหน่วยกิตได้")


def _check_prerequisites(student: Student, section: Section, enrollment_type: str):
    """เงื่อนไข #2 — เช็คเฉพาะตอนลงแบบ credit"""
    if enrollment_type != EnrollmentType.CREDIT:
        return

    prereq_links = section.subject.prerequisite_links.select_related("required_subject").all()
    for link in prereq_links:
        completed = Enrollment.objects.filter(
            student=student,
            section__open_class__subject=link.required_subject,
            status=Enrollment.Status.COMPLETED,
            enrollment_type=EnrollmentType.CREDIT,
        )
        ok = any(e.grade and grade_meets_minimum(e.grade, link.min_grade) for e in completed)
        if not ok:
            raise ValidationError(
                f"ต้องผ่านวิชา {link.required_subject.code} (ขั้นต่ำ {link.min_grade}) ก่อนจึงจะลงวิชานี้ได้"
            )


def _check_time_conflict(student: Student, section: Section):
    """เงื่อนไข #4/#5 — เช็คทุก slot ของ section ใหม่ กับทุก slot ของทุก section ที่ลงอยู่แล้วในเทอมเดียวกัน"""
    new_slots = list(section.slots.all())

    existing_sections = Section.objects.filter(
        enrollments__student=student,
        enrollments__status=Enrollment.Status.ENROLLED,
        open_class__semester=section.semester,
    ).distinct()

    for existing_section in existing_sections:
        for existing_slot in existing_section.slots.all():
            for new_slot in new_slots:
                if new_slot.overlaps(existing_slot):
                    raise ValidationError(
                        f"เวลาเรียนชนกับ {existing_section.subject.code}-{existing_section.section_number} "
                        f"({existing_slot.get_day_of_week_display()} {existing_slot.start_time}-{existing_slot.end_time})"
                    )


def _check_credit_limit(student: Student, section: Section, enrollment_type: str):
    """เงื่อนไข #7 — audit ไม่นับหน่วยกิต"""
    if enrollment_type != EnrollmentType.CREDIT:
        return

    current_credits = sum(
        e.section.subject.credits
        for e in Enrollment.objects.filter(
            student=student,
            section__open_class__semester=section.semester,
            status=Enrollment.Status.ENROLLED,
            enrollment_type=EnrollmentType.CREDIT,
        ).select_related("section__open_class__subject")
    )
    projected = current_credits + section.subject.credits
    if projected > student.max_credits:
        raise ValidationError(
            f"หน่วยกิตรวมจะเกินโควตา ({projected}/{student.max_credits} หน่วยกิต) "
            f"ตามสถานภาพนักศึกษาปัจจุบัน"
        )


@transaction.atomic
def enroll_student(student: Student, section_id: int, enrollment_type: str = EnrollmentType.CREDIT) -> Enrollment:
    """
    จุดเดียวที่ควรเรียกจาก view เพื่อลงทะเบียน
    ล็อกแถว Section ด้วย select_for_update กันสอง request แย่งที่นั่งสุดท้ายพร้อมกัน (race condition)
    เมื่อลงทะเบียนสำเร็จจะสร้างรายการ Payment สถานะ 'รอชำระ' ให้อัตโนมัติตามค่าลงทะเบียน
    """
    section = Section.objects.select_for_update().select_related("open_class__subject", "open_class__semester").get(pk=section_id)

    _check_registration_period(section)
    _check_student_status(student)
    _check_program_lock(student, section)
    _check_duplicate_enrollment(student, section)
    _check_already_passed(student, section, enrollment_type)
    _check_prerequisites(student, section, enrollment_type)
    _check_time_conflict(student, section)
    _check_credit_limit(student, section, enrollment_type)

    # เงื่อนไข #6: เช็คที่นั่งเป็นลำดับสุดท้าย ภายใต้ row lock เดียวกัน เพื่อกัน over-booking
    if section.is_full():
        raise ValidationError("กลุ่มเรียนนี้เต็มแล้ว กรุณาเลือกกลุ่มอื่น")

    enrollment = Enrollment.objects.create(
        student=student,
        section=section,
        enrollment_type=enrollment_type,
        status=Enrollment.Status.ENROLLED,
    )
    Payment.objects.create(
        enrollment=enrollment,
        amount=enrollment.fee_amount,
        status=Payment.Status.PENDING,
    )
    return enrollment


@transaction.atomic
def withdraw_enrollment(student: Student, enrollment_id: int) -> Enrollment:
    """ถอนวิชา — ต้องอยู่ก่อนเส้นตายถอนวิชาของเทอมนั้น (แยกจากช่วงลงทะเบียน)"""
    enrollment = Enrollment.objects.select_for_update().select_related("section__open_class__semester").get(
        pk=enrollment_id, student=student
    )
    if enrollment.status != Enrollment.Status.ENROLLED:
        raise ValidationError("รายการนี้ไม่ได้อยู่ในสถานะลงทะเบียนอยู่ ถอนไม่ได้")

    if timezone.now() > enrollment.section.semester.withdrawal_deadline:
        raise ValidationError("เลยกำหนดเส้นตายการถอนวิชาของภาคการศึกษานี้แล้ว")

    enrollment.status = Enrollment.Status.WITHDRAWN
    enrollment.withdrawn_at = timezone.now()
    enrollment.save(update_fields=["status", "withdrawn_at"])
    return enrollment


@transaction.atomic
def pay_for_enrollment(student: Student, payment_id: int, method: str) -> Payment:
    """จ่ายรายการ Payment ที่ยังค้างอยู่ (สถานะ pending) ให้เป็น paid — เดโมเท่านั้น ไม่ได้ต่อ payment gateway จริง"""
    payment = Payment.objects.select_for_update().select_related("enrollment__student").get(
        pk=payment_id, enrollment__student=student
    )
    if payment.status != Payment.Status.PENDING:
        raise ValidationError("รายการนี้ไม่ได้อยู่ในสถานะรอชำระ")

    payment.status = Payment.Status.PAID
    payment.method = method
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "method", "paid_at"])
    return payment
