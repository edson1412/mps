from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q, Sum
from django.template.loader import get_template
from django.views.generic import ListView
from xhtml2pdf import pisa
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .models import *
from .forms import *
from accounts.models import CustomUser
import io
import csv
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    # Prisoner statistics
    prisoners = Prisoner.objects.filter(is_active=True)
    
    if not request.user.is_superuser:
        prisoners = prisoners.filter(prison_station__name=request.user.prison_station)
    
    total_prisoners = prisoners.count()
    convicted_count = prisoners.filter(prisoner_class='convicted').count()
    remand_count = prisoners.filter(prisoner_class='remand').count()
    
    # Children count (from female prisoners)
    female_prisoners = prisoners.filter(sex='female')
    children_count = sum([p.physical.children_count for p in female_prisoners if hasattr(p, 'physical') and p.physical.children_count]) if female_prisoners.exists() else 0
    
    # Recidivism rate
    risk_assessments = RiskAssessment.objects.filter(prisoner__in=prisoners)
    recidivism_count = risk_assessments.filter(previous_conviction=True).count()
    recidivism_rate = (recidivism_count / total_prisoners * 100) if total_prisoners > 0 else 0
    
    # Prisoner population for current month and last 5 months
    months = []
    prisoner_counts = []
    today = datetime.now().date()
    
    for i in range(5, -1, -1):  # From 5 months ago to current month
        month_start = (today - relativedelta(months=i)).replace(day=1)
        month_end = (month_start + relativedelta(months=1) - relativedelta(days=1))
        month_name = month_start.strftime('%b %Y')
        
        count = prisoners.filter(
            date_admitted__lte=month_end,
            is_active=True
        ).count()
        
        months.append(month_name)
        prisoner_counts.append(count)
    
    # Debug: Log the population data
    logger.debug(f"Months: {months}, Prisoner Counts: {prisoner_counts}")
    
    # Upcoming releases (next 30 days)
    today = datetime.now().date()
    next_month = today + timedelta(days=30)
    
    upcoming_releases = []
    if request.user.is_superuser or prisoners.exists():
        convicted_prisoners = ConvictedPrisoner.objects.filter(
            Q(date_of_release_on_remission__gte=today) & 
            Q(date_of_release_on_remission__lte=next_month)
        )
        
        if not request.user.is_superuser:
            convicted_prisoners = convicted_prisoners.filter(prisoner__prison_station__name=request.user.prison_station)
        
        upcoming_releases = convicted_prisoners.order_by('date_of_release_on_remission')[:10]
    
    # Recent activities
    recent_activities = ActivityLog.objects.all().order_by('-timestamp')[:10] if request.user.is_superuser else None
    
    # Lockup summary
    lockup_summary = {
        'male_convicted': prisoners.filter(sex='male', prisoner_class='convicted').count(),
        'female_convicted': prisoners.filter(sex='female', prisoner_class='convicted').count(),
        'male_remand': prisoners.filter(sex='male', prisoner_class='remand').count(),
        'female_remand': prisoners.filter(sex='female', prisoner_class='remand').count(),
        'male_murder_convicted': ConvictedPrisoner.objects.filter(
            prisoner__sex='male', 
            prisoner__prisoner_class='convicted',
            offense__in=['Murder contrary to section 209 of the Penal Code']
        ).count(),
        'female_murder_convicted': ConvictedPrisoner.objects.filter(
            prisoner__sex='female', 
            prisoner__prisoner_class='convicted',
            offense__in=['Murder contrary to section 209 of the Penal Code']
        ).count(),
        'male_foreigner_remand': prisoners.filter(sex='male', prisoner_class='remand', 
            particulars__nationality__in=['mozambican', 'zimbabwean', 'congolese', 'zambian', 'tanzanian', 
                                        'chinese', 'japanese', 'korean', 'indian', 'british', 'south_african', 
                                        'burundi', 'rwandan', 'botswana']).count(),
        'female_foreigner_remand': prisoners.filter(sex='female', prisoner_class='remand', 
            particulars__nationality__in=['mozambican', 'zimbabwean', 'congolese', 'zambian', 'tanzanian', 
                                        'chinese', 'japanese', 'korean', 'indian', 'british', 'south_african', 
                                        'burundi', 'rwandan', 'botswana']).count(),
        'male_foreigner_remand_murder': ConvictedPrisoner.objects.filter(
            prisoner__sex='male', 
            prisoner__prisoner_class='remand',
            offense__in=['Murder contrary to section 209 of the Penal Code'],
            prisoner__particulars__nationality__in=['mozambican', 'zimbabwean', 'congolese', 'zambian', 'tanzanian', 
                                                  'chinese', 'japanese', 'korean', 'indian', 'british', 'south_african', 
                                                  'burundi', 'rwandan', 'botswana']
        ).count(),
        'female_foreigner_remand_murder': ConvictedPrisoner.objects.filter(
            prisoner__sex='female', 
            prisoner__prisoner_class='remand',
            offense__in=['Murder contrary to section 209 of the Penal Code'],
            prisoner__particulars__nationality__in=['mozambican', 'zimbabwean', 'congolese', 'zambian', 'tanzanian', 
                                                  'chinese', 'japanese', 'korean', 'indian', 'british', 'south_african', 
                                                  'burundi', 'rwandan', 'botswana']
        ).count(),
        'children': children_count,
        'grand_total': total_prisoners,
    }
    
    context = {
        'total_prisoners': total_prisoners,
        'convicted_count': convicted_count,
        'remand_count': remand_count,
        'children_count': children_count,
        'recidivism_rate': round(recidivism_rate, 2),
        'months': months,
        'prisoner_counts': prisoner_counts,
        'upcoming_releases': upcoming_releases,
        'recent_activities': recent_activities,
        'lockup_summary': lockup_summary,
    }
    
    return render(request, 'prison/dashboard.html', context)

