import datetime
import os
from collections import OrderedDict
import json
import operator

from ckan.common import c, _
import ckan.lib.helpers as h
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from markupsafe import Markup

import ckanext.scheming.helpers as sh


def get_current_year():
    return datetime.datetime.today().year


def wa_license_icon(id):
    icons = {
        'cc-by': ['cc', 'cc-by'],
        'cc-nc': ['cc', 'cc-by', 'cc-nc'],
        'cc-by-sa': ['cc', 'cc-by', 'cc-sa'],
        'cc-zero': ['cc', 'cc-zero'],
    }
    if id not in icons:
        return ''
    # return h.url_for_static('license-{}.png'.format(id))
    return Markup(
        ''.join(
            '<img width=20 src="{}">'.
            format(h.url_for_static('{}.png'.format(icon)))
            for icon in icons[id]
        )
    )


def datawa_scheming_select_options(field_name):
    schema = sh.scheming_get_dataset_schema('dataset')
    try:
        access_level_options = sh.scheming_field_by_name(
            schema['dataset_fields'], field_name)['choices']
        options = {i['value']: i['label'] for i in access_level_options}
    except Exception as e:
        raise e
    return options


def datawa_get_option_label(options, option):
    if option in options:
        option_label = options[option]
        return option_label
    return option


def access_level_text(access_level=None, all=False, as_json=False):
    access_level_text = {
        "open": "This dataset is available for use by everyone",
        "open_login": "This dataset is available for use by everyone - login required",
        "fees_apply": "This dataset is available for use subject to payment",
        "restricted": "This dataset is available for use subject to approval",
        "govt_only": "This dataset is available for government use only",
        "mixed": "A variety of access levels apply to this dataset's resources"
    }
    if all:
        return json.dumps(access_level_text) if as_json else access_level_text
    if access_level in access_level_text:
        return access_level_text[access_level]
    return ''


def license_data(pkg):
    license_id = ''
    license_icon= ''
    license_title = ''
    license_url = ''
    license_specified = True

    if 'license_id' in pkg and pkg['license_id']:
        license_id = pkg['license_id']
        license_title = pkg['license_title']
        if license_id.startswith('custom'):
            license_icon = 'custom'
            if 'custom_license_url' in pkg and pkg['custom_license_url']:
                license_url = pkg['custom_license_url']
            else:
                license_title = 'Custom licence not supplied'
                license_specified = False
        else:
            license_icon = license_id
            if 'license_url' in pkg:
                license_url = pkg['license_url']
    else:
        license_id = 'not_specified'
        license_icon = 'not_specified'
        license_title = 'Licence not supplied'
        license_specified = False


    license_data = {
        'license_id' : license_id,
        'license_icon': license_icon,
        'license_title': license_title,
        'license_url': license_url,
        'license_specified': license_specified
    }

    return license_data

def organization_slugs_by_creation():
    ''' Retuns a list of organization slugs ordered from newest to oldest '''

    # Get a list of all the site's organizations from CKAN
    organizations = toolkit.get_action('organization_list')(
            data_dict={'sort': 'package_count desc', 'all_fields': True, 'include_dataset_count': True, 'include_groups': True})

    # FIXME Not sure why this only returns organisations that have packages in them

    # return slugs
    return [s['name'] for s in sorted(organizations, reverse=True, key=lambda k: k['created'])]

def organization_slugs_by_creation_and_rank():
    ''' Retuns a list of organization slugs ordered from 
        highest rank to lowest,
        newest to oldest '''

    def multisort(xs, specs):
        for key, reverse in reversed(specs):
            xs.sort(key=operator.itemgetter(key), reverse=reverse)
        return xs

    # Get a list of all the site's organizations from CKAN
    organizations = toolkit.get_action('organization_list')(
            data_dict={'sort': 'package_count desc', 'all_fields': True, 'include_extras': True, 'include_dataset_count': True, 'include_groups': True})

    # FIXME Not sure why this only returns organisations that have packages in them

    # generate a list of dicts - slug, creation, rank
    # 
    # Add a 'rank' key under the Custom Fields for the organization
    # with either a positive or negative value to manually 
    # promote (postive values greater than 1) or demote (values less than 1)
    orgs = []
    for o in organizations:
        rank = 1
        if 'extras' in o:
            for e in o['extras']:
                if e['key'] == 'rank':
                    try:
                        rank = int(e['value'])
                    except ValueError:
                        rank = 1
        orgs.append({
            'slug': o['name'],
            'created': o['created'],
            'rank': rank
            })

    #return slugs sorted by rank, then by created date
    return [s['slug'] for s in multisort(list(orgs), (('rank', True), ('created', True)))]

