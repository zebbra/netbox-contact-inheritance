from django.urls import path

from . import views

urlpatterns = [
    path('effective-contacts/', views.EffectiveContactsView.as_view(), name='effective-contacts'),
]
