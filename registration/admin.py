from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from .models import (
    University,
    Faculty,
    Department,
    Curriculum,
    CurriculumSubject,
    Program,
    Student,
    Subject,
    Prerequisite,
    Semester,
    OpenClass,
    Section,
    ScheduleSlot,
    Enrollment,
    Payment,
)


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "university")
    list_filter = ("university",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "faculty")
    list_filter = ("faculty",)


class CurriculumSubjectInline(admin.TabularInline):
    model = CurriculumSubject
    extra = 1


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department")
    list_filter = ("department",)
    inlines = [CurriculumSubjectInline]


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    """ภาคของแต่ละภาควิชา (เช่น CPE มีภาคปกติ/ภาคพิเศษของตัวเอง) — จัดการที่นี่ก่อนไปตั้งใน Student/Section"""
    list_display = ("department", "name")
    list_filter = ("department",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "curriculum", "program", "year_level", "status", "gpa")
    list_filter = ("program", "status", "curriculum")
    search_fields = ("student_id", "user__username", "user__first_name", "user__last_name")

    class Media:
        js = ("registration/admin_program_filter.js",)

    def get_urls(self):
        custom = [
            path(
                "programs-for-curriculum/<int:curriculum_id>/",
                self.admin_site.admin_view(self.programs_for_curriculum),
                name="registration_student_programs_for_curriculum",
            ),
        ]
        return custom + super().get_urls()

    def programs_for_curriculum(self, request, curriculum_id):
        curriculum = Curriculum.objects.filter(pk=curriculum_id).select_related("department").first()
        if not curriculum:
            return JsonResponse({"programs": []})
        programs = list(
            Program.objects.filter(department=curriculum.department).order_by("name").values("id", "name")
        )
        return JsonResponse({"programs": programs})


class PrerequisiteInline(admin.TabularInline):
    model = Prerequisite
    fk_name = "subject"
    extra = 1


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "credits", "department")
    list_filter = ("department",)
    search_fields = ("code", "name")
    inlines = [PrerequisiteInline]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("year", "term", "registration_start", "registration_end", "withdrawal_deadline")


@admin.register(OpenClass)
class OpenClassAdmin(admin.ModelAdmin):
    list_display = ("subject", "semester")
    list_filter = ("semester", "subject__department")


class ScheduleSlotInline(admin.TabularInline):
    model = ScheduleSlot
    extra = 1


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("open_class", "section_number", "program", "instructor_name", "seats_remaining", "max_capacity")
    list_filter = ("open_class__semester", "program")
    inlines = [ScheduleSlotInline]

    class Media:
        js = ("registration/admin_program_filter.js",)

    def seats_remaining(self, obj):
        return obj.seats_remaining

    def get_urls(self):
        custom = [
            path(
                "programs-for-openclass/<int:open_class_id>/",
                self.admin_site.admin_view(self.programs_for_openclass),
                name="registration_section_programs_for_openclass",
            ),
        ]
        return custom + super().get_urls()

    def programs_for_openclass(self, request, open_class_id):
        open_class = OpenClass.objects.filter(pk=open_class_id).select_related("subject__department").first()
        if not open_class:
            return JsonResponse({"programs": []})
        programs = list(
            Program.objects.filter(department=open_class.subject.department).order_by("name").values("id", "name")
        )
        return JsonResponse({"programs": programs})


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "section", "enrollment_type", "status", "grade", "enrolled_at")
    list_filter = ("status", "enrollment_type", "section__open_class__semester")
    search_fields = ("student__student_id", "section__open_class__subject__code")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "amount", "method", "status", "paid_at", "created_at")
    list_filter = ("status", "method")
    search_fields = ("enrollment__student__student_id",)
