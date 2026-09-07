"""
Models สำหรับระบบลงทะเบียนเรียน — โครงสร้างตาม ER diagram:

University -> Faculty -> Department -> Curriculum -> Subject
                                          |            (Core / Major Elective / GenEd ผ่าน CurriculumSubject)
                                          v
                                       Student
Subject -> OpenClass -> Section -> Enrollment -> Payment
                                       ^
                                    Student

ครอบคลุมเงื่อนไขทั้งหมดที่ตกลงกันไว้:
 1. ช่วงเวลาลงทะเบียนเปิดอยู่                     -> Semester.registration_start/end
 2. Prerequisite ผ่านแล้ว (เฉพาะ credit)          -> Prerequisite + Enrollment(status=completed)
 3. ไม่ลงซ้ำ / ไม่เคยผ่านวิชานี้แล้ว                -> ตรวจใน services.py
 4. เวลาเรียนไม่ชนกับวิชาอื่น (ทุก slot)           -> ScheduleSlot
 5. Lecture+Lab ผูกกันเป็นก้อนเดียว               -> Section มีหลาย ScheduleSlot
 6. ที่นั่งยังไม่เต็ม (ปฏิเสธ ไม่มี waitlist)        -> Section.max_capacity
 7. หน่วยกิตรวม (เฉพาะ credit) ไม่เกินโควตา         -> ตรวจใน services.py
 8. สถานภาพนักศึกษาปกติ                          -> Student.status
 9. ภาค/หลักสูตรของนักศึกษาตรงกับภาคของ section     -> Student.program / Section.program
"""

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


# เกรดเรียงจากสูง->ต่ำ ใช้เทียบว่า "ผ่านเกณฑ์ขั้นต่ำ" หรือยัง (ไม่รวมเกรดที่ไม่ใช่ตัวเลข เช่น W, AU)
GRADE_ORDER = ["A", "B+", "B", "C+", "C", "D+", "D", "F"]


def grade_meets_minimum(grade: str, minimum: str) -> bool:
    """คืนค่า True ถ้า grade ดีกว่าหรือเท่ากับ minimum (เช่น B >= D คือผ่าน)"""
    if grade not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(grade) <= GRADE_ORDER.index(minimum)


class StudentStatus(models.TextChoices):
    ACTIVE = "active", "ปกติ"
    PROBATION = "probation", "รอพินิจ"
    SUSPENDED = "suspended", "พักการเรียน / ถูกตัดสิทธิ์"


# ---------------------------------------------------------------------------
# ลำดับชั้นองค์กร: University -> Faculty -> Department -> Curriculum
# ---------------------------------------------------------------------------

class University(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name_plural = "Universities"

    def __str__(self):
        return self.name


class Faculty(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="faculties")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=200)

    class Meta:
        unique_together = ("university", "code")
        verbose_name_plural = "Faculties"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=200)

    class Meta:
        unique_together = ("faculty", "code")

    def __str__(self):
        return f"{self.code} - {self.name}"


class Curriculum(models.Model):
    """หลักสูตร เช่น 'วศ.บ. วิศวกรรมคอมพิวเตอร์ (หลักสูตรปรับปรุง 2565)'"""

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="curricula")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)

    class Meta:
        unique_together = ("department", "code")
        verbose_name_plural = "Curricula"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Program(models.Model):
    """เงื่อนไข #9: 'ภาค' ของแต่ละภาควิชา (เช่น ภาคปกติ/ภาคพิเศษ) — แต่ละภาควิชากำหนดรายการของตัวเองได้"""

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="programs")
    name = models.CharField(max_length=100, help_text="เช่น ภาคปกติ, ภาคพิเศษ, ภาคนานาชาติ")

    class Meta:
        unique_together = ("department", "name")
        ordering = ["department__code", "name"]

    def __str__(self):
        return f"{self.department.code} - {self.name}"


# ---------------------------------------------------------------------------
# นักศึกษา — สังกัดหลักสูตร (Curriculum) โดยตรง ตาม ER diagram
# ---------------------------------------------------------------------------

class Student(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student_id = models.CharField(max_length=15, unique=True)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, related_name="students")
    program = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name="students",
        help_text="ภาคของนักศึกษา (ต้องอยู่ในภาควิชาเดียวกับ curriculum.department)",
    )
    year_level = models.PositiveSmallIntegerField(default=1)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=StudentStatus.choices, default=StudentStatus.ACTIVE)

    def __str__(self):
        return f"{self.student_id} - {self.user.get_full_name() or self.user.username}"

    @property
    def department(self) -> Department:
        return self.curriculum.department

    @property
    def max_credits(self) -> int:
        """เงื่อนไข #7: โควตาหน่วยกิตขึ้นกับสถานภาพนักศึกษา"""
        if self.status == StudentStatus.PROBATION:
            return settings.MAX_CREDITS_PROBATION
        return settings.MAX_CREDITS_NORMAL


