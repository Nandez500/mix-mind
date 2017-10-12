#!/usr/bin/env python
"""
Turn recipes json into a readable menu
"""

import argparse
import json
import string
import itertools
from collections import OrderedDict

import pandas as pd
import numpy as np

ANY_SPIRIT = 'brandy, dry gin, genever, amber rum, white rum, rye whiskey'.split(',')

def get_fraction(amount):
    numer, denom = float(amount).as_integer_ratio()
    if denom == 1:
        return numer
    whole = numer / denom
    numer = numer % denom
    return "{}{}/{}".format(str(whole)+' ' if whole > 0 else '', numer, denom)

def get_ingredient_amount(name, amount, unit):
    if isinstance(amount, basestring):
        amount_str = amount
        if amount == 'dash':
            unit = 'of '
        else:
            unit = ''
    elif unit == 'oz':
        amount_str = get_fraction(amount)
    else:
        amount_str = str(amount)
    if unit:
        unit += ' '
    return "\t{} {}{}".format(amount_str, unit, name)

def convert_to_menu(recipes):
    """ Convert recipe json into readible format
    """

    menu = []
    for drink_name, recipe in recipes.iteritems():
        lines = []
        lines.append(drink_name)
        unit = recipe.get('unit', 'oz')
        prep = recipe.get('prep', '')

        info = recipe.get('info')
        if info:
            lines.append('\t"{}"'.format(info))

        for ingredient, amount in recipe['ingredients'].iteritems():
            lines.append(get_ingredient_amount(ingredient, amount, unit))

        for ingredient, amount in recipe.get('optional', {}).iteritems():
            linestr = "{} (optional)".format(get_ingredient_amount(ingredient, amount, unit))
            lines.append(linestr)

        misc = recipe.get('misc')
        if misc:
            lines.append("\t{}".format(misc))

        garnish = recipe.get('garnish')
        if garnish:
            lines.append("\t{}, for garnish".format(garnish))

        examples = recipe.get('examples')
        if examples:
            lines.append("\t    Examples: ".format(examples))
            for e in examples:
                lines.append("\t    ${:.2f} | {}".format(e.values()[0], e.keys()[0]))

        variants = recipe.get('variants')
        if variants:
            lines.append("\t    Variant{}:".format('s' if len(variants) > 1 else ''))
            for v in variants:
                lines.append("\t    {}".format(v))

        menu.append('\n'.join(lines))
    return menu

def expand_recipes(df, recipes):

    for drink_name, recipe in recipes.iteritems():

        # ignore non-numeric ingredients
        ingredients_names = [k for k,v in recipe['ingredients'].iteritems() \
                if not isinstance(v, basestring)]
        ingredients_amounts = [v for k,v in recipe['ingredients'].iteritems() \
                if not isinstance(v, basestring)]

        # calculate cost for every combination of ingredients for this drink
        examples = []
        for bottles in get_all_bottle_combinations(df, ingredients_names):
            sum_ = 0
            for bottle, type_, amount in zip(bottles, ingredients_names, ingredients_amounts):
                sum_ += cost_by_bottle_and_volume(df, bottle, type_, amount)
            examples.append({', '.join(bottles) : sum_})
        recipes[drink_name]['examples'] = examples

    return recipes


def cost_by_bottle_and_volume(df, bottle, type_, amount, unit='oz'):
    # TODO bottle and type comparison
    bottle_row = df[(df['Bottle'] == bottle) & (df['type'] == type_)]
    per_unit = min(bottle_row['$/{}'.format(unit)])
    return per_unit * amount

def get_all_bottle_combinations(df, types):
    bottle_lists = [slice_on_type(df, t)['Bottle'].tolist() for t in types]
    opts = itertools.product(*bottle_lists)
    return opts

def slice_on_type(df, type_):
    return df[df['type'] == type_]


def load_cost_df(barstock_csv, include_all=False):
    df = pd.read_csv(barstock_csv)
    df = df.dropna(subset=['Type'])
    df['type'] = map(string.lower, df['Type'])

    # convert money columns to floats
    for col in [col for col in df.columns if '$' in col]:
        df[col] = df[col].replace('[\$,]', '', regex=True).astype(float)

    # drop out of stock items
    if not include_all:
        #log debug how many dropped
        df = df[df["In Stock"] != 0]

    return df

def get_parser():
    p = argparse.ArgumentParser(description="""
Example usage:
    ./program -v -d
""", formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('-v', dest='verbose', action='store_true')
    p.add_argument('-a', dest='all', action='store_true', help="Include all recipes regardless of stock")
    p.add_argument('-p', dest='prices', action='store_true', help="Calculate prices for example drinks based on stock")
    p.add_argument('-w', dest='write', default=None, help="Save text menu out to a file")

    return p

def main():

    args = get_parser().parse_args()

    with open('recipes.json') as fp:
        base_recipes = json.load(fp, object_pairs_hook=OrderedDict)

    if args.prices:
        df = load_cost_df('Barstock - Sheet1.csv', args.all)
        all_recipes = expand_recipes(df, base_recipes)
        menu = convert_to_menu(all_recipes)
    else:
        menu = convert_to_menu(base_recipes)

    # TODO sorting?

    if args.write:
        with open(args.write, 'w') as fp:
            fp.write('\n\n'.join(menu))
    else:
        print '\n\n'.join(menu)

if __name__ == "__main__":
    main()
