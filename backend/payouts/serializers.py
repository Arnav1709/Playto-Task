from rest_framework import serializers

from .models import BankAccount, LedgerEntry, Merchant, Payout


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "name", "email"]


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ["id", "account_holder_name", "bank_name", "masked_account_number", "ifsc"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    signed_amount_paise = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount_paise",
            "signed_amount_paise",
            "description",
            "payout_id",
            "created_at",
        ]

    def get_signed_amount_paise(self, obj: LedgerEntry) -> int:
        if obj.entry_type == LedgerEntry.Type.DEBIT:
            return -obj.amount_paise
        return obj.amount_paise


class PayoutSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "amount_paise",
            "status",
            "attempt_count",
            "bank_account",
            "processing_started_at",
            "last_attempted_at",
            "next_retry_at",
            "completed_at",
            "failed_at",
            "failure_reason",
            "created_at",
            "updated_at",
        ]

