#!/usr/bin/env python
"""
Turn recipes json into a readable menu
"""

import argparse
import json
import string
import itertools
from collections import OrderedDict
from fractions import Fraction

import pandas as pd
import numpy as np

ML_PER_OZ = 29.5735
UNITS = ['oz', 'mL']

def get_fraction(amount):
    numer, denom = float(amount).as_integer_ratio()
    if denom == 1:
        return numer
    whole = numer / denom
    numer = numer % denom
    return "{}{}/{}".format(str(whole)+' ' if whole > 0 else '', numer, denom)

def get_ingredient_str(name, amount, unit):
    if isinstance(amount, basestring):
        amount_str = amount
        if amount == 'dash':
            unit = 'of'
        else:
            unit = ''
    elif unit == 'oz':
        amount_str = get_fraction(amount)
    else:
        amount_str = str(amount)
    if unit:
        unit += ' '
    return "\t{} {}{}".format(amount_str, unit, name)

def check_stat(field, tracker, example, drink_name):
    if example[field] > tracker[field]:
        tracker.update(example)
        tracker['name'] = drink_name
    return tracker

def convert_to_menu(recipes, prices=True, all_=True):
    """ Convert recipe json into readible format
    """

    menu = []
    most_expensive = {'cost':0}
    most_booze = {'drinks':0}
    most_abv = {'abv': 0}
    for drink_name, recipe in recipes.iteritems():
        lines = []
        lines.append(drink_name)
        unit = recipe.get('unit', 'oz')
        prep = recipe.get('prep', '')

        info = recipe.get('info')
        if info:
            lines.append('\t"{}"'.format(info))

        for ingredient, amount in recipe['ingredients'].iteritems():
            lines.append(get_ingredient_str(ingredient, amount, unit))

        for ingredient, amount in recipe.get('optional', {}).iteritems():
            linestr = "{} (optional)".format(get_ingredient_str(ingredient, amount, unit))
            lines.append(linestr)

        misc = recipe.get('misc')
        if misc:
            lines.append("\t{}".format(misc))

        garnish = recipe.get('garnish')
        if garnish:
            lines.append("\t{}, for garnish".format(garnish))

        examples = recipe.get('examples')
        if examples and prices:
            lines.append("\t    Examples: ".format(examples))
            for e in examples:
                lines.append("\t    ${cost:.2f} | {abv:.2f}% ABV | {drinks:.2f} | {bottles}".format(**e))
                most_expensive = check_stat('cost', most_expensive, e, drink_name)
                most_booze = check_stat('drinks', most_booze, e, drink_name)
                most_abv = check_stat('abv', most_abv, e, drink_name)

        variants = recipe.get('variants')
        if variants:
            lines.append("\t    Variant{}:".format('s' if len(variants) > 1 else ''))
            for v in variants:
                lines.append("\t    {}".format(v))

        if all_ or examples:
            menu.append('\n'.join(lines))
        else:
            print "Can't make {}".format(drink_name)
    print "Most Expensive: {name}, ${cost:.2f} | {abv:.2f}% ABV | {drinks:.2f} | {bottles}".format(**most_expensive)
    print "Most Booze: {name}, ${cost:.2f} | {abv:.2f}% ABV | {drinks:.2f} | {bottles}".format(**most_booze)
    print "Highest ABV (estimate): {name}, ${cost:.2f} | {abv:.2f}% ABV | {drinks:.2f} | {bottles}".format(**most_abv)
    return menu

def expand_recipes(df, recipes):

    for drink_name, recipe in recipes.iteritems():
        unit = recipe.get('unit', 'oz')
        prep = recipe.get('prep', 'shake')

        ingredients_names = []
        ingredients_amounts = []
        for name, amount in recipe['ingredients'].iteritems():
            if isinstance(amount, basestring):
                if amount == 'Top with':
                    amount = 3.0
                elif 'dash' in amount:
                    amount = dash_to_volume(amount, unit)
                elif 'tsp' in amount:
                    try:
                        amount = float(amount.split()[0])
                    except ValueError:
                        amount = float(Fraction(amount_str.split()[0]))
                    amount = tsp_to_volume(amount, unit)
                else:
                    continue
            ingredients_names.append(name)
            ingredients_amounts.append(amount)

        # calculate cost for every combination of ingredients for this drink
        examples = []
        for bottles in get_all_bottle_combinations(df, ingredients_names):
            sum_ = 0
            std_drinks = 0
            volume = 1.5 if prep == 'shake' else 0.5
            for bottle, type_, amount in zip(bottles, ingredients_names, ingredients_amounts):
                sum_ += cost_by_bottle_and_volume(df, bottle, type_, amount, unit)
                std_drinks += drinks_by_bottle_and_volume(df, bottle, type_, amount, unit)
                volume += amount
            abv = 40.0 * (std_drinks*(1.5 if unit == 'oz' else 45.0) / volume)
            examples.append({'bottles': ', '.join(bottles),
                             'cost': sum_,
                             'abv': abv,
                             'drinks': std_drinks})
        recipes[drink_name]['examples'] = examples

    return recipes

