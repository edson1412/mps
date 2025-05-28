from django import forms
from .models import *
from accounts.models import CustomUser
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from dateutil.relativedelta import relativedelta

User = get_user_model()

class PrisonStationForm(forms.ModelForm):
    class Meta:
        model = PrisonStation
        fields = ['name', 'code', 'location', 'capacity', 'date_established']
        widgets = {
            'date_established': forms.DateInput(attrs={'type': 'date'}),
        }

class PrisonerForm(forms.ModelForm):
    class Meta:
        model = Prisoner
        exclude = ['created_by', 'last_modified', 'is_active']
        widgets = {
            'date_admitted': forms.DateInput(attrs={'type': 'date'}),
            'image': forms.FileInput(attrs={'accept': 'image/*'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user and not self.user.is_superuser:
            self.fields['prison_station'].queryset = PrisonStation.objects.filter(name=self.user.prison_station)

class ConvictedPrisonerForm(forms.ModelForm):
    class Meta:
        model = ConvictedPrisoner
        exclude = ['prisoner', 'release_date', 'date_of_release_on_remission']
        widgets = {
            'date_of_committal': forms.DateInput(attrs={'type': 'date'}),
            'wef_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'reduction_notes': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields explicit
        self.fields['reduction_months'].required = False
        self.fields['reduction_notes'].required = False
        self.fields['notes'].required = False

class RemandPrisonerForm(forms.ModelForm):
    class Meta:
        model = RemandPrisoner
        exclude = ['prisoner']
        widgets = {
            'next_court_date': forms.DateInput(attrs={'type': 'date'}),
        }

class RiskAssessmentForm(forms.ModelForm):
    class Meta:
        model = RiskAssessment
        exclude = ['prisoner']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['previous_convictions_count'].required = False

class PrisonerParticularsForm(forms.ModelForm):
    class Meta:
        model = PrisonerParticulars
        exclude = ['prisoner']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields explicit
        self.fields['denomination'].required = False
        self.fields['spouse_name'].required = False
        self.fields['spouse_location'].required = False
        self.fields['mobile_number'].required = False
        self.fields['national_id'].required = False
        self.fields['passport_number'].required = False
        self.fields['driving_license'].required = False
        self.fields['profession'].required = False
        self.fields['past_occupation'].required = False
        self.fields['home_location'].required = False

class PhysicalCharacteristicsForm(forms.ModelForm):
    class Meta:
        model = PhysicalCharacteristics
        exclude = ['prisoner']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['head_abnormalities'].required = False
        self.fields['marks_tattoos_scars'].required = False
        self.fields['children_count'].required = False

class RehabilitationProgramForm(forms.ModelForm):
    class Meta:
        model = RehabilitationProgram
        exclude = ['prisoner']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program_name'].required = False
        self.fields['program_level'].required = False

class PrisonerTransferForm(forms.ModelForm):
    class Meta:
        model = PrisonerTransfer
        fields = ['to_prison', 'reason']
    
    def __init__(self, *args, **kwargs):
        self.prisoner = kwargs.pop('prisoner', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.prisoner:
            self.fields['to_prison'].queryset = PrisonStation.objects.exclude(id=self.prisoner.prison_station.id)

class SentenceReductionForm(forms.ModelForm):
    class Meta:
        model = ConvictedPrisoner
        fields = ['reduction_months', 'reduction_notes']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reduction_months'].required = False
        self.fields['reduction_notes'].required = False

class SearchForm(forms.Form):
    search_query = forms.CharField(required=False, label='Search Prisoners')
    prisoner_class = forms.ChoiceField(
        choices=[('', 'All')] + Prisoner.PRISONER_CLASS_CHOICES,
        required=False,
        label='Prisoner Class'
    )
    prison_station = forms.ModelChoiceField(
        queryset=PrisonStation.objects.all(),
        required=False,
        label='Prison Station'
    )
    risk_level = forms.ChoiceField(
        choices=[('', 'All')] + RiskAssessment.RISK_LEVEL_CHOICES,
        required=False,
        label='Risk Level'
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and not user.is_superuser:
            self.fields['prison_station'].queryset = PrisonStation.objects.filter(name=user.prison_station)
            self.fields['prison_station'].initial = PrisonStation.objects.get(name=user.prison_station)
            self.fields['prison_station'].widget.attrs['disabled'] = True