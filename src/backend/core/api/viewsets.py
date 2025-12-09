"""API endpoints"""

import uuid
from logging import getLogger
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.text import slugify

from rest_framework import decorators, mixins, pagination, throttling, viewsets
from rest_framework import (
    exceptions as drf_exceptions,
)
from rest_framework import (
    response as drf_response,
)
from rest_framework import (
    status as drf_status,
)

from core import enums, models, utils
from core.recording.enums import FileExtension
from core.recording.event.authentication import StorageEventAuthentication
from core.recording.event.exceptions import (
    InvalidBucketError,
    InvalidFileTypeError,
    ParsingEventDataError,
)
from core.recording.event.notification import notification_service
from core.recording.event.parsers import get_parser
from core.recording.worker.exceptions import (
    RecordingStartError,
    RecordingStopError,
)
from core.recording.worker.factories import (
    get_worker_service,
)
from core.recording.worker.mediator import (
    WorkerServiceMediator,
)
from core.services.invitation import InvitationService
from core.services.livekit_events import (
    LiveKitEventsService,
    LiveKitWebhookError,
)
from core.services.lobby import (
    LobbyParticipantNotFound,
    LobbyService,
)
from core.services.participants_management import (
    ParticipantsManagement,
    ParticipantsManagementException,
)
from core.services.room_creation import RoomCreation
from core.services.subtitle import SubtitleException, SubtitleService

from ..authentication.livekit import LiveKitTokenAuthentication
from . import permissions, serializers
from .feature_flag import FeatureFlag

# pylint: disable=too-many-ancestors

logger = getLogger(__name__)


class NestedGenericViewSet(viewsets.GenericViewSet):
    """
    A generic Viewset aims to be used in a nested route context.
    e.g: `/api/v1.0/resource_1/<resource_1_pk>/resource_2/<resource_2_pk>/`

    It allows to define all url kwargs and lookup fields to perform the lookup.
    """

    lookup_fields: list[str] = ["pk"]
    lookup_url_kwargs: list[str] = []

    def __getattribute__(self, item):
        """
        This method is overridden to allow to get the last lookup field or lookup url kwarg
        when accessing the `lookup_field` or `lookup_url_kwarg` attribute. This is useful
        to keep compatibility with all methods used by the parent class `GenericViewSet`.
        """
        if item in ["lookup_field", "lookup_url_kwarg"]:
            return getattr(self, item + "s", [None])[-1]

        return super().__getattribute__(item)

    def get_queryset(self):
        """
        Get the list of items for this view.

        `lookup_fields` attribute is enumerated here to perform the nested lookup.
        """
        queryset = super().get_queryset()

        # The last lookup field is removed to perform the nested lookup as it corresponds
        # to the object pk, it is used within get_object method.
        lookup_url_kwargs = (
            self.lookup_url_kwargs[:-1]
            if self.lookup_url_kwargs
            else self.lookup_fields[:-1]
        )

        filter_kwargs = {}
        for index, lookup_url_kwarg in enumerate(lookup_url_kwargs):
            if lookup_url_kwarg not in self.kwargs:
                raise KeyError(
                    f"Expected view {self.__class__.__name__} to be called with a URL "
                    f'keyword argument named "{lookup_url_kwarg}". Fix your URL conf, or '
                    "set the `.lookup_fields` attribute on the view correctly."
                )

            filter_kwargs.update(
                {self.lookup_fields[index]: self.kwargs[lookup_url_kwarg]}
            )

        return queryset.filter(**filter_kwargs)


class SerializerPerActionMixin:
    """
    A mixin to allow to define serializer classes for each action.

    This mixin is useful to avoid to define a serializer class for each action in the
    `get_serializer_class` method.
    """

    serializer_classes: dict[str, type] = {}
    default_serializer_class: type = None

    def get_serializer_class(self):
        """
        Return the serializer class to use depending on the action.
        """
        return self.serializer_classes.get(self.action, self.default_serializer_class)


class Pagination(pagination.PageNumberPagination):
    """Pagination to display no more than 100 objects per page sorted by creation date."""

    ordering = "-created_on"
    max_page_size = 100
    page_size_query_param = "page_size"