# ---------------------------------------------------------------------------
# วิชา — Subject เป็นรายวิชาในคลังกลาง ผูกกับภาควิชาที่เป็นเจ้าของวิชา
# Curriculum เลือก Subject มาประกอบเป็นหลักสูตรผ่าน CurriculumSubject (พร้อมระบุหมวดวิชา)
# ---------------------------------------------------------------------------

class Subject(models.Model):
    code = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=200)
    credits = models.PositiveSmallIntegerField()
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="subjects")
    prerequisites = models.ManyToManyField(
        "self", through="Prerequisite", symmetrical=False, related_name="unlocks"
    )

    def __str__(self):
        return f"{self.code} {self.name}"


class SubjectCategory(models.TextChoices):
    CORE = "core", "Core Subject (วิชาแกน)"
    MAJOR_ELECTIVE = "major_elective", "Major Elective (วิชาเลือกสาขา)"
    GENED = "gened", "GenEd (วิชาศึกษาทั่วไป)"


class CurriculumSubject(models.Model):
    """วิชาที่หลักสูตรหนึ่งๆ บรรจุไว้ พร้อมระบุว่าเป็นวิชาแกน/เลือกสาขา/ศึกษาทั่วไป"""

    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, related_name="curriculum_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="curriculum_links")
    category = models.CharField(max_length=20, choices=SubjectCategory.choices)

    class Meta:
        unique_together = ("curriculum", "subject")

    def __str__(self):
        return f"{self.curriculum.code}: {self.subject.code} ({self.get_category_display()})"


class Prerequisite(models.Model):
    """เงื่อนไข #2: subject ต้องผ่าน required_subject ด้วยเกรดขั้นต่ำ min_grade ก่อน"""

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="prerequisite_links")
    required_subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="required_for_links")
    min_grade = models.CharField(max_length=2, choices=[(g, g) for g in GRADE_ORDER], default="D")

    class Meta:
        unique_together = ("subject", "required_subject")

    def clean(self):
        if self.subject_id == self.required_subject_id:
            raise ValidationError("วิชาไม่สามารถเป็น prerequisite ของตัวเองได้")

    def __str__(self):
        return f"{self.subject.code} ต้องผ่าน {self.required_subject.code} (ขั้นต่ำ {self.min_grade})"


class Semester(models.Model):
    year = models.PositiveSmallIntegerField(help_text="ปีการศึกษา เช่น 2569")
    term = models.PositiveSmallIntegerField(help_text="ภาคเรียน 1/2/3(ฤดูร้อน)")
    registration_start = models.DateTimeField()
    registration_end = models.DateTimeField()
    withdrawal_deadline = models.DateTimeField(
        help_text="เส้นตายการถอนวิชา (แยกจากช่วงลงทะเบียน)"
    )

    class Meta:
        unique_together = ("year", "term")
        ordering = ["-year", "-term"]

    def __str__(self):
        return f"{self.year}/{self.term}"


# ---------------------------------------------------------------------------
# การเปิดสอน: Subject -> OpenClass (เปิดสอนเทอมไหน) -> Section (กลุ่มเรียนย่อย)
# ---------------------------------------------------------------------------

class OpenClass(models.Model):
    """วิชาที่ถูกเปิดสอนในภาคการศึกษาหนึ่งๆ (อาจมีหลาย Section ย่อยอยู่ข้างใน)"""

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="open_classes")
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name="open_classes")

    class Meta:
        unique_together = ("subject", "semester")

    def __str__(self):
        return f"{self.subject.code} ({self.semester})"


