"""
Effective contacts of circuits and circuit terminations.

A circuit is not part of the site hierarchy. Its contacts come from three places:
- the circuit itself and its provider (provider contacts reach the circuit unless their depth is "none")
- per termination side, the scope the termination is attached to (region, site group, site, location)
- per termination side, the devices cabled to it, found by tracing the cable paths through patch panels
"""
from dataclasses import dataclass, field, replace

from django.db.models import Q

from circuits.models import Circuit, CircuitTermination
from core.models import ObjectType
from dcim.models import CablePath
from dcim.utils import decompile_path_node, path_node_to_object
from tenancy.models import ContactAssignment

from .resolver import EffectiveContact, get_effective_contacts, resolve_depth
from .rules import DEPTH_NONE, pick_nearest

CIRCUIT_MODELS = (Circuit, CircuitTermination)


@dataclass
class Section:
    key: str  # 'circuit', 'A' or 'Z'
    title: str
    termination: object = None
    scope: object = None
    devices: list = field(default_factory=list)
    items: list = field(default_factory=list)


def cabled_devices(termination):
    """
    Devices whose cable path runs into this termination from its own side, through any patch panels.
    """
    node_ct = ObjectType.objects.get_for_model(CircuitTermination).pk
    own = f'{node_ct}:{termination.pk}'
    devices = {}
    for cp in CablePath.objects.filter(_nodes__contains=termination):
        # The first circuit termination on a path is the one on the origin's side
        first = next(
            (step for step in cp.path if any(decompile_path_node(n)[0] == node_ct for n in step)),
            None,
        )
        if not first or own not in first:
            continue
        for node in cp.path[0]:
            device = getattr(path_node_to_object(node), 'device', None)
            if device is not None:
                devices[device.pk] = device
    return sorted(devices.values(), key=lambda d: d.name or '')


def _merge(groups):
    """
    Merge lists of EffectiveContact, keeping the nearest per (contact, role); earlier groups win ties.
    """
    candidates = []
    for offset, items in enumerate(groups):
        for ec in items:
            candidates.append({
                'contact': ec.assignment.contact_id,
                'role': ec.assignment.role_id,
                'distance': ec.distance + offset * 0.001,
                'priority': ec.assignment.priority,
                'sort_name': ec.assignment.contact.name,
                'item': ec,
            })
    return [c['item'] for c in pick_nearest(candidates)]


def termination_section(termination, user=None):
    scope = termination.termination
    scope_items = []
    if scope is not None and hasattr(scope, 'get_contacts'):
        # Contacts that reach the scope itself; for the termination they are all inherited
        scope_items = [
            replace(ec, inherited=True, distance=ec.distance + 1)
            for ec in get_effective_contacts(scope, user)
        ]
    devices = cabled_devices(termination)
    device_items = [
        replace(ec, inherited=True, distance=ec.distance + 1, via=device)
        for device in devices
        for ec in get_effective_contacts(device, user)
    ]
    side = termination.term_side
    return Section(
        key=side,
        title=f'Side {side}',
        termination=termination,
        scope=scope,
        devices=devices,
        items=[replace(ec, section=side) for ec in _merge([scope_items, device_items])],
    )


def circuit_section(circuit, user=None):
    ot_circuit = ObjectType.objects.get_for_model(circuit)
    ot_provider = ObjectType.objects.get_for_model(circuit.provider)
    qs = ContactAssignment.objects.filter(
        Q(object_type=ot_circuit, object_id=circuit.pk) | Q(object_type=ot_provider, object_id=circuit.provider_id)
    ).select_related('contact', 'role')
    if user is not None:
        qs = qs.restrict(user, 'view')
    items = []
    for a in qs:
        depth, _ = resolve_depth(a)
        on_provider = a.object_type_id == ot_provider.pk
        if on_provider and depth == DEPTH_NONE:
            continue
        items.append(EffectiveContact(
            assignment=a,
            source=circuit.provider if on_provider else circuit,
            source_level='provider' if on_provider else 'circuit',
            distance=1 if on_provider else 0,
            inherited=on_provider,
            depth=depth,
        ))
    return Section(key='circuit', title='Circuit', items=[replace(ec, section='circuit') for ec in _merge([items])])


def get_circuit_sections(obj, user=None):
    """
    Return the contact sections for a circuit (circuit and provider, then side A and Z) or for a
    single circuit termination (its side only).
    """
    if isinstance(obj, CircuitTermination):
        return [termination_section(obj, user)]
    sections = [circuit_section(obj, user)]
    for termination in obj.terminations.order_by('term_side'):
        sections.append(termination_section(termination, user))
    return sections