class UserViewSet(
    mixins.UpdateModelMixin, viewsets.GenericViewSet, mixins.ListModelMixin
):
    """User ViewSet"""

    permission_classes = [permissions.IsSelf]
    queryset = models.User.objects.all()
    serializer_class = serializers.UserSerializer

    def get_queryset(self):
        """
        Limit listed users by querying the email field with a trigram similarity
        search if a query is provided.
        Limit listed users by excluding users already in the document if a document_id
        is provided.
        """
        queryset = self.queryset

        if self.action == "list":
            if not settings.ALLOW_UNSECURE_USER_LISTING:
                return models.User.objects.none()

            # Filter users by email similarity
            if query := self.request.GET.get("q", ""):
                queryset = queryset.filter(email__trigram_word_similar=query)

        return queryset

    @decorators.action(
        detail=False,
        methods=["get"],
        url_name="me",
        url_path="me",
        permission_classes=[permissions.IsAuthenticated],
    )
    def get_me(self, request):
        """
        Return information on currently logged user
        """
        context = {"request": request}
        return drf_response.Response(
            self.serializer_class(request.user, context=context).data
        )


class RequestEntryAnonRateThrottle(throttling.AnonRateThrottle):
    """Throttle Anonymous user requesting room entry"""

    scope = "request_entry"


class CreationCallbackAnonRateThrottle(throttling.AnonRateThrottle):
    """Throttle Anonymous user requesting room generation callback"""

    scope = "creation_callback"


class RoomViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoints to access and perform actions on rooms.
    """

    permission_classes = [permissions.RoomPermissions]
    queryset = models.Room.objects.all()
    serializer_class = serializers.RoomSerializer

    def get_object(self):
        """Allow getting a room by its slug."""
        try:
            uuid.UUID(self.kwargs["pk"])
            filter_kwargs = {"pk": self.kwargs["pk"]}
        except ValueError:
            filter_kwargs = {"slug": slugify(self.kwargs["pk"])}
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, **filter_kwargs)
        # May raise a permission denied
        self.check_object_permissions(self.request, obj)
        return obj

    def retrieve(self, request, *args, **kwargs):
        """
        Allow unregistered rooms when activated.
        For unregistered rooms we only return a null id and the livekit room and token.
        """
        try:
            instance = self.get_object()
        except Http404:
            if not settings.ALLOW_UNREGISTERED_ROOMS:
                raise
            slug = slugify(self.kwargs["pk"])
            username = request.query_params.get("username", None)
            data = {
                "id": None,
                "livekit": {
                    "url": settings.LIVEKIT_CONFIGURATION["url"],
                    "room": slug,
                    "token": utils.generate_token(
                        room=slug, user=request.user, username=username
                    ),
                },
            }
        else:
            data = self.get_serializer(instance).data

        return drf_response.Response(data)

    def list(self, request, *args, **kwargs):
        """Limit listed rooms to the ones related to the authenticated user."""
        user = self.request.user

        if user.is_authenticated:
            queryset = (
                self.filter_queryset(self.get_queryset()).filter(users=user).distinct()
            )
        else:
            queryset = self.get_queryset().none()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return drf_response.Response(serializer.data)

    def perform_create(self, serializer):
        """Set the current user as owner of the newly created room."""
        room = serializer.save()
        models.ResourceAccess.objects.create(
            resource=room,
            user=self.request.user,
            role=models.RoleChoices.OWNER,
        )

        if callback_id := self.request.data.get("callback_id"):
            RoomCreation().persist_callback_state(callback_id, room)

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="start-recording",
        permission_classes=[
            permissions.HasPrivilegesOnRoom,
        ],
    )
    @FeatureFlag.require("recording")
    def start_room_recording(self, request, pk=None):  # pylint: disable=unused-argument
        """Start recording a room."""

        serializer = serializers.StartRecordingSerializer(data=request.data)

        if not serializer.is_valid():
            return drf_response.Response(
                {"detail": "Invalid request."}, status=drf_status.HTTP_400_BAD_REQUEST
            )

        mode = serializer.validated_data["mode"]
        room = self.get_object()

        # May raise exception if an active or initiated recording already exist for the room
        recording = models.Recording.objects.create(room=room, mode=mode)

        models.RecordingAccess.objects.create(
            user=self.request.user, role=models.RoleChoices.OWNER, recording=recording
        )

        worker_service = get_worker_service(mode=recording.mode)
        worker_manager = WorkerServiceMediator(worker_service=worker_service)

        try:
            worker_manager.start(recording)
        except RecordingStartError:
            return drf_response.Response(
                {"error": f"Recording failed to start for room {room.slug}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {"message": f"Recording successfully started for room {room.slug}"},
            status=drf_status.HTTP_201_CREATED,
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="stop-recording",
        permission_classes=[
            permissions.HasPrivilegesOnRoom,
        ],
    )
    @FeatureFlag.require("recording")
    def stop_room_recording(self, request, pk=None):  # pylint: disable=unused-argument
        """Stop room recording."""

        room = self.get_object()

        try:
            recording = models.Recording.objects.get(
                room=room, status=models.RecordingStatusChoices.ACTIVE
            )
        except models.Recording.DoesNotExist as e:
            raise drf_exceptions.NotFound(
                "No active recording found for this room."
            ) from e

        worker_service = get_worker_service(mode=recording.mode)
        worker_manager = WorkerServiceMediator(worker_service=worker_service)

        try:
            worker_manager.stop(recording)
        except RecordingStopError:
            return drf_response.Response(
                {"error": f"Recording failed to stop for room {room.slug}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {"message": f"Recording stopped for room {room.slug}."}
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="request-entry",
        permission_classes=[],
        throttle_classes=[RequestEntryAnonRateThrottle],
    )
    def request_entry(self, request, pk=None):  # pylint: disable=unused-argument
        """Request entry to a room"""

        serializer = serializers.RequestEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room = self.get_object()
        lobby_service = LobbyService()

        participant, livekit = lobby_service.request_entry(
            room=room,
            request=request,
            **serializer.validated_data,
        )
        response = drf_response.Response({**participant.to_dict(), "livekit": livekit})
        lobby_service.prepare_response(response, participant.id)

        return response

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="enter",
        permission_classes=[
            permissions.HasPrivilegesOnRoom,
        ],
    )
    def allow_participant_to_enter(self, request, pk=None):  # pylint: disable=unused-argument
        """Accept or deny a participant's entry request."""

        serializer = serializers.ParticipantEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room = self.get_object()

        if room.is_public:
            return drf_response.Response(
                {"message": "Room has no lobby system."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        lobby_service = LobbyService()

        try:
            lobby_service.handle_participant_entry(
                room_id=room.id,
                participant_id=str(serializer.validated_data.get("participant_id")),
                allow_entry=serializer.validated_data.get("allow_entry"),
            )
            return drf_response.Response({"message": "Participant was updated."})

        except LobbyParticipantNotFound:
            return drf_response.Response(
                {"message": "Participant not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

    @decorators.action(
        detail=True,
        methods=["GET"],
        url_path="waiting-participants",
        permission_classes=[
            permissions.HasPrivilegesOnRoom,
        ],
    )
    def list_waiting_participants(self, request, pk=None):  # pylint: disable=unused-argument
        """List waiting participants."""
        room = self.get_object()

        if room.is_public:
            return drf_response.Response({"participants": []})

        lobby_service = LobbyService()

        participants = lobby_service.list_waiting_participants(room.id)
        return drf_response.Response({"participants": participants})

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="webhooks-livekit",
        permission_classes=[],
    )
    def webhooks_livekit(self, request):
        """Process webhooks from LiveKit."""

        livekit_events_service = LiveKitEventsService()

        try:
            livekit_events_service.receive(request)
            return drf_response.Response(
                {"status": "success"}, status=drf_status.HTTP_200_OK
            )
        except LiveKitWebhookError as e:
            status_code = getattr(e, "status_code", drf_status.HTTP_400_BAD_REQUEST)

            if status_code == drf_status.HTTP_500_INTERNAL_SERVER_ERROR:
                raise e

            return drf_response.Response(
                {"status": "error", "message": str(e)}, status=status_code
            )

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="creation-callback",
        permission_classes=[],
        throttle_classes=[CreationCallbackAnonRateThrottle],
    )
    def creation_callback(self, request):
        """Retrieve cached room data via an unauthenticated request with a unique ID.

        Designed for interoperability across iframes, popups, and other contexts,
        even on the same domain, bypassing browser security restrictions on direct communication.
        """

        serializer = serializers.CreationCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room = RoomCreation().get_callback_state(
            callback_id=serializer.validated_data.get("callback_id")
        )

        return drf_response.Response(
            {"status": "success", "room": room}, status=drf_status.HTTP_200_OK
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="invite",
        permission_classes=[
            permissions.HasPrivilegesOnRoom,
        ],
    )
    def invite(self, request, pk=None):  # pylint: disable=unused-argument
        """Send email invitations to join a room.

        This API endpoint allows a user with appropriate privileges to send email invitations
        to one or more recipients, inviting them to join the specified room.
        """

        room = self.get_object()

        serializer = serializers.RoomInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        emails = serializer.validated_data.get("emails")
        emails = list(set(emails))

        InvitationService().invite_to_room(
            room=room, sender=request.user, emails=emails
        )

        return drf_response.Response(
            {"status": "success", "message": "invitations sent"},
            status=drf_status.HTTP_200_OK,
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="start-subtitle",
        permission_classes=[
            permissions.HasLiveKitRoomAccess,
        ],
        authentication_classes=[LiveKitTokenAuthentication],
    )
    @FeatureFlag.require("subtitle")
    def start_subtitle(self, request, pk=None):  # pylint: disable=unused-argument
        """Start realtime transcription for the room.

        Requires valid LiveKit token for room authorization.
        Anonymous users can start subtitles if they have room access tokens.
        """

        room = self.get_object()

        try:
            SubtitleService().start_subtitle(room)
        except SubtitleException:
            return drf_response.Response(
                {"error": f"Subtitles failed to start for room {room.slug}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {"status": "success"}, status=drf_status.HTTP_200_OK
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="mute-participant",
        url_name="mute-participant",
        permission_classes=[permissions.HasPrivilegesOnRoom],
    )
    def mute_participant(self, request, pk=None):  # pylint: disable=unused-argument
        """Mute a specific track for a participant in the room."""
        room = self.get_object()

        serializer = serializers.MuteParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ParticipantsManagement().mute(
                room_name=str(room.pk),
                identity=str(serializer.validated_data["participant_identity"]),
                track_sid=serializer.validated_data["track_sid"],
            )
        except ParticipantsManagementException:
            return drf_response.Response(
                {"error": "Failed to mute participant"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {
                "status": "success",
            },
            status=drf_status.HTTP_200_OK,
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="update-participant",
        url_name="update-participant",
        permission_classes=[permissions.HasPrivilegesOnRoom],
    )
    def update_participant(self, request, pk=None):  # pylint: disable=unused-argument
        """Update participant attributes, permissions, or metadata."""
        room = self.get_object()

        serializer = serializers.UpdateParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ParticipantsManagement().update(
                room_name=str(room.pk),
                identity=str(serializer.validated_data["participant_identity"]),
                metadata=serializer.validated_data.get("metadata"),
                attributes=serializer.validated_data.get("attributes"),
                permission=serializer.validated_data.get("permission"),
                name=serializer.validated_data.get("name"),
            )
        except ParticipantsManagementException:
            return drf_response.Response(
                {"error": "Failed to update participant"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {
                "status": "success",
            },
            status=drf_status.HTTP_200_OK,
        )

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="remove-participant",
        url_name="remove-participant",
        permission_classes=[permissions.HasPrivilegesOnRoom],
    )
    def remove_participant(self, request, pk=None):  # pylint: disable=unused-argument
        """Remove a participant from the room."""
        room = self.get_object()

        serializer = serializers.BaseParticipantsManagementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ParticipantsManagement().remove(
                room_name=str(room.pk),
                identity=str(serializer.validated_data["participant_identity"]),
            )
        except ParticipantsManagementException:
            return drf_response.Response(
                {"error": "Failed to remove participant"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {"status": "success"}, status=drf_status.HTTP_200_OK
        )


class ResourceAccessViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoints to access and perform actions on resource accesses.
    """

    permission_classes = [permissions.ResourceAccessPermission]
    queryset = models.ResourceAccess.objects.all()
    serializer_class = serializers.ResourceAccessSerializer

    def get_queryset(self):
        """Return the queryset according to the action."""

        queryset = super().get_queryset()

        # Restrict access to resources the user either has explicit
        # permissions for or administrative privileges over.
        if self.action == "list":
            user = self.request.user
            queryset = queryset.filter(
                Q(resource__accesses__user=user),
                resource__accesses__role__in=[
                    models.RoleChoices.ADMIN,
                    models.RoleChoices.OWNER,
                ],
            ).distinct()

        return queryset


class RecordingViewSet(
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoints to access and perform actions on recordings.
    """

    pagination_class = Pagination
    permission_classes = [permissions.HasAbilityPermission]
    queryset = models.Recording.objects.all()
    serializer_class = serializers.RecordingSerializer

    def get_queryset(self):
        """Restrict recordings to the user's ones."""
        user = self.request.user
        return (
            super()
            .get_queryset()
            .filter(Q(accesses__user=user) | Q(accesses__team__in=user.get_teams()))
        )

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="storage-hook",
        authentication_classes=[StorageEventAuthentication],
    )
    @FeatureFlag.require("storage_event")
    def on_storage_event_received(self, request, pk=None):  # pylint: disable=unused-argument
        """Handle incoming storage hook events for recordings."""

        parser = get_parser()

        try:
            recording_id = parser.get_recording_id(request.data)

        except ParsingEventDataError as e:
            raise drf_exceptions.PermissionDenied(f"Invalid request data: {e}") from e

        except InvalidBucketError as e:
            raise drf_exceptions.PermissionDenied("Invalid bucket specified") from e

        except InvalidFileTypeError as e:
            return drf_response.Response(
                {"message": f"Ignore this file type, {e}"},
            )

        try:
            recording = models.Recording.objects.get(id=recording_id)
        except models.Recording.DoesNotExist as e:
            raise drf_exceptions.NotFound("No recording found for this event.") from e

        if not recording.is_savable():
            raise drf_exceptions.PermissionDenied(
                f"Recording with ID {recording_id} cannot be saved because it is either,"
                " in an error state or has already been saved."
            )

        # Attempt to notify external services about the recording
        # This is a non-blocking operation - failures are logged but don't interrupt the flow
        notification_succeeded = notification_service.notify_external_services(
            recording
        )

        recording.status = (
            models.RecordingStatusChoices.NOTIFICATION_SUCCEEDED
            if notification_succeeded
            else models.RecordingStatusChoices.SAVED
        )
        recording.save()

        return drf_response.Response(
            {"message": "Event processed."},
        )

    def _auth_get_original_url(self, request):
        """
        Extracts and parses the original URL from the "HTTP_X_ORIGINAL_URL" header.
        Raises PermissionDenied if the header is missing.
        The original url is passed by nginx in the "HTTP_X_ORIGINAL_URL" header.
        See corresponding ingress configuration in Helm chart and read about the
        nginx.ingress.kubernetes.io/auth-url annotation to understand how the Nginx ingress
        is configured to do this.
        Based on the original url and the logged-in user, we must decide if we authorize Nginx
        to let this request go through (by returning a 200 code) or if we block it (by returning
        a 403 error). Note that we return 403 errors without any further details for security
        reasons.
        """
        # Extract the original URL from the request header
        original_url = request.META.get("HTTP_X_ORIGINAL_URL")
        if not original_url:
            logger.debug("Missing HTTP_X_ORIGINAL_URL header in subrequest")
            raise drf_exceptions.PermissionDenied()

        logger.debug("Original url: '%s'", original_url)
        return urlparse(original_url)

    def _auth_get_url_params(self, pattern, fragment):
        """
        Extracts URL parameters from the given fragment using the specified regex pattern.
        Raises PermissionDenied if parameters cannot be extracted.
        """

        match = pattern.search(fragment)

        try:
            return match.groupdict()
        except (ValueError, AttributeError) as exc:
            logger.debug("Failed to extract parameters from subrequest URL: %s", exc)
            raise drf_exceptions.PermissionDenied() from exc

    @decorators.action(detail=False, methods=["get"], url_path="media-auth")
    def media_auth(self, request, *args, **kwargs):
        """
        This view is used by an Nginx subrequest to control access to a recording's
        media file.
        When we let the request go through, we compute authorization headers that will be added to
        the request going through thanks to the nginx.ingress.kubernetes.io/auth-response-headers
        annotation. The request will then be proxied to the object storage backend who will
        respond with the file after checking the signature included in headers.
        """

        parsed_url = self._auth_get_original_url(request)

        url_params = self._auth_get_url_params(
            enums.RECORDING_STORAGE_URL_PATTERN, parsed_url.path
        )

        user = request.user
        recording_id = url_params["recording_id"]

        extension = url_params["extension"]
        if extension not in [item.value for item in FileExtension]:
            raise drf_exceptions.ValidationError({"detail": "Unsupported extension."})

        try:
            recording = models.Recording.objects.get(id=recording_id)
        except models.Recording.DoesNotExist as e:
            raise drf_exceptions.NotFound("No recording found for this event.") from e

        if extension != recording.extension:
            raise drf_exceptions.NotFound("No recording found with this extension.")

        abilities = recording.get_abilities(user)

        if not abilities["retrieve"]:
            logger.debug("User '%s' lacks permission for attachment", user.id)
            raise drf_exceptions.PermissionDenied()

        if not recording.is_saved:
            logger.debug("Recording '%s' has not been saved", recording)
            raise drf_exceptions.PermissionDenied()

        request = utils.generate_s3_authorization_headers(recording.key)

        return drf_response.Response("authorized", headers=request.headers, status=200)


class DeviceViewSet(viewsets.GenericViewSet):
    """API endpoints for push notification device registration."""

    permission_classes = [permissions.IsAuthenticated]

    @decorators.action(detail=False, methods=["post"], url_path="apns/register")
    def register_apns(self, request):
        """Register an APNS device for push notifications."""
        try:
            from push_notifications.models import APNSDevice
        except ImportError:
            return drf_response.Response(
                {"error": "Push notifications not configured"},
                status=drf_status.HTTP_501_NOT_IMPLEMENTED,
            )

        serializer = serializers.APNSDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device, created = APNSDevice.objects.update_or_create(
            registration_id=serializer.validated_data["registration_id"],
            defaults={
                "user": request.user,
                "active": True,
                "device_id": serializer.validated_data.get("device_id"),
                "name": serializer.validated_data.get("name", ""),
            },
        )

        return drf_response.Response(
            {"status": "success", "created": created},
            status=drf_status.HTTP_201_CREATED if created else drf_status.HTTP_200_OK,
        )

    @decorators.action(detail=False, methods=["post"], url_path="apns/unregister")
    def unregister_apns(self, request):
        """Unregister an APNS device."""
        try:
            from push_notifications.models import APNSDevice
        except ImportError:
            return drf_response.Response(
                {"error": "Push notifications not configured"},
                status=drf_status.HTTP_501_NOT_IMPLEMENTED,
            )

        registration_id = request.data.get("registration_id")
        if not registration_id:
            return drf_response.Response(
                {"error": "registration_id required"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        APNSDevice.objects.filter(
            user=request.user,
            registration_id=registration_id,
        ).update(active=False)

        return drf_response.Response({"status": "success"})

    @decorators.action(detail=False, methods=["post"], url_path="webpush/register")
    def register_webpush(self, request):
        """Register a WebPush device for push notifications."""
        try:
            from push_notifications.models import WebPushDevice
        except ImportError:
            return drf_response.Response(
                {"error": "Push notifications not configured"},
                status=drf_status.HTTP_501_NOT_IMPLEMENTED,
            )

        serializer = serializers.WebPushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device, created = WebPushDevice.objects.update_or_create(
            registration_id=serializer.validated_data["registration_id"],
            defaults={
                "user": request.user,
                "active": True,
                "p256dh": serializer.validated_data["p256dh"],
                "auth": serializer.validated_data["auth"],
                "browser": serializer.validated_data.get("browser", ""),
            },
        )

        return drf_response.Response(
            {"status": "success", "created": created},
            status=drf_status.HTTP_201_CREATED if created else drf_status.HTTP_200_OK,
        )

    @decorators.action(detail=False, methods=["post"], url_path="webpush/unregister")
    def unregister_webpush(self, request):
        """Unregister a WebPush device."""
        try:
            from push_notifications.models import WebPushDevice
        except ImportError:
            return drf_response.Response(
                {"error": "Push notifications not configured"},
                status=drf_status.HTTP_501_NOT_IMPLEMENTED,
            )

        registration_id = request.data.get("registration_id")
        if not registration_id:
            return drf_response.Response(
                {"error": "registration_id required"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        WebPushDevice.objects.filter(
            user=request.user,
            registration_id=registration_id,
        ).update(active=False)

        return drf_response.Response({"status": "success"})


class CallViewSet(viewsets.GenericViewSet):
    """API endpoints for managing incoming phone calls."""

    permission_classes = [permissions.IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.services.phone_system import PhoneSystemService

        self.phone_system = PhoneSystemService()

    @decorators.action(detail=False, methods=["get"], url_path="pending")
    def list_pending_calls(self, request):
        """List all pending incoming calls for the current user."""
        pending_calls = self.phone_system.get_user_pending_calls(str(request.user.id))

        return drf_response.Response(
            {
                "calls": [
                    serializers.PendingCallSerializer(
                        {
                            "call_id": call.call_id,
                            "caller_number": call.caller_number,
                            "callee_number": call.callee_number,
                            "lobby_room_name": call.lobby_room_name,
                            "sip_participant_identity": call.sip_participant_identity,
                            "status": call.status,
                            "created_at": call.created_at,
                        }
                    ).data
                    for call in pending_calls
                ]
            }
        )

    @decorators.action(detail=False, methods=["post"], url_path="accept")
    def accept_call(self, request):
        """Accept an incoming call and transfer to a meeting room."""
        from core.services.phone_system import (
            PendingCallStatus,
            TransferError,
        )

        print(f"[DEBUG] Accept call request.data: {request.data}")
        print(f"[DEBUG] Accept call request.data type: {type(request.data)}")

        serializer = serializers.AcceptCallSerializer(data=request.data)
        print(f"[DEBUG] Serializer initial data: {serializer.initial_data}")
        is_valid = serializer.is_valid()
        print(f"[DEBUG] Serializer is_valid: {is_valid}")
        if not is_valid:
            print(f"[DEBUG] Accept call validation errors: {serializer.errors}")
            return drf_response.Response(serializer.errors, status=drf_status.HTTP_400_BAD_REQUEST)

        call_id = str(serializer.validated_data["call_id"])
        print(f"[DEBUG] Looking up pending call with ID: {call_id}")
        pending_call = self.phone_system.get_pending_call(call_id)
        print(f"[DEBUG] Pending call found: {pending_call}")

        if not pending_call:
            print("[DEBUG] Returning 404 - Call not found")
            return drf_response.Response(
                {"error": "Call not found or expired"},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Verify the call belongs to this user
        print(f"[DEBUG] Checking user: pending_call.target_user_id={pending_call.target_user_id}, request.user.id={request.user.id}")
        if pending_call.target_user_id != str(request.user.id):
            print("[DEBUG] Returning 403 - Unauthorized")
            return drf_response.Response(
                {"error": "Unauthorized"},
                status=drf_status.HTTP_403_FORBIDDEN,
            )

        print(f"[DEBUG] Checking status: pending_call.status={pending_call.status}, RINGING={PendingCallStatus.RINGING.value}")
        if pending_call.status != PendingCallStatus.RINGING.value:
            print(f"[DEBUG] Returning 400 - Not in ringing state: {pending_call.status}")
            return drf_response.Response(
                {"error": f"Call is not in ringing state: {pending_call.status}"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        # Room was pre-created when the call arrived (in livekit_events._handle_participant_joined)
        # This allows the push notification to include room_id and room_slug
        try:
            room = models.Room.objects.get(id=pending_call.meeting_room_id)
        except models.Room.DoesNotExist:
            logger.error(
                "Pre-created room %s not found for call %s",
                pending_call.meeting_room_id,
                call_id,
            )
            return drf_response.Response(
                {"error": "Room not found"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Update call status
        self.phone_system.update_call_status(
            call_id,
            PendingCallStatus.ACCEPTED,
        )

        # Signal lobby-bot to answer the call by setting room metadata
        # The lobby-bot watches for {"status": "accepted"} and then publishes
        # its audio track, which triggers livekit-sip to answer the call
        try:
            self.phone_system.signal_call_accepted(pending_call.lobby_room_name, call_id)
        except Exception as e:
            logger.exception("Failed to signal call acceptance for %s", call_id)
            return drf_response.Response(
                {"error": f"Failed to signal call acceptance: {e}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Wait for lobby-bot to publish track and livekit-sip to answer the call
        # This delay allows the SIP call to be established before we transfer
        import time
        time.sleep(0.5)

        # Transfer SIP participant to the room
        try:
            self.phone_system.transfer_to_room(pending_call, str(room.id))
            self.phone_system.update_call_status(call_id, PendingCallStatus.TRANSFERRED)

        except TransferError:
            logger.exception("Transfer failed for call %s", call_id)
            return drf_response.Response(
                {"error": "Failed to transfer call"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Generate LiveKit config for the user to join
        livekit_config = utils.generate_livekit_config(
            room_id=str(room.id),
            user=request.user,
            username=request.user.full_name or str(request.user),
            configuration=room.configuration,
            is_admin_or_owner=True,
        )

        return drf_response.Response(
            {
                "status": "success",
                "room": {
                    "id": str(room.id),
                    "name": room.name,
                    "slug": room.slug,
                },
                "livekit": livekit_config,
                "caller_number": pending_call.caller_number,
            }
        )

    @decorators.action(detail=False, methods=["post"], url_path="decline")
    def decline_call(self, request):
        """Decline an incoming call."""
        from core.services.phone_system import PendingCallStatus

        serializer = serializers.DeclineCallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        call_id = str(serializer.validated_data["call_id"])
        pending_call = self.phone_system.get_pending_call(call_id)

        if not pending_call:
            return drf_response.Response(
                {"error": "Call not found or expired"},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Verify the call belongs to this user
        if pending_call.target_user_id != str(request.user.id):
            return drf_response.Response(
                {"error": "Unauthorized"},
                status=drf_status.HTTP_403_FORBIDDEN,
            )

        # Update status and hangup
        self.phone_system.update_call_status(call_id, PendingCallStatus.DECLINED)
        self.phone_system.hangup_participant(
            pending_call.lobby_room_name,
            pending_call.sip_participant_identity,
        )
        self.phone_system.clear_pending_call(call_id)

        return drf_response.Response({"status": "success"})

    @decorators.action(detail=False, methods=["post"], url_path="initiate")
    def initiate_outbound_call(self, request):
        """Initiate an outbound SIP call to a phone number."""
        from core.services.outbound_call import (
            OutboundCallException,
            OutboundCallService,
        )

        logger.info("initiate_outbound_call: request.data=%s", request.data)
        logger.info(
            "initiate_outbound_call: OUTBOUND_CALL_ENABLED=%s, OUTBOUND_SIP_TRUNK_ID=%s",
            settings.OUTBOUND_CALL_ENABLED,
            settings.OUTBOUND_SIP_TRUNK_ID,
        )

        serializer = serializers.InitiateOutboundCallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data["phone_number"]

        # Normalize phone number to E.164
        if phone_number.startswith("0"):
            phone_number = "+33" + phone_number[1:]

        logger.info("Creating room for outbound call to %s", phone_number)

        try:
            # Create a new room for this call (same pattern as incoming calls)
            # Set name=slug so that slug is auto-generated from name via slugify
            max_attempts = 10
            room = None
            for _ in range(max_attempts):
                slug = utils.generate_room_slug()
                if not models.Room.objects.filter(slug=slug).exists():
                    room = models.Room.objects.create(
                        name=slug,  # slug is derived from name via slugify
                        access_level=models.RoomAccessLevel.RESTRICTED,
                    )
                    break
            if room is None:
                raise OutboundCallException("Failed to generate unique room slug")
            logger.info("Room created: slug=%s, id=%s", room.slug, room.id)

            # Set the user as owner of the room
            models.ResourceAccess.objects.create(
                resource=room,
                user=request.user,
                role=models.RoleChoices.OWNER,
            )
            logger.info("ResourceAccess created for user %s", request.user)

            # Generate LiveKit token for user
            livekit_config = utils.generate_livekit_config(
                room_id=str(room.id),
                user=request.user,
                username=request.user.full_name or str(request.user),
                configuration=room.configuration,
                is_admin_or_owner=True,
            )
            logger.info("LiveKit config generated")

            # Initiate outbound call
            outbound_service = OutboundCallService()
            call_result = outbound_service.initiate_call(
                phone_number=phone_number,
                room_name=str(room.id),
                participant_identity=f"sip_{phone_number}",
                participant_name=phone_number,
            )
            logger.info("Outbound call initiated: %s", call_result)

        except OutboundCallException as e:
            logger.error("initiate_outbound_call OutboundCallException: %s", str(e))
            if 'room' in locals():
                room.delete()
            return drf_response.Response(
                {"error": str(e)},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("initiate_outbound_call unexpected error: %s", str(e))
            if 'room' in locals():
                room.delete()
            return drf_response.Response(
                {"error": f"Unexpected error: {str(e)}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return drf_response.Response(
            {
                "status": "success",
                "room": {
                    "id": str(room.id),
                    "name": room.name,
                    "slug": room.slug,
                },
                "livekit": livekit_config,
                "sip_call_id": call_result["sip_call_id"],
                "phone_number": phone_number,
            }
        )