@login_required
def prisoner_list(request):
    form = SearchForm(request.GET or None, user=request.user)
    
    # Base queryset
    prisoners = Prisoner.objects.filter(is_active=True)
    
    # Filter by station for non-superusers
    if not request.user.is_superuser:
        if request.user.prison_station:
            prisoners = prisoners.filter(prison_station=request.user.prison_station)
        else:
            prisoners = Prisoner.objects.none()
            messages.warning(request, "You haven't been assigned to a prison station.")
    
    # Apply search filters if form is valid
    if form.is_valid():
        search_query = form.cleaned_data.get('search_query')
        prisoner_class = form.cleaned_data.get('prisoner_class')
        risk_level = form.cleaned_data.get('risk_level')
        
        if search_query:
            prisoners = prisoners.filter(
                Q(prisoner_number__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(middle_name__icontains=search_query) |
                Q(surname__icontains=search_query)
            )
        
        if prisoner_class:
            prisoners = prisoners.filter(prisoner_class=prisoner_class)
        
        if risk_level:
            prisoner_ids = RiskAssessment.objects.filter(
                risk_level=risk_level
            ).values_list('prisoner_id', flat=True)
            prisoners = prisoners.filter(id__in=prisoner_ids)
    
    context = {
        'prisoners': prisoners,
        'form': form,
    }
    return render(request, 'prison/prisoner_list.html', context)

@login_required
def add_prisoner(request):
    if request.method == 'POST':
        prisoner_form = PrisonerForm(request.POST, request.FILES, user=request.user)
        
        if prisoner_form.is_valid():
            prisoner = prisoner_form.save(commit=False)
            prisoner.created_by = request.user
            prisoner.save()
            
            # Create related records based on prisoner class
            if prisoner.prisoner_class == 'convicted':
                return redirect('add_convicted_details', prisoner_id=prisoner.id)
            else:
                return redirect('add_remand_details', prisoner_id=prisoner.id)
    else:
        prisoner_form = PrisonerForm(user=request.user)
    
    context = {
        'prisoner_form': prisoner_form,
    }
    return render(request, 'prison/add_prisoner.html', context)

@login_required
def add_convicted_details(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    if request.method == 'POST':
        form = ConvictedPrisonerForm(request.POST)
        particulars_form = PrisonerParticularsForm(request.POST)
        physical_form = PhysicalCharacteristicsForm(request.POST)
        risk_form = RiskAssessmentForm(request.POST)
        rehab_form = RehabilitationProgramForm(request.POST)
        
        if all([
            form.is_valid(),
            particulars_form.is_valid(),
            physical_form.is_valid(),
            risk_form.is_valid(),
            rehab_form.is_valid()
        ]):
            # Save convicted details
            convicted = form.save(commit=False)
            convicted.prisoner = prisoner
            convicted.save()
            
            # Save particulars
            particulars = particulars_form.save(commit=False)
            particulars.prisoner = prisoner
            particulars.save()
            
            # Save physical characteristics
            physical = physical_form.save(commit=False)
            physical.prisoner = prisoner
            physical.save()
            
            # Save risk assessment
            risk = risk_form.save(commit=False)
            risk.prisoner = prisoner
            risk.save()
            
            # Save rehabilitation program
            rehab = rehab_form.save(commit=False)
            rehab.prisoner = prisoner
            rehab.save()
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='create',
                model='ConvictedPrisoner',
                object_id=prisoner.id,
                details=f'Added convicted prisoner {prisoner.prisoner_number}'
            )
            
            messages.success(request, 'Convicted prisoner details added successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
        else:
            # Log validation errors
            logger.error(f"Convicted details form errors: {form.errors}")
            logger.error(f"Particulars form errors: {particulars_form.errors}")
            logger.error(f"Physical form errors: {physical_form.errors}")
            logger.error(f"Risk form errors: {risk_form.errors}")
            logger.error(f"Rehab form errors: {rehab_form.errors}")
            messages.error(request, 'Please correct the errors in the form.')
    else:
        form = ConvictedPrisonerForm()
        particulars_form = PrisonerParticularsForm()
        physical_form = PhysicalCharacteristicsForm()
        risk_form = RiskAssessmentForm()
        rehab_form = RehabilitationProgramForm()
    
    context = {
        'prisoner': prisoner,
        'form': form,
        'particulars_form': particulars_form,
        'physical_form': physical_form,
        'risk_form': risk_form,
        'rehab_form': rehab_form,
    }
    return render(request, 'prison/add_convicted_details.html', context)

@login_required
def add_remand_details(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    if request.method == 'POST':
        form = RemandPrisonerForm(request.POST)
        particulars_form = PrisonerParticularsForm(request.POST)
        physical_form = PhysicalCharacteristicsForm(request.POST)
        
        if all([
            form.is_valid(),
            particulars_form.is_valid(),
            physical_form.is_valid(),
        ]):
            # Save remand details
            remand = form.save(commit=False)
            remand.prisoner = prisoner
            remand.save()
            
            # Save particulars
            particulars = particulars_form.save(commit=False)
            particulars.prisoner = prisoner
            particulars.save()
            
            # Save physical characteristics
            physical = physical_form.save(commit=False)
            physical.prisoner = prisoner
            physical.save()
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='create',
                model='RemandPrisoner',
                object_id=prisoner.id,
                details=f'Added remand prisoner {prisoner.prisoner_number}'
            )
            
            messages.success(request, 'Remand prisoner details added successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
        else:
            # Log validation errors
            logger.error(f"Remand form errors: {form.errors}")
            logger.error(f"Particulars form errors: {particulars_form.errors}")
            logger.error(f"Physical form errors: {physical_form.errors}")
            messages.error(request, 'Please correct the errors in the form.')
    else:
        form = RemandPrisonerForm()
        particulars_form = PrisonerParticularsForm()
        physical_form = PhysicalCharacteristicsForm()
    
    context = {
        'prisoner': prisoner,
        'form': form,
        'particulars_form': particulars_form,
        'physical_form': physical_form,
    }
    return render(request, 'prison/add_remand_details.html', context)

@login_required
def prisoner_detail(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    transfers = prisoner.transfers.all()

    context = {
        'prisoner': prisoner,
        'transfers': transfers,
    }

    try:
        context['physical'] = prisoner.physical
        context['particulars'] = prisoner.particulars
    except ObjectDoesNotExist:
        messages.error(request, f"Critical data (Particulars or Physical) is missing for prisoner {prisoner.prisoner_number}. Please edit the prisoner to add the missing information.")
        # Redirect to the appropriate edit page if essential data is missing
        if prisoner.prisoner_class == 'convicted':
            return redirect('edit_convicted_details', prisoner_id=prisoner.id)
        else:
            return redirect('edit_remand_details', prisoner_id=prisoner.id)


    if prisoner.prisoner_class == 'convicted':
        try:
            context['convicted_details'] = prisoner.convicted_details
            context['risk_assessment'] = prisoner.risk_assessment
            context['rehabilitation'] = prisoner.rehabilitation
        except ObjectDoesNotExist:
            messages.error(request, f"Convicted prisoner details are missing. Please add them.")
            return redirect('edit_convicted_details', prisoner_id=prisoner.id)
    else:
        try:
            context['remand_details'] = prisoner.remand_details
        except ObjectDoesNotExist:
            messages.error(request, f"Remand prisoner details are missing. Please add them.")
            return redirect('edit_remand_details', prisoner_id=prisoner.id)


    return render(request, 'prison/prisoner_detail.html', context)

@login_required
def edit_prisoner(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    # Check if user has permission to edit this prisoner
    if not request.user.is_superuser and prisoner.prison_station.name != request.user.prison_station:
        messages.error(request, 'You do not have permission to edit this prisoner.')
        return redirect('prisoner_list')
    
    if request.method == 'POST':
        form = PrisonerForm(request.POST, request.FILES, instance=prisoner, user=request.user)
        
        if form.is_valid():
            form.save()
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='update',
                model='Prisoner',
                object_id=prisoner.id,
                details=f'Updated prisoner {prisoner.prisoner_number}'
            )
            
            messages.success(request, 'Prisoner updated successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
    else:
        form = PrisonerForm(instance=prisoner, user=request.user)
    
    context = {
        'form': form,
        'prisoner': prisoner,
    }
    return render(request, 'prison/edit_prisoner.html', context)

@login_required
def edit_convicted_details(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)

    if prisoner.prisoner_class != 'convicted':
        messages.error(request, 'This prisoner is not a convicted prisoner.')
        return redirect('prisoner_detail', prisoner_id=prisoner.id)

    # Use get_or_create to handle cases where related objects might not exist yet
    convicted, _ = ConvictedPrisoner.objects.get_or_create(prisoner=prisoner)
    particulars, _ = PrisonerParticulars.objects.get_or_create(prisoner=prisoner)
    physical, _ = PhysicalCharacteristics.objects.get_or_create(prisoner=prisoner)
    risk, _ = RiskAssessment.objects.get_or_create(prisoner=prisoner)
    rehab, _ = RehabilitationProgram.objects.get_or_create(prisoner=prisoner)

    if request.method == 'POST':
        prisoner_form = PrisonerForm(request.POST, request.FILES, instance=prisoner, user=request.user)
        convicted_form = ConvictedPrisonerForm(request.POST, instance=convicted)
        particulars_form = PrisonerParticularsForm(request.POST, instance=particulars)
        physical_form = PhysicalCharacteristicsForm(request.POST, instance=physical)
        risk_form = RiskAssessmentForm(request.POST, instance=risk)
        rehab_form = RehabilitationProgramForm(request.POST, instance=rehab)

        if all([
            prisoner_form.is_valid(),
            convicted_form.is_valid(),
            particulars_form.is_valid(),
            physical_form.is_valid(),
            risk_form.is_valid(),
            rehab_form.is_valid()
        ]):
            prisoner_form.save()
            convicted_form.save()
            particulars_form.save()
            physical_form.save()
            risk_form.save()
            rehab_form.save()

            ActivityLog.objects.create(
                user=request.user,
                action='update',
                model='ConvictedPrisoner',
                object_id=prisoner.id,
                details=f'Updated all details for convicted prisoner {prisoner.prisoner_number}'
            )

            messages.success(request, 'Convicted prisoner details updated successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
        else:
            messages.error(request, "Please correct the validation errors.")

    else:
        prisoner_form = PrisonerForm(instance=prisoner, user=request.user)
        convicted_form = ConvictedPrisonerForm(instance=convicted)
        particulars_form = PrisonerParticularsForm(instance=particulars)
        physical_form = PhysicalCharacteristicsForm(instance=physical)
        risk_form = RiskAssessmentForm(instance=risk)
        rehab_form = RehabilitationProgramForm(instance=rehab)

    context = {
        'prisoner': prisoner,
        'prisoner_form': prisoner_form,
        'convicted_form': convicted_form,
        'particulars_form': particulars_form,
        'physical_form': physical_form,
        'risk_form': risk_form,
        'rehab_form': rehab_form,
    }
    return render(request, 'prison/edit_convicted_details.html', context)

@login_required
def edit_remand_details(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)

    if prisoner.prisoner_class != 'remand':
        messages.error(request, 'This prisoner is not a remand prisoner.')
        return redirect('prisoner_detail', prisoner_id=prisoner.id)
    
    # Use get_or_create to handle cases where related objects might not exist yet
    remand, _ = RemandPrisoner.objects.get_or_create(prisoner=prisoner)
    particulars, _ = PrisonerParticulars.objects.get_or_create(prisoner=prisoner)
    physical, _ = PhysicalCharacteristics.objects.get_or_create(prisoner=prisoner)

    if request.method == 'POST':
        prisoner_form = PrisonerForm(request.POST, request.FILES, instance=prisoner, user=request.user)
        remand_form = RemandPrisonerForm(request.POST, instance=remand)
        particulars_form = PrisonerParticularsForm(request.POST, instance=particulars)
        physical_form = PhysicalCharacteristicsForm(request.POST, instance=physical)

        if all([
            prisoner_form.is_valid(),
            remand_form.is_valid(),
            particulars_form.is_valid(),
            physical_form.is_valid(),
        ]):
            prisoner_form.save()
            remand_form.save()
            particulars_form.save()
            physical_form.save()

            ActivityLog.objects.create(
                user=request.user,
                action='update',
                model='RemandPrisoner',
                object_id=prisoner.id,
                details=f'Updated all details for remand prisoner {prisoner.prisoner_number}'
            )

            messages.success(request, 'Remand prisoner details updated successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
        else:
            messages.error(request, "Please correct the validation errors.")
    else:
        prisoner_form = PrisonerForm(instance=prisoner, user=request.user)
        remand_form = RemandPrisonerForm(instance=remand)
        particulars_form = PrisonerParticularsForm(instance=particulars)
        physical_form = PhysicalCharacteristicsForm(instance=physical)

    context = {
        'prisoner': prisoner,
        'prisoner_form': prisoner_form,
        'form': remand_form,
        'particulars_form': particulars_form,
        'physical_form': physical_form,
    }
    return render(request, 'prison/edit_remand_details.html', context)

@login_required
def delete_prisoner(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    # Check if user has permission to delete this prisoner
    if not request.user.is_superuser and prisoner.prison_station.name != request.user.prison_station:
        messages.error(request, 'You do not have permission to delete this prisoner.')
        return redirect('prisoner_list')
    
    if request.method == 'POST':
        prisoner.is_active = False
        prisoner.save()
        
        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action='delete',
            model='Prisoner',
            object_id=prisoner.id,
            details=f'Deleted prisoner {prisoner.prisoner_number}'
        )
        
        messages.success(request, 'Prisoner deleted successfully.')
        return redirect('prisoner_list')
    
    return render(request, 'prison/delete_prisoner.html', {'prisoner': prisoner})

@login_required
def transfer_prisoner(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    # Only admin can transfer prisoners
    if not request.user.is_superuser:
        messages.error(request, 'Only administrators can transfer prisoners.')
        return redirect('prisoner_detail', prisoner_id=prisoner.id)
    
    if request.method == 'POST':
        form = PrisonerTransferForm(request.POST, prisoner=prisoner, user=request.user)
        
        if form.is_valid():
            transfer = form.save(commit=False)
            transfer.prisoner = prisoner
            transfer.from_prison = prisoner.prison_station
            transfer.transferred_by = request.user
            transfer.save()
            
            # Update prisoner's prison station
            prisoner.prison_station = transfer.to_prison
            prisoner.save()
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='transfer',
                model='Prisoner',
                object_id=prisoner.id,
                details=f'Transferred prisoner {prisoner.prisoner_number} from {transfer.from_prison} to {transfer.to_prison}'
            )
            
            messages.success(request, 'Prisoner transferred successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
    else:
        form = PrisonerTransferForm(prisoner=prisoner, user=request.user)
    
    context = {
        'form': form,
        'prisoner': prisoner,
    }
    return render(request, 'prison/transfer_prisoner.html', context)

@login_required
def apply_sentence_reduction(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    # Check if prisoner is convicted
    if prisoner.prisoner_class != 'convicted':
        messages.error(request, 'Sentence reduction only applies to convicted prisoners.')
        return redirect('prisoner_detail', prisoner_id=prisoner.id)
    
    # Check if user has permission
  
    
    convicted = prisoner.convicted_details
    
    if request.method == 'POST':
        form = SentenceReductionForm(request.POST, instance=convicted)
        
        if form.is_valid():
            form.save()
            
            # Create release on remission record
            ReleaseOnRemission.objects.create(
                prisoner=prisoner,
                release_date=convicted.date_of_release_on_remission,
                original_sentence=convicted.sentence,
                remission_months=convicted.sentence / 3,
                reduction_months=convicted.reduction_months,
                reduction_reason=convicted.reduction_notes,
                processed_by=request.user
            )
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='update',
                model='ConvictedPrisoner',
                object_id=prisoner.id,
                details=f'Applied sentence reduction to prisoner {prisoner.prisoner_number}'
            )
            
            messages.success(request, 'Sentence reduction applied successfully.')
            return redirect('prisoner_detail', prisoner_id=prisoner.id)
    else:
        form = SentenceReductionForm(instance=convicted)
    
    context = {
        'form': form,
        'prisoner': prisoner,
        'convicted': convicted,
    }
    return render(request, 'prison/apply_sentence_reduction.html', context)

@login_required
def generate_prisoner_report(request, prisoner_id):
    prisoner = get_object_or_404(Prisoner, id=prisoner_id)
    
    # Check if user has permission to view this prisoner
    if not request.user.is_superuser and prisoner.prison_station.name != request.user.prison_station:
        messages.error(request, 'You do not have permission to view this prisoner.')
        return redirect('prisoner_list')
    
    template = get_template('prison/prisoner_report.html')
    
    context = {
        'prisoner': prisoner,
        'today': datetime.now().date(),
    }
    
    if prisoner.prisoner_class == 'convicted':
        context.update({
            'convicted_details': prisoner.convicted_details,
            'particulars': prisoner.particulars,
            'risk_assessment': prisoner.risk_assessment,
            'rehabilitation': prisoner.rehabilitation,
        })
    else:
        context['remand_details'] = prisoner.remand_details
    
    context.update({
        'particulars': prisoner.particulars,
        'physical': prisoner.physical,
    })
    
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="prisoner_{prisoner.prisoner_number}_report.pdf"'
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('We had some errors generating the PDF')
    
    return response

@login_required
def upcoming_releases_report(request):
    today = datetime.now().date()
    next_month = today + timedelta(days=30)
    
    prisoners = Prisoner.objects.filter(is_active=True)
    
    if not request.user.is_superuser:
        prisoners = prisoners.filter(prison_station__name=request.user.prison_station)
    
    convicted_prisoners = ConvictedPrisoner.objects.filter(
        prisoner__in=prisoners,
        date_of_release_on_remission__gte=today,
        date_of_release_on_remission__lte=next_month
    ).order_by('date_of_release_on_remission')
    
    if request.GET.get('format') == 'pdf':
        template = get_template('prison/upcoming_releases_pdf.html')
        
        context = {
            'releases': convicted_prisoners,
            'today': today,
            'next_month': next_month,
            'user': request.user,
        }
        
        html = template.render(context)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="upcoming_releases_report.pdf"'
        
        pisa_status = pisa.CreatePDF(html, dest=response)
        
        if pisa_status.err:
            return HttpResponse('We had some errors generating the PDF')
        
        return response
    elif request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="upcoming_releases_report.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Prisoner Number', 'Name', 'Prison Station', 
            'Release Date', 'Original Sentence (months)', 
            'Remission Months', 'Reduction Months', 'Offense'
        ])
        
        for cp in convicted_prisoners:
            writer.writerow([
                cp.prisoner.prisoner_number,
                cp.prisoner.full_name,
                cp.prisoner.prison_station.name,
                cp.date_of_release_on_remission.strftime('%Y-%m-%d'),
                cp.sentence,
                round(cp.sentence / 3, 2),
                cp.reduction_months,
                cp.offense,
            ])
        
        return response
    
    context = {
        'releases': convicted_prisoners,
        'today': today,
        'next_month': next_month,
    }
    return render(request, 'prison/upcoming_releases.html', context)

@login_required
def create_prison_station(request):
    if request.method == 'POST':
        form = PrisonStationForm(request.POST)
        if form.is_valid():
            station = form.save(commit=False)
            station.created_by = request.user
            station.save()
            messages.success(request, f'Prison station "{station.name}" created successfully!')
            return redirect('manage_prison_stations')
    else:
        form = PrisonStationForm()
    
    return render(request, 'prison/create_prison_station.html', {'form': form})


def manage_prison_stations(request):
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    
    stations = PrisonStation.objects.all()
    
    if request.method == 'POST':
        form = PrisonStationForm(request.POST)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Prison station added successfully.')
            return redirect('manage_prison_stations')
    else:
        form = PrisonStationForm()
    
    context = {
        'stations': stations,
        'form': form,
    }
    return render(request, 'prison/manage_prison_stations.html', context)

@login_required
def edit_prison_station(request, station_id):
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    
    station = get_object_or_404(PrisonStation, id=station_id)
    
    if request.method == 'POST':
        form = PrisonStationForm(request.POST, instance=station)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Prison station updated successfully.')
            return redirect('manage_prison_stations')
    else:
        form = PrisonStationForm(instance=station)
    
    context = {
        'form': form,
        'station': station,
    }
    return render(request, 'prison/edit_prison_station.html', context)

@login_required
def delete_prison_station(request, station_id):
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    
    station = get_object_or_404(PrisonStation, id=station_id)
    
    if request.method == 'POST':
        # Check if station has prisoners
        if Prisoner.objects.filter(prison_station=station).exists():
            messages.error(request, 'Cannot delete prison station with assigned prisoners.')
            return redirect('manage_prison_stations')
        
        station.delete()
        messages.success(request, 'Prison station deleted successfully.')
        return redirect('manage_prison_stations')
    
    return render(request, 'prison/delete_prison_station.html', {'station': station})

def prison_statistics_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    prisoners = Prisoner.objects.filter(is_active=True)
    
    if not request.user.is_superuser:
        prisoners = prisoners.filter(prison_station__name=request.user.prison_station)
    
    # Prisoner counts by class
    counts_by_class = prisoners.values('prisoner_class').annotate(count=Count('id'))
    
    # Prisoner counts by station (for admin)
    counts_by_station = []
    if request.user.is_superuser:
        counts_by_station = PrisonStation.objects.annotate(
            prisoner_count=Count('prisoner', filter=Q(prisoner__is_active=True))
        ).values('name', 'prisoner_count')
    
    # Risk level distribution
    risk_distribution = RiskAssessment.objects.filter(
        prisoner__in=prisoners
    ).values('risk_level').annotate(count=Count('id'))
    
    # Recidivism rate
    recidivism_count = RiskAssessment.objects.filter(
        prisoner__in=prisoners,
        previous_conviction=True
    ).count()
    recidivism_rate = (recidivism_count / prisoners.count() * 100) if prisoners.count() > 0 else 0
    
    # Children count (from female prisoners)
    female_prisoners = prisoners.filter(sex='female')
    children_count = sum([p.physical.children_count for p in female_prisoners if hasattr(p, 'physical') and p.physical.children_count])
    
    data = {
        'counts_by_class': list(counts_by_class),
        'counts_by_station': list(counts_by_station),
        'risk_distribution': list(risk_distribution),
        'recidivism_rate': round(recidivism_rate, 2),
        'total_prisoners': prisoners.count(),
        'children_count': children_count,
    }
    
    return JsonResponse(data)