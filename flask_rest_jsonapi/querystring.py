# -*- coding: utf-8 -*-

"""Helper to deal with querystring parameters according to jsonapi specification"""

import json

from flask import current_app

from flask_rest_jsonapi.exceptions import BadRequest, InvalidFilters, InvalidSort, InvalidField, InvalidInclude

class QueryStringManager(object):
    """Querystring parser according to jsonapi reference"""

    MANAGED_KEYS = (
        'filter',
        'page',
        'fields',
        'sort',
        'include',
        'q',
        'group'
    )

    def __init__(self, querystring):
        """Initialization instance

        :param dict querystring: query string dict from request.args
        """
        if not isinstance(querystring, dict):
            raise ValueError('QueryStringManager require a dict-like object querystring parameter')

        self.qs = querystring

    def _get_key_values(self, name):
        """Return a dict containing key / values items for a given key, used for items like filters, page, etc.

        :param str name: name of the querystring parameter
        :return dict: a dict of key / values items
        """
        results = {}

        for key, value in self.qs.items():
            try:
                if not key.startswith(name):
                    continue

                key_start = key.index('[') + 1
                key_end = key.index(']')
                item_key = key[key_start:key_end]

                if ',' in value:
                    item_value = value.split(',')
                else:
                    item_value = value
                results.update({item_key: item_value})
            except Exception:
                raise BadRequest("Parse error", source={'parameter': key})

        return results

    @property
    def querystring(self):
        """Return original querystring but containing only managed keys

        :return dict: dict of managed querystring parameter
        """
        return {key: value for (key, value) in self.qs.items() if key.startswith(self.MANAGED_KEYS)}

    @property
    def grouping(self):
        """Return group fields from query string.

        :return list: group information
        """
        groups = self.qs.get('group')
        if groups is not None:
            return groups.split(",")

    @property
    def filters(self):
        """Return filters from query string.

        :return list: filter information
        """
        filters = self.qs.get('filter')
        if filters is not None:
            try:
                filters = json.loads(filters)
            except (ValueError, TypeError):
                raise InvalidFilters("Parse error")

        return filters

    @property
    def pagination(self):
        """Return all page parameters as a dict.

        :return dict: a dict of pagination information

        To allow multiples strategies, all parameters starting with `page` will be included. e.g::

            {
                "number": '25',
                "size": '150',
            }

        Example with number strategy::

            >>> query_string = {'page[number]': '25', 'page[size]': '10'}
            >>> parsed_query.pagination
            {'number': '25', 'size': '10'}
        """
        # check values type
        result = self._get_key_values('page')
        for key, value in result.items():
            if key not in ('number', 'size'):
                raise BadRequest("{} is not a valid parameter of pagination".format(key), source={'parameter': 'page'})
            try:
                int(value)
            except ValueError:
                raise BadRequest("Parse error", source={'parameter': 'page[{}]'.format(key)})

        if current_app.config.get('ALLOW_DISABLE_PAGINATION', True) is False and int(result.get('size', 1)) == 0:
            raise BadRequest("You are not allowed to disable pagination", source={'parameter': 'page[size]'})

        if current_app.config.get('MAX_PAGE_SIZE') is not None and 'size' in result:
            if int(result['size']) > current_app.config['MAX_PAGE_SIZE']:
                raise BadRequest("Maximum page size is {}".format(current_app.config['MAX_PAGE_SIZE']),
                                 source={'parameter': 'page[size]'})

        return result

    '''
    Fields and sorting both return Schema field names, not attributes.
    Datalayer can't use schema yet, because schema is now being defined from the result of get_object.
    Thus we are forced to have field names == attributes. Not an issue really.

    TODO Enforce this
    '''
    @property
    def fields(self):
        """Return fields wanted by client.

        :return dict: a dict of sparse fieldsets information

        Return value will be a dict containing all fields by resource, for example::

            {
                "user": ['name', 'email'],
            }

        """
        result = self._get_key_values('fields')
        for key, value in result.items():
            if not isinstance(value, list):
                result[key] = [value]

        return result

    @property
    def sorting(self):
        """Return fields to sort by including sort name for SQLAlchemy and row
        sort parameter for other ORMs

        :return list: a list of sorting information

        Example of return value::

            [
                {'field': 'created_at', 'order': 'desc'},
            ]

        """
        if self.qs.get('sort'):
            sorting_results = []
            for sort_field in self.qs['sort'].split(','):
                field = sort_field.replace('-', '')
                order = 'desc' if sort_field.startswith('-') else 'asc'
                sorting_results.append({'field': field, 'order': order})
            return sorting_results

        return []

    @property
    def include(self):
        """Return fields to include

        :return list: a list of include information
        """
        include_param = self.qs.get('include', [])

        if current_app.config.get('MAX_INCLUDE_DEPTH') is not None:
            for include_path in include_param:
                if len(include_path.split('.')) > current_app.config['MAX_INCLUDE_DEPTH']:
                    raise InvalidInclude("You can't use include through more than {} relationships"
                                         .format(current_app.config['MAX_INCLUDE_DEPTH']))

        return include_param.split(',') if include_param else []