def drinks_by_bottle_and_volume(df, bottle, type_, amount, unit='oz'):
    """ Standard drink is 1.5 oz or 45 ml at 80 proof
    """
    proof = get_bottle_by_type(df, bottle, type_)['Proof'].median()
    adjusted_proof = proof / 80.0
    adjusted_amount = amount / (1.5 if unit == 'oz' else 45.0)
    return adjusted_proof * adjusted_amount

def cost_by_bottle_and_volume(df, bottle, type_, amount, unit='oz'):
    per_unit = get_bottle_by_type(df, bottle, type_)['$/{}'.format(unit)].median()
    return per_unit * amount

def get_bottle_by_type(df, bottle, type_):
    by_type = slice_on_type(df, type_)
    row = by_type[by_type['Bottle'] == bottle]
    if len(row) > 1:
        raise ValueError('{} "{}" has multiple entries in the input data!'.format(type_, bottle))
    return row

def dash_to_volume(amount, unit):
    # TODO find numeric value in amount; regex time??
    # ds = 0.62 mL
    ds = 2.0 * 0.62
    if unit == 'mL':
        return ds
    elif unit == 'oz':
        return ds / ML_PER_OZ

def tsp_to_volume(amount, unit):
    return amount * (0.125 if unit == 'oz' else 5.0)


def get_all_bottle_combinations(df, types):
    bottle_lists = [slice_on_type(df, t)['Bottle'].tolist() for t in types]
    opts = itertools.product(*bottle_lists)
    return opts

def slice_on_type(df, type_):
    if type_ in ['rum', 'whiskey', 'tequila', 'vermouth']:
        return df[df['type'].str.contains(type_)]
    elif type_ == 'any spirit':
        return df[df['Category'] == 'Spirit']
    elif type_ == 'bitters':
        return df[df['Category'] == 'Bitters']

    return df[df['type'] == type_]

def load_cost_df(barstock_csv, include_all=False):
    df = pd.read_csv(barstock_csv)
    df = df.dropna(subset=['Type'])
    df['type'] = map(string.lower, df['Type'])

    # convert money columns to floats
    for col in [col for col in df.columns if '$' in col]:
        df[col] = df[col].replace('[\$,]', '', regex=True).astype(float)

    df['Proof'] = df['Proof'].fillna(0)

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
    p.add_argument('-b', dest='barstock', default='Barstock - Sheet1.csv', help="Barstock csv filename")
    p.add_argument('-r', dest='recipes', default='recipes.json', help="Barstock csv filename")
    p.add_argument('-a', dest='all', action='store_true', help="Include all recipes regardless of stock")
    p.add_argument('-p', dest='prices', action='store_true', help="Calculate and display prices for example drinks based on stock")
    p.add_argument('-w', dest='write', default=None, help="Save text menu out to a file")
    p.add_argument('-s', dest='stats', action='store_true', help="Just show some stats")

    return p

def main():

    args = get_parser().parse_args()

    with open('recipes.json') as fp:
        base_recipes = json.load(fp, object_pairs_hook=OrderedDict)

    df = load_cost_df(args.barstock, args.all)
    all_recipes = expand_recipes(df, base_recipes)
    menu = convert_to_menu(all_recipes, args.prices, args.all)

    if args.stats:  # HAX FIXME
        return

    # TODO sorting?

    if args.write:
        with open(args.write, 'w') as fp:
            fp.write('\n\n'.join(menu))
    else:
        print '\n\n'.join(menu)

if __name__ == "__main__":
    main()
