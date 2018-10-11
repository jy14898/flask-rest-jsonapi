# -*- coding: utf-8 -*-

"""Helpers to deal with marshmallow schemas"""

from marshmallow import class_registry
from marshmallow.base import SchemaABC
from marshmallow_jsonapi.fields import Relationship as GenericRelationship

from flask_rest_jsonapi.exceptions import InvalidInclude

from marshmallow_jsonapi.schema import Schema as DefaultSchema, SchemaOpts as DefaultOpts

class SchemaOpts(DefaultOpts):
    """Options to use JSONAPI types and ids to build URLs instead of hard coding URLs."""

    def __init__(self, meta, *args, **kwargs):
        for attr in ['self_url', 'self_url_kwargs', 'self_url_many', 
                     'self_view', 'self_view_kwargs', 'self_view_many']:
            if getattr(meta, attr, None): raise ValueError('No need to specify old URL methods')

        type_ = getattr(meta, 'type_', None)

        # Transfer Flask options to URL options, to piggy-back on its handling
        setattr(meta, 'self_url', "/{}/{{id}}".format(type_))
        setattr(meta, 'self_url_kwargs', {"id":"<id>"})
        setattr(meta, 'self_url_many', "/{}".format(type_))

        super(SchemaOpts, self).__init__(meta, *args, **kwargs)

class Schema(DefaultSchema):
    OPTIONS_CLASS = SchemaOpts

    class Meta:
        pass

class Relationship(GenericRelationship):
    def get_related_url(self, obj):
        self.related_url = "/{}".format(self.type_)
        self.related_url_kwargs = {'id': '<id>'} 

        return super().get_related_url(obj)
        

def compute_schema(schema_cls, default_kwargs, qs, include):
    """Compute a schema around compound documents and sparse fieldsets

    :param Schema schema_cls: the schema class
    :param dict default_kwargs: the schema default kwargs
    :param QueryStringManager qs: qs
    :param list include: the relation field to include data from

    :return Schema schema: the schema computed
    """
    # manage include_data parameter of the schema
    schema_kwargs = default_kwargs
    schema_kwargs['include_data'] = tuple()

    # collect sub-related_includes
    related_includes = {}

    if include:
        for include_path in include:
            field = include_path.split('.')[0]

            if field not in schema_cls._declared_fields:
                raise InvalidInclude("{} has no attribute {}".format(schema_cls.__name__, field))
            elif not isinstance(schema_cls._declared_fields[field], GenericRelationship):
                raise InvalidInclude("{} is not a relationship attribute of {}".format(field, schema_cls.__name__))

            schema_kwargs['include_data'] += (field, )
            if field not in related_includes:
                related_includes[field] = []
            if '.' in include_path:
                related_includes[field] += ['.'.join(include_path.split('.')[1:])]

    # make sure id field is in only parameter unless marshamllow will raise an Exception
    if schema_kwargs.get('only') is not None and 'id' not in schema_kwargs['only']:
        schema_kwargs['only'] += ('id',)

    # create base schema instance
    schema = schema_cls(**schema_kwargs)

    # manage sparse fieldsets
    if schema.opts.type_ in qs.fields:
        tmp_only = set(schema.declared_fields.keys()) & set(qs.fields[schema.opts.type_])
        if schema.only:
            tmp_only &= set(schema.only)
        schema.only = tuple(tmp_only)

        # make sure again that id field is in only parameter unless marshamllow will raise an Exception
        if schema.only is not None and 'id' not in schema.only:
            schema.only += ('id',)

    # manage compound documents
    if include:
        for include_path in include:
            field = include_path.split('.')[0]
            relation_field = schema.declared_fields[field]
            related_schema_cls = schema.declared_fields[field].__dict__['_Relationship__schema']
            related_schema_kwargs = {}
            if isinstance(related_schema_cls, SchemaABC):
                related_schema_kwargs['many'] = related_schema_cls.many
                related_schema_cls = related_schema_cls.__class__
            if isinstance(related_schema_cls, str):
                related_schema_cls = class_registry.get_class(related_schema_cls)
            related_schema = compute_schema(related_schema_cls,
                                            related_schema_kwargs,
                                            qs,
                                            related_includes[field] or None)
            relation_field.__dict__['_Relationship__schema'] = related_schema

    return schema


def get_model_field(schema, field):
    """Get the model field of a schema field

    :param Schema schema: a marshmallow schema
    :param str field: the name of the schema field
    :return str: the name of the field in the model
    """
    if schema._declared_fields.get(field) is None:
        raise Exception("{} has no attribute {}".format(schema.__name__, field))

    if schema._declared_fields[field].attribute is not None:
        return schema._declared_fields[field].attribute
    return field


def get_relationships(schema, model_field=False):
    """Return relationship fields of a schema

    :param Schema schema: a marshmallow schema
    :param list: list of relationship fields of a schema
    """
    relationships = [key for (key, value) in schema._declared_fields.items() if isinstance(value, GenericRelationship)]

    if model_field is True:
        relationships = [get_model_field(schema, key) for key in relationships]

    return relationships


def get_related_schema(schema, field):
    """Retrieve the related schema of a relationship field

    :param Schema schema: the schema to retrieve le relationship field from
    :param field: the relationship field
    :return Schema: the related schema
    """
    return schema._declared_fields[field].__dict__['_Relationship__schema']


def get_schema_from_type(resource_type):
    """Retrieve a schema from the registry by his type

    :param str type_: the type of the resource
    :return Schema: the schema class
    """
    for cls_name, cls in class_registry._registry.items():
        try:
            if cls[0].opts.type_ == resource_type:
                return cls[0]
        except Exception:
            pass

    raise Exception("Couldn't find schema for type: {}".format(resource_type))


def get_schema_field(schema, field):
    """Get the schema field of a model field

    :param Schema schema: a marshmallow schema
    :param str field: the name of the model field
    :return str: the name of the field in the schema
    """
    schema_fields_to_model = {key: get_model_field(schema, key) for (key, value) in schema._declared_fields.items()}
    for key, value in schema_fields_to_model.items():
        if value == field:
            return key

    raise Exception("Couldn't find schema field from {}".format(field))
