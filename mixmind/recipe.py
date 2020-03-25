"""
DrinkRecipe class encapsulates how a drink recipe is calculated and formulated,
can provide itself as a dict/json, tuple of values, do conversions, etc.
Just generally make it better OOP
"""
import re
from fractions import Fraction
from recordtype import recordtype
import itertools
import string

from . import util

# water volume added by preperation method for ABV estimate
WATER_BY_PREP = {'shake': 1.6, 'stir': 1.3, 'build': 1.0, 'pour': 1.0}
WATER_BY_ICE = {'cubed': 1.1, 'crushed': 1.4, 'neat': 1.0}

EXAMPLE_LIMIT = 3

class RecipeError(Exception):
    pass

class DrinkRecipe(object):
    """ Initialize a drink with a handle to the available stock data and its recipe json
    """
    RecipeExample = recordtype('RecipeExample', [('kinds', []), ('cost', 0), ('abv', 0), ('std_drinks', 0), ('volume', 0)])
    RecipeStats = recordtype('RecipeStats', 'min_cost,max_cost,min_abv,max_abv,min_std_drinks,max_std_drinks,avg_abv,avg_cost,avg_std_drinks,volume', default=RecipeExample)

    @util.default_initializer
    def __init__(self, name, recipe_dict, stock_df=None):
        # from recipe dict pull out other info and set defaults
        self.info      =  recipe_dict.get('info', '')
        self.style     =  recipe_dict.get('style', '')
        self.tag       =  recipe_dict.get('tag', '')
        self.iba_info  =  recipe_dict.get('IBA_description', '')
        self.origin    =  recipe_dict.get('origin', '')
        self.unit      =  recipe_dict.get('unit', 'oz') # cL, mL, tsp, dash, drop
        self.prep      =  recipe_dict.get('prep', 'shake') # build, stir, blend
        self.ice       =  recipe_dict.get('ice', 'cubed') # crushed, neat
        self.glass     =  recipe_dict.get('glass', 'cocktail') # rocks, martini, flute, collins, highball
        self.variants  =  recipe_dict.get('variants',  [])
        self.max_cost     =  0
        self.examples     =  []
        self.ingredients  =  []
        self.stats = None
        for type_str, quantity in recipe_dict.get('ingredients', {}).items():
            self.ingredients.append(QuantizedIngredient(type_str, quantity, self.unit))
        for type_str, quantity in recipe_dict.get('optional', {}).items():
            self.ingredients.append(OptionalIngredient(type_str, quantity, self.unit))
        if recipe_dict.get('misc'):
            self.ingredients.append(Ingredient(recipe_dict.get('misc')))
        if recipe_dict.get('garnish'):
            self.ingredients.append(Garnish(recipe_dict.get('garnish')))

        self.show_examples = False

    def __str__(self):
        """ Drink recipe basic plain text output format
        """
        lines = []
        lines.append(self.name)
        lines.extend([i.str() for i in self.ingredients])
        if self.variants:
            lines.append("\tVariants:")
            lines.extend(['\t'+v for v in self.variants])
        if self.show_examples:
            lines.append("\tExamples:")
            lines.extend(['\t'+v for v in self.examples])
        lines.append('')
        return '\n'.join(lines)

    def __repr__(self):
        return "{}:{}".format(self.__class__.__name__, self.name)

    def prep_line(self, extended=True, caps=True):
        case_fn = str.upper if caps else str.lower
        layout = "{{}} glass | {{}}{} | {{}}".format("" if self.ice == 'neat' else " ice") if extended else "{} | {} | {}"
        return case_fn(layout.format(self.glass, self.ice, self.prep))

    @property
    def can_make(self):
        return bool(self.examples)

    def convert(self, to_unit, rounded=True, convert_nonstandard=False):
        """ Convert the main unit of this recipe
        """
        if self.unit == to_unit:
            return
        for ingredient in self.ingredients:
            ingredient.recipe_unit = to_unit
            if ingredient.unit in ['ds', 'drop'] and not convert_nonstandard:
                continue
            try:
                ingredient.convert(to_unit, rounded=rounded)
            except NotImplementedError:
                pass
        self.unit = to_unit

    def generate_examples(self, barstock, stats=False):
        """ Given a Barstock, calculate examples drinks from the data
        e.g. For every dry gin and vermouth in Barstock, generate every Martini
        that can be made, along with the cost,abv,std_drinks from the ingredients
        """
        ingredients = self._get_quantized_ingredients()
        example_kinds = barstock.get_all_kind_combinations((i.specifier for i in ingredients))
        del self.examples # need to make possible to run again
        self.examples = []
        for kinds in example_kinds:
            # TODO refactor to generate IngredientSpecifiers for the kind lists
            example = DrinkRecipe.RecipeExample(); example.kinds = []
            for kind, ingredient in zip(kinds, ingredients):
                if ingredient.unit == 'literal':
                    continue
                example.cost       += ingredient.get_cost(kind, barstock)
                example.std_drinks += ingredient.get_std_drinks(kind, barstock)
                example.volume     += ingredient.get_amount_as(self.unit, rounded=False, single_value=True)
                # remove juice and such from the kinds listed
                if barstock.get_kind_category(util.IngredientSpecifier(ingredient.specifier.ingredient, kind)) in ['Vermouth', 'Liqueur', 'Bitters', 'Spirit', 'Wine']:
                    example.kinds.append(kind)
            example.kinds = ', '.join(example.kinds);
            example.volume *= WATER_BY_PREP.get(self.prep, 1.0)
            example.volume *= WATER_BY_ICE.get(self.ice, 1.0)
            example.abv = util.calculate_abv(example.std_drinks, example.volume, self.unit)
            self.max_cost = max(self.max_cost, example.cost)
            self.examples.append(example)
        if stats and self.examples:
            self.calculate_stats()
            # attempting to use an average here instead of max_cost
            self.max_cost = self.stats.avg_cost
        # Apply a limit on the number of examples used
        if len(self.examples) > EXAMPLE_LIMIT:
            # TODO grabbing spaced indicies
            self.examples = [self.examples[0],
                    self.examples[(len(self.examples)-1)//2],
                    self.examples[len(self.examples)-1]]
        return self # so it can be used when chained

    def calculate_stats(self):
        """ After generating examples, calculate stats for this drink
        """
        if not self.examples:
            return False
        if self.stats:
            return True
        def _find_example(examples, attr, max_=False):
            return sorted(examples, key=lambda e: getattr(e, attr), reverse=max_)[0]
        def _mean(examples, attr):
            return sum((getattr(e, attr) for e in examples)) / float(len(examples))
        self.stats = self.RecipeStats()
        self.stats.min_cost = _find_example(self.examples, 'cost')
        self.stats.max_cost = _find_example(self.examples, 'cost', max_=True)
        self.stats.min_abv = _find_example(self.examples, 'abv')
        self.stats.max_abv = _find_example(self.examples, 'abv', max_=True)
        self.stats.min_std_drinks = _find_example(self.examples, 'std_drinks')
        self.stats.max_std_drinks = _find_example(self.examples, 'std_drinks', max_=True)
        self.stats.volume = _find_example(self.examples, 'volume', max_=True).volume
        self.stats.avg_cost = _mean(self.examples, 'cost')
        self.stats.avg_abv = _mean(self.examples, 'abv')
        self.stats.avg_std_drinks = _mean(self.examples, 'std_drinks')
        return True

    def primary_spirit(self):
        max_amount = 0
        max_ingredient = None
        for i in self._get_quantized_ingredients(): # TODO enforce ingredient Category tags
            amount = i.get_amount_as(self.unit, rounded=False, single_value=True)
            if amount > max_amount and not i.top_with:
                max_amount = amount
                max_ingredient = i.specifier.ingredient
        return max_ingredient

    def first_ingredient(self):
        return self.ingredients[0].specifier

    def contains_ingredient(self, ingredient, include_optional=False):
        ingredients = self.ingredients if include_optional else self._get_quantized_ingredients()
        return any((ingredient in i for i in ingredients))

    def _get_quantized_ingredients(self, include_optional=False):
        return [i for i in self.ingredients if type(i) == QuantizedIngredient]

class Ingredient(object):
    """ An "ingredient" is every item that should be represented in standard text
    """
    def _repr_fmt(self):
        return "<{}[{{}}]>".format(self.__class__.__name__)

    @util.default_initializer
    def __init__(self, description):
        self.unit = None
        self.specifier = util.IngredientSpecifier(description)

    def str(self):
        return str(self.description)

    def __repr__(self):
        return self._repr_fmt().format(self.description)

    def __contains__(self, item):
        return item in self.description.lower()

    def convert(self, *args, **kwargs):
        pass


class Garnish(Ingredient):
    """ An ingredient line that denotes it's a garnish
    """
    def str(self):
        return "{}, for garnish".format(super(Garnish, self).str())

    def __repr__(self):
        return super(Garnish, self)._repr_fmt().format(self.description)


class QuantizedIngredient(Ingredient):
    """ Has a unit based on the raw quantity, responsible for unit conversions, text output
    type_str: as written in the recipe, may be in the form ingredient:kind
    ingredient: identify an ingredient, e.g. rye whiskey
    kind: specify an ingredient, e.g. Bulliet Rye
    TODO: support quantized unit that is a number of items (basil leaves, raspberries, etc.)
        - may need to use regex to match against "3-4"
    """
    @util.default_initializer
    def __init__(self, type_str, raw_quantity, recipe_unit):
        self.top_with = False
        self.specifier = util.IngredientSpecifier.from_string(type_str)

        # interpret the raw quantity
        if isinstance(raw_quantity, str):
            if raw_quantity == 'Top with': # counts at 3 ounces on average
                self.amount = util.convert_units(3.0, 'oz', recipe_unit, rounded=True)
                self.unit = recipe_unit
                self.top_with = True

            elif 'dash' in raw_quantity:
                self.unit = 'ds'
                if raw_quantity == 'dash':
                    self.amount = 1
                elif re.match(r'[0-9]+ dashes', raw_quantity):
                    self.amount = int(raw_quantity.split()[0])
                elif re.match(r'[0-9]+ to [0-9]+ dashes', raw_quantity):
                    self.amount = (int(raw_quantity.split()[0]), int(raw_quantity.split()[2]))
                else:
                    raise RecipeError("Unknown format for dash amount: {} {}".format(raw_quantity, type_str))

            elif 'tsp' in raw_quantity:
                try:
                    self.amount = float(raw_quantity.split()[0])
                except ValueError:
                    self.amount = float(Fraction(raw_quantity.split()[0]))
                self.unit = 'tsp'

            elif 'drop' in raw_quantity:
                self.unit = 'drop'
                if raw_quantity == 'drop':
                    self.amount = 1
                elif re.match(r'[0-9]+ drops', raw_quantity):
                    self.amount = int(raw_quantity.split()[0])
                else:
                    raise RecipeError("Unknown format for drop amount: {} {}".format(raw_quantity, type_str))

            elif raw_quantity in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']:
                self.amount = raw_quantity
                self.unit = 'literal'
            else:
                # accept other options as literal ingredients
                self.amount = raw_quantity
                self.unit = 'literal'
                #raise RecipeError(u"Unknown ingredient quantity: {} {}".format(raw_quantity, type_str))
        else:
            self.amount = raw_quantity
            self.unit = recipe_unit

    def __contains__(self, item):
        return item in self.specifier.ingredient.lower() or \
             (self.specifier.kind and item in self.specifier.kind.lower())

    def __repr__(self):
        return super(QuantizedIngredient, self)._repr_fmt().format("{},{},{}".format(self.amount, self.unit, self.specifier))

    def convert(self, new_unit, rounded=True):
        if self.unit == 'literal':
            return
        self.amount = self.get_amount_as(new_unit, rounded=rounded)
        self.unit = new_unit

    def get_amount_as(self, new_unit, rounded=True, single_value=False):
        if self.unit == 'literal':
            return
        if isinstance(self.amount, tuple):
            lower  = util.convert_units(self.amount[0], self.unit, new_unit, rounded=rounded)
            higher = util.convert_units(self.amount[1], self.unit, new_unit, rounded=rounded)
            amount = (lower+higher)/2.0 if single_value else (lower, higher)
        else:
            amount = util.convert_units(self.amount, self.unit, new_unit, rounded=rounded)
        return amount

    def str(self):
        if self.top_with:
            return "Top with {}".format(self.specifier)
        if self.unit == 'literal':
            return "{} {}".format(self.amount, self.specifier)

        if self.unit == 'ds':
            if isinstance(self.amount, tuple):
                amount = "{:.0f} to {:.0f}".format(self.amount[0], self.amount[1])
                unit = 'dashes'
            elif self.amount == 1:
                amount = 'dash'
                unit = 'of'
            else:
                amount = "{:.0f}".format(self.amount)
                unit = 'dashes'
        elif self.unit == 'drop':
            if isinstance(self.amount, tuple):
                amount = "{:.0f} to {:.0f}".format(self.amount[0], self.amount[1])
                unit = 'drops'
            elif self.amount == 1:
                amount = 'drop'
                unit = 'of'
            else:
                amount = "{:.0f}".format(self.amount)
                unit = 'drops'
        elif self.unit in ['oz', 'tsp']:
            amount = util.to_fraction(self.amount)
            unit = self.unit
        elif self.unit == 'mL':
            unit = self.unit
            if self.amount < 10.0:
                amount = "{:.1f}".format(self.amount)
            else:
                amount = "{:.0f}".format(self.amount)
        else:
            amount = self.amount
            unit = self.unit

        formats = {
                #u'mL': u"{:.0f} {} {}",
                'cL': "{:.1f} {} {}",
                }
        return formats.get(self.unit, "{} {} {}").format(amount, unit, self.specifier)

    def get_cost(self, kind, barstock):
        if self.unit == 'literal':
            return 0
        amount = self.get_amount_as(self.recipe_unit, rounded=False, single_value=True)
        return barstock.cost_by_kind_and_volume(util.IngredientSpecifier(self.specifier.ingredient, kind), amount, self.recipe_unit)

    def get_std_drinks(self, kind, barstock):
        if self.unit == 'literal':
            return 0
        amount = self.get_amount_as(self.recipe_unit, rounded=False, single_value=True)
        abv = barstock.get_kind_abv(util.IngredientSpecifier(self.specifier.ingredient, kind))
        return util.calculate_std_drinks(abv, amount, self.recipe_unit)


class OptionalIngredient(QuantizedIngredient):
    """ A quantized ingredient that just gets an extra output tag
    """
    def str(self):
        return "{}, (optional)".format(super(OptionalIngredient, self).str())

