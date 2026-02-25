from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class Ingredient(BaseModel):
    name: str
    quantity: float
    unit: str  # "can", "lb", "tsp", "cups", "cloves", "" (for count)


class Meal(BaseModel):
    id: int
    name: str
    servings: int
    cuisine: str
    staple: bool
    ingredients: list[Ingredient]


class WeekPlan(BaseModel):
    week_start: date
    meals: dict[str, int]  # {"mon": 1, "tue": 2, ...}
    status: str  # "draft", "confirmed"
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class IngredientMapping(BaseModel):
    keyword: str
    todoist_section: str
    display_name: str


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DAY_LABELS = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

TODOIST_SECTIONS = [
    "Produce",
    "Meat",
    "Seafood",
    "Dairy & Eggs",
    "Cheese",
    "Bread & Bakery",
    "Pasta & Grains",
    "Canned Goods",
    "Condiments & Sauces",
    "Spices",
    "Frozen",
    "Drinks",
    "Other",
]
