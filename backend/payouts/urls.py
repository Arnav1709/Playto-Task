from django.urls import path

from .views import DashboardView, MerchantListView, PayoutDetailView, PayoutListCreateView

urlpatterns = [
    path("merchants", MerchantListView.as_view(), name="merchant-list"),
    path("merchants/", MerchantListView.as_view(), name="merchant-list-slash"),
    path("merchant/dashboard", DashboardView.as_view(), name="dashboard"),
    path("merchant/dashboard/", DashboardView.as_view(), name="dashboard-slash"),
    path("payouts", PayoutListCreateView.as_view(), name="payout-list-create"),
    path("payouts/", PayoutListCreateView.as_view(), name="payout-list-create-slash"),
    path("payouts/<uuid:payout_id>", PayoutDetailView.as_view(), name="payout-detail"),
    path("payouts/<uuid:payout_id>/", PayoutDetailView.as_view(), name="payout-detail-slash"),
]

