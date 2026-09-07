from django import forms

from .models import EnrollmentType


class EnrollForm(forms.Form):
    section_id = forms.IntegerField(widget=forms.HiddenInput)
    enrollment_type = forms.ChoiceField(
        choices=EnrollmentType.choices,
        initial=EnrollmentType.CREDIT,
        widget=forms.RadioSelect,
    )
