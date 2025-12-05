"""Management command to set up the phone system."""

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import PhoneNumber, User
from core.services.telephony import TelephonyException, TelephonyService


class Command(BaseCommand):
    """Set up the phone system: assign phone numbers and create dispatch rules."""

    help = "Set up the phone system with phone numbers and SIP dispatch rules"

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone-number",
            type=str,
            help="Phone number to assign (E.164 format, e.g., +14155551234)",
        )
        parser.add_argument(
            "--user-email",
            type=str,
            help="Email of the user to assign the phone number to",
        )
        parser.add_argument(
            "--create-dispatch-rules",
            action="store_true",
            help="Create SIP dispatch rules for lobby phone numbers",
        )
        parser.add_argument(
            "--delete-dispatch-rules",
            action="store_true",
            help="Delete existing lobby dispatch rules",
        )

    def handle(self, *args, **options):
        phone_number = options.get("phone_number")
        user_email = options.get("user_email")
        create_rules = options.get("create_dispatch_rules")
        delete_rules = options.get("delete_dispatch_rules")

        # Assign phone number to user
        if phone_number and user_email:
            self._assign_phone_number(phone_number, user_email)

        # Handle dispatch rules
        if delete_rules:
            self._delete_dispatch_rules()

        if create_rules:
            self._create_dispatch_rules()

    def _assign_phone_number(self, phone_number: str, user_email: str):
        """Assign a phone number to a user."""
        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"User with email '{user_email}' not found")
            )
            return

        phone, created = PhoneNumber.objects.update_or_create(
            phone_number=phone_number,
            defaults={
                "user": user,
                "is_active": True,
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created phone number {phone_number} for user {user_email}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated phone number {phone_number} for user {user_email}"
                )
            )

    def _create_dispatch_rules(self):
        """Create lobby dispatch rules."""
        if not settings.PHONE_SYSTEM_ENABLED:
            self.stderr.write(
                self.style.WARNING(
                    "Phone system not enabled. Set PHONE_SYSTEM_ENABLED=True"
                )
            )
            return

        lobby_numbers = settings.PHONE_SYSTEM_LOBBY_PHONE_NUMBERS
        if not lobby_numbers:
            self.stderr.write(
                self.style.WARNING(
                    "No lobby phone numbers configured. "
                    "Set PHONE_SYSTEM_LOBBY_PHONE_NUMBERS"
                )
            )
            return

        self.stdout.write(
            f"Creating dispatch rules for lobby numbers: {lobby_numbers}"
        )

        try:
            telephony = TelephonyService()
            telephony.create_lobby_dispatch_rules()
            self.stdout.write(
                self.style.SUCCESS("Successfully created lobby dispatch rules")
            )
        except TelephonyException as e:
            self.stderr.write(
                self.style.ERROR(f"Failed to create dispatch rules: {e}")
            )

    def _delete_dispatch_rules(self):
        """Delete lobby dispatch rules."""
        self.stdout.write("Deleting existing lobby dispatch rules...")

        try:
            telephony = TelephonyService()
            telephony.delete_lobby_dispatch_rules()
            self.stdout.write(
                self.style.SUCCESS("Successfully deleted lobby dispatch rules")
            )
        except TelephonyException as e:
            self.stderr.write(
                self.style.ERROR(f"Failed to delete dispatch rules: {e}")
            )