class Section(models.Model):
    """1 Section = 1 กลุ่มเรียนย่อยของ OpenClass อาจมีหลาย ScheduleSlot (lecture+lab) ผูกกันเป็นก้อนเดียว -> เงื่อนไข #5"""

    open_class = models.ForeignKey(OpenClass, on_delete=models.CASCADE, related_name="sections")
    section_number = models.CharField(max_length=10)
    instructor_name = models.CharField(max_length=200)
    program = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name="sections",
        null=True, blank=True,
        help_text="เงื่อนไข #9: ล็อกว่า section นี้เปิดรับเฉพาะภาคไหน (เว้นว่าง = ทุกภาคลงได้)",
    )
    max_capacity = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("open_class", "section_number")

    def __str__(self):
        return f"{self.open_class.subject.code}-{self.section_number} ({self.open_class.semester})"

    @property
    def subject(self) -> Subject:
        return self.open_class.subject

    @property
    def semester(self) -> Semester:
        return self.open_class.semester

    @property
    def enrolled_count(self) -> int:
        return self.enrollments.filter(status=Enrollment.Status.ENROLLED).count()

    @property
    def seats_remaining(self) -> int:
        return self.max_capacity - self.enrolled_count

    def is_full(self) -> bool:
        """เงื่อนไข #6: เต็มแล้ว = ปฏิเสธ ไม่มี waitlist"""
        return self.enrolled_count >= self.max_capacity


class SlotType(models.TextChoices):
    LECTURE = "lecture", "บรรยาย"
    LAB = "lab", "ปฏิบัติการ"


class ScheduleSlot(models.Model):
    """เงื่อนไข #4 + #5: หนึ่ง section มีได้หลายช่วงเวลา ต้องเช็ค conflict ทุกช่วง"""

    DAYS = [
        (0, "จันทร์"), (1, "อังคาร"), (2, "พุธ"), (3, "พฤหัสบดี"),
        (4, "ศุกร์"), (5, "เสาร์"), (6, "อาทิตย์"),
    ]

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="slots")
    slot_type = models.CharField(max_length=10, choices=SlotType.choices, default=SlotType.LECTURE)
    day_of_week = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)

    def overlaps(self, other: "ScheduleSlot") -> bool:
        if self.day_of_week != other.day_of_week:
            return False
        return self.start_time < other.end_time and self.end_time > other.start_time

    def __str__(self):
        return f"{self.section} [{self.get_slot_type_display()}] {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"


class EnrollmentType(models.TextChoices):
    CREDIT = "credit", "นับหน่วยกิต"
    AUDIT = "audit", "audit (ไม่นับหน่วยกิต)"


class Enrollment(models.Model):
    """การลงทะเบียนของนักศึกษาในแต่ละ section"""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", "ลงทะเบียนอยู่"
        WITHDRAWN = "withdrawn", "ถอนแล้ว"
        COMPLETED = "completed", "เรียนจบแล้ว (มีเกรด)"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="enrollments")
    enrollment_type = models.CharField(
        max_length=10, choices=EnrollmentType.choices, default=EnrollmentType.CREDIT
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ENROLLED)
    grade = models.CharField(max_length=2, blank=True, null=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # เงื่อนไข #3: กันลงทะเบียนซ้ำ section เดียวกัน (สถานะ enrolled ซ้ำ)
        constraints = [
            models.UniqueConstraint(
                fields=["student", "section"],
                condition=models.Q(status="enrolled"),
                name="unique_active_enrollment_per_section",
            )
        ]

    def __str__(self):
        return f"{self.student.student_id} -> {self.section} ({self.get_status_display()})"

    @property
    def counts_toward_credits(self) -> bool:
        """เงื่อนไข #7: audit ไม่นับหน่วยกิต"""
        return self.enrollment_type == EnrollmentType.CREDIT

    @property
    def total_paid(self):
        return self.payments.filter(status=Payment.Status.PAID).aggregate(
            total=models.Sum("amount")
        )["total"] or 0

    @property
    def amount_due(self):
        return self.fee_amount - self.total_paid

    @property
    def fee_amount(self):
        """ค่าลงทะเบียนของ enrollment นี้ = หน่วยกิต x อัตราต่อหน่วยกิต (audit ก็ต้องจ่ายเหมือนกันตามนโยบายทั่วไป)"""
        return self.section.subject.credits * settings.CREDIT_FEE_RATE


class Payment(models.Model):
    """การชำระเงินค่าลงทะเบียน — 1 enrollment จ่ายได้หลายงวด (ผ่อนชำระ) จึงเป็น 1:N"""

    class Status(models.TextChoices):
        PENDING = "pending", "รอชำระ"
        PAID = "paid", "ชำระแล้ว"
        FAILED = "failed", "ชำระไม่สำเร็จ"

    class Method(models.TextChoices):
        CASH = "cash", "เงินสด"
        BANK_TRANSFER = "bank_transfer", "โอนเงิน"
        CREDIT_CARD = "credit_card", "บัตรเครดิต"
        QR_PROMPTPAY = "qr_promptpay", "พร้อมเพย์"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.QR_PROMPTPAY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.enrollment} - {self.amount} บาท ({self.get_status_display()})"
