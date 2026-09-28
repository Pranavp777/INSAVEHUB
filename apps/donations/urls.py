from django.urls import path

from apps.donations import views

app_name = "donations"

urlpatterns = [
    path("donations/", views.donation_index_view, name="index"),
    path("donations/create/", views.create_donation_view, name="create"),
    path("donations/verify/", views.verify_donation_payment_view, name="verify"),
    path("donations/receipt/<str:donation_id>/", views.donation_receipt_view, name="receipt"),
]
