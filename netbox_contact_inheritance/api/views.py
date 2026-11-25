from django.apps import apps
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox.api.authentication import IsAuthenticatedOrLoginNotRequired
from tenancy.api.serializers import ContactAssignmentSerializer, ContactRoleSerializer, ContactSerializer

from ..circuit_contacts import CIRCUIT_MODELS, get_circuit_sections
from ..resolver import SUPPORTED_MODELS, get_effective_contacts


class EffectiveContactsView(APIView):
    """
    GET ?object_type=dcim.device&object_id=123

    Returns the effective contacts of an object: its own assignments plus inherited ones,
    each with the object it is inherited from.
    """
    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(
        parameters=[
            OpenApiParameter('object_type', OpenApiTypes.STR, required=True, description='e.g. dcim.device'),
            OpenApiParameter('object_id', OpenApiTypes.INT, required=True),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        label = request.query_params.get('object_type', '')
        object_id = request.query_params.get('object_id', '')
        try:
            model = apps.get_model(label)
        except (LookupError, ValueError):
            raise ValidationError({'object_type': f'Unknown object type "{label}"'})
        if model not in SUPPORTED_MODELS + CIRCUIT_MODELS:
            supported = ', '.join(m._meta.label_lower for m in SUPPORTED_MODELS + CIRCUIT_MODELS)
            raise ValidationError({'object_type': f'Not supported. Supported: {supported}'})
        if not object_id.isdigit():
            raise ValidationError({'object_id': 'An integer object_id is required'})

        obj = model.objects.restrict(request.user, 'view').filter(pk=object_id).first()
        if obj is None:
            raise NotFound()

        ctx = {'request': request}
        if model in CIRCUIT_MODELS:
            entries = [(s.key, ec) for s in get_circuit_sections(obj, request.user) for ec in s.items]
        else:
            entries = [(None, ec) for ec in get_effective_contacts(obj, request.user)]
        results = []
        for section, ec in entries:
            a = ec.assignment
            results.append({
                'assignment': ContactAssignmentSerializer(a, nested=True, context=ctx).data,
                'contact': ContactSerializer(a.contact, context=ctx).data,
                'role': ContactRoleSerializer(a.role, nested=True, context=ctx).data if a.role else None,
                'priority': a.priority or None,
                'inherited': ec.inherited,
                'inherit_depth': ec.depth,
                'source': {
                    'object_type': ec.source._meta.label_lower,
                    'object_id': ec.source.pk,
                    'display': str(ec.source),
                    'level': ec.source_level,
                    'distance': ec.distance,
                },
                'section': section,
                'via': {
                    'object_type': ec.via._meta.label_lower,
                    'object_id': ec.via.pk,
                    'display': str(ec.via),
                } if ec.via else None,
            })
        return Response({'count': len(results), 'results': results})