def get_os_env_value(key):
    return os.environ.get(key, '')

class CustomTheme(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IFacets, inherit=True)
    plugins.implements(plugins.IRoutes, inherit=True)

    # IRoutes
    def after_map(self, map):
        map.connect('bpatheme_summary', '/summary',
                    controller='ckanext.bpatheme.controller:SummaryController',
                    action='index')
        map.connect('bpatheme_contact', '/contact',
                    controller='ckanext.bpatheme.controller:ContactController',
                    action='index')
        return map

    # IPackageController
    def before_search(self, search_params):
        def make_insensitive(query):
            twiddled = []

            for c in query:
                if c.isalpha():
                    twiddled.append("[")
                    twiddled.append(c.upper())
                    twiddled.append(c.lower())
                    twiddled.append("]")
                else:
                    twiddled.append(c)

            output = u""

            return output.join(twiddled)

        # fix for ckanext-hierarchy required by migration to 2.8
        try:
            c.fields
        except AttributeError:
            c.fields = []

        # Search by fields for BPA Data Portal

        extras = search_params.get("extras")
        if not extras:
            # There are no extras in the search params, so do nothing.
            return search_params
        search_by = extras.get("ext_search_by")
        if not search_by:
            # The user didn't specify a specific field, so do nothing
            return search_params

        # Prepend the field name to the query
        q = search_params["q"]
        q = make_insensitive(q)
        search_terms = []
        for term in q.split():
            search_terms.append(
                "{search_by}:/.*{q}.*/".format(q=term, search_by=search_by)
            )
        q = " AND ".join(search_terms)
        search_params["q"] = q

        return search_params

    # IConfigurer
    def update_config(self, config):
        toolkit.add_template_directory(config, "templates")
        toolkit.add_public_directory(config, "static")
        toolkit.add_resource('fanstatic', 'bpatheme')

    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')
        schema.update({
            'ckanext.datawa.slip_harvester_token': [ignore_missing, str],
        })

        return schema

    # ITemplateHelpers
    def get_helpers(self):
        return {
            'get_current_year': get_current_year,
            'wa_license_icon': wa_license_icon,
            'access_level_text': access_level_text,
            'license_data': license_data,
            'datawa_scheming_select_options': datawa_scheming_select_options,
            'datawa_get_option_label': datawa_get_option_label,
            'organization_slugs_by_creation': organization_slugs_by_creation,
            'organization_slugs_by_creation_and_rank': organization_slugs_by_creation_and_rank,
            'get_os_env_value': get_os_env_value
        }

    # Ifacets
    def dataset_facets(self, facets_dict, package_type):
        ## In addtion to the defaults, we want these facets
        facets_dict['organization'] = _('Initiative')
        facets_dict['sequence_data_type'] = _('Sequence Data Type')

        ## We want the facets to appear in this order, with any others at the end
        facet_order = [
                'organization',
                'sequence_data_type',
                'res_format',
                'tags',
                ]

        ## Updating facet positions
        fct_keys = [key for key in facets_dict.keys()]
        # remove any items from facet_order not in fct_keys
        facet_order = [item for item in facet_order if item in fct_keys]
        # generate new order of facet_keys following facet_order
        for item in facet_order:
            fct_keys.insert(facet_order.index(item), fct_keys.pop(fct_keys.index(item)))
        # create OrderedDict of facets
        updated_facet_dict = OrderedDict([(key,facets_dict[key]) for key in fct_keys])
        facets_dict = updated_facet_dict

        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):
        facets_dict = self.dataset_facets(facets_dict, package_type)

        fct_keys = [key for key in facets_dict.keys()]
        if 'organization' in fct_keys:
            del facets_dict['organization']

        return facets_dict
