import uuid

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BankAccount, LedgerEntry, Merchant, Payout
from .serializers import BankAccountSerializer, LedgerEntrySerializer, MerchantSerializer, PayoutSerializer
from .services import balances_for_merchant, create_payout_idempotently


def merchant_id_from_request(request) -> tuple[str | None, Response | None]:
    merchant_id = request.headers.get("X-Merchant-ID")
    if not merchant_id:
        return None, Response(
            {"error": "missing_merchant", "message": "X-Merchant-ID header is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        uuid.UUID(str(merchant_id))
    except ValueError:
        return None, Response(
            {"error": "invalid_merchant", "message": "X-Merchant-ID must be a valid UUID."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not Merchant.objects.filter(id=merchant_id).exists():
        return None, Response(
            {"error": "merchant_not_found", "message": "Merchant does not exist."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return str(merchant_id), None


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.all()
        return Response({"merchants": MerchantSerializer(merchants, many=True).data})


class DashboardView(APIView):
    def get(self, request):
        merchant_id, error = merchant_id_from_request(request)
        if error:
            return error

        merchant = get_object_or_404(Merchant, id=merchant_id)
        recent_ledger_entries = LedgerEntry.objects.filter(merchant=merchant).select_related("payout")[:12]
        recent_payouts = (
            Payout.objects.filter(merchant=merchant)
            .select_related("bank_account")
            .order_by("-created_at")[:12]
        )
        bank_accounts = BankAccount.objects.filter(merchant=merchant)

        return Response(
            {
                "merchant": MerchantSerializer(merchant).data,
                **balances_for_merchant(merchant_id),
                "bank_accounts": BankAccountSerializer(bank_accounts, many=True).data,
                "recent_ledger_entries": LedgerEntrySerializer(recent_ledger_entries, many=True).data,
                "recent_payouts": PayoutSerializer(recent_payouts, many=True).data,
            }
        )


class PayoutListCreateView(APIView):
    def get(self, request):
        merchant_id, error = merchant_id_from_request(request)
        if error:
            return error

        payouts = (
            Payout.objects.filter(merchant_id=merchant_id)
            .select_related("bank_account")
            .order_by("-created_at")
        )
        return Response({"payouts": PayoutSerializer(payouts, many=True).data})

    def post(self, request):
        merchant_id, error = merchant_id_from_request(request)
        if error:
            return error

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"error": "missing_idempotency_key", "message": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            uuid.UUID(str(idempotency_key))
        except ValueError:
            return Response(
                {"error": "invalid_idempotency_key", "message": "Idempotency-Key must be a UUID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_paise = request.data.get("amount_paise")
        bank_account_id = request.data.get("bank_account_id")

        if isinstance(amount_paise, bool) or not isinstance(amount_paise, int):
            return Response(
                {"error": "invalid_amount", "message": "amount_paise must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount_paise <= 0:
            return Response(
                {"error": "invalid_amount", "message": "amount_paise must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not bank_account_id:
            return Response(
                {"error": "missing_bank_account", "message": "bank_account_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body, status_code = create_payout_idempotently(
            merchant_id=merchant_id,
            amount_paise=amount_paise,
            bank_account_id=str(bank_account_id),
            idempotency_key=str(idempotency_key),
        )
        return Response(body, status=status_code)


class PayoutDetailView(APIView):
    def get(self, request, payout_id):
        merchant_id, error = merchant_id_from_request(request)
        if error:
            return error

        payout = get_object_or_404(
            Payout.objects.select_related("bank_account"),
            id=payout_id,
            merchant_id=merchant_id,
        )
        return Response(PayoutSerializer(payout).data)

