# -*- coding: utf-8 -*-

import urllib.request, urllib.parse, urllib.error
import copy
import uuid

from sqlalchemy import Boolean, DateTime, Column, Integer, ForeignKey, Enum, Float, Unicode
from sqlalchemy_utils import UUIDType

from . import util
from .database import db
from .compose_html import close

Categories = 'Spirit Liqueur Vermouth Bitters Syrup Juice Mixer Wine Beer Dry Ice'.split()

# key is the value that should exist in the CSV file,
# inner key is the name in the Model
display_name_mappings = {
    "Category":    {'k':  "Category",     'v':  str, 'csv': 1},
    "Ingredient":  {'k':  "Type",         'v':  str, 'csv': 2},
    "Type":        {'k':  "Type",         'v':  str},
    "Kind":        {'k':  "Kind",         'v':  str, 'csv': 3},
    "Bottle":      {'k':  "Kind",         'v':  str},
    "In Stock":    {'k':  "In_Stock",     'v':  util.from_bool_from_num},
    "ABV":         {'k':  "ABV",          'v':  util.from_float, 'csv': 5},
    "Proof":       {'k':  "ABV",          'v':  lambda x: util.from_float(x) / 2.0},
    "Size (mL)":   {'k':  "Size_mL",      'v':  util.from_float, 'csv': 7},
    "Size (oz)":   {'k':  "Size_oz",      'v':  util.from_float},
    "Price Paid":  {'k':  "Price_Paid",   'v':  util.from_price_float, 'csv': 9},
    "$/mL":        {'k':  "Cost_per_mL",  'v':  util.from_price_float},
    "$/cL":        {'k':  "Cost_per_cL",  'v':  util.from_price_float},
    "$/oz":        {'k':  "Cost_per_oz",  'v':  util.from_price_float},
}

# TODO value constraints (e.g. 100% max abv, no negative price, etc.)
class Ingredient(db.Model):
    uuid       = Column(UUIDType(), default=uuid.uuid4)
    bar_id     = Column(Integer(), ForeignKey('bar.id'), primary_key=True)
    Category   = Column(Enum(*Categories))
    Type       = Column(Unicode(length=100), primary_key=True)
    Kind       = Column(Unicode(length=255), primary_key=True)
    In_Stock   = Column(Boolean(), default=True)
    ABV        = Column(Float(), default=0.0)
    Size_mL    = Column(Float(), default=0.0)
    Price_Paid = Column(Float(), default=0.0)
    # computed
    type_        = Column(Unicode(length=100))
    Size_oz      = Column(Float(), default=0.0)
    Cost_per_mL  = Column(Float(), default=0.0)
    Cost_per_cL  = Column(Float(), default=0.0)
    Cost_per_oz  = Column(Float(), default=0.0)

    def as_dict(self):
        data = {'iid': self.iid()}
        for attr in 'Category Type Kind In_Stock ABV Size_mL Price_Paid Size_oz Cost_per_oz'.split(' '):
            data[attr] = getattr(self, attr)
        return data

    _csv_labels = sorted([label for label, val in display_name_mappings.items() if val.get('csv')],
            key=lambda x: display_name_mappings[x].get('csv'))
    _iid_prefix = "ingredient-"

    @classmethod
    def csv_heading(self):
        return '{}\n'.format(','.join(self._csv_labels))

    def as_csv(self):
        return '{}\n'.format(','.join([str(self[display_name_mappings[attr]['k']])
                for attr in self._csv_labels]))

    def __getitem__(self, field):
        return getattr(self, field)

    def __setitem__(self, field, value):
        return setattr(self, field, value)

    def iid(self):
        """Ingredient ID: combines UUID with prefix suitable as HTML id"""
        return "{}{}".format(self._iid_prefix, self.uuid)

    @classmethod
    def query_by_iid(cls, iid):
        return cls.query.filter_by(uuid=uuid.UUID(iid[len(cls._iid_prefix):])).one_or_none()
