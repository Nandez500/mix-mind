#!/usr/bin/env python

from flask import Flask, render_template, flash, request
from wtforms import validators, widgets, Form, Field, TextField, TextAreaField, StringField, SubmitField, BooleanField, DecimalField

import menu_gen
import recipe as drink_recipe

# app config
app = Flask(__name__)
app.config.from_object(__name__)
with open('local_secret') as fp:
    app.config['SECRET_KEY'] = fp.read().strip()


class MixMindServer():
    def __init__(self):
        base_recipes = menu_gen.load_recipe_json(['recipes.json'])
        self.recipes = {name:drink_recipe.DrinkRecipe(name, recipe) for name, recipe in base_recipes.iteritems()}

mms = MixMindServer()


class ReusableForm(Form):
    name = TextField('Name:', validators=[validators.required()])
    email = TextField('Email:', validators=[validators.required(), validators.Length(min=6, max=35)])
    password = TextField('Passwords:', validators=[validators.required(), validators.Length(min=3, max=35)])


class ToggleField(BooleanField):
    def __call__(self, **kwargs):
        return super(ToggleField, self).__call__(
                data_toggle="toggle",
                data_on="{} Enabled".format(self.label.text),
                data_off="{} Disabled".format(self.label.text),
                data_width="300",
                **kwargs)

class CSVField(Field):
    widget = widgets.TextInput()

    def _value(self):
        if self.data:
            return u', '.join(self.data)
        else:
            return u''

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [x.strip() for x in valuelist[0].split(',')]
        else:
            self.data = []

class ToggleButtonWidget(widgets.Input):
    pass

class DrinksForm(Form):
    # display options
    prices = BooleanField("Prices", description="Display prices for drinks based on stock")
    prep_line = BooleanField("Preparation", description="Display a line showing glass, ice, and prep")
    stats = BooleanField("Stats", description="Print out a detailed statistics block for the selected recipes")
    examples = BooleanField("Examples", description="Show specific examples of a recipe based on the ingredient stock")
    all_ingredients = BooleanField("All Ingredients", description="Show every ingredient instead of just the main liquors with each example")
    convert = TextField("Convert", description="Convert recipes to a different primary unit", default=None, validators=[validators.AnyOf(['oz','mL','cL']), validators.Optional()])
    markup = DecimalField("Markup", description="Drink markup: price = ceil((base_cost+1)*markup)", default=1.2)
    ignore_info = BooleanField("Info", description="Show the info line for recipes")
    ignore_origin = BooleanField("Origin", description="Check origin and mark drinks as Schubar originals", default=True)
    ignore_variants = BooleanField("Variants", description="Show variants for drinks", default=True)

    # filtering options
    all_ = BooleanField("Allow all ingredients", description="Include all ingredients from barstock whether or not that are marked in stock")
    include = CSVField("Include", description="Filter by ingredient(s) that must be contained in the recipe")
    exclude = CSVField("Include", description="Filter by ingredient(s) that must NOT be contained in the recipe")
    use_or = BooleanField("Logical OR", description="Use logical OR for included and excluded ingredient lists instead of default AND")
    # TODO make these selection fields
    style = TextField("Style", description="Include drinks matching the style such as After Dinner or Longdrink")
    glass = TextField("Glass", description="Include drinks matching the glass type such as cocktail or rocks")
    prep = TextField("Prep", description="Include drinks matching the prep method such as shake or build")
    ice = TextField("Ice", description="Include drinks matching the ice used such as crushed")

    def reset(self):
        blankData = MultiDict([ ('csrf', self.reset_csrf() ) ])
        self.process(blankData)

@app.route("/", methods=['GET', 'POST'])
def hello():
    #form = ReusableForm(request.form)
    form = DrinksForm(request.form)
    recipes = []

    print form.errors
    if request.method == 'POST':
        if form.validate():
            # Save the comment here.
            flash("Settings applied")
            print request
        else:
            flash("Error in form validation")

    return render_template('hello.html', form=form, recipes=recipes)

def generate_recipes(form):
    base_recipes = util.load_recipe_json(args.recipes)
    if args.barstock:
        barstock = Barstock.load(args.barstock, args.all)
        recipes = [drink_recipe.DrinkRecipe(name, recipe).generate_examples(barstock)
            for name, recipe in base_recipes.iteritems()]
    else:
        recipes = [drink_recipe.DrinkRecipe(name, recipe) for name, recipe in base_recipes.iteritems()]
    if args.convert:
        print "Converting recipes to unit: {}".format(args.convert)
        map(lambda r: r.convert(args.convert), recipes)
    recipes = filter_recipes(recipes, filter_options)


@app.route('/json/<recipe_name>')
def recipe_json(recipe_name):
    try:
        return str(mms.recipes[recipe_name])
    except KeyError:
        return "{} not found".format(recipe_name)



