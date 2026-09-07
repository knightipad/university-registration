from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q

from .forms import EnrollForm
from .models import Enrollment, Payment, Section, Semester, Student
from .services import enroll_student, pay_for_enrollment, withdraw_enrollment


def _get_student(request):
    """คืนค่า Student ของผู้ใช้ที่ login อยู่ หรือ None ถ้าบัญชีนี้ไม่ใช่นักศึกษา (เช่น บัญชี admin)"""
    try:
        return request.user.student
    except Student.DoesNotExist:
        return None


def _current_semester():
    """เลือกเทอมที่ช่วงลงทะเบียนกำลังเปิดอยู่ ถ้าไม่มีให้ใช้เทอมล่าสุด"""
    from django.utils import timezone

    now = timezone.now()
    open_semester = Semester.objects.filter(registration_start__lte=now, registration_end__gte=now).first()
    return open_semester or Semester.objects.first()


@login_required
def browse_sections(request):
    student = _get_student(request)
    if student is None:
        messages.error(request, "บัญชีนี้ไม่มีข้อมูลนักศึกษาผูกอยู่ (เช่น บัญชีแอดมิน) กรุณา login ด้วยบัญชีนักศึกษา หรือใช้หน้า /admin/ แทน")
        return render(request, "registration/browse_sections.html", {"student": None, "semester": None, "sections": [], "form": EnrollForm()})

    semester = _current_semester()
    form = EnrollForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            enrollment = enroll_student(
                student=student,
                section_id=form.cleaned_data["section_id"],
                enrollment_type=form.cleaned_data["enrollment_type"],
            )
            messages.success(request, f"ลงทะเบียน {enrollment.section} สำเร็จ ค่าลงทะเบียน {enrollment.fee_amount:.2f} บาท (ดูรายละเอียดที่ตารางเรียนของฉัน)")
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else str(e))
        return redirect("browse_sections")

    sections = []
    if semester:
        sections = (
            Section.objects.filter(open_class__semester=semester)
            .filter(Q(program__isnull=True) | Q(program=student.program))
            .select_related("open_class__subject", "open_class__semester", "program")
            .prefetch_related("slots")
        )

    return render(
        request,
        "registration/browse_sections.html",
        {"student": student, "semester": semester, "sections": sections, "form": form},
    )


@login_required
def my_schedule(request):
    student = _get_student(request)
    if student is None:
        messages.error(request, "บัญชีนี้ไม่มีข้อมูลนักศึกษาผูกอยู่ (เช่น บัญชีแอดมิน) กรุณา login ด้วยบัญชีนักศึกษา หรือใช้หน้า /admin/ แทน")
        return render(request, "registration/my_schedule.html", {"student": None, "enrollments": [], "total_credits": 0})

    if request.method == "POST":
        if "enrollment_id" in request.POST:
            try:
                withdraw_enrollment(student, request.POST.get("enrollment_id"))
                messages.success(request, "ถอนวิชาสำเร็จ")
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else str(e))
        elif "payment_id" in request.POST:
            try:
                payment = pay_for_enrollment(student, request.POST.get("payment_id"), request.POST.get("method", Payment.Method.QR_PROMPTPAY))
                messages.success(request, f"ชำระเงิน {payment.amount:.2f} บาท สำเร็จ")
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else str(e))
        return redirect("my_schedule")

    enrollments = (
        Enrollment.objects.filter(student=student, status=Enrollment.Status.ENROLLED)
        .select_related("section__open_class__subject", "section__open_class__semester")
        .prefetch_related("section__slots", "payments")
    )
    total_credits = sum(
        e.section.subject.credits for e in enrollments if e.counts_toward_credits
    )

    return render(
        request,
        "registration/my_schedule.html",
        {"student": student, "enrollments": enrollments, "total_credits": total_credits},
    )
