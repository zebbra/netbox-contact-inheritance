from netbox.plugins import PluginTemplateExtension

from .circuit_contacts import get_circuit_sections
from .reach import COLUMN_LABELS, COLUMNS, get_contact_reach
from .resolver import get_effective_contacts


class EffectiveContactsPanel(PluginTemplateExtension):
    """
    Shows the effective contacts of an object on its detail page: its own assignments and those
    inherited from parent objects, each with the object it comes from.
    """
    models = [
        'dcim.site',
        'dcim.location',
        'dcim.rack',
        'dcim.device',
        'virtualization.virtualmachine',
    ]

    def right_page(self):
        request = self.context['request']
        if not request.user.has_perm('tenancy.view_contactassignment'):
            return ''
        obj = self.context['object']
        return self.render('netbox_contact_inheritance/effective_contacts.html', {
            'effective_contacts': get_effective_contacts(obj, request.user),
        })


class ContactReachPanel(PluginTemplateExtension):
    """
    Shows on a contact's page, per assignment, how many objects below the assigned object inherit it.
    """
    models = ['tenancy.contact']

    def full_width_page(self):
        request = self.context['request']
        if not request.user.has_perm('tenancy.view_contactassignment'):
            return ''
        return self.render('netbox_contact_inheritance/contact_reach.html', {
            'reach_rows': get_contact_reach(self.context['object'], request.user),
            'columns': [(key, COLUMN_LABELS[key]) for key, *_ in COLUMNS],
        })


class CircuitContactsPanel(PluginTemplateExtension):
    """
    Effective contacts of a circuit (own and provider, then per termination side the scope and the
    cabled devices), or of a single circuit termination.
    """
    models = ['circuits.circuit', 'circuits.circuittermination']

    def right_page(self):
        request = self.context['request']
        if not request.user.has_perm('tenancy.view_contactassignment'):
            return ''
        obj = self.context['object']
        sections = get_circuit_sections(obj, request.user)
        return self.render('netbox_contact_inheritance/circuit_contacts.html', {
            'sections': sections,
            'show_section_headers': len(sections) > 1 or bool(sections[0].termination),
        })


template_extensions = [EffectiveContactsPanel, ContactReachPanel, CircuitContactsPanel]
