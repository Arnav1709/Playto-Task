from django.contrib import admin

from .models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "created_at")
    search_fields = ("name", "email")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "bank_name", "masked_account_number", "ifsc")
    list_filter = ("bank_name",)
    search_fields = ("merchant__name", "masked_account_number", "ifsc")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "amount_paise", "status", "attempt_count", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "merchant__name")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "entry_type", "amount_paise", "payout", "created_at")
    list_filter = ("entry_type",)
    search_fields = ("merchant__name", "description")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "key", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("merchant__name", "key")

